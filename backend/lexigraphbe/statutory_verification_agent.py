"""
Statutory Verification Agent for Stage 4: Full Statutory Verification & Ingredient Matching.
Retrieves complete statutory context for candidate sections shortlisted in Stage 3 and evaluates
essential statutory ingredients against verified case facts in ONE single batched LLM call.
Extracts punishment text and Arnesh Kumar (<=7 years) threshold metrics into output contract.
Model: gpt-4o-mini (MODEL_STAGE2) — structured verification, near-deterministic ingredient matching.
"""

import csv
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from langchain_core.messages import HumanMessage, SystemMessage

from .config import extract_json_from_text, get_llm, MODEL_STAGE2
from .prompts import STAGE4_STATUTORY_VERIFICATION_SYSTEM_PROMPT, STAGE4_STATUTORY_VERIFICATION_USER_PROMPT_TEMPLATE
from .schemas import ChapterIdentificationObject, LegalQueryObject, StatutoryVerificationObject
from .statute_repository import StatuteRepository


def parse_punishment_and_severity(text: str, section_number: str = "", statute: str = "") -> Tuple[str, float, bool]:
    """
    Extracts punishment text, max imprisonment in years, and Arnesh Kumar threshold (>7 years).
    Validates against StatuteRepository First Schedule CrPC/BNSS ground truth.

    Returns:
        (punishment_text, max_imprisonment_years, arnesh_kumar_threshold_exceeded)
    """
    clean_sec = (section_number or "").strip().upper().replace("SECTION ", "").replace("IPC_", "").replace("BNS_", "")
    first_sched = StatuteRepository.get_instance().get_first_schedule_metadata(clean_sec, statute)

    if first_sched:
        p_max = first_sched["punishment_maximum"]
        p_min = first_sched["punishment_minimum"]
        p_text = f"Punishment: {p_min + ' to ' if p_min else ''}{p_max}"
        
        if p_max in ("Death", "Life Imprisonment"):
            return (p_text, 20.0, True)
        
        matches = re.findall(r"(\d+)\s*(?:years?|yrs?)", p_max.lower())
        if matches:
            max_yrs = max(float(m) for m in matches)
            return (p_text, max_yrs, max_yrs > 7.0)

    if not text:
        return ("Punishment as prescribed by law.", 3.0, False)

    cleaned = text.lower()
    punishment_snippet = text.strip()

    # Check Life or Death penalty
    if "imprisonment for life" in cleaned or "death" in cleaned or "life imprisonment" in cleaned:
        return (punishment_snippet, 20.0, True)

    # Search for numeric years in text e.g. "3 years", "7 years", "10 years", "2 years"
    matches = re.findall(r"(\d+)\s*(?:years?|yrs?)", cleaned)
    if matches:
        years = [float(m) for m in matches]
        max_yrs = max(years)
        exceeded = max_yrs > 7.0
        return (punishment_snippet, max_yrs, exceeded)

    # Search for months e.g. "6 months", "3 months"
    month_matches = re.findall(r"(\d+)\s*(?:months?|mths?)", cleaned)
    if month_matches:
        months = [float(m) for m in month_matches]
        max_yrs = round(max(months) / 12.0, 2)
        return (punishment_snippet, max_yrs, False)

    return (punishment_snippet, 3.0, False)


