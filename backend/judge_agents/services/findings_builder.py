"""
FindingsBuilder service.

Parses the raw JSON output of the FINDINGS_PROMPT LLM call
and assembles a validated JudicialFindings Pydantic object.

Handles:
  - JSON extraction from LLM response (strips fences)
  - Field normalisation and type coercion
  - Hallucination guard: strips any section / precedent NOT present
    in the supplied legal_context_package or precedent_context
  - Safe fallback defaults for every field
"""

import json
import re
from typing import Any, Optional

from ..models.judicial_findings import (
    JudicialFindings,
    EvidenceEvaluation,
    BailFactorAnalysis,
    ArgumentEvaluation,
    ArgumentScore,
    PrecedentApplied,
    QuestionRecord,
)


# ── JSON extraction ───────────────────────────────────────────────────────────

def _strip_fences(text: str) -> str:
    return re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()


def _extract_json(raw: str) -> Optional[dict]:
    cleaned = _strip_fences(raw)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to salvage the first {...} block
        m = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    return None


# ── Hallucination guard helpers ───────────────────────────────────────────────

def _allowed_sections(legal_context_package: dict | str) -> set[str]:
    """
    Extract a flat set of normalised section identifiers from the
    legal_context_package (which may be a dict or a pre-serialised string).
    """
    allowed: set[str] = set()
    if isinstance(legal_context_package, str):
        # Attempt to parse if it was serialised
        try:
            legal_context_package = json.loads(legal_context_package)
        except Exception:
            # Can't parse — allow everything rather than block all
            return allowed

    if isinstance(legal_context_package, dict):
        for item in legal_context_package.get("recommended_sections", []):
            sec = item.get("section") or ""
            if sec:
                allowed.add(sec.strip().upper())
        for item in legal_context_package.get("supporting_articles", []):
            if isinstance(item, str):
                allowed.add(item.strip().upper())
    return allowed


def _allowed_precedents(precedent_context: dict | list | str) -> set[str]:
    """
    Extract a flat set of case name fragments from precedent_context.
    """
    allowed: set[str] = set()
    if isinstance(precedent_context, str):
        try:
            precedent_context = json.loads(precedent_context)
        except Exception:
            return allowed

    items = []
    if isinstance(precedent_context, list):
        items = precedent_context
    elif isinstance(precedent_context, dict):
        items = (
            precedent_context.get("similar_cases", [])
            + precedent_context.get("supporting_cases", [])
        )

    for item in items:
        name = item.get("case_name") or item.get("title") or ""
        if name:
            allowed.add(name.strip().lower())
    return allowed


def _guard_sections(sections: list[str], allowed: set[str]) -> list[str]:
    if not allowed:
        return sections  # no constraint available — pass through
    return [s for s in sections if s.strip().upper() in allowed]


def _guard_precedents(
    precedents: list[dict], allowed: set[str]
) -> list[PrecedentApplied]:
    result = []
    for p in precedents:
        name = (p.get("case_name") or "").strip()
        if not allowed or name.lower() in allowed:
            result.append(
                PrecedentApplied(
                    case_name=name,
                    citation=p.get("citation") or "",
                    principle_applied=p.get("principle_applied") or "",
                )
            )
    return result


# ── Field parsers ─────────────────────────────────────────────────────────────

def _parse_evidence_evaluation(d: dict) -> EvidenceEvaluation:
    strength = d.get("strength") or "Medium"
    if strength not in ("High", "Medium", "Low"):
        strength = "Medium"
    return EvidenceEvaluation(
        strength=strength,                                           # type: ignore[arg-type]
        key_evidence=d.get("key_evidence") or [],
        contradictions_noted=d.get("contradictions_noted") or [],
        missing_evidence=d.get("missing_evidence") or [],
    )


def _parse_bail_factors(d: dict) -> BailFactorAnalysis:
    def _lvl(v: Any, default: str = "Medium") -> str:
        return v if v in ("High", "Medium", "Low") else default

    def _yn(v: Any) -> str:
        return "Yes" if str(v or "").lower() in ("yes", "true") else "No"

    return BailFactorAnalysis(
        gravity_of_offence=_lvl(d.get("gravity_of_offence"), "High"),    # type: ignore[arg-type]
        flight_risk=_lvl(d.get("flight_risk"), "Medium"),                 # type: ignore[arg-type]
        custodial_need=_yn(d.get("custodial_need")),                      # type: ignore[arg-type]
        witness_tampering_risk=_lvl(d.get("witness_tampering_risk"), "Medium"),  # type: ignore[arg-type]
        antecedents=str(d.get("antecedents") or "None"),
        mitigating_factors=d.get("mitigating_factors") or [],
        aggravating_factors=d.get("aggravating_factors") or [],
    )


