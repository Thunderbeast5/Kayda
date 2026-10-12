"""
Refinements service — Phase 5
===============================
Post-processing layer applied to JudicialFindings before they
reach the Legal Verification Agent.

Responsibilities
----------------
1. Hallucination guard — strips any section/precedent in findings
   that is NOT present in the provided legal_context_package or
   precedent_context. (FindingsBuilder already does this at parse
   time; this service re-checks as a second safety net.)

2. Confidence calibration — adjusts raw LLM confidence based on
   objective factors (evidence strength, argument scores, missing
   evidence, contradictions). Keeps the model honest.

3. Bail conditions generator — generates standard BNSS/CrPC
   conditions when preliminary_finding is "Bail Likely Granted"
   and conditions_if_granted is empty.

4. Edge case handler — ensures the findings object is complete
   and coherent even when inputs are sparse (no precedents,
   missing evidence, empty arguments).

All methods are deterministic — no LLM calls.
"""

from __future__ import annotations

import re
from typing import Optional

from ..models.judicial_findings import (
    JudicialFindings,
    PrecedentApplied,
    EvidenceEvaluation,
    BailFactorAnalysis,
)


# ── 1. Hallucination guard ─────────────────────────────────────────────────────

def _allowed_sections_set(legal_context_package: dict) -> set[str]:
    """Normalised set of section keys from the legal package."""
    allowed: set[str] = set()
    for item in legal_context_package.get("recommended_sections") or []:
        sec = str(item.get("section") or "").strip()
        if sec:
            allowed.add(sec.upper())
            # also add without spaces: "BNS117"
            allowed.add(sec.upper().replace(" ", ""))
    for art in legal_context_package.get("supporting_articles") or []:
        if isinstance(art, str):
            m = re.search(r'Article\s+(\d+[A-Za-z]?)', art, re.IGNORECASE)
            if m:
                allowed.add(f"ARTICLE {m.group(1).upper()}")
                allowed.add(f"ARTICLE_{m.group(1).upper()}")
    return allowed


def _allowed_precedents_set(precedent_context: dict | list) -> set[str]:
    """Lowercased set of known case names."""
    allowed: set[str] = set()
    items = []
    if isinstance(precedent_context, list):
        items = precedent_context
    elif isinstance(precedent_context, dict):
        items = (
            (precedent_context.get("similar_cases") or [])
            + (precedent_context.get("supporting_cases") or [])
        )
    for item in items:
        name = (item.get("case_name") or "").strip().lower()
        if name:
            allowed.add(name)
    return allowed


def apply_hallucination_guard(
    findings: JudicialFindings,
    legal_context_package: dict,
    precedent_context: dict | list,
) -> JudicialFindings:
    """
    Remove any section or precedent from findings that is not
    present in the provided context packages.

    Returns a new JudicialFindings with clean lists.
    """
    allowed_secs  = _allowed_sections_set(legal_context_package)
    allowed_precs = _allowed_precedents_set(precedent_context)

    # Guard sections
    clean_sections: list[str] = []
    stripped_sections: list[str] = []
    for sec in findings.sections_applied:
        sec_upper = sec.strip().upper()
        sec_no_space = sec_upper.replace(" ", "")
        if not allowed_secs or sec_upper in allowed_secs or sec_no_space in allowed_secs:
            clean_sections.append(sec)
        else:
            stripped_sections.append(sec)

    if stripped_sections:
        print(f"[HallucinationGuard] Stripped sections: {stripped_sections}")

    # Guard precedents
    clean_precs: list[PrecedentApplied] = []
    stripped_precs: list[str] = []
    for p in findings.precedents_applied:
        name_lower = p.case_name.strip().lower()
        if not allowed_precs or name_lower in allowed_precs:
            clean_precs.append(p)
        else:
            stripped_precs.append(p.case_name)

    if stripped_precs:
        print(f"[HallucinationGuard] Stripped precedents: {stripped_precs}")

    # Return updated findings (Pydantic model_copy with overrides)
    data = findings.model_dump()
    data["sections_applied"]    = clean_sections
    data["precedents_applied"]  = [p.model_dump() for p in clean_precs]
    return JudicialFindings(**data)