class StatutoryVerificationAgent:
    """
    Stage 4 Statutory Verification & Ingredient Matching Agent (Schema v4.0).
    Uses StatuteRepository singleton for cached statutory text lookups.
    """

    def __init__(
        self,
        llm: Optional[Any] = None,
        min_confidence_threshold: float = 0.70,
    ):
        self._llm = llm
        self.min_confidence_threshold = min_confidence_threshold
        self.statute_db = StatuteRepository.get_instance().get_statute_db()

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm(temperature=0.1, model_name=MODEL_STAGE2)
        return self._llm

    def _load_statutory_text_db(self):
        """Loads complete statutory text database from data/new/ CSV and JSON datasets."""
        ipc_paths = [
            Path("data/new/ipc_sections.csv"),
            Path("../data/new/ipc_sections.csv"),
            Path("c:/MootCourt/data/new/ipc_sections.csv"),
        ]
        bns_paths = [
            Path("data/new/bns_sections_clean.csv"),
            Path("../data/new/bns_sections_clean.csv"),
            Path("c:/MootCourt/data/new/bns_sections_clean.csv"),
        ]

        # Load IPC DB
        for p in ipc_paths:
            if p.exists():
                try:
                    with open(p, mode="r", encoding="utf-8", errors="ignore") as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            sec_num = (row.get("Section") or "").replace("IPC_", "").strip()
                            offense = (row.get("Offense") or "").strip()
                            desc = (row.get("Description") or "").strip()
                            punishment = (row.get("Punishment") or "").strip()
                            if sec_num:
                                self.statute_db[f"IPC_{sec_num}"] = {
                                    "statute": "IPC",
                                    "section_number": sec_num,
                                    "section_title": offense,
                                    "full_text": desc,
                                    "punishment": punishment or desc,
                                    "explanations": "See statutory description.",
                                    "illustrations": "N/A",
                                    "exceptions": "N/A",
                                    "provisos": "N/A",
                                }
                    break
                except Exception:
                    pass

        # Load BNS DB
        for p in bns_paths:
            if p.exists():
                try:
                    with open(p, mode="r", encoding="utf-8", errors="ignore") as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            sec_num = (row.get("Section") or "").strip()
                            title = (row.get("Title") or "").strip()
                            desc = (row.get("Description") or "").strip()
                            chap = (row.get("Chapter") or "").strip()
                            if sec_num:
                                self.statute_db[f"BNS_{sec_num}"] = {
                                    "statute": "BNS",
                                    "section_number": sec_num,
                                    "section_title": title,
                                    "full_text": desc,
                                    "punishment": desc,
                                    "explanations": chap,
                                    "illustrations": "N/A",
                                    "exceptions": "N/A",
                                    "provisos": "N/A",
                                }
                    break
                except Exception:
                    pass

    def retrieve_statutory_context_for_candidates(
        self,
        chapter_obj: ChapterIdentificationObject,
    ) -> List[Dict[str, Any]]:
        """Retrieves full statutory context records for all section candidates shortlisted in Stage 3."""
        regime_str = chapter_obj.legal_regime or ""
        statute_prefix = "BNS" if "BNS" in regime_str.upper() else "IPC"

        context_list = []
        for sec_cand in chapter_obj.section_candidates:
            clean_sec = sec_cand.section_number.strip()
            db_key = f"{statute_prefix}_{clean_sec}"

            record = self.statute_db.get(db_key)
            if not record:
                record = next(
                    (val for key, val in self.statute_db.items() if val["section_number"] == clean_sec),
                    None,
                )

            if record:
                p_text, max_yrs, exceeded = parse_punishment_and_severity(record["punishment"] or record["full_text"], section_number=clean_sec, statute=statute_prefix)
                rec_copy = dict(record)
                rec_copy["parsed_punishment_text"] = p_text
                rec_copy["parsed_max_imprisonment_years"] = max_yrs
                rec_copy["parsed_arnesh_kumar_threshold_exceeded"] = exceeded
                context_list.append(rec_copy)
            else:
                p_text, max_yrs, exceeded = parse_punishment_and_severity("", section_number=clean_sec, statute=statute_prefix)
                context_list.append({
                    "statute": statute_prefix,
                    "section_number": clean_sec,
                    "section_title": sec_cand.section_title,
                    "full_text": f"Section {clean_sec} - {sec_cand.section_title}",
                    "punishment": p_text,
                    "parsed_punishment_text": p_text,
                    "parsed_max_imprisonment_years": max_yrs,
                    "parsed_arnesh_kumar_threshold_exceeded": exceeded,
                    "explanations": "N/A",
                    "illustrations": "N/A",
                    "exceptions": "N/A",
                    "provisos": "N/A",
                })

        return context_list

    def run(
        self,
        legal_query: Union[LegalQueryObject, Dict[str, Any], str],
        chapter_object: Union[ChapterIdentificationObject, Dict[str, Any], str],
        correction_feedback: Optional[str] = None,
    ) -> StatutoryVerificationObject:
        """
        Runs Stage 4 Statutory Verification on Stage 1 LegalQueryObject and Stage 3 ChapterIdentificationObject.

        Args:
            legal_query: Verified LegalQueryObject from Stage 1.
            chapter_object: Verified ChapterIdentificationObject from Stage 3.
            correction_feedback: Feedback from StatutoryVerificationAuditor if retrying.

        Returns:
            StatutoryVerificationObject instance.
        """
        if isinstance(legal_query, LegalQueryObject):
            query_obj = legal_query
            query_json_str = legal_query.to_downstream_json()
        elif isinstance(legal_query, dict):
            query_obj = LegalQueryObject.model_validate(legal_query)
            query_json_str = json.dumps(legal_query, indent=2)
        else:
            query_obj = LegalQueryObject.model_validate(json.loads(str(legal_query)))
            query_json_str = str(legal_query)

        if isinstance(chapter_object, ChapterIdentificationObject):
            chap_obj = chapter_object
            chap_json_str = chapter_object.to_downstream_json()
        elif isinstance(chapter_object, dict):
            chap_obj = ChapterIdentificationObject.model_validate(chapter_object)
            chap_json_str = json.dumps(chapter_object, indent=2)
        else:
            chap_obj = ChapterIdentificationObject.model_validate(json.loads(str(chapter_object)))
            chap_json_str = str(chapter_object)

        # Retrieve complete statutory context for shortlisted candidate sections
        statutory_records = self.retrieve_statutory_context_for_candidates(chap_obj)
        statutory_context_json = json.dumps(statutory_records, indent=2)

        feedback_section = ""
        if correction_feedback:
            feedback_section = f"\nATTENTION - PREVIOUS STATUTORY VERIFICATION AUDIT FEEDBACK:\n{correction_feedback}\n"

        user_prompt = STAGE4_STATUTORY_VERIFICATION_USER_PROMPT_TEMPLATE.format(
            legal_query_json=query_json_str,
            chapter_object_json=chap_json_str,
            statutory_context_json=statutory_context_json,
            correction_feedback_section=feedback_section,
        )

        messages = [
            SystemMessage(content=STAGE4_STATUTORY_VERIFICATION_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]

        response = self.llm.invoke(messages)
        response_text = response.content if hasattr(response, "content") else str(response)

        extracted_dict = extract_json_from_text(response_text)

        # Validate with StatutoryVerificationObject Pydantic schema (v4.0)
        statutory_obj = StatutoryVerificationObject.model_validate(extracted_dict)
        statutory_obj.schema_version = "4.0"

        # Passthrough legal_regime from Stage 3 ChapterIdentificationObject
        statutory_obj.legal_regime = chap_obj.legal_regime or "IPC + CrPC"

        print(f"[StatutoryVerificationAgent] Before fallback: verified_offences={len(statutory_obj.verified_offences)}, verified_sections={len(statutory_obj.verified_sections)}")

        # If verified_offences is empty but verified_sections exist, populate verified_offences
        if not statutory_obj.verified_offences and statutory_obj.verified_sections:
            from .schemas import VerifiedOffenceItemStage4, IngredientEvaluationItem
            for v_sec in statutory_obj.verified_sections:
                eval_items = []
                for ing in v_sec.ingredients:
                    eval_items.append(
                        IngredientEvaluationItem(
                            ingredient=ing.ingredient,
                            matched_fact=ing.reason,
                            status="Satisfied" if ing.status in ("Satisfied", "Partially Satisfied") else "Missing",
                            reason=ing.reason,
                            confidence=0.90,
                        )
                    )
                statutory_obj.verified_offences.append(
                    VerifiedOffenceItemStage4(
                        section_number=v_sec.section_number,
                        statute="IPC" if "BNS" not in (v_sec.section_number or "") else "BNS",
                        title=v_sec.section_title,
                        ingredient_evaluation=eval_items,
                        overall_prima_facie_strength="Strong" if v_sec.overall_confidence >= 0.85 else "Moderate",
                        missing_mandatory_facts=[],
                        missing_supporting_facts=[],
                        investigation_requirements=["Verify witness statements", "Collect documentary evidence"],
                        legal_reasoning=f"Ingredients evaluated for Section {v_sec.section_number} {v_sec.section_title}.",
                        overall_status="Prima Facie Attracted" if v_sec.overall_confidence >= 0.70 else "Partially Attracted"
                    )
                )
        
        print(f"[StatutoryVerificationAgent] After fallback: verified_offences={len(statutory_obj.verified_offences)}, verified_sections={len(statutory_obj.verified_sections)}")

        for v_sec in statutory_obj.verified_sections:
            if v_sec.overall_confidence < self.min_confidence_threshold:
                note = f"Verified section {v_sec.section_number} ('{v_sec.section_title}') confidence {v_sec.overall_confidence:.2f} < cutoff {self.min_confidence_threshold}."
                if note not in statutory_obj.manual_review:
                    statutory_obj.manual_review.append(note)

        statutory_obj.verified_sections.sort(key=lambda x: x.overall_confidence, reverse=True)
        return statutory_obj
