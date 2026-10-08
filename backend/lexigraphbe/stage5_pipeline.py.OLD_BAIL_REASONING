"""
Stage 5 Pipeline orchestrating BailReasoningAgent and BailReasoningVerifierAgent.
Transforms Stage 0 CaseContextObject + Stage 1 LegalQueryObject + Stage 4 StatutoryVerificationObject into verified BailReasoningObject.
Caps retries at 1 max for genuine judgment failures, falling back to manual_review flags.
"""

from typing import Any, Dict, Optional, Union
from .bail_reasoning_agent import BailReasoningAgent
from .bail_verifier_agent import BailReasoningVerifierAgent
from .schemas import BailReasoningObject, BailVerificationResult, CaseContextObject, LegalQueryObject, StatutoryVerificationObject


class Stage5Pipeline:
    """
    Complete Stage 5 pipeline for Anticipatory Bail Reasoning Engine.
    Executes Inputs -> BailReasoningAgent -> BailReasoningVerifierAgent -> Reflection Retry Loop -> Verified BailReasoningObject.
    Caps retries at 1 max for genuine judgment failures, falling back to manual_review flags.
    """

    def __init__(
        self,
        reasoning_agent: Optional[BailReasoningAgent] = None,
        verifier_agent: Optional[BailReasoningVerifierAgent] = None,
        max_retries: int = 1,
    ):
        self.reasoning_agent = reasoning_agent or BailReasoningAgent()
        self.verifier_agent = verifier_agent or BailReasoningVerifierAgent()
        self.max_retries = max_retries

    def run(
        self,
        case_context: Union[CaseContextObject, Dict[str, Any], str],
        legal_query: Union[LegalQueryObject, Dict[str, Any], str],
        statutory_object: Union[StatutoryVerificationObject, Dict[str, Any], str],
    ) -> BailVerificationResult:
        """
        Runs full Stage 5 pipeline on CaseContextObject, LegalQueryObject, and StatutoryVerificationObject.

        Args:
            case_context: Verified CaseContextObject from Stage 0.
            legal_query: Verified LegalQueryObject from Stage 1.
            statutory_object: Verified StatutoryVerificationObject from Stage 4.

        Returns:
            BailVerificationResult containing final verified BailReasoningObject and audit details.
        """
        correction_feedback = None
        current_attempt = 0

        last_bail_obj: Optional[BailReasoningObject] = None
        verification_result: Optional[BailVerificationResult] = None

        while current_attempt <= self.max_retries:
            current_attempt += 1

            # Step 1: Bail Reasoning Evaluation
            last_bail_obj = self.reasoning_agent.run(
                case_context=case_context,
                legal_query=legal_query,
                statutory_object=statutory_object,
                correction_feedback=correction_feedback,
            )

            # Step 2: Verification Audit Check
            verification_result = self.verifier_agent.verify(
                case_context=case_context,
                statutory_object=statutory_object,
                bail_object=last_bail_obj,
            )

            if verification_result.status == "VERIFIED":
                verification_result.verified_bail_object = last_bail_obj
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
        if last_bail_obj:
            if verification_result and verification_result.issues:
                for issue in verification_result.issues:
                    flag_note = f"Unresolved bail reasoning audit issue ({issue.target}): {issue.issue}"
                    if flag_note not in last_bail_obj.manual_review:
                        last_bail_obj.manual_review.append(flag_note)

            if verification_result:
                verification_result.verified_bail_object = last_bail_obj
                verification_result.feedback += " (Exhausted retries -> Flagged for human review)."
                return verification_result

        return BailVerificationResult(
            status="RETRY",
            issues=[],
            feedback="Pipeline execution completed without verification (Flagged for human review).",
            verified_bail_object=last_bail_obj,
        )
