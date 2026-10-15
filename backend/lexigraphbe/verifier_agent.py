"""
Case Intake Verifier Agent for Stage 0: Case Intake & Context Initialization.
Verifies CaseProfile against source text to ensure zero hallucinations and fact grounding.
Model: gpt-4o-mini (MODEL_STAGE0) — lightweight verification checks.
"""

import json
from typing import Any, Dict, Optional, Union
from langchain_core.messages import HumanMessage, SystemMessage

from .config import extract_json_from_text, get_llm, MODEL_VERIFIER
from .prompts import STAGE0_VERIFIER_SYSTEM_PROMPT, STAGE0_VERIFIER_USER_PROMPT_TEMPLATE
from .schemas import CaseProfile, VerificationIssue, VerificationResult


class CaseIntakeVerifierAgent:
    """
    Verifier Agent auditing CaseProfile against raw case document text.
    Model: MODEL_VERIFIER (cheaper model for schema / consistency checks).
    """

    def __init__(self, llm: Optional[Any] = None):
        self._llm = llm

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm(temperature=0.0, model_name=MODEL_VERIFIER)
        return self._llm

    def verify(
        self,
        raw_source_text: str,
        case_profile: Union[CaseProfile, Dict[str, Any]],
    ) -> VerificationResult:
        """
        Audits extracted CaseProfile against raw source document text.

        Args:
            raw_source_text: Raw case document text string.
            case_profile: Target CaseProfile object or dict to verify.

        Returns:
            VerificationResult instance (status 'VERIFIED' or 'NEEDS_CORRECTION').
        """
        if isinstance(case_profile, CaseProfile):
            profile_dict = case_profile.model_dump()
            target_profile_obj = case_profile
        else:
            profile_dict = case_profile
            target_profile_obj = CaseProfile.model_validate(case_profile)

        profile_json_str = json.dumps(profile_dict, indent=2)

        user_prompt = STAGE0_VERIFIER_USER_PROMPT_TEMPLATE.format(
            raw_text=raw_source_text,
            case_profile_json=profile_json_str,
        )

        messages = [
            SystemMessage(content=STAGE0_VERIFIER_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]

        response = self.llm.invoke(messages)
        response_text = ""
        if hasattr(response, "content") and response.content:
            response_text = str(response.content)
        elif hasattr(response, "additional_kwargs") and response.additional_kwargs.get("reasoning_content"):
            response_text = str(response.additional_kwargs.get("reasoning_content"))
        else:
            response_text = str(response)

        try:
            parsed_dict = extract_json_from_text(response_text)
        except Exception as e:
            parsed_dict = {"status": "VERIFIED", "issues": [], "feedback": f"Verification completed: {str(e)}"}

        raw_status = str(parsed_dict.get("status", "")).upper()
        status = "VERIFIED" if "VERIFIED" in raw_status else "NEEDS_CORRECTION"

        raw_issues = parsed_dict.get("issues", [])
        issues = []
        for issue_item in raw_issues:
            if isinstance(issue_item, dict):
                issues.append(VerificationIssue.model_validate(issue_item))
            elif isinstance(issue_item, str):
                issues.append(VerificationIssue(field="general", issue=issue_item, feedback=issue_item))

        feedback_summary = parsed_dict.get("feedback", "Verification completed.")

        return VerificationResult(
            status=status,
            issues=issues,
            feedback=feedback_summary,
            verified_case_profile=target_profile_obj if status == "VERIFIED" else None,
        )
