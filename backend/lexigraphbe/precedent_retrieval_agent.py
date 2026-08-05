"""
Precedent Retrieval Agent for Stage 6: Judicial Precedent Retrieval Engine.
Retrieves relevant Supreme Court and High Court anticipatory bail precedents by computing real mathematical
TF-IDF vector cosine similarity and Jaccard offence set overlap in Python code (PrecedentSimilarityMatcher).
Uses MODEL_TIER_REASONING flagship model for deep ratio decidendi extraction over mathematically matched precedents.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from langchain_core.messages import HumanMessage, SystemMessage

from .config import extract_json_from_text, get_llm_for_tier, MODEL_TIER_REASONING
from .prompts import STAGE6_PRECEDENT_RETRIEVAL_SYSTEM_PROMPT, STAGE6_PRECEDENT_RETRIEVAL_USER_PROMPT_TEMPLATE
from .schemas import BailReasoningObject, CaseContextObject, LegalQueryObject, PrecedentRetrievalObject, StatutoryVerificationObject
from .precedent_matcher import PrecedentSimilarityMatcher


def load_precedents_corpus() -> List[Dict[str, Any]]:
    """
    Loads grounded judicial precedents dataset from data/new/precedents_structured.json.
    Falls back to inline dataset if file is inaccessible.
    """
    candidate_paths = [
        Path("data/new/precedents_structured.json"),
        Path("../data/new/precedents_structured.json"),
        Path("c:/MootCourt/data/new/precedents_structured.json"),
    ]
    for p in candidate_paths:
        if p.exists():
            try:
                with open(p, mode="r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list) and len(data) > 0:
                        return data
            except Exception:
                pass
    return [
        {
            "case_id": "PREC_SC_001",
            "case_name": "Arnesh Kumar v. State of Bihar",
            "court": "Supreme Court of India",
            "citation": "(2014) 8 SCC 273",
            "year": 2014,
            "offences_covered": ["498A IPC", "4 Dowry Prohibition Act", "85 BNS"],
            "procedural_stage": "Anticipatory Bail",
            "bail_outcome": "Anticipatory Bail Guidelines Formulated",
            "facts_summary": "Allegations of matrimonial cruelty and dowry harassment under Section 498A IPC.",
            "ratio_decidendi": "Arrest should not be automatic in offences punishable with imprisonment up to seven years; compliance with Section 41A CrPC / Section 35 BNSS notice is mandatory prior to arrest."
        }
    ]


class PrecedentRetrievalAgent:
    """
    Stage 6 Precedent Retrieval Agent retrieving landmark judicial precedents.
    Integrates local PrecedentSimilarityMatcher (TF-IDF vector cosine + Jaccard similarity) for real mathematical scoring.
    Uses MODEL_TIER_REASONING flagship model for deep ratio decidendi extraction over mathematically matched precedents.
    """

    def __init__(
        self,
        llm: Optional[Any] = None,
        corpus_path: Optional[str] = None,
        matcher: Optional[PrecedentSimilarityMatcher] = None,
        min_similarity_threshold: float = 0.70,
    ):
        self._llm = llm
        self.min_similarity_threshold = min_similarity_threshold
        self.corpus: List[Dict[str, Any]] = self._load_corpus(corpus_path)
        self.matcher = matcher or PrecedentSimilarityMatcher()

    def _load_corpus(self, custom_path: Optional[str] = None) -> List[Dict[str, Any]]:
        if custom_path:
            p = Path(custom_path)
            if p.exists():
                with open(p, mode="r", encoding="utf-8") as f:
                    return json.load(f)
        return load_precedents_corpus()

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm_for_tier(tier=MODEL_TIER_REASONING, temperature=0.1)
        return self._llm

    def run(
        self,
        case_context: Union[CaseContextObject, Dict[str, Any], str],
        legal_query: Union[LegalQueryObject, Dict[str, Any], str],
        statutory_object: Union[StatutoryVerificationObject, Dict[str, Any], str],
        bail_object: Union[BailReasoningObject, Dict[str, Any], str],
        correction_feedback: Optional[str] = None,
    ) -> PrecedentRetrievalObject:
        """
        Runs Stage 6 Precedent Retrieval on Stage 0, Stage 1, Stage 4, and Stage 5 verified objects.

        Returns:
            PrecedentRetrievalObject instance.
        """
        # Standardize inputs
        cco_obj = case_context if isinstance(case_context, CaseContextObject) else CaseContextObject.model_validate(case_context if isinstance(case_context, dict) else json.loads(str(case_context)))
        qo_obj = legal_query if isinstance(legal_query, LegalQueryObject) else LegalQueryObject.model_validate(legal_query if isinstance(legal_query, dict) else json.loads(str(legal_query)))
        svo_obj = statutory_object if isinstance(statutory_object, StatutoryVerificationObject) else StatutoryVerificationObject.model_validate(statutory_object if isinstance(statutory_object, dict) else json.loads(str(statutory_object)))
        bro_obj = bail_object if isinstance(bail_object, BailReasoningObject) else BailReasoningObject.model_validate(bail_object if isinstance(bail_object, dict) else json.loads(str(bail_object)))

        cco_json_str = cco_obj.to_downstream_json()
        qo_json_str = qo_obj.to_downstream_json()
        svo_json_str = svo_obj.to_downstream_json()
        bro_json_str = bro_obj.to_downstream_json()

        # Step 1: Run local mathematical similarity matcher (TF-IDF vector cosine + Jaccard scoring)
        math_matches = self.matcher.rank_precedents(
            case_context=cco_obj,
            legal_query=qo_obj,
            statutory_object=svo_obj,
            bail_object=bro_obj,
            precedents_corpus=self.corpus,
            top_k=5,
        )

        matched_corpus_json_str = json.dumps([m.model_dump() for m in math_matches], indent=2)

        feedback_section = ""
        if correction_feedback:
            feedback_section = f"\nATTENTION - PREVIOUS PRECEDENT RETRIEVAL AUDIT FEEDBACK:\n{correction_feedback}\n"

        user_prompt = STAGE6_PRECEDENT_RETRIEVAL_USER_PROMPT_TEMPLATE.format(
            case_context_json=cco_json_str,
            legal_query_json=qo_json_str,
            statutory_object_json=svo_json_str,
            bail_object_json=bro_json_str,
            judgment_corpus_json=matched_corpus_json_str,
            correction_feedback_section=feedback_section,
        )

        messages = [
            SystemMessage(content=STAGE6_PRECEDENT_RETRIEVAL_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]

        response = self.llm.invoke(messages)
        response_text = response.content if hasattr(response, "content") else str(response)

        extracted_dict = extract_json_from_text(response_text)

        # Validate with PrecedentRetrievalObject Pydantic schema
        prec_obj = PrecedentRetrievalObject.model_validate(extracted_dict)

        # Enforce exact mathematical similarity scores calculated by PrecedentSimilarityMatcher
        score_map = {m.case_name.lower(): m.computed_similarity_score for m in math_matches}
        for precedent in prec_obj.precedents:
            c_name = precedent.case_name.lower()
            if c_name in score_map:
                precedent.similarity_score = score_map[c_name]

            if precedent.similarity_score < self.min_similarity_threshold:
                note = f"Precedent '{precedent.case_name}' mathematical similarity score {precedent.similarity_score:.2f} < cutoff {self.min_similarity_threshold}."
                if note not in prec_obj.manual_review:
                    prec_obj.manual_review.append(note)

        # Sort precedents by mathematical similarity_score descending
        prec_obj.precedents.sort(key=lambda x: x.similarity_score, reverse=True)

        return prec_obj
