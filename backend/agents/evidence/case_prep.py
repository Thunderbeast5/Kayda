"""
CasePrepAgent
=============
Stage-2 of the Evidence pipeline.

Responsibility:
  Takes any Indian legal document (FIR PDF, anticipatory bail order, etc.),
  extracts ALL facts with the LLM, then splits them into:

    CaseBrief    -- student-facing (incident, parties, evidence, submissions)
    HiddenGround -- judge-only    (bail outcome, ratio decidendi, court reasoning)

This separation ensures students debate the case without knowing the real verdict.

Usage:
    from agents.evidence.case_prep import CasePrepAgent
    agent = CasePrepAgent()
    result = agent.prepare(source="path/to/CASE_1602_2026_INPUT.pdf", session_id="abc123")
    # result.case_brief    → give to prosecutor / defense
    # result.hidden_ground → give to judge only
    # result.timeline      → give to all
"""

from __future__ import annotations

import json
import os
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# path setup
# ---------------------------------------------------------------------------
_EVIDENCE_DIR = Path(__file__).resolve().parent
_AGENTS_DIR   = _EVIDENCE_DIR.parent
_BACKEND_DIR  = _AGENTS_DIR.parent
sys.path.insert(0, str(_AGENTS_DIR))

load_dotenv(_BACKEND_DIR / ".env")

from config.llm_config import get_llm

# ---------------------------------------------------------------------------
# Imports: works both when imported as package AND run directly as a script.
# ---------------------------------------------------------------------------
try:
    # Imported as part of the package (normal use):
    #   from agents.evidence.case_prep import CasePrepAgent
    from .evidence import extract_text_from_any
    from .schemas import (
        BailOrderFacts, CaseBrief, CasePrepResult,
        FIRFacts, HiddenGround, ProceduralStep, TimelineEvent,
    )
except ImportError:
    # Running directly:  python agents/evidence/case_prep.py --file ...
    # __file__ parent is the evidence/ folder; add its parent (agents/) to path
    _here = Path(__file__).resolve().parent
    if str(_here) not in sys.path:
        sys.path.insert(0, str(_here))
    from evidence import extract_text_from_any          # type: ignore
    from schemas import (                                # type: ignore
        BailOrderFacts, CaseBrief, CasePrepResult,
        FIRFacts, HiddenGround, ProceduralStep, TimelineEvent,
    )


# ====================================================================
# Helpers
# ====================================================================

