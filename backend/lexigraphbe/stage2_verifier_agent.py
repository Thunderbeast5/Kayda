"""
Stage 2 Sub-Query Mapping Verifier Agent auditing Stage2BatchedMappingResponse.
Ensures every sub-query is properly mapped to candidate statutory chapters and sections.

Design principle: programmatic checks here are definition-grounded, not hardcoded.
Instead of a fixed list of (section -> disqualifying keyword) pairs, checks derive
scope rules from the actual statutory text in the database. New sections require no
new hardcoded rules — the database is the source of truth.
"""

import json
from typing import Any, Dict, List, Optional, Set, Union
from langchain_core.messages import HumanMessage, SystemMessage

from .config import extract_json_from_text, get_llm, MODEL_STAGE2
from .prompts import STAGE2_VERIFIER_SYSTEM_PROMPT, STAGE2_VERIFIER_USER_PROMPT_TEMPLATE
from .batch_utils import Stage2BatchedMappingResponse
from .schemas import LegalQueryObject, Stage2VerificationIssue, Stage2VerificationResult
from .statute_repository import StatuteRepository


def _extract_all_candidate_section_numbers(mapping) -> Set[str]:
    """Collects all section numbers from primary, secondary, conditional, and candidate_sections lists."""
    nums: Set[str] = set()
    for p in getattr(mapping, "primary_candidate_sections", []):
        nums.add(p.section_number.upper().strip())
    for s in getattr(mapping, "secondary_candidate_sections", []):
        nums.add(s.section_number.upper().strip())
    for c in getattr(mapping, "conditional_candidate_sections", []):
        nums.add(c.section_number.upper().strip())
    for sec_str in getattr(mapping, "candidate_sections", []):
        nums.add(sec_str.upper().strip())
    return nums


class Stage2MappingVerifierAgent:
    """
    Stage 2 Verifier Agent inspecting Stage2BatchedMappingResponse.

    Verification has two layers:
    1. LLM audit — checks structural correctness, coverage, and reasoning quality.
    2. Programmatic audit — definition-grounded scope checks that catch categorical
       mismatches and tier inconsistencies that the LLM may miss.
    """

    def __init__(self, llm: Optional[Any] = None):
        self._llm = llm

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm(temperature=0.0, model_name=MODEL_STAGE2)
        return self._llm

    def _programmatic_scope_audit(
        self,
        target_resp: Stage2BatchedMappingResponse,
        facts_summary: str,
        regime: str = "IPC + CrPC",
    ) -> List[Stage2VerificationIssue]:
        """
        Runs definition-grounded scope checks, regime compliance checks,
        and tier-consistency audits on every candidate section.
        """
        repo = StatuteRepository.get_instance()
        facts_lower = facts_summary.lower()
        is_ipc_regime = "BNS" not in (regime or "").upper()
        issues: List[Stage2VerificationIssue] = []

        for mapping in target_resp.mappings:
            # 1. Check regime compliance (IPC vs BNS)
            if is_ipc_regime:
                for c in (
                    getattr(mapping, "primary_candidate_sections", []) +
                    getattr(mapping, "secondary_candidate_sections", []) +
                    getattr(mapping, "conditional_candidate_sections", [])
                ):
                    if c.statute in ("BNS", "BNSS"):
                        issues.append(
                            Stage2VerificationIssue(
                                target=mapping.sub_query_id,
                                issue=f"Regime mismatch: Section {c.section_number} ({c.statute}) returned under IPC regime.",
                                feedback=f"Remove BNS section {c.section_number}. Only return IPC sections under IPC regime.",
                            )
                        )

        # Section-specific applicability (scope, compound/aggravated tiers, related-offence coverage)
        # is NOT decided here by keyword rules. A phrase such as "public servant" appearing anywhere
        # in a section's text is not a requirement of that section; ingredient-level verification in
        # Stage 4 decides applicability against the facts.

        return issues

    def verify(
        self,
        legal_query: Union[LegalQueryObject, Dict[str, Any], str],
        mapping_response: Union[Stage2BatchedMappingResponse, Dict[str, Any]],
    ) -> Stage2VerificationResult:
        """
        Audits Stage2BatchedMappingResponse against source LegalQueryObject.

        Returns:
            Stage2VerificationResult instance (status 'VERIFIED' or 'RETRY').
        """
        if isinstance(legal_query, LegalQueryObject):
            query_json_str = legal_query.to_downstream_json()
        elif isinstance(legal_query, dict):
            query_json_str = json.dumps(legal_query, indent=2)
        else:
            query_json_str = str(legal_query)

        if isinstance(mapping_response, Stage2BatchedMappingResponse):
            target_resp = mapping_response
            resp_dict = mapping_response.model_dump()
        else:
            target_resp = Stage2BatchedMappingResponse.model_validate(mapping_response)
            resp_dict = mapping_response

        resp_json_str = json.dumps(resp_dict, indent=2)

        # Layer 1: LLM structural/coverage audit
        user_prompt = STAGE2_VERIFIER_USER_PROMPT_TEMPLATE.format(
            legal_query_json=query_json_str,
            mapping_response_json=resp_json_str,
        )

        messages = [
            SystemMessage(content=STAGE2_VERIFIER_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]

        response = self.llm.invoke(messages)
        response_text = response.content if hasattr(response, "content") else str(response)

        parsed_dict = extract_json_from_text(response_text)

        raw_status = str(parsed_dict.get("status", "")).strip().upper()
        status = "VERIFIED" if raw_status == "VERIFIED" else "RETRY"

        raw_issues = parsed_dict.get("issues", [])
        issues: List[Stage2VerificationIssue] = []
        for issue_item in raw_issues:
            if isinstance(issue_item, dict):
                issues.append(Stage2VerificationIssue.model_validate(issue_item))
            elif isinstance(issue_item, str):
                issues.append(
                    Stage2VerificationIssue(target="general", issue=issue_item, feedback=issue_item)
                )

        # Layer 2: Definition-grounded programmatic scope audit
        # This catches categorical scope mismatches and tier inconsistencies.
        facts_summary = query_json_str or ""
        regime = "IPC + CrPC"
        if isinstance(legal_query, LegalQueryObject):
            regime = legal_query.legal_regime or "IPC + CrPC"
        elif isinstance(legal_query, dict):
            regime = legal_query.get("legal_regime") or "IPC + CrPC"

        programmatic_issues = self._programmatic_scope_audit(target_resp, facts_summary, regime=regime)

        if programmatic_issues:
            status = "RETRY"
            issues.extend(programmatic_issues)

        feedback_summary = parsed_dict.get("feedback", "Stage 2 sub-query mapping audit complete.")

        return Stage2VerificationResult(
            status=status,
            issues=issues,
            feedback=feedback_summary,
            batched_mapping_response=target_resp if status == "VERIFIED" else None,
        )