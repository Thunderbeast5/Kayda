"""
Stage 6 Pipeline orchestrating PrecedentRetrievalAgent and PrecedentVerificationAuditor.
Transforms Stage 0 CaseContextObject + Stage 1 LegalQueryObject + Stage 4 StatutoryVerificationObject + Stage 5 BailReasoningObject into verified PrecedentRetrievalObject.
Caps retries at 1 max for genuine judgment failures, falling back to manual_review flags.
"""

from typing import Any, Dict, Optional, Union
from .precedent_retrieval_agent import PrecedentRetrievalAgent
from .precedent_verifier_agent import PrecedentVerificationAuditor
from .schemas import BailReasoningObject, CaseContextObject, LegalQueryObject, PrecedentRetrievalObject, PrecedentVerificationResult, StatutoryVerificationObject


class Stage6Pipeline:
    """
    Complete Stage 6 pipeline for Judicial Precedent Retrieval Engine.
    Executes Inputs -> PrecedentRetrievalAgent -> PrecedentVerificationAuditor -> Reflection Retry Loop -> Verified PrecedentRetrievalObject.
    Caps retries at 1 max for genuine judgment failures, falling back to manual_review flags.
    """

    def __init__(
        self,
        retrieval_agent: Optional[PrecedentRetrievalAgent] = None,
        verifier_agent: Optional[PrecedentVerificationAuditor] = None,
        max_retries: int = 1,
    ):
        self.retrieval_agent = retrieval_agent or PrecedentRetrievalAgent()
        self.verifier_agent = verifier_agent or PrecedentVerificationAuditor()
        self.max_retries = max_retries

    def run(
        self,
        case_context: Union[CaseContextObject, Dict[str, Any], str],
        legal_query: Union[LegalQueryObject, Dict[str, Any], str],
        statutory_object: Union[StatutoryVerificationObject, Dict[str, Any], str],
        bail_object: Union[BailReasoningObject, Dict[str, Any], str],
    ) -> PrecedentVerificationResult:
        """
        Runs full Stage 6 pipeline on CaseContextObject, LegalQueryObject, StatutoryVerificationObject, and BailReasoningObject.

        Returns:
            PrecedentVerificationResult containing final verified PrecedentRetrievalObject and audit details.
        """
        correction_feedback = None
        current_attempt = 0

        last_prec_obj: Optional[PrecedentRetrievalObject] = None
        verification_result: Optional[PrecedentVerificationResult] = None

        while current_attempt <= self.max_retries:
            current_attempt += 1

            # Step 1: Precedent Retrieval
            last_prec_obj = self.retrieval_agent.run(
                case_context=case_context,
                legal_query=legal_query,
                statutory_object=statutory_object,
                bail_object=bail_object,
                correction_feedback=correction_feedback,
            )

            # Step 2: Verification Audit Check
            verification_result = self.verifier_agent.verify(
                case_context=case_context,
                statutory_object=statutory_object,
                bail_object=bail_object,
                precedent_object=last_prec_obj,
            )

            if verification_result.status == "VERIFIED":
                verification_result.verified_precedent_object = last_prec_obj
                return verification_result

            # Step 3: Prepare feedback for single reflection retry
            if current_attempt <= self.max_retries:
                feedback_parts = [f"Attempt {current_attempt} verification failed with audit issues:"]
                for issue in verification_result.issues:
                    feedback_parts.append(f"- Target '{issue.target}': {issue.issue} | Action: {issue.feedback}")
                if verification_result.feedback:
                    feedback_parts.append(f"Summary: {verification_result.feedback}")
                correction_feedback = "\n".join(feedback_parts)

        # Fallback Policy: If retries are exhausted, attach issues to manual_review
        if last_prec_obj:
            if verification_result and verification_result.issues:
                for issue in verification_result.issues:
                    flag_note = f"Unresolved precedent retrieval audit issue ({issue.target}): {issue.issue}"
                    if flag_note not in last_prec_obj.manual_review:
                        last_prec_obj.manual_review.append(flag_note)

            if verification_result:
                verification_result.verified_precedent_object = last_prec_obj
                verification_result.feedback += " (Exhausted retries -> Flagged for human review)."
                return verification_result

        return PrecedentVerificationResult(
            status="RETRY",
            issues=[],
            feedback="Pipeline execution completed without verification (Flagged for human review).",
            verified_precedent_object=last_prec_obj,
        )
