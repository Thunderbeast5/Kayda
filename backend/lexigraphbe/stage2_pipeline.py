"""
Stage 2 Pipeline orchestrating Stage2SubQueryMappingAgent and Stage2MappingVerifierAgent.
Transforms Stage 1 LegalQueryObject into verified Stage2BatchedMappingResponse.
Caps retries at 1 max for genuine mapping failures.
"""

from typing import Any, Dict, Optional, Union
from .stage2_mapping_agent import Stage2SubQueryMappingAgent
from .stage2_verifier_agent import Stage2MappingVerifierAgent
from .batch_utils import Stage2BatchedMappingResponse
from .schemas import LegalQueryObject, Stage2VerificationResult


class Stage2Pipeline:
    """
    Complete Stage 2 pipeline for Sub-Query to Chapter Candidate Batched Mapping.
    Executes LegalQueryObject -> Stage2SubQueryMappingAgent -> Stage2MappingVerifierAgent -> Reflection Retry Loop -> Verified Stage2BatchedMappingResponse.
    Caps retries at 1 max.
    """

    def __init__(
        self,
        mapping_agent: Optional[Stage2SubQueryMappingAgent] = None,
        verifier_agent: Optional[Stage2MappingVerifierAgent] = None,
        max_retries: int = 1,
    ):
        self.mapping_agent = mapping_agent or Stage2SubQueryMappingAgent()
        self.verifier_agent = verifier_agent or Stage2MappingVerifierAgent()
        self.max_retries = max_retries

    def run(
        self,
        legal_query: Union[LegalQueryObject, Dict[str, Any], str],
    ) -> Stage2VerificationResult:
        """
        Runs full Stage 2 pipeline on LegalQueryObject.

        Returns:
            Stage2VerificationResult containing final verified Stage2BatchedMappingResponse and audit details.
        """
        correction_feedback = None
        current_attempt = 0

        last_mapping_resp: Optional[Stage2BatchedMappingResponse] = None
        verification_result: Optional[Stage2VerificationResult] = None

        while current_attempt <= self.max_retries:
            current_attempt += 1

            # Step 1: Batched Mapping Evaluation
            last_mapping_resp = self.mapping_agent.run(
                legal_query=legal_query,
                correction_feedback=correction_feedback,
            )

            # Step 2: Verification Audit Check
            verification_result = self.verifier_agent.verify(
                legal_query=legal_query,
                mapping_response=last_mapping_resp,
            )

            if verification_result.status == "VERIFIED":
                verification_result.batched_mapping_response = last_mapping_resp
                return verification_result

            # Step 3: Prepare feedback for single reflection retry
            if current_attempt <= self.max_retries:
                feedback_parts = [f"Attempt {current_attempt} verification failed with audit issues:"]
                for issue in verification_result.issues:
                    feedback_parts.append(f"- Target '{issue.target}': {issue.issue} | Action: {issue.feedback}")
                if verification_result.feedback:
                    feedback_parts.append(f"Summary: {verification_result.feedback}")
                correction_feedback = "\n".join(feedback_parts)

        # Fallback Policy
        if verification_result:
            verification_result.batched_mapping_response = last_mapping_resp
            return verification_result

        return Stage2VerificationResult(
            status="RETRY",
            issues=[],
            feedback="Stage 2 pipeline execution completed without verification.",
            batched_mapping_response=last_mapping_resp,
        )
