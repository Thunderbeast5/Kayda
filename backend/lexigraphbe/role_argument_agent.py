"""
Role Argument Agent for Stage 7: Role-Specific Legal Argument Generation Engine.
Generates legally grounded, role-specific legal arguments for Prosecutor, Defence, and Judge
using verified outputs from Stage 0 (Intake), Stage 4 (Statutory Verification), Stage 5 (Bail Reasoning), and Stage 6 (Precedent Retrieval).
Uses MODEL_TIER_REASONING flagship model for deep judicial argument generation and drafting.
Zero hardcoding — all submissions are dynamically generated from verified stage inputs.
"""

import json
from typing import Any, Dict, Optional, Union
from langchain_core.messages import HumanMessage, SystemMessage

from .config import extract_json_from_text, get_llm_for_tier, MODEL_TIER_REASONING
from .prompts import STAGE7_ARGUMENT_GENERATION_SYSTEM_PROMPT, STAGE7_ARGUMENT_GENERATION_USER_PROMPT_TEMPLATE
from .schemas import (
    BailReasoningObject,
    CaseContextObject,
    PrecedentRetrievalObject,
    RoleArgumentObject,
    StatutoryVerificationObject,
)


class RoleArgumentAgent:
    """
    Stage 7 Role Argument Agent generating grounded submissions for Prosecutor, Defence, and Judge.
    Uses MODEL_TIER_REASONING flagship model for legal argument generation and judicial order drafting.
    """

    def __init__(self, llm: Optional[Any] = None):
        self._llm = llm

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm_for_tier(tier=MODEL_TIER_REASONING, temperature=0.1)
        return self._llm

    def run(
        self,
        case_context: Union[CaseContextObject, Dict[str, Any], str],
        statutory_object: Union[StatutoryVerificationObject, Dict[str, Any], str],
        bail_object: Union[BailReasoningObject, Dict[str, Any], str],
        precedent_object: Union[PrecedentRetrievalObject, Dict[str, Any], str],
        correction_feedback: Optional[str] = None,
    ) -> RoleArgumentObject:
        """
        Runs Stage 7 Role-Specific Argument Generation on verified Stage 0, Stage 4, Stage 5, and Stage 6 objects.

        Returns:
            RoleArgumentObject instance.
        """
        # Standardize inputs
        cco_obj = case_context if isinstance(case_context, CaseContextObject) else CaseContextObject.model_validate(case_context if isinstance(case_context, dict) else json.loads(str(case_context)))
        svo_obj = statutory_object if isinstance(statutory_object, StatutoryVerificationObject) else StatutoryVerificationObject.model_validate(statutory_object if isinstance(statutory_object, dict) else json.loads(str(statutory_object)))
        bro_obj = bail_object if isinstance(bail_object, BailReasoningObject) else BailReasoningObject.model_validate(bail_object if isinstance(bail_object, dict) else json.loads(str(bail_object)))
        pro_obj = precedent_object if isinstance(precedent_object, PrecedentRetrievalObject) else PrecedentRetrievalObject.model_validate(precedent_object if isinstance(precedent_object, dict) else json.loads(str(precedent_object)))

        # Check upstream Stage 4 statutory verification status
        if not svo_obj.verified_sections or svo_obj.verification_status in ["FAILED_RETRY_EXHAUSTED", "UNVERIFIED"]:
            from .schemas import DefenceArguments, JudgeOrder, ProsecutorArguments
            return RoleArgumentObject(
                prosecutor_arguments=ProsecutorArguments(prayer="Deferred due to statutory verification failure."),
                defence_arguments=DefenceArguments(prayer="Deferred due to statutory verification failure."),
                judge_order=JudgeOrder(
                    issues=["Whether argument generation can proceed?"],
                    facts_considered=[],
                    applicable_law=[],
                    statutory_analysis="Statutory verification failed in Stage 4.",
                    bail_factor_analysis="N/A",
                    precedents=[],
                    reasoning="Argument generation deferred due to unverified statutory foundation.",
                    decision="Deferred",
                    conditions=[]
                ),
                manual_review=["Stage 7 argument generation deferred due to upstream Stage 4 statutory verification failure (no verified sections / unverified statutory foundation)."],
                verification_status="DEFERRED_UPSTREAM_FAILURE"
            )

        cco_json_str = cco_obj.to_downstream_json()
        svo_json_str = svo_obj.to_downstream_json()
        bro_json_str = bro_obj.to_downstream_json()
        pro_json_str = pro_obj.to_downstream_json()

        feedback_section = ""
        if correction_feedback:
            feedback_section = f"\nATTENTION - PREVIOUS ARGUMENT GENERATION AUDIT FEEDBACK:\n{correction_feedback}\n"

        user_prompt = STAGE7_ARGUMENT_GENERATION_USER_PROMPT_TEMPLATE.format(
            case_context_json=cco_json_str,
            statutory_object_json=svo_json_str,
            bail_object_json=bro_json_str,
            precedent_object_json=pro_json_str,
            correction_feedback_section=feedback_section,
        )

        messages = [
            SystemMessage(content=STAGE7_ARGUMENT_GENERATION_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]

        response = self.llm.invoke(messages)
        response_text = response.content if hasattr(response, "content") else str(response)

        extracted_dict = extract_json_from_text(response_text)

        # Validate with RoleArgumentObject Pydantic schema
        role_arg_obj = RoleArgumentObject.model_validate(extracted_dict)

        # Cross-reference precedent citations against Stage 6 retrieved precedents
        retrieved_precedent_names = {p.case_name.lower() for p in pro_obj.precedents}
        retrieved_citations = {p.citation.lower() for p in pro_obj.precedents if p.citation}

        for cited_p in role_arg_obj.prosecutor_arguments.precedents:
            if cited_p.lower() not in retrieved_precedent_names and not any(c in cited_p.lower() for c in retrieved_citations):
                note = f"Prosecutor cited precedent '{cited_p}' not present in Stage 6 retrieved precedents."
                if note not in role_arg_obj.manual_review:
                    role_arg_obj.manual_review.append(note)

        for cited_p in role_arg_obj.defence_arguments.precedents:
            if cited_p.lower() not in retrieved_precedent_names and not any(c in cited_p.lower() for c in retrieved_citations):
                note = f"Defence cited precedent '{cited_p}' not present in Stage 6 retrieved precedents."
                if note not in role_arg_obj.manual_review:
                    role_arg_obj.manual_review.append(note)

        for cited_p in role_arg_obj.judge_order.precedents:
            if cited_p.lower() not in retrieved_precedent_names and not any(c in cited_p.lower() for c in retrieved_citations):
                note = f"Judge cited precedent '{cited_p}' not present in Stage 6 retrieved precedents."
                if note not in role_arg_obj.manual_review:
                    role_arg_obj.manual_review.append(note)

        return role_arg_obj
