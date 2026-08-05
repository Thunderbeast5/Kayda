"""
Chapter Identification Agent for Stage 3: IPC/BNS Chapter & Section Title Identification.
Identifies relevant IPC/BNS chapters and candidate section titles from lightweight index.
Zero statutory body text (no explanations, illustrations, punishments, exceptions, or provisos).
Uses MODEL_TIER_CHEAP lightweight model for index shortlisting.
"""

import json
from typing import Any, Dict, Optional, Union
from langchain_core.messages import HumanMessage, SystemMessage

from .config import extract_json_from_text, get_llm_for_tier, MODEL_TIER_CHEAP
from .classifier_prefilter import StatuteClassifierPrefilter
from .prompts import STAGE3_CHAPTER_IDENTIFICATION_SYSTEM_PROMPT, STAGE3_CHAPTER_IDENTIFICATION_USER_PROMPT_TEMPLATE
from .schemas import ChapterIdentificationObject, LegalQueryObject


class ChapterIdentificationAgent:
    """
    Stage 3 Chapter Identification Agent mapping Stage 1 legal concepts to
    candidate chapters and section titles using lightweight index matching.
    """

    def __init__(
        self,
        llm: Optional[Any] = None,
        min_confidence_threshold: float = 0.70,
        prefilter: Optional[StatuteClassifierPrefilter] = None,
    ):
        self._llm = llm
        self.min_confidence_threshold = min_confidence_threshold
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
    ) -> ChapterIdentificationObject:
        """
        Processes Stage 1 LegalQueryObject and returns shortlisted ChapterIdentificationObject.

        Args:
            legal_query: Stage 1 LegalQueryObject instance or JSON string.
            correction_feedback: Feedback from ChapterVerificationAgent if retrying.

        Returns:
            ChapterIdentificationObject instance.
        """
        # Standardize input
        if isinstance(legal_query, LegalQueryObject):
            query_obj = legal_query
            query_json_str = legal_query.to_downstream_json()
        elif isinstance(legal_query, dict):
            query_obj = LegalQueryObject.model_validate(legal_query)
            query_json_str = json.dumps(legal_query, indent=2)
        elif isinstance(legal_query, str):
            parsed = json.loads(legal_query)
            query_obj = LegalQueryObject.model_validate(parsed)
            query_json_str = legal_query
        else:
            raise ValueError(f"Invalid legal_query type: {type(legal_query)}")

        # Step 1: Pre-filter candidate sections locally using StatuteClassifierPrefilter (0 LLM calls)
        candidates = self.prefilter.shortlist_candidates_for_query(
            query_obj,
            top_k=15,
            target_regime=query_obj.legal_regime,
        )
        candidates_dict_list = [c.model_dump() for c in candidates]
        index_candidates_json = json.dumps(candidates_dict_list, indent=2)

        # Step 2: Build LLM prompt for batched index shortlisting
        feedback_section = ""
        if correction_feedback:
            feedback_section = f"\nATTENTION - PREVIOUS CHAPTER VERIFICATION FEEDBACK FOR CORRECTION:\n{correction_feedback}\n"

        user_prompt = STAGE3_CHAPTER_IDENTIFICATION_USER_PROMPT_TEMPLATE.format(
            legal_query_json=query_json_str,
            index_candidates_json=index_candidates_json,
            correction_feedback_section=feedback_section,
        )

        messages = [
            SystemMessage(content=STAGE3_CHAPTER_IDENTIFICATION_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]

        response = self.llm.invoke(messages)
        response_text = response.content if hasattr(response, "content") else str(response)

        extracted_dict = extract_json_from_text(response_text)

        # Validate with ChapterIdentificationObject Pydantic schema
        chapter_obj = ChapterIdentificationObject.model_validate(extracted_dict)

        # Passthrough legal_regime from Stage 1 LegalQueryObject
        chapter_obj.legal_regime = query_obj.legal_regime

        # Evaluate confidence cutoffs (< 0.70 threshold)
        for chap_cand in chapter_obj.chapter_candidates:
            if chap_cand.confidence < self.min_confidence_threshold:
                warning = f"Chapter candidate '{chap_cand.chapter_name}' ({chap_cand.chapter_number}) confidence {chap_cand.confidence:.2f} < cutoff {self.min_confidence_threshold}."
                if warning not in chapter_obj.manual_review:
                    chapter_obj.manual_review.append(warning)

        for sec_cand in chapter_obj.section_candidates:
            if sec_cand.confidence < self.min_confidence_threshold:
                warning = f"Section candidate '{sec_cand.section_title}' (Section {sec_cand.section_number}) confidence {sec_cand.confidence:.2f} < cutoff {self.min_confidence_threshold}."
                if warning not in chapter_obj.manual_review:
                    chapter_obj.manual_review.append(warning)

        # Sort section candidates by confidence descending
        chapter_obj.section_candidates.sort(key=lambda x: x.confidence, reverse=True)

        return chapter_obj