def _strip_json(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    last = max(text.rfind("}"), text.rfind("]"))
    return text[: last + 1].strip() if last != -1 else text


def _call_llm(prompt: str) -> str:
    llm = get_llm(temperature=0)
    return llm.invoke(prompt).content


def _parse_json(raw: str) -> Dict[str, Any]:
    try:
        return json.loads(_strip_json(raw))
    except json.JSONDecodeError:
        print(f"[case_prep] JSON parse warning — first 400 chars:\n{raw[:400]}")
        return {}


def _build_session_id(source: str) -> str:
    path = Path(source)
    base = path.stem[:30] if path.exists() else "_".join(source.split()[:4])[:30]
    base = re.sub(r"[^a-zA-Z0-9_-]", "_", base)
    ts   = datetime.now().strftime("%Y%m%d%H%M%S")
    uid  = uuid.uuid4().hex[:6]
    return f"{base}_{ts}_{uid}"


# ====================================================================
# Prompt: detect document type
# ====================================================================

_DOC_TYPE_PROMPT = """\
You are a legal document classifier. Read the beginning of the document and identify its type.

Types:
  "bail_order"   : A court order / judgement on an anticipatory bail / regular bail application
  "fir"          : First Information Report filed at police station
  "charge_sheet" : Police charge sheet (final report) filed in court
  "general"      : Any other legal document

Return ONLY one of the four words above. No explanation.

DOCUMENT (first 2000 chars):
{text}
"""


def detect_doc_type(raw_text: str) -> str:
    snippet = raw_text[:2000]
    result  = _call_llm(_DOC_TYPE_PROMPT.format(text=snippet)).strip().lower()
    valid   = {"bail_order", "fir", "charge_sheet", "general"}
    if result not in valid:
        print(f"[case_prep] Unknown doc type '{result}' — defaulting to bail_order")
        return "bail_order"
    print(f"[case_prep] Detected document type: {result}")
    return result


# ====================================================================
# Prompt: extract bail order facts (all fields including hidden ones)
# ====================================================================

_BAIL_ORDER_EXTRACTION_PROMPT = """\
You are a legal document analyst. Extract structured facts from this Indian
anticipatory bail or regular bail court order.

CRITICAL RULES:
- Output ALL strings in English (translate Marathi/Hindi text).
- Transliterate person names to Roman script.
- Use DD/MM/YYYY for dates, HH:MM 24h for times.
- Return ONLY valid JSON (no markdown, no commentary).

The document may be a bail ORDER (court's decision) or a bail APPLICATION
(petition filed by accused). Extract whatever is present.

Return this JSON schema exactly:
{{
  "document_type": "bail_order",
  "case_number": "ABA 1602/2026 or null",
  "court": "High Court of Judicature at Bombay or null",
  "judge": "MADHAV J. JAMDAR, J. or null",
  "date_of_order": "DD/MM/YYYY or null",
  "bail_type": "anticipatory",
  "applicant": "name of accused seeking bail or null",
  "respondent": "State of Maharashtra or null",
  "complainant": "original FIR complainant or null",
  "victims": ["names of victims"],
  "co_accused": ["other accused persons named"],
  "applicant_counsel": "advocate name or null",
  "state_counsel": "APP/advocate name or null",
  "investigating_officer": "IO name/designation or null",
  "fir_number": "182/2025 or null",
  "police_station": "Nandgaon or null",
  "district": "Nashik or null",
  "incident_summary": "one paragraph describing the underlying crime",
  "incident_date": "DD/MM/YYYY or null",
  "incident_time": "HH:MM or null",
  "incident_place": "village/city where crime occurred or null",
  "offence_nature": "dacoity at village fair or null",
  "sections_charged": ["BNS 310(2)", "BNSS 482"],
  "property_stolen": ["gold necklace 4gm Rs.24000", "gold ornaments of Prasanna Borse"],
  "total_loss": "total rupee value or null",
  "chargesheet_filed": true,
  "applicant_described_as_absconding": true,
  "custodial_interrogation_sought": true,
  "identification_parade_required": true,
  "defense_submissions": [
    "Applicant not involved in crime",
    "No criminal antecedents"
  ],
  "prosecution_submissions": [
    "Identification parade required, custodial interrogation necessary"
  ],
  "procedural_history": [
    {{"date": "20/04/2025", "event": "FIR No.182/2025 registered at Nandgaon PS"}},
    {{"date": "21/04/2025", "event": "First remand report filed"}}
  ],
  "evidence_items": [
    "Cell phone of Shubham Deepak Shelke traced to accused",
    "SIM card handed over by Shelke to applicant"
  ],
  "actual_bail_outcome": "granted OR rejected OR modified",
  "court_reasoning": "The court's reasoning paragraph verbatim",
  "bail_conditions_imposed": ["conditions if bail granted"],
  "bail_amount": "Rs. X or null",
  "ratio_decidendi": "The legal principle applied by the court",
  "judicial_observations": ["observation 1", "observation 2"],
  "key_legal_findings": ["finding 1 e.g. custodial interrogation necessary", "finding 2"]
}}

DOCUMENT TEXT:
{text}
"""


# ====================================================================
# Prompt: extract FIR facts
# ====================================================================

_FIR_EXTRACTION_PROMPT = """\
You are a legal document analyst. Extract structured facts from this Indian
FIR (First Information Report) or police complaint.

CRITICAL RULES:
- Output ALL strings in English (translate Marathi/Hindi text).
- Transliterate person names to Roman script.
- Use DD/MM/YYYY for dates, HH:MM 24h for times.
- Return ONLY valid JSON (no markdown, no commentary).

Return this JSON schema exactly:
{{
  "document_type": "fir",
  "fir_number": "182/2025 or null",
  "police_station": "Nandgaon or null",
  "district": "Nashik or null",
  "date_filed": "DD/MM/YYYY or null",
  "investigating_officer": "name or null",
  "complainant": "name of person who filed report or null",
  "accused": ["name1", "name2"],
  "victims": ["name1"],
  "incident_summary": "one paragraph what happened",
  "incident_date": "DD/MM/YYYY or null",
  "incident_time": "HH:MM or null",
  "incident_place": "location or null",
  "modus_operandi": "how crime was committed or null",
  "cash_stolen": "amount or null",
  "gold_stolen": "description e.g. '4gm gold necklace Rs.24000' or null",
  "vehicles_involved": [
    {{"type": null, "registration_no": null, "make_model": null,
      "engine_chassis_no": null, "estimated_value": null}}
  ],
  "other_property_stolen": ["item1"],
  "total_estimated_loss": "total Rs. amount or null",
  "sections_charged": ["BNS 310(2)"],
  "evidence_summary": ["evidence item 1"],
  "witness_names": ["witness 1"],
  "investigation_status": "chargesheet filed / under investigation / etc. or null"
}}

DOCUMENT TEXT:
{text}
"""


# ====================================================================
# Prompt: build timeline
# ====================================================================

_TIMELINE_PROMPT = """\
You are a legal analyst. Extract a chronological timeline of 4-8 KEY events
from this Indian legal document.

DOCUMENT TYPE: {document_type}

Rules:
- For bail orders: include incident, FIR registration, each remand/hearing, bail order.
- For FIRs: include incident, complaint, FIR registration, investigation steps.
- date: "DD/MM/YYYY" or null. time: "HH:MM" 24h or null.
- event_type: one of [incident, fir_registered, complaint_filed, bail_hearing,
  bail_granted, bail_rejected, court_order, investigation_action,
  remand_report, chargesheet_filed, other]
- description: one clear factual sentence.
- actors: people directly involved in this event.
- Return ONLY a valid JSON array.

[
  {{
    "date": "DD/MM/YYYY or null",
    "time": "HH:MM or null",
    "event_type": "string",
    "description": "string",
    "actors": ["name1"],
    "witnesses": [],
    "location": "string or null",
    "amount": "numeric string or null"
  }}
]

DOCUMENT TEXT:
{text}
"""


# ====================================================================
# CasePrepAgent
# ====================================================================

class CasePrepAgent:
    """
    Prepares a case from a legal document for the moot court simulator.

    Key output:
      case_brief    - student-facing (NO court outcome)
      hidden_ground - judge-only (real outcome + reasoning)
      timeline      - chronological events
    """

    def prepare(
        self,
        source: Union[str, Path],
        session_id: Optional[str] = None,
    ) -> CasePrepResult:
        """
        Full preparation pipeline.

        Args:
            source     : file path or raw text string
            session_id : optional, auto-generated if not provided

        Returns:
            CasePrepResult
        """
        # Step 1: extract text
        print(f"[case_prep] Extracting text from: {str(source)[:80]}")
        raw_text   = extract_text_from_any(source)
        session_id = session_id or _build_session_id(str(source))
        print(f"[case_prep] Session ID: {session_id}")
        print(f"[case_prep] Text length: {len(raw_text)} chars")

        # Step 2: detect document type
        doc_type = detect_doc_type(raw_text)

        # Step 3: extract facts based on doc type
        warnings: List[str] = []
        if doc_type == "fir" or doc_type == "charge_sheet":
            facts = self._extract_fir_facts(raw_text, warnings)
            case_brief, hidden_ground = self._split_fir(facts, raw_text)
        else:
            # bail_order or general -> use bail_order extraction
            facts = self._extract_bail_order_facts(raw_text, warnings)
            case_brief, hidden_ground = self._split_bail_order(facts, raw_text)

        # Step 4: extract timeline
        timeline = self._extract_timeline(raw_text, doc_type, warnings)

        return CasePrepResult(
            session_id=session_id,
            document_type=doc_type,
            case_brief=case_brief,
            hidden_ground=hidden_ground,
            timeline=timeline,
            raw_text=raw_text,
            extraction_warnings=warnings,
        )

    # ----------------------------------------------------------------
    # FIR extraction
    # ----------------------------------------------------------------

    def _extract_fir_facts(
        self,
        raw_text: str,
        warnings: List[str],
    ) -> FIRFacts:
        print("[case_prep] Running FIR extraction...")
        prompt   = _FIR_EXTRACTION_PROMPT.format(text=raw_text[:20000])
        raw_resp = _call_llm(prompt)
        data     = _parse_json(raw_resp)
        if not data:
            warnings.append("FIR extraction returned empty JSON")
            return FIRFacts()
        return FIRFacts(**{k: v for k, v in data.items() if k in FIRFacts.model_fields})

    def _split_fir(
        self,
        facts: FIRFacts,
        raw_text: str,
    ):
        """FIR has no hidden ground — all facts are public."""
        brief = CaseBrief(
            document_type     = "fir",
            bail_type         = "regular",
            fir_number        = facts.fir_number,
            police_station    = facts.police_station,
            district          = facts.district,
            complainant       = facts.complainant,
            victims           = facts.victims,
            co_accused        = facts.accused,
            incident_summary  = facts.incident_summary or "",
            incident_date     = facts.incident_date,
            incident_time     = facts.incident_time,
            incident_place    = facts.incident_place,
            offence_nature    = facts.modus_operandi,
            sections_charged  = facts.sections_charged,
            evidence_items    = facts.evidence_summary,
            investigation_facts = [
                f"Investigation status: {facts.investigation_status}"
            ] if facts.investigation_status else [],
            chargesheet_filed = (
                "chargesheet" in (facts.investigation_status or "").lower()
            ),
            prosecution_submissions = [],
            defense_submissions     = [],
            procedural_history      = [],
            property_stolen = [
                x for x in [facts.cash_stolen, facts.gold_stolen] + facts.other_property_stolen
                if x
            ],
            total_loss            = facts.total_estimated_loss,
            raw_case_narrative    = raw_text[:5000],
        )
        hidden = HiddenGround(
            actual_bail_outcome            = None,
            expected_outcome_justification = "FIR document — no bail decision yet.",
        )
        return brief, hidden

    # ----------------------------------------------------------------
    # Bail order extraction
    # ----------------------------------------------------------------

    def _extract_bail_order_facts(
        self,
        raw_text: str,
        warnings: List[str],
    ) -> BailOrderFacts:
        print("[case_prep] Running bail order extraction...")
        prompt   = _BAIL_ORDER_EXTRACTION_PROMPT.format(text=raw_text[:20000])
        raw_resp = _call_llm(prompt)
        data     = _parse_json(raw_resp)
        if not data:
            warnings.append("Bail order extraction returned empty JSON")
            return BailOrderFacts()

        # Coerce procedural_history list of dicts -> List[ProceduralStep]
        ph_raw = data.pop("procedural_history", []) or []
        ph     = [ProceduralStep(**x) for x in ph_raw if isinstance(x, dict)]
        data["procedural_history"] = ph  # type: ignore

        return BailOrderFacts(**{k: v for k, v in data.items()
                                 if k in BailOrderFacts.model_fields})

    def _split_bail_order(
        self,
        facts: BailOrderFacts,
        raw_text: str,
    ):
        """
        Split BailOrderFacts into:
          CaseBrief    (student safe — no outcome)
          HiddenGround (judge only — real outcome)
        """
        # Build a redacted narrative: strip the final outcome paragraph(s)
        # Heuristic: paragraphs containing "dismissed", "rejected", "granted",
        # "bail is rejected", "accordingly ... dismissed" etc.
        narrative = self._redact_outcome(raw_text)

        brief = CaseBrief(
            document_type          = facts.document_type,
            bail_type              = facts.bail_type,
            case_number            = facts.case_number,
            court                  = facts.court,
            fir_number             = facts.fir_number,
            police_station         = facts.police_station,
            district               = facts.district,
            applicant              = facts.applicant,
            respondent             = facts.respondent,
            complainant            = facts.complainant,
            victims                = facts.victims,
            co_accused             = facts.co_accused,
            incident_summary       = facts.incident_summary or "",
            offence_nature         = facts.offence_nature,
            incident_date          = facts.incident_date,
            incident_time          = facts.incident_time,
            incident_place         = facts.incident_place,
            sections_charged       = facts.sections_charged,
            evidence_items         = facts.evidence_items,
            investigation_facts    = self._build_investigation_facts(facts),
            chargesheet_filed      = facts.chargesheet_filed,
            custodial_interrogation_sought  = facts.custodial_interrogation_sought,
            identification_parade_required  = facts.identification_parade_required,
            prosecution_submissions = facts.prosecution_submissions,
            defense_submissions     = facts.defense_submissions,
            procedural_history      = facts.procedural_history,
            property_stolen         = facts.property_stolen,
            total_loss              = facts.total_loss,
            raw_case_narrative      = narrative,
        )

        hidden = HiddenGround(
            actual_bail_outcome            = facts.actual_bail_outcome,
            bail_conditions_imposed        = facts.bail_conditions_imposed,
            bail_amount                    = facts.bail_amount,
            ratio_decidendi                = facts.ratio_decidendi,
            court_reasoning                = facts.court_reasoning,
            key_legal_findings             = facts.key_legal_findings,
            judicial_observations          = facts.judicial_observations,
            expected_outcome_justification = self._build_outcome_justification(facts),
        )

        return brief, hidden

    # ----------------------------------------------------------------
    # Timeline
    # ----------------------------------------------------------------

    def _extract_timeline(
        self,
        raw_text: str,
        doc_type: str,
        warnings: List[str],
    ) -> List[TimelineEvent]:
        print("[case_prep] Extracting timeline...")
        prompt = _TIMELINE_PROMPT.format(
            document_type=doc_type,
            text=raw_text[:18000],
        )
        raw_resp = _call_llm(prompt)
        cleaned  = _strip_json(raw_resp)
        try:
            events_raw = json.loads(cleaned)
            if not isinstance(events_raw, list):
                warnings.append("Timeline LLM did not return a JSON array")
                return []
        except json.JSONDecodeError:
            warnings.append("Timeline JSON parse failed")
            return []

        events: List[TimelineEvent] = []
        for i, e in enumerate(events_raw):
            if not isinstance(e, dict):
                continue
            events.append(TimelineEvent(
                event_id    = f"E{i+1}",
                date        = e.get("date"),
                time        = e.get("time"),
                event_type  = e.get("event_type", "other"),
                description = e.get("description"),
                actors      = e.get("actors") or [],
                witnesses   = e.get("witnesses") or [],
                location    = e.get("location"),
                amount      = e.get("amount"),
            ))
        print(f"[case_prep] Timeline: {len(events)} events extracted")
        return events

    # ----------------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------------

    @staticmethod
    def _redact_outcome(raw_text: str) -> str:
        """
        Remove the final paragraph(s) that reveal the court's decision.
        Looks for paragraphs containing outcome keywords (dismissed/granted/rejected)
        and strips them.
        """
        _OUTCOME_RE = re.compile(
            r"(?:anticipatory bail application is|bail application is|"
            r"accordingly[,\s]+the|appeal is|application is)\s+"
            r"(?:dismissed|rejected|allowed|granted|disposed of)",
            re.IGNORECASE,
        )

        paragraphs = re.split(r"\n{2,}", raw_text)
        safe = []
        for para in paragraphs:
            if _OUTCOME_RE.search(para):
                # Replace the entire outcome paragraph with a placeholder
                safe.append("[COURT DECISION — REDACTED FOR MOOT COURT EXERCISE]")
            else:
                safe.append(para)
        return "\n\n".join(safe)

    @staticmethod
    def _build_investigation_facts(facts: BailOrderFacts) -> List[str]:
        items = []
        if facts.chargesheet_filed:
            items.append("Chargesheet has been filed.")
        if facts.applicant_described_as_absconding:
            items.append("Applicant described as absconding in the chargesheet.")
        if facts.custodial_interrogation_sought:
            items.append("State seeks custodial interrogation of the applicant.")
        if facts.identification_parade_required:
            items.append("Identification parade is required in this case.")
        return items

    @staticmethod
    def _build_outcome_justification(facts: BailOrderFacts) -> str:
        outcome = facts.actual_bail_outcome or "unknown"
        reason  = facts.court_reasoning or facts.ratio_decidendi or ""
        return (
            f"The court {outcome} the anticipatory bail application. "
            f"Key reasoning: {reason[:500]}"
        )


# ====================================================================
# CLI entry point
# ====================================================================

if __name__ == "__main__":
    import argparse, sys

    parser = argparse.ArgumentParser(
        description="Case Prep Agent — prepare a moot court case from any legal document."
    )
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--file", "-f", help="Path to PDF, .docx, .txt, or image file")
    grp.add_argument("--text", "-t", help="Raw case text string")
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--show-hidden", action="store_true",
                        help="Also print HiddenGround (judge-only data)")
    args = parser.parse_args()

    agent  = CasePrepAgent()
    result = agent.prepare(
        source=args.file or args.text,
        session_id=args.session_id,
    )

    print("\n" + "=" * 70)
    print("CASE BRIEF  (student-facing)")
    print("=" * 70)
    print(result.case_brief.model_dump_json(indent=2))

    print("\n" + "=" * 70)
    print("TIMELINE")
    print("=" * 70)
    for ev in result.timeline:
        print(f"  [{ev.event_id}] {ev.date or '?'} {ev.time or ''} — {ev.event_type}: {ev.description}")

    if args.show_hidden:
        print("\n" + "=" * 70)
        print("HIDDEN GROUND  (judge-only — DO NOT SHOW TO STUDENTS)")
        print("=" * 70)
        print(result.hidden_ground.model_dump_json(indent=2))

    if result.extraction_warnings:
        print("\nWarnings:", result.extraction_warnings)
