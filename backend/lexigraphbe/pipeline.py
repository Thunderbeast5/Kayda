"""
Stage 0 Pipeline orchestrating CaseIntakeAgent and CaseIntakeVerifierAgent.
Implements Programmatic-First Dual-Tier Verification:
- Tier 2 Programmatic Pre-Check: Hard Contract validation for Stage 1 downstream agents.
- Tier 1 LLM Verifier Check: Self-reflection check against raw documents (bypassed if contract blocked).
- Capped Retry Policy (max_retries = 1): Re-asks once max for genuine judgment failures, then falls back to human review flags.
"""

from typing import Any, Dict, Optional, Union
from .intake_agent import CaseIntakeAgent
from .verifier_agent import CaseIntakeVerifierAgent
from .schemas import CaseProfile, IntakeInput, VerificationResult, VerificationIssue


class Stage0Pipeline:
    """
    Complete Stage 0 pipeline for case intake and context initialization.
    Executes intake extraction -> programmatic hard contract check -> conditional verifier check -> verified profile.
    Caps retries at 1 max for genuine judgment failures, falling back to human confirmation flags.
    """

    def __init__(
        self,
        intake_agent: Optional[CaseIntakeAgent] = None,
        verifier_agent: Optional[CaseIntakeVerifierAgent] = None,
        max_retries: int = 1,
    ):
        self.intake_agent = intake_agent or CaseIntakeAgent()
        self.verifier_agent = verifier_agent or CaseIntakeVerifierAgent()
        self.max_retries = max_retries

    def run(
        self,
        intake_input: Union[IntakeInput, str, Dict[str, Any]],
    ) -> VerificationResult:
        """
        Runs full Stage 0 pipeline on raw input.

        Args:
            intake_input: Raw text string, dict, or IntakeInput instance.

        Returns:
            VerificationResult containing final verified CaseProfile and execution details.
        """
        if isinstance(intake_input, str):
            inp = IntakeInput(documents_text=intake_input)
        elif isinstance(intake_input, dict):
            inp = IntakeInput(**intake_input)
        elif isinstance(intake_input, IntakeInput):
            inp = intake_input
        else:
            raise ValueError(f"Invalid input type: {type(intake_input)}")

        raw_text = inp.documents_text or ""
        correction_feedback = None
        current_attempt = 0

        last_profile: Optional[CaseProfile] = None
        verification_result: Optional[VerificationResult] = None

        while current_attempt <= self.max_retries:
            current_attempt += 1

            # Step 1: Intake Extraction (single structured LLM call)
            last_profile = self.intake_agent.run(
                intake_input=inp,
                correction_feedback=correction_feedback,
            )

            # Step 2: Tier 2 Programmatic Hard Contract Validation FIRST (0 LLM calls)
            contract_status, violations = last_profile.validate_stage1_contract()

            if contract_status == "CONTRACT_BLOCKED":
                # Programmatic check failed mandatory fields; short-circuit LLM Verifier call
                verification_result = VerificationResult(
                    status="NEEDS_CORRECTION",
                    contract_status=contract_status,
                    issues=[VerificationIssue(field="mandatory_contract", issue=v, feedback=v) for v in violations],
                    feedback=f"Stage 1 Hard Contract BLOCKED ({len(violations)} mandatory field violations: {', '.join(violations)})",
                    verified_case_profile=last_profile,
                )
            else:
                # Step 3: Tier 1 LLM Verifier Agent Check against raw text
                verification_result = self.verifier_agent.verify(
                    raw_source_text=raw_text,
                    case_profile=last_profile,
                )
                verification_result.contract_status = contract_status
                verification_result.verified_case_profile = last_profile

                if verification_result.status == "VERIFIED":
                    return verification_result

            # If corrections needed, prepare feedback string for single retry attempt
            if current_attempt <= self.max_retries:
                feedback_parts = [f"Attempt {current_attempt} verification failed with issues:"]
                for issue in verification_result.issues:
                    feedback_parts.append(f"- Field '{issue.field}': {issue.issue} | Action: {issue.feedback}")
                if verification_result.feedback:
                    feedback_parts.append(f"Summary: {verification_result.feedback}")
                correction_feedback = "\n".join(feedback_parts)

        # Fallback Policy: If retries are exhausted, flag for human confirmation instead of failing or looping
        if last_profile:
            last_profile.flag_for_confirmation = True
            if verification_result:
                verification_result.verified_case_profile = last_profile
                verification_result.feedback += " (Exhausted retries -> Flagged for human review)."
                return verification_result

        return VerificationResult(
            status="NEEDS_CORRECTION",
            contract_status="CONTRACT_BLOCKED",
            issues=[],
            feedback="Pipeline execution completed without verification (Flagged for human review).",
            verified_case_profile=last_profile,
        )
