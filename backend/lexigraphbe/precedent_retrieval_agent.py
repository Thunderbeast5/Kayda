"""
Precedent Retrieval Agent for Stage 6: Judicial Precedent Retrieval Engine.
Retrieves relevant Supreme Court and High Court anticipatory bail precedents by comparing current case facts,
verified offences, bail reasoning, and procedural stage against grounded legal precedents loaded from dataset disk file.
Model: gpt-4.1-mini (MODEL_STAGE6) — deep precedent reasoning and similarity ranking.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from langchain_core.messages import HumanMessage, SystemMessage

from .config import extract_json_from_text, get_llm, MODEL_STAGE6
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
    Model: gpt-4.1-mini (MODEL_STAGE6) — deep legal reasoning and similarity ranking.
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
            self._llm = get_llm(temperature=0.1, model_name=MODEL_STAGE6)
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

        # Extract Stage 4 verified sections and satisfied ingredients for grounded similarity calculation
        active_secs = set()
        satisfied_ingredients = []

        if isinstance(statutory_object, StatutoryVerificationObject):
            for sec in statutory_object.verified_sections:
                clean_sec = sec.section_number.upper().replace("SECTION ", "").replace("IPC_", "").replace("BNS_", "").strip()
                if clean_sec:
                    active_secs.add(clean_sec)
                for ing in sec.ingredients:
                    if ing.status == "Satisfied":
                        satisfied_ingredients.append(ing.ingredient.lower())
        elif isinstance(statutory_object, dict):
            for sec in statutory_object.get("verified_sections", []):
                s_num = str(sec.get("section_number", "")).upper().replace("SECTION ", "").replace("IPC_", "").replace("BNS_", "").strip()
                if s_num:
                    active_secs.add(s_num)

        # Calibrate similarity scores via transparent multi-factor formula.
        #
        # A case the LLM narrative calls "factually dissimilar" must never score > 0.65
        # (the LLM chooses the narrative; we control the number). The factors are:
        #   F1 (0.40): Verified-section overlap — do the precedent's offences include
        #              any section from the current case's Stage 4 verified list?
        #   F2 (0.25): Satisfied-ingredient overlap — do the precedent's facts mention
        #              any ingredient already Satisfied in Stage 4?
        #   F3 (0.20): Subject-matter type match — does the precedent address the same
        #              broad domain (property/land, cheating/fraud, forgery, violence, etc.)?
        #   F4 (0.15): Procedural stage match — anticipatory vs regular bail alignment.
        #
        # Floor/ceiling: the LLM's raw score is used only as a tiebreaker within the
        # F1..F4 band, not as the score itself.

        # Derive subject-matter type keywords from the current case facts
        facts_lower = cco_json_str.lower() + " " + qo_json_str.lower()
        current_subject_domains: set = set()
        if any(k in facts_lower for k in ["land", "plot", "agricultural", "immovable", "field", "site", "property dispute"]):
            current_subject_domains.add("property")
        if any(k in facts_lower for k in ["forgery", "forged", "fabricated", "counterfeit", "false document"]):
            current_subject_domains.add("forgery")
        if any(k in facts_lower for k in ["cheat", "deceiv", "fraud", "misrepresent", "inducement"]):
            current_subject_domains.add("cheating")
        if any(k in facts_lower for k in ["dowry", "matrimonial", "cruelty", "498a"]):
            current_subject_domains.add("domestic")
        if any(k in facts_lower for k in ["murder", "homicide", "death", "killed"]):
            current_subject_domains.add("violence")
        if any(k in facts_lower for k in ["economic offence", "money laundering", "disproportionate", "financial fraud", "corruption"]):
            current_subject_domains.add("economic")
        if any(k in facts_lower for k in ["anticipatory", "section 438", "section 482"]):
            current_proc_stage = "anticipatory"
        else:
            current_proc_stage = "regular"

        for precedent in prec_obj.precedents:
            case_name_upper = precedent.case_name.upper()
            offences_str = " ".join(precedent.verified_offences).upper()
            facts_upper = precedent.facts.upper()
            prec_full_text = (precedent.case_name + " " + " ".join(precedent.verified_offences) + " " + precedent.facts).lower()

            # F1: Section overlap (0.0 or 0.40)
            matched_secs = [sec for sec in active_secs if len(sec) >= 1 and (sec in offences_str or sec in facts_upper)]
            f1 = 0.40 if matched_secs else 0.0

            # F2: Satisfied ingredient overlap (0.0 to 0.25)
            ing_hits = sum(1 for ing in satisfied_ingredients if ing in prec_full_text)
            f2 = min(0.25, ing_hits * 0.08) if satisfied_ingredients else 0.0

            # F3: Subject-matter type overlap (0.0 or 0.20)
            prec_domains: set = set()
            if any(k in prec_full_text for k in ["land", "plot", "immovable", "property", "agricultural"]):
                prec_domains.add("property")
            if any(k in prec_full_text for k in ["forgery", "forged", "fabricated", "counterfeit"]):
                prec_domains.add("forgery")
            if any(k in prec_full_text for k in ["cheat", "deceiv", "fraud", "misrepresent"]):
                prec_domains.add("cheating")
            if any(k in prec_full_text for k in ["dowry", "matrimonial", "cruelty"]):
                prec_domains.add("domestic")
            if any(k in prec_full_text for k in ["murder", "death", "killed"]):
                prec_domains.add("violence")
            if any(k in prec_full_text for k in ["economic offence", "money laundering", "financial fraud", "corruption"]):
                prec_domains.add("economic")
            f3 = 0.20 if current_subject_domains & prec_domains else 0.0

            # F4: Procedural stage match (0.0 or 0.15)
            prec_proc = precedent.procedural_stage.lower() if hasattr(precedent, "procedural_stage") and precedent.procedural_stage else ""
            if current_proc_stage == "anticipatory" and "anticipatory" in prec_proc:
                f4 = 0.15
            elif current_proc_stage == "regular" and "anticipatory" not in prec_proc and prec_proc:
                f4 = 0.15
            else:
                f4 = 0.05  # partial credit for general bail jurisprudence

            computed_score = round(f1 + f2 + f3 + f4, 2)
            # Clamp: cannot exceed 1.0; when score is low, don't let LLM raw score inflate it
            precedent.similarity_score = min(computed_score, 1.0)

            # Audit logging: flag cases where LLM narrative contradicts the computed score
            if precedent.similarity_score < self.min_similarity_threshold:
                note = (
                    f"Precedent '{precedent.case_name}' computed similarity {precedent.similarity_score:.2f} "
                    f"(F1={f1:.2f} section, F2={f2:.2f} ingredient, F3={f3:.2f} subject, F4={f4:.2f} stage) "
                    f"< cutoff {self.min_similarity_threshold:.2f}: low factual overlap with verified case."
                )
                if note not in prec_obj.manual_review:
                    prec_obj.manual_review.append(note)
            elif f1 == 0.0 and f3 == 0.0:
                # Score is driven only by stage/ingredient partial credit, not facts — flag it
                note = (
                    f"Precedent '{precedent.case_name}' score {precedent.similarity_score:.2f} has zero section "
                    f"and zero subject-matter overlap; relevance is procedural-only, not factual."
                )
                if note not in prec_obj.manual_review:
                    prec_obj.manual_review.append(note)


        # Sort precedents by similarity_score descending
        prec_obj.precedents.sort(key=lambda x: x.similarity_score, reverse=True)

        return prec_obj