# ── 2. Confidence calibration ──────────────────────────────────────────────────

def calibrate_confidence(
    findings: JudicialFindings,
    evidence_context: dict,
) -> JudicialFindings:
    """
    Adjusts the LLM-reported confidence based on objective evidence factors.

    Calibration rules:
    - Start with LLM confidence
    - Deduct for missing evidence items (−3 each, max −15)
    - Deduct for contradictions (−5 each, max −15)
    - Boost if evidence_strength is "High" (+5)
    - Deduct if evidence_strength is "Low" (−5)
    - Deduct if sections_applied is empty (−10)
    - Deduct if precedents_applied is empty (−5)
    - Clamp to [10, 95] — never 0 or 100 from calibration alone

    Returns updated JudicialFindings with calibrated confidence.
    """
    raw = findings.confidence
    adj = raw

    ev = evidence_context or {}
    missing = ev.get("missing_evidence") or []
    contras = ev.get("contradictions") or []
    strength = str(ev.get("evidence_strength") or "").strip().lower()

    # Missing evidence penalty
    adj -= min(len(missing) * 3, 15)

    # Contradiction penalty
    adj -= min(len(contras) * 5, 15)

    # Strength adjustment
    if strength == "high":
        adj += 5
    elif strength == "low":
        adj -= 5

    # Missing legal framework penalty
    if not findings.sections_applied:
        adj -= 10
    if not findings.precedents_applied:
        adj -= 5

    # Clamp
    calibrated = max(10, min(95, adj))

    if calibrated != raw:
        print(f"[ConfidenceCalibration] {raw}% → {calibrated}% "
              f"(missing={len(missing)}, contradictions={len(contras)}, "
              f"strength={strength})")

    data = findings.model_dump()
    data["confidence"] = calibrated
    return JudicialFindings(**data)


# ── 3. Bail conditions generator ──────────────────────────────────────────────

# Standard anticipatory bail conditions under BNSS / CrPC
_STANDARD_CONDITIONS = [
    "The applicant shall make themselves available for interrogation by the "
    "Investigating Officer as and when required.",
    "The applicant shall not leave the country without prior permission of this Court.",
    "The applicant shall surrender their passport to the Investigating Officer "
    "within 7 days of this order.",
    "The applicant shall not directly or indirectly tamper with evidence or "
    "attempt to influence prosecution witnesses.",
    "The applicant shall report to the concerned police station every Monday "
    "between 10:00 AM and 12:00 PM until further orders.",
]

_GRAVITY_EXTRA_CONDITIONS = {
    "High": [
        "The applicant shall furnish a personal bond of ₹1,00,000 with two sureties "
        "of like amount to the satisfaction of the Investigating Officer.",
        "The applicant shall not enter the district of the alleged offence without "
        "prior permission of this Court.",
    ],
    "Medium": [
        "The applicant shall furnish a personal bond of ₹50,000 with one surety.",
    ],
    "Low": [],
}


def generate_bail_conditions(
    findings: JudicialFindings,
    bail_assessment_report: dict,
) -> JudicialFindings:
    """
    If preliminary_finding is "Bail Likely Granted" and conditions_if_granted
    is empty, generate standard bail conditions based on gravity.

    Returns updated JudicialFindings.
    """
    if findings.preliminary_finding != "Bail Likely Granted":
        return findings

    if findings.conditions_if_granted:
        return findings  # conditions already set by LLM

    gravity = str(
        findings.bail_factor_analysis.gravity_of_offence
        or bail_assessment_report.get("gravity_of_offence")
        or "Medium"
    ).strip().title()

    conditions = list(_STANDARD_CONDITIONS)
    conditions += _GRAVITY_EXTRA_CONDITIONS.get(gravity, [])

    # Add flight risk condition if relevant
    if findings.bail_factor_analysis.flight_risk in ("High", "Medium"):
        conditions.append(
            "The applicant shall surrender their passport to the IO immediately."
        )

    print(f"[BailConditionsGenerator] Generated {len(conditions)} standard conditions "
          f"(gravity: {gravity}).")

    data = findings.model_dump()
    data["conditions_if_granted"] = conditions
    return JudicialFindings(**data)


