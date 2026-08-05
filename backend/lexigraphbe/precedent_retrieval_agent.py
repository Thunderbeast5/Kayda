"""
Precedent Retrieval Agent for Stage 6: Judicial Precedent Retrieval Engine.
Retrieves relevant Supreme Court and High Court anticipatory bail precedents by comparing current case facts,
verified offences, bail reasoning, and procedural stage against grounded legal precedents loaded from dataset disk file.
Uses MODEL_TIER_REASONING flagship model for deep precedent reasoning and similarity ranking over grounded corpus entries.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from langchain_core.messages import HumanMessage, SystemMessage

from .config import extract_json_from_text, get_llm_for_tier, MODEL_TIER_REASONING
from .prompts import STAGE6_PRECEDENT_RETRIEVAL_SYSTEM_PROMPT, STAGE6_PRECEDENT_RETRIEVAL_USER_PROMPT_TEMPLATE
from .schemas import BailReasoningObject, CaseContextObject, LegalQueryObject, PrecedentRetrievalObject, StatutoryVerificationObject


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
    Stage 6 Precedent Retrieval Agent retrieving landmark judicial precedents matching current case facts.
    Loads grounded precedents dataset from data/new/precedents_structured.json.
    Uses MODEL_TIER_REASONING flagship model for deep legal reasoning and similarity ranking.
    """

    def __init__(
        self,
        llm: Optional[Any] = None,
        corpus_path: Optional[str] = None,
        min_similarity_threshold: float = 0.70,
    ):
        self._llm = llm
        self.min_similarity_threshold = min_similarity_threshold
        self.corpus: List[Dict[str, Any]] = self._load_corpus(corpus_path)

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
        if isinstance(case_context, CaseContextObject):
            cco_json_str = case_context.to_downstream_json()
        elif isinstance(case_context, dict):
            cco_json_str = json.dumps(case_context, indent=2)
        else:
            cco_json_str = str(case_context)

        if isinstance(legal_query, LegalQueryObject):
            qo_json_str = legal_query.to_downstream_json()
        elif isinstance(legal_query, dict):
            qo_json_str = json.dumps(legal_query, indent=2)
        else:
            qo_json_str = str(legal_query)

        if isinstance(statutory_object, StatutoryVerificationObject):
            svo_json_str = statutory_object.to_downstream_json()
        elif isinstance(statutory_object, dict):
            svo_json_str = json.dumps(statutory_object, indent=2)
        else:
            svo_json_str = str(statutory_object)

        if isinstance(bail_object, BailReasoningObject):
            bro_json_str = bail_object.to_downstream_json()
        elif isinstance(bail_object, dict):
            bro_json_str = json.dumps(bail_object, indent=2)
        else:
            bro_json_str = str(bail_object)

        # Grounded precedent dataset passed to prompt
        corpus_json_str = json.dumps(self.corpus, indent=2)

        feedback_section = ""
        if correction_feedback:
            feedback_section = f"\nATTENTION - PREVIOUS PRECEDENT RETRIEVAL AUDIT FEEDBACK:\n{correction_feedback}\n"

        user_prompt = STAGE6_PRECEDENT_RETRIEVAL_USER_PROMPT_TEMPLATE.format(
            case_context_json=cco_json_str,
            legal_query_json=qo_json_str,
            statutory_object_json=svo_json_str,
            bail_object_json=bro_json_str,
            judgment_corpus_json=corpus_json_str,
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

        # Check similarity cutoff (< 0.70 threshold)
        for precedent in prec_obj.precedents:
            if precedent.similarity_score < self.min_similarity_threshold:
                note = f"Precedent '{precedent.case_name}' similarity score {precedent.similarity_score:.2f} < cutoff {self.min_similarity_threshold}."
                if note not in prec_obj.manual_review:
                    prec_obj.manual_review.append(note)

        # Sort precedents by similarity_score descending
        prec_obj.precedents.sort(key=lambda x: x.similarity_score, reverse=True)

        return prec_obj
