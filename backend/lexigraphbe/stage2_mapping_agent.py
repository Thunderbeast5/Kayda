"""
Stage 2 Sub-Query to Chapter Candidate Mapping Agent.
Maps decomposed sub-queries ($SQ_1, SQ_2, \\dots, SQ_N$) from Stage 1 to candidate statutory chapters and sections
using local StatuteClassifierPrefilter candidates in ONE single batched LLM request.
"""

import json
from typing import Any, Dict, Optional, Union
from langchain_core.messages import HumanMessage, SystemMessage

from .config import extract_json_from_text, get_llm_for_tier, MODEL_TIER_CHEAP
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
            self._llm = get_llm_for_tier(tier=MODEL_TIER_CHEAP, temperature=0.1)
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

        # Step 1: Run local StatuteClassifierPrefilter (0 API calls)
        prefiltered_matches = []
        regime = query_obj.legal_regime or "IPC + CrPC"
        statute_type = "BNS" if "BNS" in regime.upper() else "IPC"

        for concept_item in query_obj.legal_concepts:
            matches = self.prefilter.prefilter_candidates(
                query_text=concept_item.concept,
                statute_type=statute_type,
                top_k=10,
            )
            prefiltered_matches.extend(matches)

        # Deduplicate pre-filter matches
        dedup_dict = {}
        for m in prefiltered_matches:
            k = f"{m.statute_type}_{m.section_number}"
            if k not in dedup_dict or m.score > dedup_dict[k]["score"]:
                dedup_dict[k] = {
                    "statute": m.statute_type,
                    "section_number": m.section_number,
                    "section_title": m.section_title,
                    "chapter_name": m.chapter_name,
                    "score": round(m.score, 4),
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
