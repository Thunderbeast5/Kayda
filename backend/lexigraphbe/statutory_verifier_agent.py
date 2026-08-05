"""
Statutory Verification Auditor for Stage 4: Full Statutory Verification & Ingredient Matching.
Audits StatutoryVerificationObject against source facts and statutory context to verify 7 criteria.
Uses MODEL_TIER_REASONING flagship model (equal to or stronger than reasoning agent) for audit checks.
Includes programmatic pre-checks for instant deterministic verification.
"""

import json
from typing import Any, Dict, Optional, Union
from langchain_core.messages import HumanMessage, SystemMessage

from .config import extract_json_from_text, get_llm_for_tier, MODEL_TIER_REASONING
from .prompts import STAGE4_VERIFIER_SYSTEM_PROMPT, STAGE4_VERIFIER_USER_PROMPT_TEMPLATE
from .schemas import ChapterIdentificationObject, LegalQueryObject, StatutoryVerificationIssue, StatutoryVerificationObject, StatutoryVerificationResult


class StatutoryVerificationAuditor:
    """
    Stage 4 Statutory Verification Auditor inspecting StatutoryVerificationObject.
    Uses MODEL_TIER_REASONING flagship model (equal to or stronger than reasoning agent) for audit checks.
    Includes programmatic pre-checks for instant deterministic verification.
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
        legal_query: Union[LegalQueryObject, Dict[str, Any], str],
        chapter_object: Union[ChapterIdentificationObject, Dict[str, Any], str],
        statutory_object: Union[StatutoryVerificationObject, Dict[str, Any]],
    ) -> StatutoryVerificationResult:
        """
        Audits StatutoryVerificationObject against source LegalQueryObject and ChapterIdentificationObject.

        Args:
            legal_query: Verified LegalQueryObject from Stage 1.
            chapter_object: Verified ChapterIdentificationObject from Stage 3.
            statutory_object: Target StatutoryVerificationObject to verify.

        Returns:
            StatutoryVerificationResult instance (status 'VERIFIED' or 'RETRY').
        """
        # Parse inputs
        if isinstance(legal_query, LegalQueryObject):
            query_json_str = legal_query.to_downstream_json()
        elif isinstance(legal_query, dict):
            query_json_str = json.dumps(legal_query, indent=2)
        else:
            query_json_str = str(legal_query)

        if isinstance(chapter_object, ChapterIdentificationObject):
            target_chap = chapter_object
            chap_json_str = chapter_object.to_downstream_json()
        else:
            target_chap = ChapterIdentificationObject.model_validate(chapter_object)
            chap_json_str = json.dumps(chapter_object, indent=2)

        if isinstance(statutory_object, StatutoryVerificationObject):
            target_stat = statutory_object
            stat_dict = statutory_object.model_dump()
        else:
            stat_dict = statutory_object
            target_stat = StatutoryVerificationObject.model_validate(statutory_object)

        stat_json_str = json.dumps(stat_dict, indent=2)

        # ----------------------------------------------------------------------
        # PROGRAMMATIC AUDIT PRE-CHECKS (Deterministic & 0-Cost)
        # ----------------------------------------------------------------------
        programmatic_issues = []

        # 1. Section Number Matching Check against Stage 3 Candidates
        candidate_sec_numbers = {s.section_number.strip().lower() for s in target_chap.section_candidates}
        for v_sec in target_stat.verified_sections:
            clean_v_num = v_sec.section_number.strip().lower()
            if candidate_sec_numbers and clean_v_num not in candidate_sec_numbers:
                programmatic_issues.append(
                    StatutoryVerificationIssue(
                        target=v_sec.section_number,
                        issue=f"Verified section '{v_sec.section_number}' was NOT in Stage 3 candidate shortlist ({candidate_sec_numbers}).",
                        feedback=f"Remove unapproved section '{v_sec.section_number}' from statutory verification object."
                    )
                )

            # 2. Check for empty ingredient reasons or missing ingredient evaluations
            for ing in v_sec.ingredients:
                if not ing.reason or not ing.reason.strip():
                    programmatic_issues.append(
                        StatutoryVerificationIssue(
                            target=f"{v_sec.section_number}:{ing.ingredient}",
                            issue=f"Ingredient '{ing.ingredient}' for Section {v_sec.section_number} lacks factual reasoning.",
                            feedback=f"Provide explicit factual reasoning for ingredient '{ing.ingredient}'."
                        )
                    )

        if programmatic_issues:
            return StatutoryVerificationResult(
                status="RETRY",
                issues=programmatic_issues,
                feedback=f"Programmatic audit detected {len(programmatic_issues)} verification issues.",
                verified_statutory_object=None
            )

        # ----------------------------------------------------------------------
        # REASONING AUDITOR CHECK (MODEL_TIER_REASONING)
        # ----------------------------------------------------------------------
        user_prompt = STAGE4_VERIFIER_USER_PROMPT_TEMPLATE.format(
            legal_query_json=query_json_str,
            chapter_object_json=chap_json_str,
            statutory_object_json=stat_json_str,
        )

        messages = [
            SystemMessage(content=STAGE4_VERIFIER_SYSTEM_PROMPT),
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
                issues.append(StatutoryVerificationIssue.model_validate(issue_item))
            elif isinstance(issue_item, str):
                issues.append(StatutoryVerificationIssue(target="general", issue=issue_item, feedback=issue_item))

        feedback_summary = parsed_dict.get("feedback", "Statutory verification audit complete.")

        if status == "VERIFIED":
            target_stat.verification_status = "VERIFIED"

        return StatutoryVerificationResult(
            status=status,
            issues=issues,
            feedback=feedback_summary,
            verified_statutory_object=target_stat if status == "VERIFIED" else None,
        )
