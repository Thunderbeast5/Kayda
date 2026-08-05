"""
Bail Reasoning Verification Agent for Stage 5: Anticipatory Bail Reasoning Engine.
Audits BailReasoningObject against source facts and statutory verification outputs to verify 7 criteria.
Uses MODEL_TIER_REASONING flagship model (equal to or stronger than reasoning agent) for audit checks.
Includes programmatic closed-set bail condition validation against Section 438(2) CrPC / Section 482(2) BNSS.
"""

import json
from typing import Any, Dict, Optional, Union
from langchain_core.messages import HumanMessage, SystemMessage

from .config import extract_json_from_text, get_llm_for_tier, MODEL_TIER_REASONING
from .prompts import STAGE5_VERIFIER_SYSTEM_PROMPT, STAGE5_VERIFIER_USER_PROMPT_TEMPLATE
from .schemas import BailReasoningObject, BailVerificationIssue, BailVerificationResult, CaseContextObject, StatutoryVerificationObject
from .bail_condition_validator import BailConditionValidator


class BailReasoningVerifierAgent:
    """
    Stage 5 Bail Reasoning Verification Agent auditing BailReasoningObject.
    Uses MODEL_TIER_REASONING flagship model (equal to or stronger than reasoning agent) for audit checks.
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
        bail_object: Union[BailReasoningObject, Dict[str, Any]],
    ) -> BailVerificationResult:
        """
        Audits BailReasoningObject against source CaseContextObject and StatutoryVerificationObject.

        Args:
            case_context: Verified CaseContextObject from Stage 0.
            statutory_object: Verified StatutoryVerificationObject from Stage 4.
            bail_object: Target BailReasoningObject to verify.

        Returns:
            BailVerificationResult instance (status 'VERIFIED' or 'RETRY').
        """
        # Format JSONs
        if isinstance(case_context, CaseContextObject):
            cco_json_str = case_context.model_dump_json(indent=2)
        elif isinstance(case_context, dict):
            cco_json_str = json.dumps(case_context, indent=2)
        else:
            cco_json_str = str(case_context)

        if isinstance(statutory_object, StatutoryVerificationObject):
            svo_json_str = statutory_object.to_downstream_json()
        elif isinstance(statutory_object, dict):
            svo_json_str = json.dumps(statutory_object, indent=2)
        else:
            svo_json_str = str(statutory_object)

        if isinstance(bail_object, BailReasoningObject):
            target_obj = bail_object
            bail_json_str = bail_object.to_downstream_json()
        else:
            target_obj = BailReasoningObject.model_validate(bail_object)
            bail_json_str = json.dumps(bail_object, indent=2)

        # ----------------------------------------------------------------------
        # PROGRAMMATIC CLOSED-SET BAIL CONDITION AUDIT (Deterministic & 0-Cost)
        # Validates every recommended bail condition against Section 438(2) CrPC / Section 482(2) BNSS
        # ----------------------------------------------------------------------
        condition_issues = []
        validator = BailConditionValidator()
        conditions_to_check = getattr(target_obj.overall_recommendation, "conditions", None) or []
        if conditions_to_check:
            _, flagged = validator.validate_all(conditions_to_check)
            for flag in flagged:
                condition_issues.append(
                    BailVerificationIssue(
                        target="recommended_conditions",
                        issue=flag,
                        feedback="Remove or replace the impermissible bail condition with an authorized category under Section 438(2) CrPC / Section 482(2) BNSS."
                    )
                )

        if condition_issues:
            return BailVerificationResult(
                status="RETRY",
                issues=condition_issues,
                feedback=f"Bail reasoning failed closed-set condition validation: {len(condition_issues)} impermissible bail conditions detected.",
                verified_bail_object=None,
            )

        user_prompt = STAGE5_VERIFIER_USER_PROMPT_TEMPLATE.format(
            case_context_json=cco_json_str,
            statutory_object_json=svo_json_str,
            bail_object_json=bail_json_str,
        )

        messages = [
            SystemMessage(content=STAGE5_VERIFIER_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]

        response = self.llm.invoke(messages)
        response_text = response.content if hasattr(response, "content") else str(response)

        parsed_dict = extract_json_from_text(response_text)

        raw_status = str(parsed_dict.get("status", "")).upper()
        status = "VERIFIED" if "VERIFIED" in raw_status else "RETRY"

        raw_issues = parsed_dict.get("issues", [])
        issues = []
        for issue_item in raw_issues:
            if isinstance(issue_item, dict):
                issues.append(BailVerificationIssue.model_validate(issue_item))
            elif isinstance(issue_item, str):
                issues.append(BailVerificationIssue(target="general", issue=issue_item, feedback=issue_item))

        feedback_summary = parsed_dict.get("feedback", "Bail reasoning verification complete.")

        if status == "VERIFIED":
            target_obj.verification_status = "VERIFIED"

        return BailVerificationResult(
            status=status,
            issues=issues,
            feedback=feedback_summary,
            verified_bail_object=target_obj if status == "VERIFIED" else None,
        )
