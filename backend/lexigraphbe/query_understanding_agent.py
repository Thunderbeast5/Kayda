"""
Query Understanding Agent for Stage 1: Query Understanding & Legal Decomposition.
Converts structured CaseContextObject into verified legal sub-queries (LegalQueryObject).
Strictly independent of statutory IPC/BNS section numbers or legal outcome predictions.
Model: gpt-4o-mini (MODEL_STAGE1).
"""

import json
from typing import Any, Dict, Optional, Union
from langchain_core.messages import HumanMessage, SystemMessage

from .config import extract_json_from_text, get_llm, MODEL_STAGE1
from .prompts import STAGE1_QUERY_UNDERSTANDING_SYSTEM_PROMPT, STAGE1_QUERY_UNDERSTANDING_USER_PROMPT_TEMPLATE
from .schemas import CaseContextObject, CaseProfile, LegalQueryObject


class QueryUnderstandingAgent:
    """
    Query Understanding Agent responsible for legal decomposition of CaseContextObject into
    independent legal concepts and single-issue sub-queries without statute section numbers.
    Passes through Stage 0 legal regime flags unchanged without re-deriving.
    Model: gpt-4o-mini (MODEL_STAGE1).
    """

    def __init__(self, llm: Optional[Any] = None, min_confidence_threshold: float = 0.70):
        self._llm = llm
        self.min_confidence_threshold = min_confidence_threshold

    @property
    def llm(self):
        if self._llm is None:
            # Use config's get_llm which now defaults to Groq
            self._llm = get_llm(temperature=0.0, model_name=MODEL_STAGE1)
        return self._llm

    def run(
        self,
        case_context: Union[CaseContextObject, CaseProfile, Dict[str, Any], str],
        correction_feedback: Optional[str] = None,
    ) -> LegalQueryObject:
        """
        Decomposes CaseContextObject into a LegalQueryObject.

        Args:
            case_context: CaseContextObject, CaseProfile, dict, or JSON string from Stage 0.
            correction_feedback: Feedback from QueryVerificationAgent if retrying.

        Returns:
            Validated LegalQueryObject instance.
        """
        # Extract Stage 0 legal regime passthrough fields directly without re-deriving
        stage0_regime = "UNKNOWN"
        stage0_flag = False
        stage0_notes = None

        if isinstance(case_context, CaseContextObject):
            stage0_regime = case_context.case_profile.legal_regime
            stage0_flag = case_context.case_profile.flag_for_confirmation
            stage0_notes = case_context.case_profile.regime_notes
        elif isinstance(case_context, CaseProfile):
            stage0_regime = case_context.legal_regime
            stage0_flag = case_context.flag_for_confirmation
            stage0_notes = case_context.regime_notes
        elif isinstance(case_context, dict):
            profile_dict = case_context.get("case_profile", case_context)
            stage0_regime = profile_dict.get("legal_regime", "UNKNOWN")
            stage0_flag = profile_dict.get("flag_for_confirmation", False)
            stage0_notes = profile_dict.get("regime_notes")
        elif isinstance(case_context, str):
            try:
                parsed_ctx = json.loads(case_context)
                if isinstance(parsed_ctx, dict):
                    profile_dict = parsed_ctx.get("case_profile", parsed_ctx)
                    stage0_regime = profile_dict.get("legal_regime", "UNKNOWN")
                    stage0_flag = profile_dict.get("flag_for_confirmation", False)
                    stage0_notes = profile_dict.get("regime_notes")
            except Exception:
                pass

        # Use typed Stage 1 slice containing only extracted fields (no raw docs/debug notes)
        from .stage_slices import get_stage1_slice, compact_json
        s1_slice = get_stage1_slice(case_context)
        case_context_str = compact_json(s1_slice.model_dump())

        feedback_section = ""
        if correction_feedback:
            feedback_section = f"\nATTENTION - PREVIOUS QUERY VERIFICATION FEEDBACK FOR CORRECTION:\n{correction_feedback}\n"

        user_prompt = STAGE1_QUERY_UNDERSTANDING_USER_PROMPT_TEMPLATE.format(
            case_context_json=case_context_str,
            correction_feedback_section=feedback_section,
        )

        messages = [
            SystemMessage(content=STAGE1_QUERY_UNDERSTANDING_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]

        response = self.llm.invoke(messages)
        response_text = response.content if hasattr(response, "content") else str(response)

        extracted_dict = extract_json_from_text(response_text)

        # Validate with LegalQueryObject Pydantic schema
        query_obj = LegalQueryObject.model_validate(extracted_dict)

        # Explicit passthrough of Stage 0 legal regime fields (never re-derived)
        query_obj.legal_regime = stage0_regime
        query_obj.flag_for_confirmation = stage0_flag
        query_obj.regime_notes = stage0_notes

        # Evaluate confidence cutoffs on legal concepts
        for item in query_obj.legal_concepts:
            if item.confidence < self.min_confidence_threshold:
                warning = f"Legal concept '{item.concept}' (confidence: {item.confidence:.2f} < cutoff {self.min_confidence_threshold}) requires manual review."
                if warning not in query_obj.manual_review:
                    query_obj.manual_review.append(warning)

        return query_obj
