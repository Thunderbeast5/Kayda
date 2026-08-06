"""
Case Intake Agent for Stage 0: Case Intake & Context Initialization.
Normalizes raw legal case documents into structured CaseProfile JSON without legal reasoning.
Enforces strict Legal Regime Precedence, Universal Procedural Document Checklists, and explicit Confidence Score Cutoff thresholds.
Model: gpt-4o-mini (MODEL_STAGE0) — lightweight extraction only.
"""

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
            self._llm = get_llm(temperature=0.1, model_name=MODEL_STAGE0)
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

        # Handle explicit user regime override
        if inp.legal_regime_override:
            extracted_dict["legal_regime"] = inp.legal_regime_override
            extracted_dict["flag_for_confirmation"] = False
            extracted_dict["regime_notes"] = f"User explicit override applied: {inp.legal_regime_override}"

        # Validate with CaseProfile schema
        case_profile = CaseProfile.model_validate(extracted_dict)
        case_profile.min_confidence_threshold = inp.min_confidence_threshold

        # Post-validation sanity check on regime precedence flags
        meta = case_profile.case_metadata
        if not inp.legal_regime_override:
            if not meta.offence_date and not meta.fir_date:
                case_profile.legal_regime = "UNKNOWN"
                case_profile.flag_for_confirmation = True
                if "Legal regime confirmation (Offence/FIR date missing)" not in case_profile.missing_information:
                    case_profile.missing_information.append("Legal regime confirmation (Offence/FIR date missing)")
                if not case_profile.regime_notes:
                    case_profile.regime_notes = "UNKNOWN legal regime: defaulted to dual IPC/BNS + CrPC/BNSS representation."
            elif not meta.offence_date and meta.fir_date:
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
