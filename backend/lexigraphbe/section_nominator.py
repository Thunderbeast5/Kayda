"""
Stage 2 section nomination (1 LLM call).

Lexical retrieval cannot connect facts to statutes that share no words with them ("allowing heavy vehicles
despite warnings" vs "so rashly or negligently as to endanger human life"); it ends up ranking on filler words.
Once Stage 1 has chosen offence families, the candidate space is small (typically 20-80 sections), so the LLM is
shown every section of those families with its ipc.json ingredients and nominates the ones that apply, each
with its own tier. BM25 retrieval remains the fallback when this call fails.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from .config import MODEL_STAGE2, extract_json_from_text, get_llm
from .family_retrieval import OFFENCE_FAMILIES, _obj, get_family_retriever
from .prompts import STAGE2_NOMINATION_SYSTEM_PROMPT, STAGE2_NOMINATION_USER_PROMPT_TEMPLATE
from .statute_repository import StatuteRepository

_TIERS = {"PRIMARY", "SECONDARY", "CONDITIONAL"}


def _section_line(sec: str, title: str, statute_db: Dict[str, Any], max_chars: int = 260) -> str:
    rec = statute_db.get(f"IPC_{sec}") or {}
    ings = rec.get("ingredients") or []
    if not ings:
        from .statutory_verification_agent import _linked_definition_ingredients
        ings = _linked_definition_ingredients(sec, statute_db)
    ing_text = "; ".join(str(i) for i in ings)
    if len(ing_text) > max_chars:
        ing_text = ing_text[:max_chars].rsplit(" ", 1)[0] + " ..."
    return f"  {sec} | {title}" + (f" | ingredients: {ing_text}" if ing_text else "")


_INTENT_OR_KNOWLEDGE = re.compile(
    r"\b(intent\w*|intend\w*|knowing\w*|knowledge|knows|reason to believe|dishonest\w*|fraudulent\w*|"
    r"voluntarily|wilful\w*|malicious\w*|deliberate\w*)\b", re.IGNORECASE)


def _requires_intent_or_knowledge(sec: str, statute_db: Dict[str, Any], retriever: Any, _depth: int = 0) -> bool:
    """True when the section's ingredients name intention or knowledge and it is not a rash/negligence offence.
    Derived offences inherit the requirement from the offence they build on ("Commission of mischief" -> 425)."""
    if sec in retriever.negligence_sections:
        return False
    ings = (statute_db.get(f"IPC_{sec}") or {}).get("ingredients") or []
    if not ings:
        from .statutory_verification_agent import _linked_definition_ingredients
        ings = _linked_definition_ingredients(sec, statute_db)
    text = " ".join(str(i) for i in ings)
    if _INTENT_OR_KNOWLEDGE.search(text):
        return True
    if _depth == 0:
        return any(_requires_intent_or_knowledge(ref, statute_db, retriever, 1)
                   for ref in referenced_offences(text, retriever) if ref != sec)
    return False


def referenced_offences(text: str, retriever: Any) -> List[str]:
    """Sections an ingredient text builds on: explicit "(Section 425)" / "s. 268", or a named base offence
    ("commission of mischief") matched against short IPC offence titles."""
    refs = [m.upper() for m in re.findall(r"\b(?:section|s\.)\s*(\d+[A-Z]*)", text, re.IGNORECASE)]
    low = text.lower()
    for name, sec in retriever.offence_names.items():
        if re.search(rf"\b(?:commission of|commits?|committing)\s+(?:a\s+|an\s+)?{re.escape(name)}\b", low):
            refs.append(sec)
    return [r for r in dict.fromkeys(refs) if r in retriever.idx_by_sec]


class SectionNominator:
    def __init__(self, llm: Optional[Any] = None):
        self._llm = llm

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm(temperature=0.0, model_name=MODEL_STAGE2)
        return self._llm

    def build_prompt(self, query_obj: Any) -> Optional[str]:
        r = get_family_retriever()
        statute_db = StatuteRepository.get_instance().get_statute_db() or {}
        facts = list(_obj(query_obj, "factual_allegations", []) or [])
        families = list(_obj(query_obj, "offence_families", []) or [])
        if not facts or not families:
            return None
        facts_block = "\n".join(
            f"  {_obj(f, 'fact_id', '')} [{_obj(f, 'conduct_type', '')}, actor: {_obj(f, 'actor', None) or 'not stated'}]: "
            f"\"{_obj(f, 'verbatim_quote', '') or _obj(f, 'description', '')}\""
            for f in facts
        )
        menu = []
        for fam in families:
            code = str(_obj(fam, "family", "")).upper()
            if code not in OFFENCE_FAMILIES:
                continue
            lines = [_section_line(r.records[i]["section_number"], r.records[i].get("title") or "", statute_db)
                     for i in r.family_members.get(code, [])]
            menu.append(
                f"FAMILY {code} (facts {', '.join(map(str, _obj(fam, 'fact_ids', []) or []))}; "
                f"alleged fault: {_obj(fam, 'fault_mode', 'UNSTATED') or 'UNSTATED'}):\n" + "\n".join(lines)
            )
        if not menu:
            return None
        return STAGE2_NOMINATION_USER_PROMPT_TEMPLATE.format(facts_block=facts_block, menu_block="\n\n".join(menu))

    def run(self, query_obj: Any) -> Optional[Dict[str, List[Dict[str, Any]]]]:
        """Returns {family_code: [nomination, ...]} or None when nomination is unavailable (caller falls back to BM25)."""
        user_prompt = self.build_prompt(query_obj)
        if not user_prompt:
            return None
        r = get_family_retriever()
        try:
            resp = self.llm.invoke([SystemMessage(content=STAGE2_NOMINATION_SYSTEM_PROMPT), HumanMessage(content=user_prompt)])
            parsed = extract_json_from_text(resp)
        except Exception as e:
            print(f"[SectionNominator] nomination failed, using BM25 retrieval only: {e}", flush=True)
            return None
        items = parsed.get("nominations") if isinstance(parsed, dict) else None
        if not isinstance(items, list):
            print("[SectionNominator] no 'nominations' list in output, using BM25 retrieval only", flush=True)
            return None
        fact_ids = {str(_obj(f, "fact_id", "")) for f in (_obj(query_obj, "factual_allegations", []) or [])}
        faults = {str(_obj(f, "fault_mode", "") or "").upper() for f in (_obj(query_obj, "offence_families", []) or [])}
        negligence_only = "RASH_OR_NEGLIGENT" in faults and not faults & {"INTENTIONAL", "KNOWING"}
        statute_db = StatuteRepository.get_instance().get_statute_db() or {}
        out: Dict[str, List[Dict[str, Any]]] = {}
        for it in items:
            if not isinstance(it, dict):
                continue
            code = str(it.get("family", "")).upper()
            sec = str(it.get("section", "")).strip().upper().replace("SECTION ", "").replace("IPC ", "")
            members = {r.records[i]["section_number"] for i in r.family_members.get(code, [])}
            if sec not in members:
                continue  # only sections from the family list shown; never an invented number
            tier = str(it.get("tier", "")).upper()
            tier = tier if tier in _TIERS else "CONDITIONAL"
            missing = it.get("missing_element")
            if negligence_only and tier != "CONDITIONAL" and _requires_intent_or_knowledge(sec, statute_db, r):
                tier = "CONDITIONAL"
                missing = "intention or knowledge (the facts allege rash or negligent conduct only)"
            out.setdefault(code, []).append({
                "section": sec,
                "tier": tier,
                "fact_ids": [str(x) for x in (it.get("fact_ids") or []) if str(x) in fact_ids],
                "missing_element": missing,
                "reason": str(it.get("reason") or "")[:200],
            })
        return out or None
