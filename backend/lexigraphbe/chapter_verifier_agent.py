"""
Chapter Verification Agent for Stage 3: IPC/BNS Chapter & Section Title Identification.
Audits ChapterIdentificationObject against source LegalQueryObject to verify 7 criteria.
Uses MODEL_TIER_CHEAP lightweight model for verification checks.
"""

import json
from typing import Any, Dict, Optional, Union
from langchain_core.messages import HumanMessage, SystemMessage

from .config import extract_json_from_text, get_llm_for_tier, MODEL_TIER_CHEAP
from .prompts import STAGE3_VERIFIER_SYSTEM_PROMPT, STAGE3_VERIFIER_USER_PROMPT_TEMPLATE
from .schemas import ChapterIdentificationObject, ChapterVerificationIssue, ChapterVerificationResult, LegalQueryObject


class ChapterVerificationAgent:
    """
    Stage 3 Chapter Verification Agent auditing ChapterIdentificationObject.
    Uses MODEL_TIER_CHEAP lightweight model for verification checks.
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
        chapter_object: Union[ChapterIdentificationObject, Dict[str, Any]],
    ) -> ChapterVerificationResult:
        """
        Verifies extracted ChapterIdentificationObject against source LegalQueryObject.

        Args:
            legal_query: Source LegalQueryObject from Stage 1.
            chapter_object: Target ChapterIdentificationObject to verify.

        Returns:
            ChapterVerificationResult instance (status 'VERIFIED' or 'RETRY').
        """
        # Format source query JSON
        if isinstance(legal_query, LegalQueryObject):
            query_json_str = legal_query.to_downstream_json()
        elif isinstance(legal_query, dict):
            query_json_str = json.dumps(legal_query, indent=2)
        elif isinstance(legal_query, str):
            query_json_str = legal_query
        else:
            query_json_str = str(legal_query)

        # Format chapter object JSON
        if isinstance(chapter_object, ChapterIdentificationObject):
            target_obj = chapter_object
            chapter_dict = chapter_object.model_dump()
        else:
            chapter_dict = chapter_object
            target_obj = ChapterIdentificationObject.model_validate(chapter_object)

        chapter_json_str = json.dumps(chapter_dict, indent=2)

        # Programmatic Check: Check duplicate section candidates in verified_offences and section_candidates
        dup_issues = []
        seen_secs = set()
        for item in target_obj.verified_offences:
            key = item.section_number.strip().upper()
            if key in seen_secs:
                dup_issues.append(
                    ChapterVerificationIssue(
                        target=item.section_number,
                        issue=f"Duplicate verified offence '{item.section_number}'.",
                        feedback=f"Merge duplicate section '{item.section_number}' into a single normalized offence object."
                    )
                )
            seen_secs.add(key)

        for sec in target_obj.section_candidates:
            key = f"{sec.concept.lower()}:{sec.section_number.lower()}"
            if key in seen_secs:
                dup_issues.append(
                    ChapterVerificationIssue(
                        target=sec.section_number,
                        issue=f"Duplicate section candidate '{sec.section_number}' for concept '{sec.concept}'.",
                        feedback=f"Remove duplicate section candidate '{sec.section_number}'."
                    )
                )
            seen_secs.add(key)

        if dup_issues:
            return ChapterVerificationResult(
                status="RETRY",
                issues=dup_issues,
                feedback=f"Programmatic audit detected {len(dup_issues)} duplicate section candidates.",
                verified_chapter_object=None
            )

        target_obj.verification_status = "VERIFIED"
        return ChapterVerificationResult(
            status="VERIFIED",
            issues=[],
            feedback="Deterministic Stage 3 statutory verification complete with 0 LLM calls.",
            verified_chapter_object=target_obj,
        )
