"""
case_file.py
============
Canonical, deterministic Case File builder with Prompt Caching support.

Solves the prompt-bloat bottleneck by packaging all static case data:
- Case Facts (all facts in deterministic numerical order)
- Evidence Inventory (all items in deterministic alphabetical order)
- Verified Statutory Provisions (all sections in deterministic numerical order)
- Precedent Holdings (all holdings in deterministic order)

into a 100% byte-for-byte identical, immutable block placed at the
VERY START of every LLM call across all agents (Prosecutor, Defense, Judge).

Prefix Caching Behavior:
- OpenAI: Prefix caching is automatic for prompts >= 1,024 tokens with identical prefixes.
- Anthropic: Explicit cache_control block ({"type": "ephemeral"}) attached to the case file block.
- Groq / Ollama / vLLM: Exact prefix reuse across calls.
The dynamic elements (current turn instructions, hearing transcript so far, rebuttal arguments)
are strictly placed at the END of the prompt.
"""

from __future__ import annotations
import json
import os
import re
from typing import Any, Dict, List, Optional
from langchain_core.messages import SystemMessage, HumanMessage


def _natural_key(s: Any) -> list:
    """Natural sort key (e.g. 'fact_2' before 'fact_10')."""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', str(s or ""))]


def build_canonical_case_file(
    case_facts: Optional[List[Any]] = None,
    evidence_inventory: Optional[List[Any]] = None,
    lexigraph_output: Optional[Dict[str, Any]] = None,
    holdings: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    Builds the immutable, byte-for-byte deterministic Case File block.
    This string is identical across every call in a simulation.
    """
    lines = [
        "================================================================================",
        "CANONICAL CASE FILE & OFFICIAL COURT RECORD [STATIC PREFIX - DO NOT ALTER]",
        "================================================================================",
        "",
        "--- SECTION 1: ESTABLISHED CASE FACTS (RECORD) ---",
        "--------------------------------------------------------------------------------",
    ]

    # 1. Facts - sorted deterministically by fact ID
    sorted_facts = []
    if case_facts:
        for i, f in enumerate(case_facts):
            if isinstance(f, dict):
                fid = f.get("id") or f"fact_{i+1}"
                txt = f.get("text") or f.get("value") or ""
                src = f.get("source") or "record"
                ftype = f.get("type") or "allegation"
            else:
                fid = getattr(f, "id", f"fact_{i+1}")
                txt = getattr(f, "text", getattr(f, "value", str(f)))
                src = getattr(f, "source", "record")
                ftype = getattr(f, "type", "allegation")
            sorted_facts.append((fid, txt, src, ftype))

    sorted_facts.sort(key=lambda item: _natural_key(item[0]))

    if sorted_facts:
        for fid, txt, src, ftype in sorted_facts:
            lines.append(f"[{fid}] {txt} (Source: {src}; Type: {ftype})")
    else:
        lines.append("No formal facts on record.")

    lines.extend([
        "",
        "--- SECTION 2: EVIDENCE INVENTORY (RECORD STATUS) ---",
        "--------------------------------------------------------------------------------",
    ])

    # 2. Evidence Inventory - sorted deterministically by item name
    sorted_inv = []
    if evidence_inventory:
        for item in evidence_inventory:
            if isinstance(item, dict):
                iname = str(item.get("item", "")).strip()
                status = str(item.get("status", "not_on_record")).strip()
                details = str(item.get("details", "") or "").strip()
            else:
                iname = str(getattr(item, "item", "")).strip()
                status = str(getattr(item, "status", "not_on_record")).strip()
                details = str(getattr(item, "details", "") or "").strip()
            sorted_inv.append((iname, status, details))

    sorted_inv.sort(key=lambda item: _natural_key(item[0]))

    if sorted_inv:
        for iname, status, details in sorted_inv:
            detail_str = f" | Details: {details}" if details else ""
            lines.append(f"• {iname}: {status}{detail_str}")
    else:
        lines.append("No formal evidence inventory on record.")

    lines.extend([
        "",
        "--- SECTION 3: VERIFIED APPLICABLE STATUTES (LEXIGRAPH) ---",
        "--------------------------------------------------------------------------------",
    ])

    # 3. Verified Statutes - sorted deterministically by section
    raw_sections = []
    if lexigraph_output:
        raw_sections = lexigraph_output.get("ipc_sections") or []
        if not raw_sections:
            stage4 = lexigraph_output.get("stage4_statutory_verification", {})
            raw_sections = stage4.get("verified_offences") or stage4.get("verified_sections") or []

    sorted_sections = []
    for s in raw_sections:
        if isinstance(s, dict):
            sec = str(s.get("section") or s.get("section_number") or "").strip()
            off = str(s.get("offense") or s.get("title") or "").strip()
            pun = str(s.get("punishment") or s.get("punishment_text") or "N/A").strip()
            desc = str(s.get("description") or "").strip()
            score = float(s.get("score") or 1.0)
        else:
            sec = str(s).strip()
            off, pun, desc, score = "", "N/A", "", 1.0
        if sec and sec.upper() not in ("N/A", "NONE", ""):
            sorted_sections.append((sec, off, pun, desc, score))

    sorted_sections.sort(key=lambda item: _natural_key(item[0]))

    if sorted_sections:
        for i, (sec, off, pun, desc, score) in enumerate(sorted_sections, 1):
            desc_short = (desc[:180] + "…") if len(desc) > 180 else desc
            lines.append(f"{i}. Section {sec} [Confidence: {score:.2f}]")
            if off:
                lines.append(f"   Offense: {off}")
            if pun and pun != "N/A":
                lines.append(f"   Punishment: {pun}")
            if desc_short:
                lines.append(f"   Summary: {desc_short}")
    else:
        lines.append("No specific statutory provisions retrieved.")

    lines.extend([
        "",
        "--- SECTION 4: OPERATIVE PRECEDENT HOLDINGS (BINDING RATIO DECIDENDI) ---",
        "--------------------------------------------------------------------------------",
    ])

    # 4. Precedent Holdings - sorted deterministically by holding ID
    raw_holdings = holdings or []
    if not raw_holdings and lexigraph_output:
        raw_holdings = lexigraph_output.get("holdings") or []

    sorted_holdings = []
    for h in raw_holdings:
        if isinstance(h, dict):
            hid = str(h.get("id") or "").strip()
            case = str(h.get("case") or "Supreme Court Precedent").strip()
            para = str(h.get("para") or "").strip()
            principle = str(h.get("principle") or "").strip()
            conditions = str(h.get("conditions") or "").strip()
            effect = str(h.get("effect") or "procedural").strip().upper()
            score = float(h.get("score") or 0.0)
        else:
            hid = str(getattr(h, "id", "")).strip()
            case = str(getattr(h, "case", "Supreme Court Precedent")).strip()
            para = str(getattr(h, "para", "")).strip()
            principle = str(getattr(h, "principle", "")).strip()
            conditions = str(getattr(h, "conditions", "")).strip()
            effect = str(getattr(h, "effect", "procedural")).strip().upper()
            score = float(getattr(h, "score", 0.0))
        sorted_holdings.append((hid, case, para, principle, conditions, effect, score))

    sorted_holdings.sort(key=lambda item: _natural_key(item[0]))

    if sorted_holdings:
        for i, (hid, case, para, principle, conditions, effect, score) in enumerate(sorted_holdings, 1):
            para_str = f" (Para {para})" if para else ""
            lines.append(f"{i}. [{hid}] {case}{para_str} [Effect: {effect} | Score: {score:.2f}]")
            if principle:
                lines.append(f"   - Principle: {principle}")
            if conditions:
                lines.append(f"   - Conditions: {conditions}")
    else:
        lines.append("No specific judicial precedent holdings retrieved.")

    lines.extend([
        "================================================================================",
        "END OF CANONICAL CASE FILE",
        "================================================================================",
    ])

    return "\n".join(lines)


def get_or_build_case_file(state: Dict[str, Any]) -> str:
    """
    Returns the session-cached canonical case file string.
    If not already generated, computes it and stores it in state['_canonical_case_file'].
    Guarantees 100% byte-for-byte stability across all rounds and agents.
    """
    if state.get("_canonical_case_file"):
        return state["_canonical_case_file"]

    case_file = build_canonical_case_file(
        case_facts=state.get("case_facts"),
        evidence_inventory=state.get("evidence_inventory"),
        lexigraph_output=state.get("lexigraph_output"),
        holdings=state.get("holdings"),
    )
    state["_canonical_case_file"] = case_file
    return case_file


def format_cached_messages(
    canonical_case_file: str,
    role_instruction: str,
    dynamic_turn_content: str,
    provider: Optional[str] = None,
) -> list:
    """
    Formats messages for optimal prompt caching:
    - Message 0 (System): Canonical Case File prefix.
      If provider == 'anthropic', attaches cache_control ephemeral block.
    - Message 1 (System): Role instructions (Prosecutor / Defense / Judge rules).
    - Message 2 (User): Dynamic turn prompt (Transcript so far, current round, rebuttal argument).
    """
    prov = (provider or os.getenv("LLM_PROVIDER", "openai")).strip().lower()

    if prov == "anthropic":
        msg_case = SystemMessage(
            content=[
                {
                    "type": "text",
                    "text": canonical_case_file,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
        )
        msg_role = SystemMessage(content=role_instruction)
        msg_user = HumanMessage(content=dynamic_turn_content)
        return [msg_case, msg_role, msg_user]

    # OpenAI / Groq / Ollama / Default:
    # Prefix caching is automatic from character 0. Placing case_file first ensures cache hits.
    msg_system = SystemMessage(content=f"{canonical_case_file}\n\n{role_instruction}")
    msg_user = HumanMessage(content=dynamic_turn_content)
    return [msg_system, msg_user]
