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


# -----------------------------------------------------------------------
# Scope-restriction phrases that, if found in a section's statutory text,
# indicate a categorical scope requirement.
#
# Each entry is:
#   (definition_phrases, absence_keywords_in_facts, disqualification_label)
#
# If ANY phrase in definition_phrases appears in the section's statutory
# definition, AND none of the absence_keywords_in_facts appear in the case
# facts, the section fails scope. The disqualification_label is used in the
# issue message.
#
# THIS IS THE ONLY PLACE WHERE SCOPE RULES ARE MAINTAINED.
# No other file should contain hardcoded section-specific rules.
# To add a new scope rule, add one tuple here — the verifier applies it
# automatically to every section in every case.
# -----------------------------------------------------------------------
_SCOPE_RESTRICTION_RULES: List[tuple] = [
    # Debtor/creditor scope — S.421 IPC and equivalents
    (
        ["being indebted", "about to become indebted", "prevent the distribution", "distribution among creditors"],
        ["creditor", "debtor", "debt", "insolvency", "loan default", "dues"],
        "debtor-creditor relationship",
    ),
    # Deceased person's property — S.404 IPC and equivalents
    (
        ["property of a person deceased", "property belonging to a deceased person", "person deceased"],
        ["deceased", "dead person", "estate of", "inheritance", "succession", "death of"],
        "property of a deceased person",
    ),
    # Public servant / fiduciary role — S.409 IPC and equivalents
    (
        ["public servant", "banker", "merchant", "factor", "broker", "attorney", "agent",
         "being entrusted with property in his capacity as"],
        ["public servant", "banker", "broker", "agent", "attorney", "factor"],
        "specific fiduciary or official capacity",
    ),
    # Matrimonial relationship — S.498A, S.304B and equivalents
    (
        ["husband or relative of husband", "relative of the husband"],
        ["husband", "wife", "marriage", "matrimonial", "wedlock", "spouse"],
        "matrimonial relationship between accused and victim",
    ),
    # Dowry death — death is mandatory — S.304B IPC / S.80 BNS
    (
        ["death of a woman", "soon before her death", "in connection with any demand for dowry"],
        ["death", "deceased", "dead", "died", "suicide", "killed", "body"],
        "death of the woman within seven years of marriage",
    ),
    # Attempt to murder — S.307 IPC — intent to kill is mandatory
    (
        ["such act done with intention of causing death", "attempt to murder"],
        ["attempt to kill", "attempt to murder", "aimed to kill", "shoot", "stab", "poison"],
        "intent and act of attempting to cause death",
    ),
    # Rape / sexual assault — S.376 IPC — sexual act is mandatory
    (
        ["sexual intercourse by a man with a woman", "without her consent"],
        ["rape", "sexual assault", "sexual intercourse", "non-consensual"],
        "non-consensual sexual intercourse",
    ),
    # Currency/stamp counterfeiting — S.489A-E — currency is mandatory
    (
        ["currency-note", "bank-note", "government stamp", "counterfeit"],
        ["currency", "note", "coin", "stamp", "counterfeit"],
        "counterfeit currency or government stamps",
    ),
]


def _extract_all_candidate_section_numbers(mapping) -> Set[str]:
    """Collects all section numbers from primary, secondary, and candidate_sections lists."""
    nums: Set[str] = set()
    for p in mapping.primary_candidate_sections:
        nums.add(p.section_number.upper().strip())
    for s in mapping.secondary_candidate_sections:
        nums.add(s.section_number.upper().strip())
    for sec_str in mapping.candidate_sections:
        nums.add(sec_str.upper().strip())
    return nums


class Stage2MappingVerifierAgent:
    """
    Stage 2 Verifier Agent inspecting Stage2BatchedMappingResponse.

    Verification has two layers:
    1. LLM audit — checks structural correctness, coverage, and reasoning quality.
    2. Programmatic audit — definition-grounded scope checks that catch categorical
       mismatches the LLM may miss. Rules derive from statutory text, not hardcoded
       section lists.
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
    ) -> List[Stage2VerificationIssue]:
        """
        Runs definition-grounded scope checks on every candidate section.

        For each section, looks up its statutory definition, then checks it
        against _SCOPE_RESTRICTION_RULES. If the definition contains a scope
        restriction phrase AND the corresponding facts are absent, it's a violation.

        This replaces all hardcoded keyword-per-section rules. To handle a new
        class of scope restriction, add one tuple to _SCOPE_RESTRICTION_RULES.
        """
        repo = StatuteRepository.get_instance()
        facts_lower = facts_summary.lower()
        issues: List[Stage2VerificationIssue] = []

        for mapping in target_resp.mappings:
            candidate_sec_nums = _extract_all_candidate_section_numbers(mapping)

            for sec_str in candidate_sec_nums:
                # Try to get the statutory definition for this section
                definition = (
                    repo.get_statutory_definition(sec_str, "IPC")
                    or repo.get_statutory_definition(sec_str, "BNS")
                    or ""
                ).lower()

                if not definition:
                    continue  # No definition available — cannot audit scope

                # Check each scope restriction rule against this definition
                for def_phrases, fact_keywords, scope_label in _SCOPE_RESTRICTION_RULES:
                    # Does this section's definition contain ANY of the scope-restriction phrases?
                    definition_has_restriction = any(
                        phrase.lower() in definition for phrase in def_phrases
                    )
                    if not definition_has_restriction:
                        continue  # This rule doesn't apply to this section

                    # Does the fact pattern contain ANY of the required fact keywords?
                    facts_satisfy_scope = any(
                        kw.lower() in facts_lower for kw in fact_keywords
                    )
                    if facts_satisfy_scope:
                        continue  # Facts satisfy the scope requirement — no violation

                    # Scope mismatch: section requires something the facts don't have
                    issues.append(
                        Stage2VerificationIssue(
                            target=mapping.sub_query_id,
                            issue=(
                                f"Scope violation: Section {sec_str} included as a candidate but its "
                                f"statutory definition requires {scope_label}, which is absent from "
                                f"the case facts. This is a categorical mismatch, not a missing ingredient."
                            ),
                            feedback=(
                                f"Remove Section {sec_str} from candidate lists. Place it in "
                                f"not_triggered_sections with reason: 'Categorical scope mismatch — "
                                f"{scope_label} not present in case facts.' Do not replace it with a "
                                f"semantically similar section unless the facts support it."
                            ),
                        )
                    )
                    break  # One issue per section per mapping — don't stack rules

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

        raw_status = str(parsed_dict.get("status", "")).upper()
        status = "VERIFIED" if "VERIFIED" in raw_status else "RETRY"

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
        # This catches categorical scope mismatches that the LLM may miss.
        # Rules are derived from statutory text — no hardcoded section lists.
        facts_summary = query_json_str or ""
        programmatic_issues = self._programmatic_scope_audit(target_resp, facts_summary)

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