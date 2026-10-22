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
        nominator: Optional[Any] = None,
        use_nomination: bool = True,
    ):
        self.mapping_agent = mapping_agent or Stage2SubQueryMappingAgent()
        self.verifier_agent = verifier_agent or Stage2MappingVerifierAgent()
        self.max_retries = max_retries
        if nominator is None and use_nomination:
            from .section_nominator import SectionNominator
            nominator = SectionNominator()
        self.nominator = nominator

    def run(
        self,
        legal_query: Union[LegalQueryObject, Dict[str, Any], str],
    ) -> Stage2VerificationResult:
        """
        Runs full Stage 2 pipeline on LegalQueryObject.

        Returns:
            Stage2VerificationResult containing final verified Stage2BatchedMappingResponse and audit details.
        """
        # Family-tagged queries: retrieval already ranked the sections; Stage 2 maps them
        # deterministically (no LLM mapping, scope checks or verifier). Applicability is decided
        # once, at ingredient level, in Stage 4.
        query_obj = legal_query
        if isinstance(legal_query, dict):
            query_obj = LegalQueryObject.model_validate(legal_query)
        elif isinstance(legal_query, str):
            import json as _json
            query_obj = LegalQueryObject.model_validate(_json.loads(legal_query))
        if getattr(query_obj, "offence_families", None):
            from .family_retrieval import build_family_mapping
            nominations = self.nominator.run(query_obj) if self.nominator else None
            mapping = build_family_mapping(query_obj, nominations=nominations,
                                           excluded=getattr(self.nominator, "last_excluded", None) if nominations else None)
            if mapping.get("retrieval_only_not_nominated"):
                print(f"  [Stage 2] BM25 hits not nominated (dropped): {mapping['retrieval_only_not_nominated']}", flush=True)
            resp = Stage2BatchedMappingResponse.model_validate(mapping)
            return Stage2VerificationResult(
                status="VERIFIED", issues=[],
                feedback=("Family-scoped LLM nomination over ipc.json sections, fused with BM25 retrieval (1 LLM call)."
                          if nominations else "Deterministic family-constrained BM25 mapping (nomination unavailable)."),
                batched_mapping_response=resp,
            )

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