# ── 4. Edge case handler ───────────────────────────────────────────────────────

def handle_edge_cases(
    findings: JudicialFindings,
    legal_context_package: dict,
    precedent_context: dict | list,
    defence_arguments: str,
    prosecution_arguments: str,
) -> JudicialFindings:
    """
    Ensures findings are coherent when inputs are sparse.

    Handles:
    - No precedents available → set preliminary_finding to "Inconclusive"
      only if confidence is also low
    - Empty judicial_analysis → generate a minimal placeholder
    - defence_arguments AND prosecution_arguments both empty →
      downgrade confidence by 20 and set Inconclusive
    - sections_applied empty → fill from legal_context_package top section
    """
    data = findings.model_dump()
    changed = False

    # No arguments from either side → can't form reliable finding
    if not defence_arguments.strip() and not prosecution_arguments.strip():
        data["preliminary_finding"]  = "Inconclusive"
        data["confidence"]           = max(10, data["confidence"] - 20)
        data["judicial_analysis"]    = (
            data.get("judicial_analysis") or
            "No arguments were presented by either party. "
            "This Court is unable to form a reliable finding."
        )
        changed = True
        print("[EdgeCaseHandler] Both arguments empty → Inconclusive.")

    # Empty judicial analysis
    if not str(data.get("judicial_analysis") or "").strip():
        data["judicial_analysis"] = (
            "Having considered the facts of the case and the applicable law, "
            "this Court makes the following preliminary finding."
        )
        changed = True
        print("[EdgeCaseHandler] Judicial analysis was empty — placeholder inserted.")

    # No sections applied → use top section from package
    if not data.get("sections_applied"):
        top_secs = [
            s.get("section", "")
            for s in (legal_context_package.get("recommended_sections") or [])
            if s.get("section")
        ]
        if top_secs:
            data["sections_applied"] = top_secs[:2]
            changed = True
            print(f"[EdgeCaseHandler] sections_applied was empty → filled with {top_secs[:2]}")

    # No precedents + low confidence → Inconclusive
    prec_items = (
        precedent_context if isinstance(precedent_context, list)
        else (precedent_context.get("similar_cases") or [] if isinstance(precedent_context, dict) else [])
    )
    if not prec_items and not data.get("precedents_applied") and data["confidence"] < 50:
        data["preliminary_finding"] = "Inconclusive"
        data["judicial_analysis"] += (
            " Note: No relevant judicial precedents were available for this matter. "
            "This finding should be treated with appropriate caution."
        )
        changed = True
        print("[EdgeCaseHandler] No precedents + low confidence → Inconclusive.")

    if changed:
        return JudicialFindings(**data)
    return findings


# ── Combined refinement pipeline ──────────────────────────────────────────────

def apply_all_refinements(
    findings: JudicialFindings,
    legal_context_package: dict,
    precedent_context: dict | list,
    evidence_context: dict,
    bail_assessment_report: dict,
    defence_arguments: str = "",
    prosecution_arguments: str = "",
) -> JudicialFindings:
    """
    Apply all Phase 5 refinements in sequence:
      1. Hallucination guard
      2. Edge case handling
      3. Confidence calibration
      4. Bail conditions generation

    Returns a fully refined JudicialFindings object.
    """
    findings = apply_hallucination_guard(findings, legal_context_package, precedent_context)
    findings = handle_edge_cases(
        findings, legal_context_package, precedent_context,
        defence_arguments, prosecution_arguments,
    )
    findings = calibrate_confidence(findings, evidence_context)
    findings = generate_bail_conditions(findings, bail_assessment_report)
    return findings
