"""
Stage 2 Sub-Query Mapping Verifier Agent auditing Stage2BatchedMappingResponse.
Ensures every sub-query is properly mapped to candidate statutory chapters and sections.
"""

import json
from typing import Any, Dict, Optional, Union
from langchain_core.messages import HumanMessage, SystemMessage

from .config import extract_json_from_text, get_llm_for_tier, MODEL_TIER_CHEAP
from .prompts import STAGE2_VERIFIER_SYSTEM_PROMPT, STAGE2_VERIFIER_USER_PROMPT_TEMPLATE
from .batch_utils import Stage2BatchedMappingResponse
from .schemas import LegalQueryObject, Stage2VerificationIssue, Stage2VerificationResult


class Stage2MappingVerifierAgent:
    """
    Stage 2 Verifier Agent inspecting Stage2BatchedMappingResponse.
    Uses MODEL_TIER_CHEAP lightweight model for mapping verification.
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
        legal_query: Union[LegalQueryObject, Dict[str, Any], str],
        mapping_response: Union[Stage2BatchedMappingResponse, Dict[str, Any]],
    ) -> Stage2VerificationResult:
        """
        Audits Stage2BatchedMappingResponse against source LegalQueryObject.

        Returns:
            Stage2VerificationResult instance (status 'VERIFIED' or 'RETRY').
        """
        if isinstance(legal_query, LegalQueryObject):
            query_json_str = legal_query.to_downstream_json()
        elif isinstance(legal_query, dict):
            query_json_str = json.dumps(legal_query, indent=2)
        else:
            query_json_str = str(legal_query)

        if isinstance(mapping_response, Stage2BatchedMappingResponse):
            target_resp = mapping_response
            resp_dict = mapping_response.model_dump()
        else:
            target_resp = Stage2BatchedMappingResponse.model_validate(mapping_response)
            resp_dict = mapping_response

        resp_json_str = json.dumps(resp_dict, indent=2)

        user_prompt = STAGE2_VERIFIER_USER_PROMPT_TEMPLATE.format(
            legal_query_json=query_json_str,
            mapping_response_json=resp_json_str,
        )

        messages = [
            SystemMessage(content=STAGE2_VERIFIER_SYSTEM_PROMPT),
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
                issues.append(Stage2VerificationIssue.model_validate(issue_item))
            elif isinstance(issue_item, str):
                issues.append(Stage2VerificationIssue(target="general", issue=issue_item, feedback=issue_item))

        feedback_summary = parsed_dict.get("feedback", "Stage 2 sub-query mapping audit complete.")

        return Stage2VerificationResult(
            status=status,
            issues=issues,
            feedback=feedback_summary,
            batched_mapping_response=target_resp if status == "VERIFIED" else None,
        )