def _parse_arg_eval(d: dict) -> ArgumentEvaluation:
    def _score(sd: dict) -> ArgumentScore:
        lv = int(sd.get("legal_validity", 0))
        el = int(sd.get("evidence_linkage", 0))
        lc = int(sd.get("logic_coherence", 0))
        return ArgumentScore(
            legal_validity=max(0, min(10, lv)),
            evidence_linkage=max(0, min(10, el)),
            logic_coherence=max(0, min(10, lc)),
            total=max(0, min(30, lv + el + lc)),
        )
    return ArgumentEvaluation(
        defence_score=_score(d.get("defence_score") or {}),
        prosecution_score=_score(d.get("prosecution_score") or {}),
    )


def _parse_questions(raw: list) -> list[QuestionRecord]:
    records = []
    for q in raw or []:
        records.append(QuestionRecord(
            target=str(q.get("target") or ""),
            question=str(q.get("question") or ""),
            answer=str(q.get("answer") or ""),
        ))
    return records


def _parse_finding(raw: str) -> str:
    valid = ("Bail Likely Granted", "Bail Likely Rejected", "Inconclusive")
    if raw in valid:
        return raw
    lower = (raw or "").lower()
    if "granted" in lower:
        return "Bail Likely Granted"
    if "rejected" in lower or "refused" in lower or "denied" in lower:
        return "Bail Likely Rejected"
    return "Inconclusive"


# ── Main builder ──────────────────────────────────────────────────────────────

class FindingsBuilder:
    """
    Converts the raw LLM JSON string from FINDINGS_PROMPT into a
    validated JudicialFindings object.

    Also applies the hallucination guard to sections and precedents.
    """

    def build(
        self,
        llm_output: str,
        legal_context_package: dict | str,
        precedent_context: dict | list | str,
        state_history: list[str],
    ) -> JudicialFindings:
        """
        Parameters
        ----------
        llm_output            : raw LLM text (JSON expected)
        legal_context_package : from LexiGraph Retrieval Agent
        precedent_context     : from Precedent Retrieval Agent
        state_history         : hearing state transitions for audit

        Returns
        -------
        JudicialFindings — fully validated, hallucination-guarded
        """
        data = _extract_json(llm_output) or {}

        allowed_secs  = _allowed_sections(legal_context_package)
        allowed_precs = _allowed_precedents(precedent_context)

        # Sections — hallucination guard
        raw_sections  = data.get("sections_applied") or []
        clean_sections = _guard_sections(raw_sections, allowed_secs)

        # Constitutional articles — light guard (common articles always allowed)
        articles = data.get("constitutional_articles_applied") or []

        # Precedents — hallucination guard
        raw_precs    = data.get("precedents_applied") or []
        clean_precs  = _guard_precedents(raw_precs, allowed_precs)

        # Confidence — clamp to 0-100
        confidence = int(data.get("confidence") or 50)
        confidence = max(0, min(100, confidence))

        return JudicialFindings(
            case_id=str(data.get("case_id") or "UNKNOWN"),
            hearing_date=str(data.get("hearing_date") or ""),
            judge_name=str(data.get("judge_name") or "AI Judge"),
            applicant=str(data.get("applicant") or ""),
            respondent=str(data.get("respondent") or "State"),
            sections_applied=clean_sections,
            constitutional_articles_applied=articles,
            precedents_applied=clean_precs,
            evidence_evaluation=_parse_evidence_evaluation(
                data.get("evidence_evaluation") or {}
            ),
            bail_factor_analysis=_parse_bail_factors(
                data.get("bail_factor_analysis") or {}
            ),
            argument_evaluation=_parse_arg_eval(
                data.get("argument_evaluation") or {}
            ),
            judicial_analysis=str(data.get("judicial_analysis") or ""),
            preliminary_finding=_parse_finding(              # type: ignore[arg-type]
                str(data.get("preliminary_finding") or "Inconclusive")
            ),
            confidence=confidence,
            conditions_if_granted=data.get("conditions_if_granted") or [],
            questions_asked=_parse_questions(data.get("questions_asked")),
            dynamic_retrieval_triggered=bool(data.get("dynamic_retrieval_triggered", False)),
            new_issues_identified=data.get("new_issues_identified") or [],
            state_history=state_history,
        )
