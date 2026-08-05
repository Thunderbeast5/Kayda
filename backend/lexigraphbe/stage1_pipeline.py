"""
Stage 1 Pipeline orchestrating QueryUnderstandingAgent and QueryVerificationAgent.
Transforms CaseContextObject into verified LegalQueryObject for Stage 2 retrieval.
Caps retries at 1 max for genuine judgment failures, falling back to manual_review flags.
"""

from typing import Any, Dict, Optional, Union
from .query_understanding_agent import QueryUnderstandingAgent
from .query_verifier_agent import QueryVerificationAgent
from .schemas import CaseContextObject, CaseProfile, LegalQueryObject, QueryVerificationResult


class Stage1Pipeline:
    """
    Complete Stage 1 pipeline for query understanding and legal decomposition.
    Executes CaseContextObject -> QueryUnderstandingAgent -> QueryVerificationAgent -> Reflection Retry Loop -> Verified LegalQueryObject.
    Caps retries at 1 max for genuine judgment failures, falling back to manual_review flags.
    """

    def __init__(
        self,
        query_agent: Optional[QueryUnderstandingAgent] = None,
        verifier_agent: Optional[QueryVerificationAgent] = None,
        max_retries: int = 1,
    ):
        self.query_agent = query_agent or QueryUnderstandingAgent()
        self.verifier_agent = verifier_agent or QueryVerificationAgent()
        self.max_retries = max_retries

    def run(
        self,
        case_context: Union[CaseContextObject, CaseProfile, Dict[str, Any], str],
    ) -> QueryVerificationResult:
        """
        Runs full Stage 1 pipeline on CaseContextObject.

        Args:
            case_context: CaseContextObject instance or equivalent JSON/dict from Stage 0.

        Returns:
            QueryVerificationResult containing final verified LegalQueryObject and audit details.
        """
        correction_feedback = None
        current_attempt = 0

        last_query_obj: Optional[LegalQueryObject] = None
        verification_result: Optional[QueryVerificationResult] = None

        while current_attempt <= self.max_retries:
            current_attempt += 1

            # Step 1: Query Decomposition
            last_query_obj = self.query_agent.run(
                case_context=case_context,
                correction_feedback=correction_feedback,
            )

            # Step 2: Query Verification Check
            verification_result = self.verifier_agent.verify(
                case_context=case_context,
                legal_query=last_query_obj,
            )

            if verification_result.status == "VERIFIED":
                verification_result.verified_query_object = last_query_obj
                return verification_result

            # Step 3: Prepare feedback for single reflection retry
            if current_attempt <= self.max_retries:
                feedback_parts = [f"Attempt {current_attempt} verification failed with issues:"]
                for issue in verification_result.issues:
                    feedback_parts.append(f"- Target '{issue.target}': {issue.issue} | Action: {issue.feedback}")
                if verification_result.feedback:
                    feedback_parts.append(f"Summary: {verification_result.feedback}")
                correction_feedback = "\n".join(feedback_parts)

        # Fallback Policy: If retries are exhausted, attach issues to manual_review and set flag_for_confirmation = True
        if last_query_obj:
            last_query_obj.flag_for_confirmation = True
            if verification_result and verification_result.issues:
                for issue in verification_result.issues:
                    flag_note = f"Unresolved verification issue ({issue.target}): {issue.issue}"
                    if flag_note not in last_query_obj.manual_review:
                        last_query_obj.manual_review.append(flag_note)

            if verification_result:
                verification_result.verified_query_object = last_query_obj
                verification_result.feedback += " (Exhausted retries -> Flagged for human review)."
                return verification_result

        return QueryVerificationResult(
            status="RETRY",
            issues=[],
            feedback="Pipeline execution completed without verification (Flagged for human review).",
            verified_query_object=last_query_obj,
        )
