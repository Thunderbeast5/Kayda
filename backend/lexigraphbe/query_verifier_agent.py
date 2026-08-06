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

        # ----------------------------------------------------------------------
        # PROGRAMMATIC CHECK 1: Closed-set statutory section leak audit
        # ----------------------------------------------------------------------
        section_leak_issues = []
        for sq in query_obj.sub_queries:
            leaks = self.section_auditor.audit_text_for_leaks(sq.query)
            for leak in leaks:
                section_leak_issues.append(
                    QueryVerificationIssue(
                        target=sq.id,
                        issue=f"Statutory section leak detected in sub-query '{sq.id}': '{leak['matched_text']}' (section {leak['section']})",
                        feedback=f"Remove all statutory section numbers from sub-query '{sq.id}'. Express purely as factual legal concept.",
                    )
                )

        # SHORT-CIRCUIT: If programmatic section leak detected, return RETRY immediately with 0 LLM API calls
        if section_leak_issues:
            return QueryVerificationResult(
                status="RETRY",
                issues=section_leak_issues,
                feedback=f"Programmatic audit blocked statutory section leak: {len(section_leak_issues)} section leaks detected.",
                verified_query_object=None,
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

        raw_status = str(parsed_dict.get("status", "")).upper()
        status = "VERIFIED" if "VERIFIED" in raw_status else "RETRY"

        raw_issues = parsed_dict.get("issues", [])
        issues = []
        for issue_item in raw_issues:
            if isinstance(issue_item, dict):
                issues.append(QueryVerificationIssue.model_validate(issue_item))
            elif isinstance(issue_item, str):
                issues.append(QueryVerificationIssue(target="general", issue=issue_item, feedback=issue_item))

        feedback_summary = parsed_dict.get("feedback", "Query verification complete.")

        if status == "VERIFIED":
            query_obj.verification_status = "VERIFIED"

        return QueryVerificationResult(
            status=status,
            issues=issues,
            feedback=feedback_summary,
            verified_query_object=query_obj if status == "VERIFIED" else None,
        )
