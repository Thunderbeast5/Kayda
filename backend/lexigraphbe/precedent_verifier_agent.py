"""
Precedent Verification Auditor for Stage 6: Judicial Precedent Retrieval Engine.
Audits PrecedentRetrievalObject against source case facts, statutory outputs, and bail evaluations to verify 7 criteria.
Model: gpt-4o-mini (MODEL_STAGE6) — inherits primary stage model.
Includes programmatic pre-checks for instant deterministic verification.
"""

import json
from typing import Any, Dict, Optional, Union
from langchain_core.messages import HumanMessage, SystemMessage

from .config import extract_json_from_text, get_llm, MODEL_STAGE6
from .prompts import STAGE6_VERIFIER_SYSTEM_PROMPT, STAGE6_VERIFIER_USER_PROMPT_TEMPLATE
from .schemas import BailReasoningObject, CaseContextObject, PrecedentRetrievalObject, PrecedentVerificationIssue, PrecedentVerificationResult, StatutoryVerificationObject


class PrecedentVerificationAuditor:
    """
    Stage 6 Precedent Verification Auditor inspecting PrecedentRetrievalObject.
    Model: gpt-4o-mini (MODEL_STAGE6) — inherits primary stage model.
    Includes programmatic pre-checks for instant deterministic verification.
    """

    def __init__(self, llm: Optional[Any] = None):
        self._llm = llm

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm(temperature=0.0, model_name=MODEL_STAGE6)
        return self._llm

    def verify(
        self,
        case_context: Union[CaseContextObject, Dict[str, Any], str],
        statutory_object: Union[StatutoryVerificationObject, Dict[str, Any], str],
        bail_object: Union[BailReasoningObject, Dict[str, Any], str],
        precedent_object: Union[PrecedentRetrievalObject, Dict[str, Any]],
    ) -> PrecedentVerificationResult:
        """
        Audits PrecedentRetrievalObject against source CaseContextObject, StatutoryVerificationObject, and BailReasoningObject.

        Args:
            case_context: Verified CaseContextObject from Stage 0.
            statutory_object: Verified StatutoryVerificationObject from Stage 4.
            bail_object: Verified BailReasoningObject from Stage 5.
            precedent_object: Target PrecedentRetrievalObject to verify.

        Returns:
            PrecedentVerificationResult instance (status 'VERIFIED' or 'RETRY').
        """
        # Format JSONs
        if isinstance(case_context, CaseContextObject):
            cco_json_str = case_context.to_downstream_json()
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
            bro_json_str = bail_object.to_downstream_json()
        elif isinstance(bail_object, dict):
            bro_json_str = json.dumps(bail_object, indent=2)
        else:
            bro_json_str = str(bail_object)

        if isinstance(precedent_object, PrecedentRetrievalObject):
            target_obj = precedent_object
            prec_dict = precedent_object.model_dump()
        else:
            target_obj = PrecedentRetrievalObject.model_validate(precedent_object)
            prec_dict = precedent_object

        prec_json_str = json.dumps(prec_dict, indent=2)

        # ----------------------------------------------------------------------
        # PROGRAMMATIC AUDIT PRE-CHECKS (Deterministic & 0-Cost)
        # ----------------------------------------------------------------------
        programmatic_issues = []

        # 1. Verification of Non-Empty Ratio Decidendi and Citations
        for p in target_obj.precedents:
            if not p.ratio_decidendi or not p.ratio_decidendi.strip():
                programmatic_issues.append(
                    PrecedentVerificationIssue(
                        target=p.case_name,
                        issue=f"Precedent '{p.case_name}' lacks ratio decidendi legal principle.",
                        feedback=f"Provide binding ratio decidendi text for '{p.case_name}'."
                    )
                )
            if not p.citation or not p.citation.strip():
                programmatic_issues.append(
                    PrecedentVerificationIssue(
                        target=p.case_name,
                        issue=f"Precedent '{p.case_name}' lacks official legal citation.",
                        feedback=f"Provide official legal citation for '{p.case_name}'."
                    )
                )

        if programmatic_issues:
            return PrecedentVerificationResult(
                status="RETRY",
                issues=programmatic_issues,
                feedback=f"Programmatic audit detected {len(programmatic_issues)} verification issues.",
                verified_precedent_object=None
            )

        # ----------------------------------------------------------------------
        # REASONING AUDITOR CHECK (MODEL_TIER_REASONING)
        # ----------------------------------------------------------------------
        user_prompt = STAGE6_VERIFIER_USER_PROMPT_TEMPLATE.format(
            case_context_json=cco_json_str,
            statutory_object_json=svo_json_str,
            bail_object_json=bro_json_str,
            precedent_object_json=prec_json_str,
        )

        messages = [
            SystemMessage(content=STAGE6_VERIFIER_SYSTEM_PROMPT),
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
                issues.append(PrecedentVerificationIssue.model_validate(issue_item))
            elif isinstance(issue_item, str):
                issues.append(PrecedentVerificationIssue(target="general", issue=issue_item, feedback=issue_item))

        feedback_summary = parsed_dict.get("feedback", "Precedent verification audit complete.")

        if status == "VERIFIED":
            target_obj.verification_status = "VERIFIED"

        return PrecedentVerificationResult(
            status=status,
            issues=issues,
            feedback=feedback_summary,
            verified_precedent_object=target_obj if status == "VERIFIED" else None,
        )
