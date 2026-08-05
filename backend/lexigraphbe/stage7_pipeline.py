"""
Stage 7 Pipeline: Role-Specific Legal Argument Generation Engine.
Orchestrates RoleArgumentAgent -> RoleArgumentVerifierAgent with max 1 reflection retry cap.
"""

from typing import Any, Dict, Optional, Union
from pydantic import BaseModel, Field

from .role_argument_agent import RoleArgumentAgent
from .role_argument_verifier_agent import RoleArgumentVerifierAgent
from .schemas import (
    BailReasoningObject,
    CaseContextObject,
    PrecedentRetrievalObject,
    RoleArgumentObject,
    RoleArgumentVerificationResult,
    StatutoryVerificationObject,
)


class Stage7PipelineResponse(BaseModel):
    status: str = Field(description="Pipeline status: 'VERIFIED', 'FAILED_RETRY_EXHAUSTED', or 'ERROR'")
    verified_role_argument_object: Optional[RoleArgumentObject] = Field(default=None, description="Verified RoleArgumentObject contract")
    audit_result: RoleArgumentVerificationResult = Field(description="Final verification audit result")
    attempts_made: int = Field(default=1, description="Number of generation-verification retry cycles attempted")


class Stage7Pipeline:
    """
    Stage 7 Pipeline orchestrating Argument Generation Agent and Argument Verification Auditor.
    Enforces a strict 1-retry cap to prevent runaway loops.
    """

    def __init__(
        self,
        argument_agent: Optional[RoleArgumentAgent] = None,
        verifier_agent: Optional[RoleArgumentVerifierAgent] = None,
        max_retries: int = 1,
    ):
        self.argument_agent = argument_agent or RoleArgumentAgent()
        self.verifier_agent = verifier_agent or RoleArgumentVerifierAgent()
        self.max_retries = max_retries

    def run(
        self,
        case_context: Union[CaseContextObject, Dict[str, Any], str],
        statutory_object: Union[StatutoryVerificationObject, Dict[str, Any], str],
        bail_object: Union[BailReasoningObject, Dict[str, Any], str],
        precedent_object: Union[PrecedentRetrievalObject, Dict[str, Any], str],
    ) -> Stage7PipelineResponse:
        """
        Executes Stage 7 Argument Generation pipeline with reflection retry loop.

        Returns:
            Stage7PipelineResponse instance.
        """
        correction_feedback = None
        attempts = 0

        while attempts <= self.max_retries:
            attempts += 1

            # 1. Generate Role-Specific Legal Arguments
            role_arg_obj = self.argument_agent.run(
                case_context=case_context,
                statutory_object=statutory_object,
                bail_object=bail_object,
                precedent_object=precedent_object,
                correction_feedback=correction_feedback,
            )

            # 2. Audit with Verification Agent
            v_res = self.verifier_agent.verify(
                case_context=case_context,
                statutory_object=statutory_object,
                bail_object=bail_object,
                precedent_object=precedent_object,
                role_argument_object=role_arg_obj,
            )

            if v_res.status == "VERIFIED":
                return Stage7PipelineResponse(
                    status="VERIFIED",
                    verified_role_argument_object=v_res.verified_role_argument_object,
                    audit_result=v_res,
                    attempts_made=attempts,
                )

            # Prepare feedback for retry
            feedback_issues = [f"- Target '{i.target}': {i.issue} Feedback: {i.feedback}" for i in v_res.issues]
            correction_feedback = "\n".join(feedback_issues)

        # Retry cap exhausted: Return fallback with manual_review notes
        role_arg_obj.manual_review.append(f"Stage 7 argument verification failed after {attempts} attempts: {v_res.feedback}")
        role_arg_obj.verification_status = "FAILED_RETRY_EXHAUSTED"

        return Stage7PipelineResponse(
            status="FAILED_RETRY_EXHAUSTED",
            verified_role_argument_object=role_arg_obj,
            audit_result=v_res,
            attempts_made=attempts,
        )
