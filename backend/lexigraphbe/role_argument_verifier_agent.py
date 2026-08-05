"""
Role Argument Verifier Agent for Stage 7: Role-Specific Legal Argument Verification Auditor.
Audits generated RoleArgumentObject against source CaseContextObject, StatutoryVerificationObject,
BailReasoningObject, and PrecedentRetrievalObject using MODEL_TIER_REASONING.
Verifies factual support, statutory alignment, 0-unretrieved precedent citation leaks,
judicial decision consistency, and closed-set bail condition compliance.
"""

import json
from typing import Any, Dict, List, Optional, Union
from langchain_core.messages import HumanMessage, SystemMessage

from .config import extract_json_from_text, get_llm_for_tier, MODEL_TIER_REASONING
from .prompts import STAGE7_VERIFIER_SYSTEM_PROMPT, STAGE7_VERIFIER_USER_PROMPT_TEMPLATE
from .schemas import (
    BailReasoningObject,
    CaseContextObject,
    PrecedentRetrievalObject,
    RoleArgumentObject,
    RoleArgumentVerificationIssue,
    RoleArgumentVerificationResult,
    StatutoryVerificationObject,
)
from .bail_condition_validator import BailConditionValidator


class RoleArgumentVerifierAgent:
    """
    Stage 7 Role Argument Verification Auditor.
    Audits generated RoleArgumentObject across 7 verification criteria using MODEL_TIER_REASONING.
    Enforces deterministic 0-cost pre-checks for unretrieved precedent citations.
    """

    def __init__(self, llm: Optional[Any] = None):
        self._llm = llm

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm_for_tier(tier=MODEL_TIER_REASONING, temperature=0.0)
        return self._llm

    def verify(
        self,
        case_context: Union[CaseContextObject, Dict[str, Any], str],
        statutory_object: Union[StatutoryVerificationObject, Dict[str, Any], str],
        bail_object: Union[BailReasoningObject, Dict[str, Any], str],
        precedent_object: Union[PrecedentRetrievalObject, Dict[str, Any], str],
        role_argument_object: Union[RoleArgumentObject, Dict[str, Any], str],
    ) -> RoleArgumentVerificationResult:
        """
        Audits generated RoleArgumentObject against Stage 0, Stage 4, Stage 5, and Stage 6 outputs.

        Returns:
            RoleArgumentVerificationResult instance with status='VERIFIED' or 'RETRY'.
        """
        # Standardize inputs
        cco_obj = case_context if isinstance(case_context, CaseContextObject) else CaseContextObject.model_validate(case_context if isinstance(case_context, dict) else json.loads(str(case_context)))
        svo_obj = statutory_object if isinstance(statutory_object, StatutoryVerificationObject) else StatutoryVerificationObject.model_validate(statutory_object if isinstance(statutory_object, dict) else json.loads(str(statutory_object)))
        bro_obj = bail_object if isinstance(bail_object, BailReasoningObject) else BailReasoningObject.model_validate(bail_object if isinstance(bail_object, dict) else json.loads(str(bail_object)))
        pro_obj = precedent_object if isinstance(precedent_object, PrecedentRetrievalObject) else PrecedentRetrievalObject.model_validate(precedent_object if isinstance(precedent_object, dict) else json.loads(str(precedent_object)))
        rao_obj = role_argument_object if isinstance(role_argument_object, RoleArgumentObject) else RoleArgumentObject.model_validate(role_argument_object if isinstance(role_argument_object, dict) else json.loads(str(role_argument_object)))

        # Deterministic 0-Cost Pre-Check: Grounding & Ratio Decidendi Audit
        retrieved_precedent_names = {p.case_name.lower() for p in pro_obj.precedents}
        retrieved_citations = {p.citation.lower() for p in pro_obj.precedents if p.citation}
        retrieved_ratios = {p.case_name.lower(): (p.ratio_decidendi or "").lower() for p in pro_obj.precedents}
        low_confidence_cases = {p.case_name.lower() for p in pro_obj.precedents if p.similarity_score < 0.70}

        unretrieved_issues: List[RoleArgumentVerificationIssue] = []

        all_cited = (
            rao_obj.prosecutor_arguments.precedents +
            rao_obj.defence_arguments.precedents +
            rao_obj.judge_order.precedents
        )

        for cited_p in all_cited:
            c_low = cited_p.lower()
            # 1. Verification of Retrieved Judgment Identity
            if c_low not in retrieved_precedent_names and not any(cit in c_low for cit in retrieved_citations):
                unretrieved_issues.append(
                    RoleArgumentVerificationIssue(
                        target=cited_p,
                        issue=f"Precedent '{cited_p}' was cited in arguments but is not demonstrably retrieved from the legal corpus in Stage 6.",
                        feedback=f"Remove ungrounded precedent '{cited_p}' or restrict citations strictly to Stage 6 grounded precedent records.",
                    )
                )
            # 2. Verification of Low Confidence (< 0.70) without Manual Clearance
            elif c_low in low_confidence_cases:
                if not any(c_low in note.lower() for note in pro_obj.manual_review):
                    unretrieved_issues.append(
                        RoleArgumentVerificationIssue(
                            target=cited_p,
                            issue=f"Precedent '{cited_p}' has low retrieval confidence (< 0.70) and was not cleared by manual review.",
                            feedback=f"Do not rely on low-confidence precedent '{cited_p}' without explicit manual review clearance.",
                        )
                    )

        if unretrieved_issues:
            return RoleArgumentVerificationResult(
                status="RETRY",
                issues=unretrieved_issues,
                feedback="RoleArgumentObject failed zero-cost auditor grounding pre-check due to ungrounded precedent citations or low-confidence reliance.",
                verified_role_argument_object=None,
            )

        # Closed-Set Bail Condition Audit: Validate judge_order.conditions against
        # Section 438(2) CrPC / Section 482(2) BNSS canonical permissible categories
        condition_validator = BailConditionValidator()
        judge_conditions = rao_obj.judge_order.conditions or []
        _, flagged_conditions = condition_validator.validate_all(judge_conditions)
        condition_issues: List[RoleArgumentVerificationIssue] = []
        for flag in flagged_conditions:
            condition_issues.append(
                RoleArgumentVerificationIssue(
                    target="judge_order.conditions",
                    issue=flag,
                    feedback="Replace the impermissible bail condition with an authorized category under Section 438(2) CrPC / Section 482(2) BNSS.",
                )
            )

        if condition_issues:
            return RoleArgumentVerificationResult(
                status="RETRY",
                issues=condition_issues,
                feedback=f"JudgeOrder failed closed-set bail condition validation: {len(condition_issues)} impermissible conditions detected.",
                verified_role_argument_object=None,
            )

        cco_json_str = cco_obj.to_downstream_json()
        svo_json_str = svo_obj.to_downstream_json()
        bro_json_str = bro_obj.to_downstream_json()
        pro_json_str = pro_obj.to_downstream_json()
        rao_json_str = rao_obj.to_downstream_json()

        user_prompt = STAGE7_VERIFIER_USER_PROMPT_TEMPLATE.format(
            case_context_json=cco_json_str,
            statutory_object_json=svo_json_str,
            bail_object_json=bro_json_str,
            precedent_object_json=pro_json_str,
            role_argument_json=rao_json_str,
        )

        messages = [
            SystemMessage(content=STAGE7_VERIFIER_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]

        response = self.llm.invoke(messages)
        response_text = response.content if hasattr(response, "content") else str(response)

        extracted_dict = extract_json_from_text(response_text)

        v_res = RoleArgumentVerificationResult.model_validate(extracted_dict)
        if v_res.status == "VERIFIED":
            rao_obj.verification_status = "VERIFIED"
            v_res.verified_role_argument_object = rao_obj
        return v_res
