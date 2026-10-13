"""
Special Act Router Agent.

Reads instructions from special_act_routing_prompt.txt and evaluates the 8 Special Acts
against:
  - CASE FACTS
  - RETRIEVED IPC/BNS SECTIONS
  - RETRIEVED BSA SECTIONS
  - RETRIEVED BNSS SECTIONS

Produces structured ActRoutingDecisionItem for each Act (PROCESS, CANDIDATE, SKIP).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from langchain_core.messages import HumanMessage, SystemMessage

from ..config import extract_json_from_text, get_llm, MODEL_STAGE2
from ..schemas.stage_special_act import ActRoutingDecisionItem
from .special_act_repository import SPECIAL_ACT_TITLES

logger = logging.getLogger(__name__)


def _load_routing_prompt_instructions() -> str:
    """Loads system instructions from special_act_routing_prompt.txt."""
    candidates = [
        Path(__file__).parent / "special_act_routing_prompt.txt",
        Path("backend/lexigraphbe/act_router/special_act_routing_prompt.txt"),
        Path("lexigraphbe/act_router/special_act_routing_prompt.txt"),
        Path("act_router/special_act_routing_prompt.txt"),
    ]
    for p in candidates:
        if p.exists():
            try:
                with open(p, mode="r", encoding="utf-8-sig") as f:
                    return f.read()
            except Exception:
                pass
    return "You are an expert Indian Criminal Law Special Act Router. Decide which Special Acts apply."


class SpecialActRouterAgent:
    """
    Step 1 of the Act Router sub-pipeline.
    Determines which of the 8 Special Act documents deserve further processing.
    """

    def __init__(self, llm: Optional[Any] = None):
        self._llm = llm
        self.instructions = _load_routing_prompt_instructions()

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm(temperature=0.0, model_name=MODEL_STAGE2)
        return self._llm

    def run(
        self,
        case_facts: str,
        ipc_bns_sections: Optional[List[Dict[str, Any]]] = None,
        bsa_sections: Optional[List[Dict[str, Any]]] = None,
        bnss_sections: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[List[ActRoutingDecisionItem], List[str]]:
        """
        Executes Special Act routing decision.

        Args:
            case_facts: Complete factual narrative of the case.
            ipc_bns_sections: Verified IPC sections mapped to BNS from Stage 4.
            bsa_sections: Verified BSA sections mapped to IEA from Stage 3b.
            bnss_sections: Verified BNSS sections mapped to CrPC from Stage 3c.

        Returns:
            Tuple of (all_decisions: List[ActRoutingDecisionItem], selected_acts: List[str])
        """
        ipc_lines = []
        for s in (ipc_bns_sections or []):
            ipc_num = s.get("ipc_section") or s.get("section_number") or ""
            bns_num = s.get("bns_equivalent") or ""
            title = s.get("title") or s.get("section_title") or ""
            bns_part = f" -> BNS {bns_num}" if bns_num and bns_num != "N/A" else ""
            ipc_lines.append(f"- IPC Section {ipc_num} ({title}){bns_part}")
        ipc_text = "\n".join(ipc_lines) if ipc_lines else "None retrieved."

        bsa_lines = []
        for s in (bsa_sections or []):
            b_num = s.get("bsa_section") or s.get("section_number") or ""
            iea_num = s.get("iea_equivalent") or s.get("replaces_IEA") or ""
            heading = s.get("heading") or ""
            iea_part = f" [Replaces IEA {iea_num}]" if iea_num and iea_num != "None" else ""
            bsa_lines.append(f"- BSA Section {b_num}: {heading}{iea_part}")
        bsa_text = "\n".join(bsa_lines) if bsa_lines else "None retrieved."

        bnss_lines = []
        for s in (bnss_sections or []):
            bn_num = s.get("bnss_section") or s.get("section_number") or ""
            crpc_num = s.get("crpc_equivalent") or s.get("replaces_CrPC") or ""
            heading = s.get("heading") or ""
            crpc_part = f" [Replaces CrPC {crpc_num}]" if crpc_num and crpc_num != "None" else ""
            bnss_lines.append(f"- BNSS Section {bn_num}: {heading}{crpc_part}")
        bnss_text = "\n".join(bnss_lines) if bnss_lines else "None retrieved."

        user_content = f"""EVALUATE THE 8 SPECIAL ACTS FOR THE FOLLOWING CASE:

