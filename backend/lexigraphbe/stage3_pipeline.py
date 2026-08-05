"""
Stage 3 Pipeline orchestrating ChapterIdentificationAgent and ChapterVerificationAgent.
Transforms Stage 1 LegalQueryObject into verified ChapterIdentificationObject.
Caps retries at 1 max for genuine judgment failures, falling back to manual_review flags.
"""

from typing import Any, Dict, Optional, Union
from .chapter_identification_agent import ChapterIdentificationAgent
from .chapter_verifier_agent import ChapterVerificationAgent
from .schemas import ChapterIdentificationObject, ChapterVerificationResult, LegalQueryObject


class Stage3Pipeline:
    """
    Complete Stage 3 pipeline for IPC/BNS Chapter & Section Title Identification.
    Executes LegalQueryObject -> ChapterIdentificationAgent -> ChapterVerificationAgent -> Reflection Retry Loop -> Verified ChapterIdentificationObject.
    Caps retries at 1 max for genuine judgment failures, falling back to manual_review flags.
    """

    def __init__(
        self,
        chapter_agent: Optional[ChapterIdentificationAgent] = None,
        verifier_agent: Optional[ChapterVerificationAgent] = None,
        max_retries: int = 1,
    ):
        self.chapter_agent = chapter_agent or ChapterIdentificationAgent()
        self.verifier_agent = verifier_agent or ChapterVerificationAgent()
        self.max_retries = max_retries

    def run(
        self,
        legal_query: Union[LegalQueryObject, Dict[str, Any], str],
        stage2_mapping: Optional[Any] = None,
    ) -> ChapterVerificationResult:
        """
        Runs full Stage 3 pipeline on LegalQueryObject and Stage 2 verified mapping.

        Args:
            legal_query: LegalQueryObject instance or equivalent JSON/dict from Stage 1.
            stage2_mapping: Stage2BatchedMappingResponse instance or JSON/dict from Stage 2.

        Returns:
            ChapterVerificationResult containing final verified Schema v3.0 ChapterIdentificationObject.
        """
        correction_feedback = None
        current_attempt = 0

        last_chapter_obj: Optional[ChapterIdentificationObject] = None
        verification_result: Optional[ChapterVerificationResult] = None

        while current_attempt <= self.max_retries:
            current_attempt += 1

            # Step 1: Statutory Verification & Normalization
            last_chapter_obj = self.chapter_agent.run(
                legal_query=legal_query,
                stage2_mapping=stage2_mapping,
                correction_feedback=correction_feedback,
            )

            # Step 2: Verification Check
            verification_result = self.verifier_agent.verify(
                legal_query=legal_query,
                chapter_object=last_chapter_obj,
            )

            if verification_result.status == "VERIFIED":
                verification_result.verified_chapter_object = last_chapter_obj
                return verification_result

            # Step 3: Prepare feedback for single reflection retry
            if current_attempt <= self.max_retries:
                feedback_parts = [f"Attempt {current_attempt} verification failed with issues:"]
                for issue in verification_result.issues:
                    feedback_parts.append(f"- Target '{issue.target}': {issue.issue} | Action: {issue.feedback}")
                if verification_result.feedback:
                    feedback_parts.append(f"Summary: {verification_result.feedback}")
                correction_feedback = "\n".join(feedback_parts)

        # Fallback Policy: If retries are exhausted, attach issues to manual_review
        if last_chapter_obj:
            if verification_result and verification_result.issues:
                for issue in verification_result.issues:
                    flag_note = f"Unresolved chapter verification issue ({issue.target}): {issue.issue}"
                    if flag_note not in last_chapter_obj.manual_review:
                        last_chapter_obj.manual_review.append(flag_note)

            if verification_result:
                verification_result.verified_chapter_object = last_chapter_obj
                verification_result.feedback += " (Exhausted retries -> Flagged for human review)."
                return verification_result

        return ChapterVerificationResult(
            status="RETRY",
            issues=[],
            feedback="Pipeline execution completed without verification (Flagged for human review).",
            verified_chapter_object=last_chapter_obj,
        )
