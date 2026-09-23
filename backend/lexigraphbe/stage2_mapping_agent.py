"""
Stage 2 Sub-Query to Chapter Candidate Mapping Agent.
Maps decomposed sub-queries ($SQ_1, SQ_2, \\dots, SQ_N$) from Stage 1 to candidate statutory chapters and sections
using local StatuteClassifierPrefilter candidates in ONE single batched LLM request.
Model: gpt-4o-mini (MODEL_STAGE2).
"""

import json
from typing import Any, Dict, Optional, Union
from langchain_core.messages import HumanMessage, SystemMessage

from .config import extract_json_from_text, get_llm, MODEL_STAGE2
from .classifier_prefilter import StatuteClassifierPrefilter
from .prompts import STAGE2_MAPPING_SYSTEM_PROMPT, STAGE2_MAPPING_USER_PROMPT_TEMPLATE
from .batch_utils import Stage2BatchedMappingResponse
from .schemas import LegalQueryObject


class Stage2SubQueryMappingAgent:
    """
    Stage 2 Agent mapping sub-queries to candidate statutory chapters and sections.
    Integrates local StatuteClassifierPrefilter (0 API calls) with batched LLM request.
    """

    def __init__(
        self,
        llm: Optional[Any] = None,
        prefilter: Optional[StatuteClassifierPrefilter] = None,
    ):
        self._llm = llm
        self.prefilter = prefilter or StatuteClassifierPrefilter()

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm(temperature=0.1, model_name=MODEL_STAGE2)
        return self._llm

    def run(
        self,
        legal_query: Union[LegalQueryObject, Dict[str, Any], str],
        correction_feedback: Optional[str] = None,
    ) -> Stage2BatchedMappingResponse:
        """
        Runs Stage 2 Batched Sub-Query Mapping on LegalQueryObject.

        Args:
            legal_query: Verified LegalQueryObject from Stage 1.
            correction_feedback: Feedback from verifier if retrying.

        Returns:
            Stage2BatchedMappingResponse instance.
        """
        if isinstance(legal_query, LegalQueryObject):
            query_obj = legal_query
            query_json_str = legal_query.to_downstream_json()
        elif isinstance(legal_query, dict):
            query_obj = LegalQueryObject.model_validate(legal_query)
            query_json_str = json.dumps(legal_query, indent=2)
        else:
            query_obj = LegalQueryObject.model_validate(json.loads(str(legal_query)))
            query_json_str = str(legal_query)

        # Step 1: Extract combined facts text from LegalQueryObject
        facts_text_parts = []
        if query_obj.important_facts:
            facts_text_parts.append(str(query_obj.important_facts.model_dump()))
        for sq in query_obj.sub_queries:
            facts_text_parts.append(sq.query)
        facts_text = " ".join(facts_text_parts)

        regime = query_obj.legal_regime or "IPC + CrPC"
        statute_type = "IPC"

        # Step 2: Run local StatuteClassifierPrefilter (0 API calls)
        prefiltered_matches = []
        for concept_item in query_obj.legal_concepts:
            matches = self.prefilter.prefilter_candidates(
                query_text=concept_item.concept,
                statute_type=statute_type,
                top_k=10,
            )
            prefiltered_matches.extend(matches)

        # Step 3: Detect factual triggers (e.g. dowry -> 498A & Sec 4 DP Act, stridhan -> 406, threat -> 506)
        trigger_suggestions = self.prefilter.detect_factual_triggers(facts_text=facts_text, statute_type=statute_type)

        # Deduplicate pre-filter matches and include trigger suggestions
        dedup_dict = {}
        for m in prefiltered_matches:
            statute_str = getattr(m, "statute", getattr(m, "statute_type", "IPC"))
            sec_num = getattr(m, "section_number", "")
            title_str = getattr(m, "title", getattr(m, "section_title", ""))
            chap_str = getattr(m, "chapter", getattr(m, "chapter_name", ""))
            score_val = getattr(m, "score", 0.0)

            is_not_triggered, elim_reason, missing_mands = self.prefilter.evaluate_fatal_disqualification(sec_num, statute_str, facts_text)

            k = f"{statute_str}_{sec_num}"
            if k not in dedup_dict or score_val > dedup_dict[k]["score"]:
                dedup_dict[k] = {
                    "statute": statute_str,
                    "section_number": sec_num,
                    "section_title": title_str,
                    "chapter_name": chap_str,
                    "score": round(score_val, 4),
                    "not_triggered": is_not_triggered,
                    "not_triggered_reason": elim_reason,
                    "missing_mandatory_ingredients": missing_mands,
                }

        for ts in trigger_suggestions:
            k = f"{ts['statute']}_{ts['section_number']}"
            if k not in dedup_dict:
                dedup_dict[k] = {
                    "statute": ts["statute"],
                    "section_number": ts["section_number"],
                    "section_title": ts["section_title"],
                    "chapter_name": "Suggested Statutory Chapter",
                    "score": 0.85,
                    "suggested_tier": ts["candidate_type"],
                    "trigger_note": ts["trigger"],
                    "disqualified": False,
                    "disqualification_reason": None,
                }

        prefilter_json_str = json.dumps(list(dedup_dict.values()), indent=2)

        feedback_section = ""
        if correction_feedback:
            feedback_section = f"\nATTENTION - PREVIOUS STAGE 2 MAPPING AUDIT FEEDBACK:\n{correction_feedback}\n"

        user_prompt = STAGE2_MAPPING_USER_PROMPT_TEMPLATE.format(
            legal_query_json=query_json_str,
            prefilter_candidates_json=prefilter_json_str,
            correction_feedback_section=feedback_section,
        )

        messages = [
            SystemMessage(content=STAGE2_MAPPING_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]

        response = self.llm.invoke(messages)
        response_text = response.content if hasattr(response, "content") else str(response)

        extracted_dict = extract_json_from_text(response_text)

        # Validate with Stage2BatchedMappingResponse Pydantic schema
        mapping_response = Stage2BatchedMappingResponse.model_validate(extracted_dict)
        return mapping_response