A. CASE FACTS:
\"\"\"
{case_facts}
\"\"\"

B. RETRIEVED IPC/BNS SECTIONS:
{ipc_text}

C. RETRIEVED BSA SECTIONS:
{bsa_text}

D. RETRIEVED BNSS SECTIONS:
{bnss_text}

E. SPECIAL-ACT DOCUMENT NAMES:
1. dowry_prohibition_act.json
2. indian_institutes_of_information_technology_act.json
3. itpa.json
4. juvenile_justice_act.json
5. pocso_act.json
6. posh_act.json
7. prohibition_of_child_marriage_act.json
8. sc_st_prevention_of_atrocities_act.json

Follow all instructions in your system prompt. For EACH of the 8 acts, decide 'PROCESS', 'CANDIDATE', or 'SKIP'.
Return STRICT JSON ONLY matching:
{{
  "act_routing": [
    {{
      "document": "pocso_act.json",
      "decision": "PROCESS" | "CANDIDATE" | "SKIP",
      "confidence": 0.95,
      "matched_facts": ["exact or closely paraphrased facts"],
      "reason": "short fact-grounded reason"
    }}, ...
  ]
}}
"""

        messages = [
            SystemMessage(content=self.instructions),
            HumanMessage(content=user_content),
        ]

        decisions: List[ActRoutingDecisionItem] = []
        selected_acts: List[str] = []

        try:
            resp = self.llm.invoke(messages)
            text_out = resp.content if hasattr(resp, "content") else str(resp)
            parsed = extract_json_from_text(text_out)
            items = parsed.get("act_routing", []) if isinstance(parsed, dict) else []

            for item in items:
                doc = str(item.get("document", "")).strip().lower()
                dec = str(item.get("decision", "SKIP")).strip().upper()
                conf = float(item.get("confidence", 0.9))
                matched = [str(x) for x in item.get("matched_facts", [])]
                reason = str(item.get("reason", ""))
                title = SPECIAL_ACT_TITLES.get(doc, doc)

                dec_obj = ActRoutingDecisionItem(
                    document=doc,
                    act_title=title,
                    decision=dec,
                    confidence=conf,
                    matched_facts=matched,
                    reason=reason,
                )
                decisions.append(dec_obj)

                if dec in ("PROCESS", "CANDIDATE"):
                    selected_acts.append(doc)

        except Exception as e:
            logger.error(f"Error during Special Act routing LLM call: {e}")
            # Safe fallback: check obvious keyword cues
            cf_lower = case_facts.lower()
            for doc, title in SPECIAL_ACT_TITLES.items():
                dec = "SKIP"
                reason = "No factual signal detected in fallback screening."
                if doc == "dowry_prohibition_act.json" and any(k in cf_lower for k in ["dowry", "stridhan", "marriage demand"]):
                    dec = "CANDIDATE"
                    reason = "Matrimonial/dowry demand mentioned in facts."
                elif doc == "pocso_act.json" and any(k in cf_lower for k in ["minor", "child", "pocso", "below 18"]):
                    dec = "CANDIDATE"
                    reason = "Child / minor victim mentioned in facts."
                elif doc == "posh_act.json" and any(k in cf_lower for k in ["workplace", "posh", "internal committee", "colleague"]):
                    dec = "CANDIDATE"
                    reason = "Workplace harassment signal detected."
                elif doc == "sc_st_prevention_of_atrocities_act.json" and any(k in cf_lower for k in ["sc/st", "caste", "dalit", "atrocity"]):
                    dec = "CANDIDATE"
                    reason = "Caste-based allegation signal detected."

                decisions.append(
                    ActRoutingDecisionItem(
                        document=doc,
                        act_title=title,
                        decision=dec,
                        confidence=0.7,
                        matched_facts=[],
                        reason=reason,
                    )
                )
                if dec in ("PROCESS", "CANDIDATE"):
                    selected_acts.append(doc)

        return decisions, selected_acts
