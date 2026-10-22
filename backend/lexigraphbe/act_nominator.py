"""
BSA / BNSS section nomination (1 LLM call per act).

Same approach as section_nominator.py for IPC: keyword clusters and anchor lists cannot tell which evidence or
procedure provisions a case raises, so the LLM is shown every section heading of the act (bsa.json / bnss.json,
grouped by chapter) together with the facts and context, and nominates sections. Every returned number is
checked against the act; anything not in it is discarded. The callers fall back to their keyword path when this
call fails.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from .config import MODEL_STAGE2, extract_json_from_text, get_llm
from .prompts import ACT_NOMINATION_USER_PROMPT_TEMPLATE, BNSS_NOMINATION_SYSTEM_PROMPT, BSA_NOMINATION_SYSTEM_PROMPT
from .statute_repository import StatuteRepository

_ACTS = {
    "BSA": {
        "system": BSA_NOMINATION_SYSTEM_PROMPT,
        "applicability": ["DIRECT", "CONTEXTUAL"],
        "categories": ["DOCUMENTARY", "ELECTRONIC_RECORDS", "EXPERT_OPINION", "ORAL_EVIDENCE", "CONFESSION_ADMISSION",
                       "PRESUMPTION_BURDEN", "RELEVANCY", "OTHER"],
    },
    "BNSS": {
        "system": BNSS_NOMINATION_SYSTEM_PROMPT,
        "applicability": ["DIRECT", "CONTEXTUAL", "ANCILLARY"],
        "categories": ["ANTICIPATORY_BAIL", "REGULAR_BAIL", "DEFAULT_BAIL", "ARREST_PROCEDURE", "NOTICE_OF_APPEARANCE",
                       "CUSTODY_REMAND", "BAIL_CONDITIONS", "INVESTIGATION", "GENERAL_PROCEDURE"],
    },
}


def _sections(act: str) -> List[Dict[str, Any]]:
    repo = StatuteRepository.get_instance()
    rows = repo.get_bsa_sections_db() if act == "BSA" else repo.get_bnss_sections_db()
    out = []
    for r in rows or []:
        raw = r.get("raw_section") or {}
        if raw.get("is_omitted") or raw.get("is_repealed"):
            continue
        out.append(r)
    return out


def facts_block_from(query_obj: Any) -> str:
    """Numbered allegations (including the accused's statements) from a Stage 1 object or dict."""
    q = query_obj if isinstance(query_obj, dict) else (query_obj.model_dump() if hasattr(query_obj, "model_dump") else {})
    facts = q.get("factual_allegations") or []
    if facts:
        return "\n".join(
            f"  {f.get('fact_id', '')} [{f.get('conduct_type', '')}]: \"{f.get('verbatim_quote') or f.get('description') or ''}\""
            for f in facts
        )
    return f"  {q.get('case_facts') or ''}"


def offences_block_from(verified_offences: Optional[List[Dict[str, Any]]]) -> str:
    lines = []
    for o in verified_offences or []:
        p = o.get("punishment") or {}
        lines.append(
            f"  IPC {o.get('section_number')} {o.get('title') or o.get('section_title') or ''} "
            f"[{o.get('classification', '')}; max {p.get('maximum') or 'unknown'}; "
            f"{'cognizable' if o.get('cognizable') else 'non-cognizable'}; {'bailable' if o.get('bailable') else 'non-bailable'}]"
        )
    return "\n".join(lines) if lines else "  (not yet determined)"


class ActSectionNominator:
    def __init__(self, act: str, llm: Optional[Any] = None):
        if act not in _ACTS:
            raise ValueError(f"Unsupported act: {act}")
        self.act = act
        self._llm = llm

    @property
    def llm(self):
        if self._llm is None:
            # MODEL_NOMINATION lets these small, high-leverage calls use a stronger model than the rest of Stage 2.
            self._llm = get_llm(temperature=0.0, model_name=os.getenv("MODEL_NOMINATION") or MODEL_STAGE2)
        return self._llm

    def menu(self) -> str:
        blocks: List[str] = []
        current = None
        for r in _sections(self.act):
            chap = (r.get("chapter_number") or "", r.get("chapter_title") or "")
            if chap != current:
                blocks.append(f"Chapter {chap[0]} - {chap[1]}")
                current = chap
            blocks.append(f"  {r['section_number']} {r.get('title') or ''}")
        return "\n".join(blocks)

    def run(self, facts_block: str, context_block: str) -> Optional[List[Dict[str, Any]]]:
        """Returns validated nominations [{section, applicability, category, applies_to, reason, record}] or None."""
        spec = _ACTS[self.act]
        prompt = ACT_NOMINATION_USER_PROMPT_TEMPLATE.format(
            facts_block=facts_block, context_block=context_block, act=self.act, menu_block=self.menu(),
            applicability_values="|".join(spec["applicability"]), category_values=", ".join(spec["categories"]),
        )
        try:
            resp = self.llm.invoke([SystemMessage(content=spec["system"]), HumanMessage(content=prompt)])
            parsed = extract_json_from_text(resp)
        except Exception as e:
            print(f"[ActSectionNominator:{self.act}] nomination failed, using fallback retrieval: {e}", flush=True)
            return None
        items = parsed.get("nominations") if isinstance(parsed, dict) else None
        if not isinstance(items, list):
            return None
        by_num = {r["section_number"]: r for r in _sections(self.act)}
        out: List[Dict[str, Any]] = []
        seen = set()
        for it in items:
            if not isinstance(it, dict):
                continue
            sec = str(it.get("section", "")).strip().upper().replace("SECTION ", "").replace(f"{self.act} ", "")
            if sec not in by_num or sec in seen:
                continue  # never an invented or duplicate number
            seen.add(sec)
            app = str(it.get("applicability", "")).upper()
            cat = str(it.get("category", "")).upper()
            out.append({
                "section": sec,
                "applicability": app if app in spec["applicability"] else "CONTEXTUAL",
                "category": cat if cat in spec["categories"] else spec["categories"][-1],
                "applies_to": str(it.get("applies_to") or "")[:160],
                "reason": str(it.get("reason") or "")[:200],
                "record": by_num[sec],
            })
        rank = {a: i for i, a in enumerate(spec["applicability"])}
        out.sort(key=lambda n: rank.get(n["applicability"], 9))
        return out or None
