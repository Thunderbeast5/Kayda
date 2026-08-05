"""
Case Intake Verifier Agent for Stage 0: Case Intake & Context Initialization.
Verifies CaseProfile against source text to ensure zero hallucinations and fact grounding.
Uses lightweight CHEAP tier model for narrow verification checks.
"""

import json
from typing import Any, Dict, Optional, Union
from langchain_core.messages import HumanMessage, SystemMessage

from .config import extract_json_from_text, get_llm_for_tier, MODEL_TIER_CHEAP
from .prompts import STAGE0_VERIFIER_SYSTEM_PROMPT, STAGE0_VERIFIER_USER_PROMPT_TEMPLATE
from .schemas import CaseProfile, VerificationIssue, VerificationResult


class CaseIntakeVerifierAgent:
    """
    Verifier Agent auditing CaseProfile against raw case document text.
    Uses CHEAP tier model for verification checks.
    """

    def __init__(self, llm: Optional[Any] = None):
        self._llm = llm

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm_for_tier(tier=MODEL_TIER_CHEAP, temperature=0.0)
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
        response_text = response.content if hasattr(response, "content") else str(response)

        parsed_dict = extract_json_from_text(response_text)

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
