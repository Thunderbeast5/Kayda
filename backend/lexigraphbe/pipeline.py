"""
Stage 0 Pipeline orchestrating CaseIntakeAgent and CaseIntakeVerifierAgent.
Implements Programmatic-First Dual-Tier Verification:
- Tier 2 Programmatic Pre-Check: Hard Contract validation for Stage 1 downstream agents.
- Tier 1 LLM Verifier Check: Self-reflection check against raw documents (bypassed if contract blocked).
- Capped Retry Policy (max_retries = 1): Re-asks once max for genuine judgment failures, then falls back to human review flags.
"""

import os
import re
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
        force_llm_verifier: bool = False,
    ):
        import os
        self.intake_agent = intake_agent or CaseIntakeAgent()
        self.verifier_agent = verifier_agent or CaseIntakeVerifierAgent()
        self.max_retries = max_retries
        self.force_llm_verifier = force_llm_verifier or (os.getenv("FORCE_STAGE0_LLM_VERIFIER", "false").lower() == "true")

    def _check_deterministic_grounding(self, raw_text: str, profile: CaseProfile) -> tuple[bool, list[str]]:
        """
        Comprehensive deterministic grounding audit.
        Verifies that extracted FIR numbers, accused names, police stations, courts,
        dates, and complainant identities actually appear in the raw source text.
        """
        import re
        if not raw_text:
            return False, ["raw_text_empty"]
        text_lower = raw_text.lower()
        ungrounded = []

        # 1. FIR Number
        fir = profile.case_metadata.fir_number
        if fir and str(fir).lower() not in text_lower:
            parts = [p for p in re.split(r"[^\w]+", str(fir)) if len(p) >= 2]
            if not all(p.lower() in text_lower for p in parts):
                ungrounded.append(f"fir_number:{fir}")

        # 2. Accused Names
        for acc in profile.get_accused_list():
            if acc and str(acc).lower() not in text_lower:
                parts = [p for p in acc.split() if len(p) > 2]
                if not any(p.lower() in text_lower for p in parts):
                    ungrounded.append(f"accused_name:{acc}")

        # 3. Police Station
        ps = profile.case_metadata.police_station
        if ps and str(ps).lower() not in ("unknown", "none", ""):
            ps_clean = str(ps).lower().replace("police station", "").strip()
            if ps_clean and ps_clean not in text_lower:
                parts = [p for p in ps_clean.split() if len(p) > 2]
                if not any(p in text_lower for p in parts):
                    ungrounded.append(f"police_station:{ps}")

        # 4. Court Name
        court = profile.case_metadata.court
        if court and str(court).lower() not in ("unknown", "none", ""):
            court_clean = str(court).lower().replace("court", "").strip()
            if court_clean and court_clean not in text_lower:
                parts = [p for p in court_clean.split() if len(p) > 2]
                if not any(p in text_lower for p in parts):
                    ungrounded.append(f"court:{court}")

        # 5. Offence Date & FIR Date
        for dt_field, dt_val in [
            ("offence_date", profile.case_metadata.offence_date),
            ("fir_date", profile.case_metadata.fir_date),
        ]:
            if dt_val and str(dt_val).lower() not in ("unknown", "none", ""):
                date_parts = [p for p in re.split(r"[^\w]+", str(dt_val)) if len(p) >= 2]
                if date_parts and not any(p in text_lower for p in date_parts):
                    ungrounded.append(f"{dt_field}:{dt_val}")

        # 6. Complainant Name
        comp = profile.parties.complainant
        if comp and str(comp).lower() not in ("unknown", "none", ""):
            comp_list = comp if isinstance(comp, list) else [str(comp)]
            for c in comp_list:
                if c and str(c).lower() not in text_lower:
                    c_parts = [p for p in str(c).split() if len(p) > 2]
                    if c_parts and not any(p.lower() in text_lower for p in c_parts):
                        ungrounded.append(f"complainant:{c}")

        # 7. Statutory Sections / Penal Provisions
        profile_text = f"{profile.case_facts or ''} {profile.regime_notes or ''}"
        cited_sections = set(re.findall(r'\b(?:u/s|section|sec\.?)\s*(\d+[A-Za-z]*(?:/\d+)*)\b', profile_text, re.IGNORECASE))
        for sec in cited_sections:
            sec_clean = re.sub(r'^[^\w]+|[^\w]+$', '', sec)
            if sec_clean and sec_clean.lower() not in text_lower:
                ungrounded.append(f"section:{sec}")

        return len(ungrounded) == 0, ungrounded

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

            # Deterministic code grounding check (names, dates, FIR numbers in source text)
            opt_verifier_bypass_stage0 = os.getenv("OPT_VERIFIER_BYPASS_STAGE0", "false").lower() in ("true", "1", "yes")
            is_grounded, ungrounded_items = self._check_deterministic_grounding(raw_text, last_profile)

            if contract_status == "CONTRACT_BLOCKED":
                # Programmatic check failed mandatory fields; short-circuit LLM Verifier call
                verification_result = VerificationResult(
                    status="NEEDS_CORRECTION",
                    contract_status=contract_status,
                    issues=[VerificationIssue(field="mandatory_contract", issue=v, feedback=v) for v in violations],
                    feedback=f"Stage 1 Hard Contract BLOCKED ({len(violations)} mandatory field violations: {', '.join(violations)})",
                    verified_case_profile=last_profile,
                )
            elif (
                opt_verifier_bypass_stage0
                and contract_status == "CONTRACT_PASSED"
                and is_grounded
                and not getattr(last_profile, "flag_for_confirmation", False)
                and len(getattr(last_profile, "low_confidence_fields", [])) == 0
                and not self.force_llm_verifier
            ):
                # Programmatic check passed completely clean with deterministic grounding verified!
                # Short-circuit LLM verifier call (OPT_VERIFIER_BYPASS_STAGE0 enabled)
                verification_result = VerificationResult(
                    status="VERIFIED",
                    contract_status=contract_status,
                    issues=[],
                    feedback="Stage 0 Programmatic hard contract and deterministic grounding passed cleanly; LLM verifier bypassed.",
                    verified_case_profile=last_profile,
                )
                return verification_result
            else:
                # Default path: Run LLM Verifier against raw documents to prevent hallucinations
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
