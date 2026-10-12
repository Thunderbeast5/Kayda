"""
Special Act Section Retrieval & Verification Agent.

Executes Step 2 (Zero-API candidate prefiltering from selected Special Act JSONs)
and Step 3 (Definition-grounded LLM evaluation & auditing).

Rules:
  - ZERO API CALL step prefilters candidates from the selected Special Act JSONs.
  - Candidate sections across selected acts are evaluated in a single LLM batch.
  - Evaluates live factual grounding; suppresses generic definitions/noise.
  - NO statutory ingredients evaluation and NO Neo4j mapping.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple, Union

from langchain_core.messages import HumanMessage, SystemMessage

from ..config import extract_json_from_text, get_llm, MODEL_STAGE2
from ..schemas.stage_special_act import (
    ActRoutingDecisionItem,
    SpecialActRetrievalObject,
    SpecialActSectionItem,
)
from .special_act_repository import SpecialActRepository
from .special_act_router_agent import SpecialActRouterAgent

logger = logging.getLogger(__name__)


STAGE_SPECIAL_ACT_SYSTEM_PROMPT = """You are a Senior Indian Criminal Law Specialist and Special Courts Judge evaluating Special Act candidate sections.

Your responsibility is to evaluate candidate sections prefiltered from selected Indian Special Acts against the provided case facts.

EVALUATION PRINCIPLES:
1. STRICT FACTUAL GROUNDING:
   - Accept a section (is_applicable: true) ONLY if there is a concrete, live factual allegation or procedural dispute directly governed by that section.
   - Ground your decision in the provided statutory text of the section.
   - Do NOT evaluate statutory ingredients (mens rea / actus reus breakdowns) — evaluate factual relevance.

2. REJECT GENERIC NOISE & INACTIVE DEFINITIONS:
   - Definitions (e.g. "Section 2: Definitions") should be REJECTED unless the interpretation of that specific defined term is directly in controversy.
   - Administrative sections (rule-making powers, notifications, board appointments) must be REJECTED.

3. STRUCTURED OUTPUT:
   For EACH candidate section, return:
   - "document": Source document name
   - "section_number": String
   - "is_applicable": true or false
   - "relevance_category": e.g. "SPECIAL_OFFENCE", "SPECIAL_PROCEDURE", "BURDEN_OF_PROOF", "PRESUMPTION", "SPECIAL_BAIL"
   - "reasoning": Specific fact-grounded explanation citing the case facts and statutory text.

Output valid JSON ONLY.
"""

STAGE_SPECIAL_ACT_USER_PROMPT_TEMPLATE = """Evaluate the following candidate Special Act sections against the case facts:

---
CASE FACTS:
\"\"\"
{case_facts}
\"\"\"
---

CANDIDATE SECTIONS TO EVALUATE:
{candidate_sections_text}
---

Evaluate every candidate section. For each section, decide if it should be ACCEPTED (is_applicable: true) or REJECTED (is_applicable: false).
Be rigorous: reject sections that are tangential, inactive definitions, or lack factual grounding.

