"""
Case Intake Agent for Stage 0: Case Intake & Context Initialization.
Normalizes raw legal case documents into structured CaseProfile JSON without legal reasoning.
Enforces strict Legal Regime Precedence, Universal Procedural Document Checklists, and explicit Confidence Score Cutoff thresholds.
Model: gpt-4o-mini (MODEL_STAGE0) — lightweight extraction only.
"""

import re
from typing import Any, Dict, Optional, Union
from langchain_core.messages import HumanMessage, SystemMessage

from .config import extract_json_from_text, get_llm, MODEL_STAGE0
from .prompts import STAGE0_INTAKE_SYSTEM_PROMPT, STAGE0_INTAKE_USER_PROMPT_TEMPLATE
from .schemas import CaseProfile, IntakeInput, LowConfidenceField


class CaseIntakeAgent:
    """
    Case Intake Agent responsible ONLY for normalizing and structuring incoming case documents.
    Does NOT perform legal reasoning, section prediction, guilt determination, or bail decisions.
    Model: gpt-4o-mini (MODEL_STAGE0).
    """

    def __init__(self, llm: Optional[Any] = None):
        self._llm = llm

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm(temperature=0.0, model_name=MODEL_STAGE0)
        return self._llm

    def run(
        self,
        intake_input: Union[IntakeInput, str, Dict[str, Any]],
        correction_feedback: Optional[str] = None,
    ) -> CaseProfile:
        """
        Processes raw case input and returns a structured CaseProfile.

        Args:
            intake_input: Raw case text string, dict, or IntakeInput object.
            correction_feedback: Feedback from CaseIntakeVerifierAgent if retrying intake.

        Returns:
            Validated CaseProfile instance.
        """
        # Standardize input
        if isinstance(intake_input, str):
            inp = IntakeInput(documents_text=intake_input)
        elif isinstance(intake_input, dict):
            inp = IntakeInput(**intake_input)
        elif isinstance(intake_input, IntakeInput):
            inp = intake_input
        else:
            raise ValueError(f"Invalid input type: {type(intake_input)}")

        # Build raw text section combining document text and user instructions/metadata
        raw_text_parts = []
        if inp.documents_text:
            raw_text_parts.append(f"DOCUMENT TEXT:\n{inp.documents_text}")
        if inp.user_query:
            raw_text_parts.append(f"USER QUERY / INSTRUCTIONS:\n{inp.user_query}")
        if inp.role:
            raw_text_parts.append(f"ROLE: {inp.role}")
        if inp.court_type:
            raw_text_parts.append(f"COURT TYPE: {inp.court_type}")
        if inp.legal_regime_override:
            raw_text_parts.append(f"USER SPECIFIED LEGAL REGIME: {inp.legal_regime_override}")

        combined_case_text = "\n\n".join(raw_text_parts) if raw_text_parts else "No document text provided."

        # Optional feedback section if re-running due to verification correction request
        feedback_section = ""
        if correction_feedback:
            feedback_section = f"\nATTENTION - PREVIOUS VERIFICATION FEEDBACK FOR CORRECTION:\n{correction_feedback}\n"

        user_prompt = STAGE0_INTAKE_USER_PROMPT_TEMPLATE.format(
            case_text=combined_case_text,
            correction_feedback_section=feedback_section,
        )

        messages = [
            SystemMessage(content=STAGE0_INTAKE_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]

        response = self.llm.invoke(messages)
        response_text = response.content if hasattr(response, "content") else str(response)

        # Parse extracted JSON
        extracted_dict = extract_json_from_text(response_text)

        # Handle legal regime deterministically via RegimeResolver (Issue S-1)
        meta_dict = extracted_dict.get("case_metadata") or {}
        offence_date = meta_dict.get("offence_date")
        fir_date = meta_dict.get("fir_date")

        # Helper to check if date is on or after 1 July 2024
        def _is_post_july_2024(d_str: Optional[str]) -> Optional[bool]:
            if not d_str:
                return None
            d = str(d_str).strip().lower()
            m = re.search(r"\b(19\d\d|20\d\d)\b", d)
            if m:
                yr = int(m.group(1))
                if yr >= 2025:
                    return True
                if yr < 2024:
                    return False
                iso_m = re.search(r"2024-(\d{1,2})", d)
                if iso_m:
                    return int(iso_m.group(1)) >= 7
                for post_m in ["july", "august", "september", "october", "november", "december", "jul", "aug", "sep", "oct", "nov", "dec"]:
                    if post_m in d:
                        return True
                for pre_m in ["january", "february", "march", "april", "may", "june", "jan", "feb", "mar", "apr", "jun"]:
                    if pre_m in d:
                        return False
            return None

        if inp.legal_regime_override:
            extracted_dict["legal_regime"] = inp.legal_regime_override
            extracted_dict["flag_for_confirmation"] = False
            extracted_dict["regime_notes"] = f"User explicit override applied: {inp.legal_regime_override}"
        else:
            post_offence = _is_post_july_2024(offence_date)
            post_fir = _is_post_july_2024(fir_date)
            sub = "BNS" if post_offence is True else ("IPC" if post_offence is False else ("BNS" if post_fir is True else "IPC"))
            proc = "BNSS" if post_fir is True else ("CrPC" if post_fir is False else ("BNSS" if post_offence is True else "CrPC"))
            extracted_dict["legal_regime"] = f"{sub} + {proc}"
            extracted_dict["flag_for_confirmation"] = (post_offence is None)
            extracted_dict["regime_notes"] = f"Deterministic regime: {sub} substantive, {proc} procedural (offence_date={offence_date}, fir_date={fir_date})."

        # Normalize case_facts from common LLM synonym keys if needed
        if not extracted_dict.get("case_facts"):
            for alt_key in ["case_narrative", "factual_narrative", "facts", "narrative", "offence_narrative"]:
                if extracted_dict.get(alt_key):
                    extracted_dict["case_facts"] = extracted_dict[alt_key]
                    break
        if not extracted_dict.get("case_facts") and inp.documents_text:
            extracted_dict["case_facts"] = inp.documents_text

        # Normalize accused party names if None (handle cases without explicit names)
        if extracted_dict.get("parties") and extracted_dict["parties"].get("accused"):
            accused_list = extracted_dict["parties"]["accused"]
            if isinstance(accused_list, list):
                for i, accused in enumerate(accused_list):
                    if isinstance(accused, dict) and accused.get("name") is None:
                        accused["name"] = "Applicant" if "anticipatory" in combined_case_text.lower() else "Accused"
        
        if extracted_dict.get("primary_participants") and extracted_dict["primary_participants"].get("accused"):
            accused_list = extracted_dict["primary_participants"]["accused"]
            if isinstance(accused_list, list):
                for i, accused in enumerate(accused_list):
                    if isinstance(accused, dict) and accused.get("name") is None:
                        accused["name"] = "Applicant" if "anticipatory" in combined_case_text.lower() else "Accused"

        # Validate with CaseProfile schema
        case_profile = CaseProfile.model_validate(extracted_dict)
        case_profile.min_confidence_threshold = inp.min_confidence_threshold

        # Post-validation sanity check on regime precedence flags
        meta = case_profile.case_metadata
        if not inp.legal_regime_override:
            if not meta.offence_date and not meta.fir_date:
                case_profile.flag_for_confirmation = True
                if not case_profile.regime_notes:
                    case_profile.regime_notes = f"Regime determined using FIR date fallback ({meta.fir_date}) because Offence Date is unstated."

        # Check universal procedural document checklist (without premature legal inferencing)
        case_profile.check_procedural_missing_documents()

        # ----------------------------------------------------------------------
        # CONFIDENCE SCORE ACTION & CUTOFF THRESHOLD EVALUATION
        # ----------------------------------------------------------------------
        cutoff = case_profile.min_confidence_threshold
        conf_dict = case_profile.confidence or {}

        if conf_dict:
            scores = [float(s) for s in conf_dict.values() if isinstance(s, (int, float))]
            case_profile.overall_confidence = round(sum(scores) / len(scores), 2) if scores else 1.0

        for field_name, score in conf_dict.items():
            if isinstance(score, (int, float)) and score < cutoff:
                # Find extracted field value if possible
                val = getattr(case_profile, field_name, None)
                if val is None and hasattr(case_profile.case_metadata, field_name):
                    val = getattr(case_profile.case_metadata, field_name, None)

                low_conf_entry = LowConfidenceField(
                    field_name=field_name,
                    confidence_score=float(score),
                    cutoff_threshold=cutoff,
                    extracted_value=val,
                    action_required=f"Field '{field_name}' score {score} < cutoff {cutoff}. Requires manual confirmation before downstream reasoning."
                )
                case_profile.low_confidence_fields.append(low_conf_entry)
                case_profile.flag_for_confirmation = True

                warning_msg = f"Manual confirmation required for '{field_name}' (low confidence: {score} < cutoff {cutoff})"
                if warning_msg not in case_profile.missing_information:
                    case_profile.missing_information.append(warning_msg)

        return case_profile
