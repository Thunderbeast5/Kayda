"""
Query Verification Agent for Stage 1: Query Understanding & Legal Decomposition.
Verifies LegalQueryObject against source CaseContextObject to ensure fact grounding,
single-issue sub-queries, and zero statutory IPC/BNS section leaks using ClosedSetSectionAuditor.
Eliminates unnecessary LLM calls by short-circuiting on programmatic section leak detection.
Model: gpt-4o-mini (MODEL_STAGE1) — inherits primary stage model.
"""

import json
from typing import Any, Dict, Optional, Union
from langchain_core.messages import HumanMessage, SystemMessage

from .config import extract_json_from_text, get_llm, MODEL_STAGE1
from .prompts import STAGE1_QUERY_VERIFICATION_SYSTEM_PROMPT, STAGE1_QUERY_VERIFICATION_USER_PROMPT_TEMPLATE
from .schemas import CaseContextObject, CaseProfile, LegalQueryObject, QueryVerificationIssue, QueryVerificationResult
from .section_matcher import ClosedSetSectionAuditor


class QueryVerificationAgent:
    """
    Verifier Agent auditing LegalQueryObject against source facts before passing to Stage 2.
    Uses closed-set section matching to accurately detect section leaks while preventing false-positives.
    Short-circuits on programmatic violations to eliminate unnecessary LLM calls.
    Model: gpt-4o-mini (MODEL_STAGE1) — inherits primary stage model.
    """

    def __init__(self, llm: Optional[Any] = None):
        self._llm = llm
        self.section_auditor = ClosedSetSectionAuditor()

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm(temperature=0.0, model_name=MODEL_STAGE1)
        return self._llm

    def verify(
        self,
        case_context: Union[CaseContextObject, CaseProfile, Dict[str, Any], str],
        legal_query: Union[LegalQueryObject, Dict[str, Any]],
    ) -> QueryVerificationResult:
        """
        Verifies extracted LegalQueryObject against source CaseContextObject.

        Args:
            case_context: Source CaseContextObject from Stage 0.
            legal_query: Target LegalQueryObject to verify.

        Returns:
            QueryVerificationResult instance (status 'VERIFIED' or 'RETRY').
        """
        # Format case context JSON
        if isinstance(case_context, CaseContextObject):
            case_context_str = case_context.to_downstream_json()
        elif isinstance(case_context, CaseProfile):
            case_context_str = json.dumps(case_context.model_dump(), indent=2)
        elif isinstance(case_context, dict):
            case_context_str = json.dumps(case_context, indent=2)
        elif isinstance(case_context, str):
            case_context_str = case_context
        else:
            case_context_str = str(case_context)

        # Format legal query JSON
        if isinstance(legal_query, LegalQueryObject):
            query_obj = legal_query
            query_dict = legal_query.model_dump()
        else:
            query_dict = legal_query
            query_obj = LegalQueryObject.model_validate(legal_query)

        query_json_str = json.dumps(query_dict, indent=2)

        # PROGRAMMATIC CHECK 0: schema relationships and traceability.
        structural_issues = []
        fact_ids = {fact.fact_id for fact in query_obj.factual_allegations}
        concept_ids = {concept.concept_id for concept in query_obj.legal_concepts}
        if query_obj.sub_queries and not query_obj.factual_allegations:
            structural_issues.append(QueryVerificationIssue(
                target="factual_allegations", issue="Sub-queries exist but no factual allegation inventory was produced.",
                feedback="Extract source-grounded factual allegations first, assign F IDs, and link each retrieval query to supporting facts."
            ))
        if len(fact_ids) != len(query_obj.factual_allegations):
            structural_issues.append(QueryVerificationIssue(
                target="factual_allegations", issue="Duplicate factual allegation IDs were found.",
                feedback="Assign a unique stable fact_id to every factual allegation."
            ))
        for concept in query_obj.legal_concepts:
            if not concept.supporting_fact_ids:
                structural_issues.append(QueryVerificationIssue(
                    target=concept.concept_id or concept.concept,
                    issue="Legal concept has no supporting fact IDs.",
                    feedback="Link the concept to one or more source-grounded factual allegation IDs, or remove it if unsupported."
                ))
            elif fact_ids and not set(concept.supporting_fact_ids).issubset(fact_ids):
                structural_issues.append(QueryVerificationIssue(
                    target=concept.concept_id or concept.concept,
                    issue="Legal concept references unknown fact IDs.",
                    feedback="Correct the fact_ids to reference factual_allegations actually present in this object."
                ))
        for sq in query_obj.sub_queries:
            if not sq.concept_id or sq.concept_id not in concept_ids:
                structural_issues.append(QueryVerificationIssue(
                    target=sq.id, issue="Sub-query does not reference a valid legal concept.",
                    feedback="Set concept_id to an existing legal_concepts entry and ensure concept text matches it exactly."
                ))
            if not sq.fact_ids or (fact_ids and not set(sq.fact_ids).issubset(fact_ids)):
                structural_issues.append(QueryVerificationIssue(
                    target=sq.id, issue="Sub-query has missing or invalid supporting fact IDs.",
                    feedback="Link the sub-query to valid factual_allegations IDs; do not invent IDs."
                ))
        if structural_issues:
            return QueryVerificationResult(
                status="RETRY", issues=structural_issues,
                feedback="Programmatic traceability audit failed before LLM review.",
                verified_query_object=None, candidate_query_object=query_obj
            )

        # ----------------------------------------------------------------------
        # PROGRAMMATIC CHECK 1: Closed-set statutory section leak audit
        # ----------------------------------------------------------------------
        section_leak_issues = []
        for sq in query_obj.sub_queries:
            for field_name, text_value in (("query", sq.query), ("concept", sq.concept)):
                leaks = self.section_auditor.audit_text_for_leaks(text_value)
                for leak in leaks:
                    section_leak_issues.append(
                        QueryVerificationIssue(
                            target=sq.id,
                            issue=f"Statutory section leak detected in sub-query {sq.id} {field_name}: '{leak['matched_text']}' (section {leak['section']})",
                            feedback=f"Remove statutory section numbers from sub-query {sq.id} {field_name}; retain a factual legal-issue description.",
                        )
                    )

        # SHORT-CIRCUIT: If programmatic section leak detected, return RETRY immediately with 0 LLM API calls
        if section_leak_issues:
            return QueryVerificationResult(
                status="RETRY",
                issues=section_leak_issues,
                feedback=f"Programmatic audit blocked statutory section leak: {len(section_leak_issues)} section leaks detected.",
                verified_query_object=None,
                candidate_query_object=query_obj,
            )

        # Step 2: Fall back to LLM Verifier only when programmatic checks pass clean
        user_prompt = STAGE1_QUERY_VERIFICATION_USER_PROMPT_TEMPLATE.format(
            case_context_json=case_context_str,
            legal_query_json=query_json_str,
        )

        messages = [
            SystemMessage(content=STAGE1_QUERY_VERIFICATION_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]

        response = self.llm.invoke(messages)
        response_text = response.content if hasattr(response, "content") else str(response)

        parsed_dict = extract_json_from_text(response_text)

        raw_status = str(parsed_dict.get("status", "")).strip().upper()
        if raw_status == "VERIFIED":
            status = "VERIFIED"
        elif raw_status == "RETRY":
            status = "RETRY"
        else:
            status = "RETRY"
            parsed_dict.setdefault("issues", []).append({
                "target": "verification_status",
                "issue": f"Verifier returned invalid status: {raw_status!r}",
                "feedback": "Return exactly VERIFIED or RETRY."
            })

        raw_issues = parsed_dict.get("issues", [])
        issues = []
        for issue_item in raw_issues:
            if isinstance(issue_item, dict):
                issues.append(QueryVerificationIssue.model_validate(issue_item))
            elif isinstance(issue_item, str):
                issues.append(QueryVerificationIssue(target="general", issue=issue_item, feedback=issue_item))

        feedback_summary = parsed_dict.get("feedback", "Query verification complete.")
        if status == "VERIFIED" and issues:
            status = "RETRY"
            feedback_summary = str(feedback_summary) + " Verifier returned issues; verification cannot pass with unresolved issues."

        if status == "VERIFIED":
            query_obj.verification_status = "VERIFIED"

        return QueryVerificationResult(
            status=status,
            issues=issues,
            feedback=feedback_summary,
            verified_query_object=query_obj if status == "VERIFIED" and not issues else None,
            candidate_query_object=query_obj if status != "VERIFIED" or issues else None,
        )