Return your response in the following JSON format ONLY:
{{
  "evaluated_sections": [
    {{
      "document": "dowry_prohibition_act.json",
      "section_number": "3",
      "is_applicable": true,
      "relevance_category": "SPECIAL_OFFENCE",
      "reasoning": "Directly applies because the complaint alleges demand and taking of dowry prior to marriage."
    }}
  ]
}}
"""


class SpecialActRetrievalAgent:
    """
    Orchestrates the entire Special Act Router Sub-Pipeline:
    1. Act Routing Decision (8 acts) via SpecialActRouterAgent
    2. Zero-API-Call candidate prefilter per selected act
    3. Batched LLM Section Evaluation & Verification
    """

    def __init__(
        self,
        llm: Optional[Any] = None,
        router: Optional[SpecialActRouterAgent] = None,
        repo: Optional[SpecialActRepository] = None,
        top_k_per_act: int = 6,
    ):
        self._llm = llm
        self.router = router or SpecialActRouterAgent(llm=self._llm)
        self.repo = repo or SpecialActRepository.get_instance()
        self.top_k_per_act = top_k_per_act

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm(temperature=0.0, model_name=MODEL_STAGE2)
        return self._llm

    def run(
        self,
        case_facts: str,
        legal_concepts: Optional[List[str]] = None,
        ipc_bns_sections: Optional[List[Dict[str, Any]]] = None,
        bsa_sections: Optional[List[Dict[str, Any]]] = None,
        bnss_sections: Optional[List[Dict[str, Any]]] = None,
    ) -> SpecialActRetrievalObject:
        """
        Executes the Special Act routing and section retrieval sub-pipeline.
        """
        notes: List[str] = []

        # ── Step 1: Act Routing Decision ───────────────────────────────
        routing_decisions, selected_acts = self.router.run(
            case_facts=case_facts,
            ipc_bns_sections=ipc_bns_sections,
            bsa_sections=bsa_sections,
            bnss_sections=bnss_sections,
        )

        notes.append(f"Act router evaluated 8 special acts. Selected {len(selected_acts)}: {', '.join(selected_acts) if selected_acts else 'None'}")

        if not selected_acts:
            return SpecialActRetrievalObject(
                act_routing=routing_decisions,
                selected_acts=[],
                relevant_sections=[],
                rejected_sections=[],
                retrieval_notes=notes,
            )

        # ── Step 2: Zero-API-Call Candidate Prefilter ──────────────────
        all_candidates: List[Dict[str, Any]] = []
        for doc in selected_acts:
            cands = self.repo.prefilter_candidates(
                document_name=doc,
                facts_text=case_facts,
                concept_terms=legal_concepts,
                top_k=self.top_k_per_act,
            )
            all_candidates.extend(cands)

        if not all_candidates:
            notes.append("No candidate sections prefiltered from selected special acts.")
            return SpecialActRetrievalObject(
                act_routing=routing_decisions,
                selected_acts=selected_acts,
                relevant_sections=[],
                rejected_sections=[],
                retrieval_notes=notes,
            )

        # ── Step 3: Batched LLM Evaluation & Auditing ──────────────────
        candidate_text_lines = []
        for c in all_candidates:
            stat_snippet = c["text"][:350] if c.get("text") else ""
            candidate_text_lines.append(
                f"- Act: {c['act_title']} ({c['document']})\n"
                f"  Section {c['section_number']}: {c['heading']}\n"
                f"  Statutory text: {stat_snippet}\n"
            )
        cand_str = "\n".join(candidate_text_lines)

        user_prompt = STAGE_SPECIAL_ACT_USER_PROMPT_TEMPLATE.format(
            case_facts=case_facts[:2500],
            candidate_sections_text=cand_str,
        )

        accepted_sections: List[SpecialActSectionItem] = []
        rejected_sections: List[SpecialActSectionItem] = []

        try:
            resp = self.llm.invoke([
                SystemMessage(content=STAGE_SPECIAL_ACT_SYSTEM_PROMPT),
                HumanMessage(content=user_prompt),
            ])
            text_out = resp.content if hasattr(resp, "content") else str(resp)
            parsed = extract_json_from_text(text_out)
            evaluated = parsed.get("evaluated_sections", []) if isinstance(parsed, dict) else []

            for item in evaluated:
                doc = str(item.get("document", "")).strip().lower()
                s_num = str(item.get("section_number", "")).strip()
                is_app = bool(item.get("is_applicable", False))
                cat = str(item.get("relevance_category", "SPECIAL_OFFENCE")).upper()
                reason = str(item.get("reasoning", ""))

                # Find candidate metadata
                c_info = next((c for c in all_candidates if c["document"] == doc and c["section_number"] == s_num), None)
                if not c_info:
                    # Looser match on section number
                    c_info = next((c for c in all_candidates if c["section_number"] == s_num), None)
                if not c_info:
                    continue

                act_title = c_info.get("act_title") or self.repo.get_act_title(doc)
                heading = c_info.get("heading") or f"Section {s_num}"
                stat_text = c_info.get("text", "")[:400]

                sec_item = SpecialActSectionItem(
                    act_document=doc or c_info["document"],
                    act_title=act_title,
                    section_number=s_num,
                    heading=heading,
                    chapter_number=c_info.get("chapter_number"),
                    chapter_title=c_info.get("chapter_title"),
                    statutory_text=stat_text,
                    relevance_category=cat,
                    relevance_reason=reason,
                    verification_status="VERIFIED" if is_app else "REJECTED",
                    verification_reason=reason,
                    confidence_score=0.9 if is_app else 0.8,
                )

                if is_app:
                    accepted_sections.append(sec_item)
                else:
                    rejected_sections.append(sec_item)

        except Exception as e:
            logger.error(f"Error in Special Act candidate evaluation: {e}")
            notes.append(f"LLM candidate evaluation encountered error ({e}); using prefilter fallback.")
            for c in all_candidates[:5]:
                sec_item = SpecialActSectionItem(
                    act_document=c["document"],
                    act_title=c["act_title"],
                    section_number=c["section_number"],
                    heading=c["heading"],
                    chapter_number=c.get("chapter_number"),
                    chapter_title=c.get("chapter_title"),
                    statutory_text=c.get("text", "")[:400],
                    relevance_category="SPECIAL_OFFENCE",
                    relevance_reason="Factual match identified via candidate prefilter.",
                    verification_status="VERIFIED",
                    verification_reason="Candidate prefilter match.",
                )
                accepted_sections.append(sec_item)

        return SpecialActRetrievalObject(
            act_routing=routing_decisions,
            selected_acts=selected_acts,
            relevant_sections=accepted_sections,
            rejected_sections=rejected_sections,
            retrieval_notes=notes,
        )
