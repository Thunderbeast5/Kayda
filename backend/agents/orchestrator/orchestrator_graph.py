"""
MootCourt Orchestrator — LangGraph State Machine (v2)
======================================================
Implements the full design spec:

  - Single controller of session lifecycle
  - Owns SimulationState (LangGraph)
  - Grounding gates: evidence verified → lexigraph verified → courtroom
  - Citation verification on every prosecution/defense turn (max 2 retries)
  - Fact-reference verification on every turn
  - Bounded courtroom loop with max_rounds
  - Redis checkpointing + scoped context slices for each agent
  - WebSocket streaming via inject-able emit callback
  - Per-node timeout + retry with exponential backoff
  - Full error logging to state.errors + frontend events

Graph:
  START
    → init_session
    → evidence_analyzer  [gate: verified?  → retry ≤2 else FAILED]
    → lexigraph          [gate: verified?  → retry ≤2 else FAILED]
    → prosecutor         [citation check, max 2 retries]
    → defense            [citation check, max 2 retries]
    → judge_evaluate
    → [conditional]
         clarification_needed → judge_question → accused → judge_evaluate
         need more rounds     → prosecutor (round_no + 1)
         done                 → judge_verdict
    → finalize
  END
"""

from __future__ import annotations

import io
import sys

# Ensure stdout/stderr can handle Unicode on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import asyncio
import json
import os
import re
import sys
import time
import traceback
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# ── Path setup ────────────────────────────────────────────────────────────────
_backend_dir   = Path(__file__).resolve().parent.parent.parent
_agents_dir    = _backend_dir / "agents"
_prosecutor_dir = _backend_dir / "prosecutor"

for _p in [str(_backend_dir), str(_agents_dir), str(_prosecutor_dir)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from dotenv import load_dotenv
load_dotenv(_backend_dir / ".env")

from langgraph.graph import StateGraph, START, END

from agents.orchestrator.state import SimulationState, Turn, Question, Fact
from agents.orchestrator.formatting import (
    extract_citations_with_act,
    extract_evidence_references,
    format_argument_markdown,
    link_facts_to_text,
    parse_argument_structure,
    structure_prosecution_turn,
    export_transcript,
)
from agents.judge.judge       import JudgeAgent
from agents.accused.accused   import AccusedAgent
from agents.defense.defense   import DefenseAgent
from agents.lexigraph          import lexigraph_node as _lexigraph_retrieve, format_for_prompt
from agents.orchestrator.case_file import get_or_build_case_file

# ── Constants ────────────────────────────────────────────────────────────────
MAX_EVIDENCE_RETRIES  = 2
MAX_LEXIGRAPH_RETRIES = 2
MAX_CITATION_RETRIES  = 2
NODE_TIMEOUT_SECS     = 120          # per-node hard timeout
JUDGE_THRESHOLD       = float(os.getenv("JUDGE_THRESHOLD", os.getenv("JUDGE_SUFFICIENCY_THRESHOLD", "6.0")))  # overall judge score threshold (0–10)
DEFAULT_MAX_ROUNDS    = int(os.getenv("ORCHESTRATOR_MAX_ROUNDS", "2"))

GROQ_PRIMARY   = os.getenv("GROQ_MODEL_PRIMARY",  "llama-3.3-70b-versatile")
GROQ_FALLBACK  = os.getenv("GROQ_MODEL_FALLBACK", "llama-3.1-8b-instant")


# ── Redis ─────────────────────────────────────────────────────────────────────

_redis_client = None
_redis_checked = False

def _redis():
    """Return Redis client or None (graceful degradation, memoized)."""
    global _redis_client, _redis_checked
    if _redis_checked:
        return _redis_client
    try:
        import redis
        r = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            decode_responses=True,
            socket_connect_timeout=0.3,
            socket_timeout=0.3,
        )
        r.ping()
        _redis_client = r
    except Exception:
        _redis_client = None
    _redis_checked = True
    return _redis_client


def _redis_set(key: str, value: Any, ttl: int = 86400) -> None:
    r = _redis()
    if r:
        try:
            r.set(key, json.dumps(value), ex=ttl)
        except Exception:
            pass


def _redis_get(key: str, default: Any = None) -> Any:
    r = _redis()
    if r:
        try:
            raw = r.get(key)
            return json.loads(raw) if raw else default
        except Exception:
            pass
    return default


def _redis_lpush(key: str, value: Any, ttl: int = 86400) -> None:
    r = _redis()
    if r:
        try:
            r.rpush(key, json.dumps(value))
            r.expire(key, ttl)
        except Exception:
            pass


# ── WebSocket event builder ───────────────────────────────────────────────────

def _event(type_: str, **kwargs) -> dict:
    return {"type": type_, **kwargs}


# ── Retry with backoff ────────────────────────────────────────────────────────

def _with_retry(fn: Callable, max_retries: int, label: str) -> Any:
    """Run fn() with exponential backoff, raise on exhaustion."""
    for attempt in range(1, max_retries + 2):
        try:
            return fn()
        except Exception as exc:
            if attempt > max_retries:
                raise
            wait = 2 ** (attempt - 1)
            print(f"[Orchestrator] {label} attempt {attempt} failed: {exc}. Retrying in {wait}s…")
            time.sleep(wait)


# ── Citation verifier ─────────────────────────────────────────────────────────

def _extract_cited_sections(text: str) -> List[str]:
    """Pull IPC/BNS/CrPC section citations with Act prefix from text."""
    return extract_citations_with_act(text)


# Standard procedural provisions (Bail, Remand, Recovery, Witness Statements, Warrants, Proclamation)
_PROCEDURAL_SECTIONS = {
    "438", "482", "437", "439", "480", "483",  # Anticipatory & regular bail (CrPC / BNSS)
    "167", "187",                                # Remand & custody (CrPC / BNSS)
    "27", "23",                                  # Recovery of evidence (IEA / BSA)
    "161", "164", "180", "183",                  # Police & judicial statements (CrPC / BNSS)
    "313", "351",                                # Statement of accused (CrPC / BNSS)
    "70", "71", "72", "73",                      # Warrants (CrPC / BNSS)
    "82", "83", "84", "85",                      # Proclamation & attachment (CrPC / BNSS)
    "156", "173", "190", "200", "202", "204",    # Investigation, charge-sheet, cognizance (CrPC / BNSS)
    # Substantive offences inseparable from proclamation/absconder cases
    "172", "174", "174a", "175",                 # IPC: non-compliance / absconding to avoid service
    "206", "209", "210",                         # BNS equivalents of IPC 172/174/174A/175
}

_STATUTE_CROSSWALK = {
    # CrPC <-> BNSS
    ("CRPC", "82"): ("BNSS", "84"),
    ("CRPC", "83"): ("BNSS", "85"),
    ("CRPC", "70"): ("BNSS", "72"),
    ("CRPC", "70(2)"): ("BNSS", "72(2)"),
    ("CRPC", "70(1)"): ("BNSS", "72(1)"),
    ("CRPC", "156"): ("BNSS", "175"),
    ("CRPC", "156(3)"): ("BNSS", "175(3)"),
    ("CRPC", "167"): ("BNSS", "187"),
    ("CRPC", "173"): ("BNSS", "193"),
    ("CRPC", "173(2)"): ("BNSS", "193(2)"),
    ("CRPC", "438"): ("BNSS", "482"),
    ("CRPC", "437"): ("BNSS", "480"),
    ("CRPC", "439"): ("BNSS", "483"),
    ("CRPC", "482"): ("BNSS", "528"),
    ("CRPC", "161"): ("BNSS", "180"),
    ("CRPC", "164"): ("BNSS", "183"),
    ("CRPC", "313"): ("BNSS", "351"),
    # IPC <-> BNS
    ("IPC", "172"): ("BNS", "206"),   # Absconding to avoid service of summons
    ("IPC", "174"): ("BNS", "209"),
    ("IPC", "174A"): ("BNS", "209"),
    ("IPC", "174a"): ("BNS", "209"),   # lowercase variant
    ("IPC", "175"): ("BNS", "210"),
    ("IPC", "341"): ("BNS", "126"),
    ("IPC", "323"): ("BNS", "115"),
    ("IPC", "324"): ("BNS", "117"),
    ("IPC", "325"): ("BNS", "118"),
    ("IPC", "354"): ("BNS", "74"),
    ("IPC", "354B"): ("BNS", "76"),
    ("IPC", "354b"): ("BNS", "76"),   # lowercase variant
    ("IPC", "379"): ("BNS", "303"),
    ("IPC", "504"): ("BNS", "352"),
    ("IPC", "506"): ("BNS", "351"),
    ("IPC", "149"): ("BNS", "190"),
    ("IPC", "420"): ("BNS", "318"),
    ("IPC", "302"): ("BNS", "103"),
    ("IPC", "307"): ("BNS", "109"),
    ("IPC", "376"): ("BNS", "64"),
    ("IPC", "498A"): ("BNS", "85"),
    ("IPC", "498a"): ("BNS", "85"),   # lowercase variant
    # IEA <-> BSA
    ("IEA", "27"): ("BSA", "23"),
}
for (a1, s1), (a2, s2) in list(_STATUTE_CROSSWALK.items()):
    _STATUTE_CROSSWALK[(a2, s2)] = (a1, s1)

_ACT_ALIASES = {
    "indian penal code": "IPC",
    "ipc": "IPC",
    "code of criminal procedure": "CRPC",
    "crpc": "CRPC",
    "cr.p.c.": "CRPC",
    "cr.p.c": "CRPC",
    "bharatiya nyaya sanhita": "BNS",
    "bns": "BNS",
    "bharatiya nagarik suraksha sanhita": "BNSS",
    "bnss": "BNSS",
    "indian evidence act": "IEA",
    "iea": "IEA",
    "bharatiya sakshya adhiniyam": "BSA",
    "bsa": "BSA",
    "pocso": "POCSO",
    "dpa": "DPA",
    "dowry prohibition act": "DPA",
    "prevention of witch (daain) practices act": "DAAIN",
    "daain act": "DAAIN",
    "daain": "DAAIN",
}


def _verify_citations(
    cited: List[str],
    lexigraph_output: Dict[str, Any],
    case_facts: Optional[List[Any]] = None,
    holdings: Optional[List[Any]] = None,
) -> tuple[bool, List[str]]:
    """
    Return (all_verified, unverified_list).
    Allowed citations = sections referenced by the retrieved holdings and the case facts,
    along with statutory retrieved sections, procedural provisions, and their crosswalk mappings.
    Handles citations with Act prefix (e.g. 'IPC 324', 'CrPC 438', 'CrPC 82', 'IPC 174').
    """
    allowed_numbers: set[str] = set(_PROCEDURAL_SECTIONS)
    allowed_full: set[str] = set()

    for p in _PROCEDURAL_SECTIONS:
        for act_tag in ("crpc", "bnss", "ipc", "bns", "iea", "bsa"):
            allowed_full.add(f"{act_tag} {p}")

    # 1. Statutory sections from lexigraph_output
    for sec in lexigraph_output.get("ipc_sections", []):
        if isinstance(sec, dict) and sec.get("section"):
            s_str = str(sec["section"]).lower().strip()
            allowed_numbers.add(s_str)
            allowed_full.add(s_str)
            base_m = re.match(r"^(\d+[a-z]?)", s_str)
            if base_m:
                allowed_numbers.add(base_m.group(1))

    for vo in lexigraph_output.get("stage4_statutory_verification", {}).get("verified_offences", []):
        sn = str(vo.get("section_number", "")).lower().strip()
        if sn:
            allowed_numbers.add(sn)
            allowed_full.add(sn)
            base_m = re.match(r"^(\d+[a-z]?)", sn)
            if base_m:
                allowed_numbers.add(base_m.group(1))

    for rs in lexigraph_output.get("recommended_sections", []):
        r_act = str(rs.get("act", "")).lower().strip()
        r_sec = str(rs.get("section", "")).lower().strip()
        if r_sec:
            allowed_numbers.add(r_sec)
            allowed_full.add(f"{r_act} {r_sec}".strip())
            base_m = re.match(r"^(\d+[a-z]?)", r_sec)
            if base_m:
                allowed_numbers.add(base_m.group(1))

    # 2. Extract sections referenced in case_facts and holdings
    text_sources: List[str] = []
    if case_facts:
        for f in case_facts:
            if isinstance(f, str):
                text_sources.append(f)
            elif isinstance(f, dict):
                text_sources.append(str(f.get("text") or f.get("value") or ""))
            else:
                text_sources.append(str(getattr(f, "text", getattr(f, "value", ""))))

    all_holdings = list(holdings or [])
    if not all_holdings:
        all_holdings = list(lexigraph_output.get("holdings", []))

    for h in all_holdings:
        if isinstance(h, str):
            text_sources.append(h)
        elif isinstance(h, dict):
            text_sources.extend([
                str(h.get("principle", "")),
                str(h.get("conditions", "")),
                str(h.get("case", "")),
                str(h.get("applicable_sections", "")),
                str(h.get("statutory_provisions", "")),
            ])
        else:
            text_sources.extend([
                str(getattr(h, "principle", "")),
                str(getattr(h, "conditions", "")),
                str(getattr(h, "case", "")),
            ])

    for sc in (lexigraph_output.get("supporting_cases", []) + lexigraph_output.get("similar_cases", [])):
        if isinstance(sc, dict):
            text_sources.extend([
                str(sc.get("case_name", "")),
                str(sc.get("ratio_decidendi", "")),
                str(sc.get("facts_summary", "")),
            ])
            for inter in sc.get("interprets", []):
                text_sources.append(str(inter))

    combined = "\n".join(text_sources)

    # List patterns: "Sections 341, 323, 354, 354B, 379, 504, 506 and 149 of the Indian Penal Code"
    list_pat = re.compile(
        r'Sections?\s+([0-9A-Za-z,\s\(\)/]+?)\s+(?:of\s+(?:the\s+)?)?'
        r'(Indian Penal Code|Code of Criminal Procedure|Bharatiya Nyaya Sanhita|Bharatiya Nagarik Suraksha Sanhita|Indian Evidence Act|Bharatiya Sakshya Adhiniyam|Prevention of Witch \(Daain\) Practices Act|CrPC|IPC|BNS|BNSS|IEA|BSA|POCSO|DPA|Daain Act|Daain)\b',
        re.IGNORECASE,
    )
    for m in list_pat.finditer(combined):
        sec_part = m.group(1)
        act_part = m.group(2).lower()
        act_norm = _ACT_ALIASES.get(act_part, act_part.upper()).lower()
        for s in re.findall(r'\b\d+[A-Za-z]?(?:\(\d+\))?\b', sec_part):
            s_lower = s.lower()
            allowed_numbers.add(s_lower)
            allowed_full.add(f"{act_norm} {s_lower}")
            base_m = re.match(r"^(\d+[a-z]?)", s_lower)
            if base_m:
                allowed_numbers.add(base_m.group(1))

    # Single mentions: "CrPC 82" or "Section 82 CrPC"
    single_pat = re.compile(r'\b(BNS|IPC|BNSS|CRPC|BSA|IEA|POCSO|DPA|DAAIN)\s*(?:Sec(?:tion|\.)?|S\.)?\s*(\d+[A-Za-z]?(?:\(\d+\))?)\b', re.IGNORECASE)
    for m in single_pat.finditer(combined):
        act_str = m.group(1).lower()
        sec_str = m.group(2).lower()
        allowed_numbers.add(sec_str)
        allowed_full.add(f"{act_str} {sec_str}")
        base_m = re.match(r"^(\d+[a-z]?)", sec_str)
        if base_m:
            allowed_numbers.add(base_m.group(1))

    sec_act_pat = re.compile(r'\b(?:Sec(?:tion|\.)?|S\.|u/s)\s*(\d+[A-Za-z]?(?:\(\d+\))?)\s*(?:of\s+(?:the\s+)?)?(BNS|IPC|BNSS|CRPC|BSA|IEA|POCSO|DPA|DAAIN)\b', re.IGNORECASE)
    for m in sec_act_pat.finditer(combined):
        act_str = m.group(2).lower()
        sec_str = m.group(1).lower()
        allowed_numbers.add(sec_str)
        allowed_full.add(f"{act_str} {sec_str}")
        base_m = re.match(r"^(\d+[a-z]?)", sec_str)
        if base_m:
            allowed_numbers.add(base_m.group(1))

    # Generic Section mentions: "Section 82", "Section 83"
    gen_sec_pat = re.compile(r'\b(?:Section|Sec\.|S\.)\s*(\d+[A-Za-z]?(?:\(\d+\))?)\b', re.IGNORECASE)
    for m in gen_sec_pat.finditer(combined):
        s_val = m.group(1).lower()
        allowed_numbers.add(s_val)
        base_m = re.match(r"^(\d+[a-z]?)", s_val)
        if base_m:
            allowed_numbers.add(base_m.group(1))

    # Crosswalk mappings
    for (a_in, s_in), (a_out, s_out) in _STATUTE_CROSSWALK.items():
        if s_in.lower() in allowed_numbers or f"{a_in.lower()} {s_in.lower()}" in allowed_full:
            allowed_numbers.add(s_out.lower())
            allowed_full.add(f"{a_out.lower()} {s_out.lower()}")
            base_m = re.match(r"^(\d+[a-z]?)", s_out.lower())
            if base_m:
                allowed_numbers.add(base_m.group(1))

    unverified = []
    for c in cited:
        c_clean = c.lower().strip()
        m = re.search(r"(\d+[a-z]?)", c_clean)
        num = m.group(1) if m else c_clean
        c_no_act = re.sub(r'^(?:bns|ipc|bnss|crpc|bsa|iea|pocso|dpa|daain)\s*', '', c_clean).strip()
        if (num in allowed_numbers or
            c_clean in allowed_full or
            c_clean in allowed_numbers or
            c_no_act in allowed_numbers):
            continue
        unverified.append(c)

    return (len(unverified) == 0), unverified


def extract_evidence_inventory(case_text: str, facts: List[Fact]) -> List[Dict[str, Any]]:
    """
    Analyzes case text and facts to produce an evidence inventory.
    The model decides what evidence matters for the case (e.g. warrants, proclamation,
    FIR, recovery memo, medical reports, eyewitness statements, digital proof)
    and tags whether each is 'present' or 'not_on_record'.
    """
    facts_summary = "\n".join([
        f"- [{getattr(f, 'id', f.get('id', f'fact_{i+1}'))}] "
        f"{getattr(f, 'text', f.get('text', f.get('value', '')))} "
        f"(Source: {getattr(f, 'source', f.get('source', 'record'))})"
        for i, f in enumerate(facts)
    ])
    prompt = (
        "You are a criminal evidence analyst for an Indian moot court.\n"
        "Analyze the following case facts and text to produce a concise EVIDENCE INVENTORY.\n"
        "Identify ONLY the core material evidentiary items (aim for at most 10-15 key items, e.g. FIR, summons/warrants, proclamation under Section 82, attachment under Section 83, weapon/recovery memo, medical/MLC report, eyewitness statements, CCTV/forensic logs).\n"
        "Do NOT create redundant, duplicated, or minor procedural sub-items.\n"
        "For each item, specify:\n"
        "- item: concise standardized name (e.g. 'fir', 'summons', 'bailable_warrant', 'non_bailable_warrant', 'proclamation_sec_82', 'attachment_sec_83', 'weapon', 'medical_report', 'eyewitnesses', 'cctv_footage')\n"
        "- status: 'present' (if in the record) OR 'not_on_record' (if absent, missing, or unproduced)\n"
        "- details: concise 1-sentence description based strictly on the case record.\n\n"
        "Return ONLY a valid JSON array of objects:\n"
        '[{"item": "...", "status": "present", "details": "..."}, ...]\n\n'
        f"CASE FACTS:\n{facts_summary}\n\n"
        f"CASE TEXT:\n{case_text}"
    )
    try:
        from config.llm_config import get_llm
        llm = get_llm(temperature=0)
        resp = llm.invoke(prompt)
        cleaned = re.sub(r"^```(?:json)?|```$", "", resp.content.strip(), flags=re.MULTILINE).strip()
        data = json.loads(cleaned)
        if isinstance(data, list) and len(data) > 0:
            print(f"[EvidenceAnalyzer] Generated evidence inventory with {len(data)} items via LLM.")
            return data
    except Exception as exc:
        print(f"[EvidenceAnalyzer] LLM evidence inventory extraction error: {exc}.")

    return []


def _verify_fact_references_with_llm(
    text: str,
    case_facts: List[Fact],
    evidence_inventory: List[Dict[str, Any]],
) -> tuple[bool, str]:
    """
    One cheap LLM verifier call using gpt-5.4-mini:
    'List every factual assertion in this argument and mark each as supported, unsupported, or contradicted by these facts.'
    """
    facts_str = "\n".join([
        f"- [{getattr(f, 'id', f.get('id', f'fact_{i+1}'))}] "
        f"{getattr(f, 'text', f.get('text', f.get('value', '')))} "
        f"(Source: {getattr(f, 'source', f.get('source', 'record'))})"
        for i, f in enumerate(case_facts)
    ])
    inv_str = json.dumps(evidence_inventory, indent=2)

    prompt = (
        "You are a factual integrity verifier for a courtroom moot-court simulation.\n"
        "Check whether the following courtroom argument fabricates facts or falsely denies existing evidence.\n\n"
        "VERIFIED CASE FACTS:\n"
        f"{facts_str}\n\n"
        "EVIDENCE INVENTORY (Status in the record):\n"
        f"{inv_str}\n\n"
        "COURTROOM ARGUMENT TO VERIFY:\n"
        f"{text}\n\n"
        "RULES:\n"
        "1. REJECT if the argument asserts that an item does not exist or was not recovered when the inventory marks it as 'present' (e.g. claiming no eyewitnesses when eyewitnesses were present, or claiming knife was not recovered when recovered).\n"
        "2. REJECT if the argument invents specific factual assertions (fabricated names of parties/witnesses, fabricated dates, or fabricated weapons) not in the case facts.\n"
        "3. REJECT if the argument claims there is no complainant or victim when the complainant/victim is identified in the facts.\n"
        "4. ACCEPT if the defense argues that evidence is missing from the record using phrases like 'the record before the court does not contain...' or 'no medical report has been produced' when that evidence is 'not_on_record' or unmentioned. This is legitimate defense advocacy.\n"
        "5. ACCEPT legal arguments, statutory interpretations, mens rea doubts, and procedural objections.\n\n"
        "Return ONLY valid JSON matching this schema:\n"
        '{"is_grounded": true or false, "reason": "brief explanation"}'
    )
    try:
        from config.llm_config import get_llm
        llm = get_llm(temperature=0)
        resp = llm.invoke(prompt)
        cleaned = re.sub(r"^```(?:json)?|```$", "", resp.content.strip(), flags=re.MULTILINE).strip()
        data = json.loads(cleaned)
        return bool(data.get("is_grounded", True)), str(data.get("reason", "OK"))
    except Exception as exc:
        # LLM verifier failed or timed out — do not block the pipeline, let heuristic gate stand
        print(f"[FactGroundingGate] LLM verifier call skipped ({exc}).")
        return True, "Verifier skipped on error"


def _verify_fact_references(
    text: str,
    case_facts: List[Fact],
    evidence_inventory: Optional[List[Dict[str, Any]]] = None,
) -> bool:
    """
    Grounding gate verifying courtroom argument against verified case facts and inventory:
    1. Structure and schema stays in code (non-empty text, ID validation).
    2. The model decides what matters: LLM verifier classifies assertions as
       supported, unsupported, or contradicted by the extracted facts and inventory.
    """
    if not text or not text.strip():
        return False

    # Dynamic verification via LLM verifier
    enable_llm_gate = os.getenv("ENABLE_LLM_FACT_VERIFIER", "true").lower() in ("true", "1", "yes")
    if enable_llm_gate and (case_facts or evidence_inventory):
        ok, reason = _verify_fact_references_with_llm(text, case_facts, evidence_inventory or [])
        if not ok:
            print(f"[FactGroundingGate][LLM Verifier] REJECTED: {reason}. Triggering regeneration.")
            return False

    return True


# ── Scoped context slices ────────────────────────────────────────────────────

def _get_debate_facts(facts: List[Any]) -> List[Any]:
    """
    Filter facts for the courtroom debate: include only allegations and procedural events.
    Excludes judicial findings/reasoning from the original judgment so agents debate the facts of the case.
    """
    if not facts:
        return []
    filtered = []
    for f in facts:
        ftype = getattr(f, "type", None) or (f.get("type") if isinstance(f, dict) else "allegation")
        if ftype in ("allegation", "procedural_event"):
            filtered.append(f)
    return filtered if filtered else facts


def _prosecutor_context(state: SimulationState) -> dict:
    """Give prosecutor only what it needs — no full state leakage."""
    last_defense = ""
    for t in reversed(state.get("transcript", [])):
        if t["speaker"] == "defense":
            last_defense = t["content"]
            break
    debate_facts = _get_debate_facts(state.get("case_facts", []))
    canonical_case_file = get_or_build_case_file(state)
    return {
        "canonical_case_file": canonical_case_file,
        "case_facts":      debate_facts,
        "evidence_inventory": state.get("evidence_inventory", []),
        "evidence_map":    {getattr(f, "id", f.get("id")): getattr(f, "text", f.get("text", "")) for f in debate_facts if getattr(f, "id", f.get("id", None))},
        "lexigraph_output": state.get("lexigraph_output", {}),
        "holdings":        state.get("holdings") or state.get("lexigraph_output", {}).get("holdings", []),
        "last_defense_argument": last_defense,
        "round_no": state.get("round_no", 1),
    }


def _defense_context(state: SimulationState) -> dict:
    last_prosecution = ""
    for t in reversed(state.get("transcript", [])):
        if t["speaker"] == "prosecutor":
            last_prosecution = t["content"]
            break
    canonical_case_file = get_or_build_case_file(state)
    return {
        "canonical_case_file": canonical_case_file,
        "case_facts":      _get_debate_facts(state.get("case_facts", [])),
        "evidence_inventory": state.get("evidence_inventory", []),
        "lexigraph_output": state.get("lexigraph_output", {}),
        "holdings":        state.get("holdings") or state.get("lexigraph_output", {}).get("holdings", []),
        "last_prosecution_argument": last_prosecution,
        "round_no": state.get("round_no", 1),
    }


def _judge_context(state: SimulationState) -> dict:
    canonical_case_file = get_or_build_case_file(state)
    return {
        "canonical_case_file": canonical_case_file,
        "case_facts":      state.get("case_facts", []),
        "evidence_inventory": state.get("evidence_inventory", []),
        "lexigraph_output": state.get("lexigraph_output", {}),
        "holdings":        state.get("holdings") or state.get("lexigraph_output", {}).get("holdings", []),
        "transcript":      state.get("transcript", []),
        "judge_scores":    state.get("judge_scores", {}),
        "pending_questions": state.get("pending_questions", []),
    }



def _accused_context(state: SimulationState) -> dict:
    pending = state.get("pending_questions", [])
    unanswered = [q for q in pending if not q["answered"]]
    return {
        "case_facts":   state.get("case_facts", []),
        "questions":    unanswered,
        "session_id":   state.get("session_id", ""),
    }


# ── Singleton agents ──────────────────────────────────────────────────────────

_judge_agent      = None
_accused_agent    = None
_defense_agent    = None
_prosecutor_agent = None


def _judge() -> JudgeAgent:
    global _judge_agent
    if not _judge_agent:
        _judge_agent = JudgeAgent()
    return _judge_agent


def _accused() -> AccusedAgent:
    global _accused_agent
    if not _accused_agent:
        _accused_agent = AccusedAgent()
    return _accused_agent


def _defense() -> DefenseAgent:
    global _defense_agent
    if not _defense_agent:
        _defense_agent = DefenseAgent()
    return _defense_agent


def _prosecutor():
    """
    Singleton ProsecutorAgent. ProsecutorAgent requires a LexiGraphAgent
    instance — we use the prosecutor.lexigraph.LexiGraphAgent for this.
    """
    global _prosecutor_agent
    if not _prosecutor_agent:
        try:
            from prosecutor.prosecutor_agent import ProsecutorAgent
            try:
                from prosecutor.lexigraph_agent import LexiGraphAgent
            except ImportError:
                from agents.lexigraph.lexigraph_agent import LexiGraphAgent
            _prosecutor_agent = ProsecutorAgent(lexigraph_agent=LexiGraphAgent())
        except Exception as exc:
            print(f"[Orchestrator] ProsecutorAgent init failed: {exc}. Will use LLM fallback each call.")
            _prosecutor_agent = None
    return _prosecutor_agent


# ── Helper: build Turn ────────────────────────────────────────────────────────

def _make_turn(
    state: SimulationState,
    speaker: str,
    content: str,
    citations: Optional[List[str]] = None,
    evidence_refs: Optional[List[str]] = None,
    structured_argument: Optional[Dict[str, Any]] = None,
    grounded: bool = True,
    unverified: Optional[List[str]] = None,
) -> Turn:
    existing = state.get("transcript", [])
    if citations is None:
        citations = extract_citations_with_act(content)
    if evidence_refs is None:
        evidence_refs = extract_evidence_references(content)
    if structured_argument is None:
        structured_argument = parse_argument_structure(content)

    return Turn(
        turn_no=len(existing) + 1,
        speaker=speaker,
        round_no=state.get("round_no", 1),
        content=content,
        citations=citations,
        evidence_refs=evidence_refs,
        structured_argument=structured_argument,
        grounded=grounded,
        unverified=unverified or [],
    )


# ══════════════════════════════════════════════════════════════════════════════
# NODES
# ══════════════════════════════════════════════════════════════════════════════

def node_init_session(state: SimulationState, *, emit: Optional[Callable] = None) -> dict:
    """
    Node 1: init_session
    Initialize Redis namespace, emit phase_change INIT.
    """
    sid = state["session_id"]
    emit and emit(_event("phase_change", phase="INIT", session_id=sid))

    # Seed Redis keys
    _redis_set(f"session:{sid}:state", {"phase": "INIT"})
    _redis_set(f"session:{sid}:transcript", [])
    _redis_set(f"session:{sid}:testimony", [])
    _redis_set(f"session:{sid}:lexicache", {})

    print(f"[Orchestrator] Session {sid} initialized.")
    return {
        "phase": "EVIDENCE",
        "evidence_inventory": [],
        "holdings": [],
        "verified": {"evidence": False, "lexigraph": False},
        "_evidence_retries": 0,
        "_lexigraph_retries": 0,
        "round_no": 1,
        "transcript": [],
        "pending_questions": [],
        "errors": [],
        "clarification_needed": False,
    }


# ─────────────────────────────────────────────────────────────────────────────

def node_evidence_analyzer(state: SimulationState, *, emit: Optional[Callable] = None) -> dict:
    """
    Node 2: evidence_analyzer
    OCR + LLM fact extraction. Gate: if extraction fails, retry ≤2 else FAILED.
    """
    sid = state["session_id"]
    emit and emit(_event("phase_change", phase="EVIDENCE"))
    print("[Orchestrator] ▶ EVIDENCE ANALYZER")

    try:
        def _run():
            case_id   = state.get("case_id", "")
            case_path = Path(case_id)

            if case_path.exists():
                # ── File path (PDF/image) — needs full OCR pipeline ─────────────────
                from agents.evidence.evidence_analyzer import analyze_evidence
                return analyze_evidence(sid, str(case_path))

            # ── Raw text — LLM-only extraction, no OCR / pytesseract needed ──────
            try:
                # Try the proper extractor first (works when pytesseract IS installed)
                from agents.evidence.evidence_analyzer import extract_facts
                return extract_facts(case_id)
            except (ImportError, ModuleNotFoundError):
                pass

            # Inline fallback: plain LLM call, zero OCR deps
            import re as _re, json as _json
            from config.llm_config import get_llm
            llm = get_llm(temperature=0)
            prompt = (
                "You are a legal document analyst.\n"
                "Extract an open, comprehensive list of facts from the following case text.\n"
                "Extract each distinct factual assertion as an item in a list, tied to its source, and classify its type.\n"
                "Classify each fact with type:\n"
                "- 'allegation': claims/allegations made by complainant, informant, FIR, prosecution, or defense\n"
                "- 'procedural_event': official process steps (FIR date, summons, bailable/non-bailable warrants, Sec 82 proclamation, attachment)\n"
                "- 'court_finding': judge's reasoning, findings, conclusions, or legal observations in the judgment\n\n"
                "Return ONLY valid JSON as a list of objects (no markdown, no commentary):\n"
                '[\n'
                '  {"id": "fact_1", "text": "NBW issued on 03.11.2022; applicants did not appear", "source": "para 14", "type": "procedural_event"},\n'
                '  {"id": "fact_2", "text": "...", "source": "...", "type": "allegation"}\n'
                ']\n\n'
                f"Case text:\n{case_id}"
            )
            resp    = llm.invoke(prompt)
            cleaned = _re.sub(r"^```(?:json)?|```$", "", resp.content.strip(),
                               flags=_re.MULTILINE).strip()
            return _json.loads(cleaned)

        raw_facts = _with_retry(_run, max_retries=2, label="evidence_analyzer")

        # Normalize to List[Fact] with explicit Fact IDs (fact_1, fact_2, ...)
        facts: List[Fact] = []
        if isinstance(raw_facts, list):
            for i, f in enumerate(raw_facts):
                if isinstance(f, Fact):
                    facts.append(f)
                elif isinstance(f, dict):
                    fid = str(f.get("id") or f"fact_{i + 1}")
                    txt = str(f.get("text") or f.get("value") or "").strip()
                    src = str(f.get("source") or "record").strip()
                    ftype = str(f.get("type") or "allegation").strip().lower()
                    if ftype not in ("allegation", "procedural_event", "court_finding"):
                        ftype = "allegation"
                    if txt:
                        facts.append(Fact(id=fid, text=txt, source=src, type=ftype))
                elif isinstance(f, str) and f.strip():
                    facts.append(Fact(id=f"fact_{i + 1}", text=f.strip(), source="record", type="allegation"))
        elif isinstance(raw_facts, dict):
            # Backward-compat fallback if a dict was returned
            for k, v in raw_facts.items():
                if isinstance(v, dict):
                    for sub_k, sub_v in v.items():
                        if sub_v:
                            fid = f"fact_{len(facts) + 1}"
                            facts.append(Fact(id=fid, text=f"{k}.{sub_k}: {sub_v}", source="record", type="allegation"))
                elif isinstance(v, list):
                    for item in v:
                        if item:
                            fid = f"fact_{len(facts) + 1}"
                            facts.append(Fact(id=fid, text=f"{k}: {item}", source="record", type="allegation"))
                elif v:
                    fid = f"fact_{len(facts) + 1}"
                    facts.append(Fact(id=fid, text=f"{k}: {v}", source="record", type="allegation"))

        if not facts:
            raise ValueError("Evidence analyzer returned zero facts.")

        # Build a basic evidence_map: each fact ID → fact text
        evidence_map = {f.id: f.text for f in facts}

        # Extract evidence inventory (what is present vs not on record)
        case_id_text = state.get("case_id", "")
        evidence_inventory = extract_evidence_inventory(case_id_text, facts)

        emit and emit(_event("agent_message", agent="evidence_analyzer",
                             round=0,
                             content=f"Extracted {len(facts)} facts and inventory of {len(evidence_inventory)} evidence items.",
                             citations=[]))

        _redis_set(f"session:{sid}:state", {
            "phase": "EVIDENCE",
            "facts_count": len(facts),
            "evidence_inventory_count": len(evidence_inventory),
        })

        return {
            "phase": "LEXIGRAPH",
            "case_facts": facts,
            "evidence_inventory": evidence_inventory,
            "evidence_map": evidence_map,
            "verified": {**state.get("verified", {}), "evidence": True},
            "_evidence_retries": 0,
        }

    except Exception as exc:
        retries = state.get("_evidence_retries", 0) + 1
        err_msg = f"Evidence extraction failed (attempt {retries}): {exc}"
        state_errors = list(state.get("errors", [])) + [err_msg]
        if emit:
            emit(_event("error", message=err_msg, recoverable=(retries <= MAX_EVIDENCE_RETRIES)))
        else:
            print(f"[Orchestrator][ERROR] {err_msg}")

        if retries > MAX_EVIDENCE_RETRIES:
            return {"phase": "FAILED", "errors": state_errors, "_evidence_retries": retries}
        return {
            "phase": "EVIDENCE",
            "errors": state_errors,
            "_evidence_retries": retries,
            "verified": {**state.get("verified", {}), "evidence": False},
        }


# ─────────────────────────────────────────────────────────────────────────────

def node_lexigraph(state: SimulationState, *, emit: Optional[Callable] = None) -> dict:
    """
    Node 3: lexigraph
    7-stage lexigraphbe pipeline + dynamic holding retrieval. Gate: verified? retry ≤2 else FAILED.
    Caches results in Redis.
    """
    sid = state["session_id"]
    emit and emit(_event("phase_change", phase="LEXIGRAPH"))
    print("[Orchestrator] ▶ LEXIGRAPH (Statutes & Precedent Holdings)")

    # Check cache first
    cached = _redis_get(f"session:{sid}:lexicache")
    if cached and (cached.get("ipc_sections") or cached.get("holdings")):
        print("[Orchestrator] LexiGraph: using cached result.")
        return {
            "phase": "COURTROOM",
            "lexigraph_output": cached,
            "holdings": cached.get("holdings", []),
            "case_context": cached.get("stage0_case_context", {}),
            "verified": {**state.get("verified", {}), "lexigraph": True},
            "_lexigraph_retries": 0,
        }

    try:
        def _run():
            # Build comprehensive query from case text and extracted facts
            case_id = state.get("case_id", "")
            case_doc_text = ""
            if Path(case_id).exists() and Path(case_id).is_file():
                try:
                    case_doc_text = Path(case_id).read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    pass
            elif len(case_id) > 20:
                case_doc_text = case_id

            facts = state.get("case_facts", [])
            facts_text = " ".join([f"[{getattr(f, 'id', f.get('id', ''))}] {getattr(f, 'text', f.get('text', f.get('value', '')))}" for f in facts])
            query = case_doc_text or facts_text or "legal case analysis"

            # Try full lexigraphbe pipeline first
            try:
                from lexigraphbe.statute_repository import StatuteRepository
                StatuteRepository.reset_instance()
                from lexigraphbe.runner import run_full_pipeline
                raw = run_full_pipeline(text=query)
                # Merge with standard format
                ipc_sections = []
                _strength_score = {"Strong": 0.95, "Moderate": 0.8, "Weak": 0.6}
                for vo in raw.get("stage4_statutory_verification", {}).get("verified_offences", []):
                    # Sections Stage 4 found not attracted are not law the courtroom should argue from.
                    if str(vo.get("overall_status", "")).strip().lower() == "not attracted":
                        continue
                    ipc_sections.append({
                        "section":     str(vo.get("section_number", "")),
                        "description": str(vo.get("title", "")),
                        "punishment":  str(vo.get("punishment_text") or (vo.get("punishment") or {}).get("maximum") or "N/A"),
                        "offense":     str(vo.get("title", "")),
                        "source":      "lexigraphbe",
                        "score":       _strength_score.get(vo.get("overall_prima_facie_strength"), 0.6),
                        "status":      vo.get("overall_status", ""),
                    })
                raw["ipc_sections"] = ipc_sections
                from agents.lexigraph.holding_retrieval import retrieve_holdings
                raw["holdings"] = retrieve_holdings(query, case_facts=facts, top_k=5)
                return raw
            except ImportError:
                pass

            # Fallback: lexigraph __init__.retrieve()
            from agents.lexigraph import retrieve
            result = retrieve(query, case_facts=facts)
            return result

        output = _with_retry(_run, max_retries=2, label="lexigraph")

        if not output.get("ipc_sections") and not output.get("stage4_statutory_verification") and not output.get("holdings"):
            raise ValueError("LexiGraph returned no sections or holdings — verification failed.")

        # Cache result
        _redis_set(f"session:{sid}:lexicache", output)

        sections_count = len(output.get("ipc_sections", []))
        holdings_count = len(output.get("holdings", []))

        # Build a citation list that excludes N/A placeholders and includes holding IDs.
        section_citations = [
            s["section"] for s in output.get("ipc_sections", [])
            if s.get("section") and str(s["section"]).strip().upper() not in ("N/A", "NOT APPLICABLE", "NA", "")
        ]
        # Also pull holding IDs from production_output if available (ProsecutorAgent pipeline)
        holding_ids = output.get("holding_ids", [])

        subtitle_parts = []
        if section_citations:
            subtitle_parts.append(f"Sections: {', '.join(section_citations)}")
        if holding_ids:
            subtitle_parts.append(f"Holdings: {', '.join(str(h) for h in holding_ids)}")
        if not subtitle_parts:
            subtitle_parts.append(f"{sections_count} sections · {holdings_count} holdings retrieved")
        subtitle = " | ".join(subtitle_parts)

        emit and emit(_event(
            "agent_message", agent="lexigraph", round=0,
            content=f"Retrieved {sections_count} verified sections and {holdings_count} precedent holdings.",
            citations=section_citations,
            subtitle=subtitle,
        ))

        return {
            "phase": "COURTROOM",
            "lexigraph_output": output,
            "holdings": output.get("holdings", []),
            "case_context": output.get("stage0_case_context", {}),
            "verified": {**state.get("verified", {}), "lexigraph": True},
            "_lexigraph_retries": 0,
        }

    except Exception as exc:
        retries = state.get("_lexigraph_retries", 0) + 1
        err_msg = f"LexiGraph failed (attempt {retries}): {exc}"
        print(f"[Orchestrator] {err_msg}")
        state_errors = list(state.get("errors", [])) + [err_msg]
        emit and emit(_event("error", message=err_msg, recoverable=(retries <= MAX_LEXIGRAPH_RETRIES)))

        if retries > MAX_LEXIGRAPH_RETRIES:
            return {"phase": "FAILED", "errors": state_errors, "_lexigraph_retries": retries}
        return {
            "phase": "LEXIGRAPH",
            "errors": state_errors,
            "_lexigraph_retries": retries,
            "verified": {**state.get("verified", {}), "lexigraph": False},
        }


# ─────────────────────────────────────────────────────────────────────────────

def _generate_with_citation_check(
    agent_fn: Callable[[], str],
    state: SimulationState,
    speaker: str,
    emit: Optional[Callable],
) -> tuple[str, List[str], bool, List[str]]:
    """
    Call agent_fn(), check citations, retry up to MAX_CITATION_RETRIES.
    Returns (content, verified_citations, grounded, unverified_citations).
    `grounded` is True only when agent_fn() succeeded and citations were verified.
    """
    lexigraph_output = state.get("lexigraph_output", {})
    case_facts       = state.get("case_facts", [])
    holdings         = state.get("holdings", []) or lexigraph_output.get("holdings", [])
    evidence_inv     = state.get("evidence_inventory", [])

    content, cited = "", []
    unverified_citations: List[str] = []
    grounded = True
    for attempt in range(1, MAX_CITATION_RETRIES + 2):
        try:
            content  = agent_fn()
        except Exception as agent_exc:
            grounded = False
            err_msg = f"[Orchestrator] {speaker} agent raised on attempt {attempt}: {agent_exc}"
            print(err_msg)
            traceback.print_exc()
            emit and emit(_event("error", message=err_msg, recoverable=True, grounded=False))
            content = ""
            if attempt > MAX_CITATION_RETRIES:
                break
            continue

        cited    = _extract_cited_sections(content)
        ok, bad  = _verify_citations(cited, lexigraph_output, case_facts=case_facts, holdings=holdings)
        fact_ok  = _verify_fact_references(content, case_facts, evidence_inv)

        if (ok or not cited) and fact_ok:
            return content, cited, True, []

        unverified_citations = list(bad) if isinstance(bad, (list, set, tuple)) else ([bad] if bad else [])
        warn = (
            f"[Orchestrator] {speaker} attempt {attempt}: "
            f"unverified citations {unverified_citations}. Regenerating…"
        )
        print(warn)
        emit and emit(_event("error", message=warn, recoverable=True))

        if attempt > MAX_CITATION_RETRIES:
            print(f"[Orchestrator] {speaker}: using last output despite unverified citations.")
            grounded = False
            break

    return content, cited, grounded, unverified_citations


def node_prosecutor(state: SimulationState, *, emit: Optional[Callable] = None) -> dict:
    """
    Node 4: prosecutor
    Generates prosecution argument with citation verification and unified formatting.
    `grounded=True` in the emitted event means the ProsecutorAgent successfully
    used LexiGraph-verified retrieval. `grounded=False` means it fell back to a
    plain LLM call or citations could not be grounded in the case record.
    """
    print(f"[Orchestrator] ▶ PROSECUTOR (Round {state.get('round_no', 1)})")
    ctx = _prosecutor_context(state)
    sid = state["session_id"]

    def _call():
        prosecutor = _prosecutor()
        if prosecutor is None:
            raise RuntimeError("ProsecutorAgent unavailable — cannot produce grounded argument.")
        facts_lines = [
            f"[{getattr(f, 'id', f.get('id', f'fact_{i+1}'))}] {getattr(f, 'text', f.get('text', f.get('value', '')))} (Source: {getattr(f, 'source', f.get('source', 'record'))})"
            for i, f in enumerate(ctx["case_facts"])
        ]
        facts_str = "\n".join(facts_lines)
        from agents.lexigraph.holding_retrieval import format_holdings_for_prompt
        holdings_block = format_holdings_for_prompt(ctx.get("holdings", [])) if ctx.get("holdings") else ""
        case_input_text = f"{facts_str}\n\n{holdings_block}" if holdings_block else facts_str

        last_defense = ctx.get("last_defense_argument", "")
        phase        = "opening" if ctx["round_no"] == 1 else "rebuttal"
        # Pass the cached lexigraph production_output so retrieval runs ONCE
        # and the LLM-retry loop only regenerates the LLM call, not the whole
        # embedding + Pinecone + graph pipeline.
        cached_production = ctx.get("lexigraph_output") or None
        case_file = ctx.get("canonical_case_file") or get_or_build_case_file(state)
        result = prosecutor.generate_turn(
            case_facts=case_file,
            phase=phase,
            opposing_argument=last_defense or None,
            production_output=cached_production,
            canonical_case_file=case_file,
        )
        formatted_md, _, _, _ = structure_prosecution_turn(
            result, ctx["case_facts"], ctx["lexigraph_output"]
        )
        return formatted_md

    content, citations, grounded, unverified = _generate_with_citation_check(_call, state, "prosecutor", emit)

    if not content:
        # Loud fallback: still produce output so the run doesn't break, but
        # flag it clearly in logs AND in the WebSocket event.
        print(f"[Orchestrator][WARN] PROSECUTOR round {ctx['round_no']}: grounded=False — "
              "ProsecutorAgent failed to produce output; using plain LLM fallback.")
        try:
            from config.llm_config import get_llm
            llm       = get_llm()
            laws_str  = format_for_prompt(ctx["lexigraph_output"])
            facts_lines = [
                f"[{getattr(f, 'id', f.get('id', f'fact_{i+1}'))}] {getattr(f, 'text', f.get('text', f.get('value', '')))} (Source: {getattr(f, 'source', f.get('source', 'record'))})"
                for i, f in enumerate(ctx["case_facts"])
            ]
            facts_str = "\n".join(facts_lines)
            resp = llm.invoke(
                f"You are a prosecution lawyer. Round {ctx['round_no']}.\n"
                f"Facts:\n{facts_str}\n"
                f"Verified laws:\n{laws_str}\n"
                f"Defense (last round): {ctx.get('last_defense_argument','(none)')}\n"
                f"Deliver a structured courtroom argument citing verified IPC sections with Act names (e.g. IPC 324) and referencing fact IDs (e.g. [fact_1])."
            )
            raw_fallback = resp.content
            content, citations, _, _ = structure_prosecution_turn(
                raw_fallback, ctx["case_facts"], ctx["lexigraph_output"]
            )
        except Exception as fb_exc:
            print(f"[Orchestrator][ERROR] Prosecutor plain-LLM fallback also failed: {fb_exc}")
            content = "[Prosecutor argument unavailable — retrieval and fallback both failed.]"
            citations = []
        emit and emit(_event("warn",
                             message="Prosecutor used plain-LLM fallback (no LexiGraph grounding).",
                             grounded=False,
                             unverified=unverified))
    elif not grounded:
        print(f"[Orchestrator][WARN] PROSECUTOR round {ctx['round_no']}: grounded=False — "
              f"unverified citations remain: {unverified}")
        emit and emit(_event("warn",
                             message=f"Prosecutor argument has unverified citations: {unverified}",
                             grounded=False,
                             unverified=unverified))

    ev_refs = extract_evidence_references(content) or link_facts_to_text(content, ctx["case_facts"])
    parsed_struct = parse_argument_structure(content)
    turn = _make_turn(
        state,
        "prosecutor",
        content,
        citations=citations,
        evidence_refs=ev_refs,
        structured_argument=parsed_struct,
        grounded=grounded,
        unverified=unverified,
    )
    transcript = list(state.get("transcript", [])) + [turn]
    _redis_lpush(f"session:{sid}:transcript", turn)
    emit and emit(_event("agent_message", agent="prosecutor",
                          round=state.get("round_no", 1), content=content,
                          citations=citations, evidence_refs=ev_refs,
                          grounded=grounded, unverified=unverified))

    return {"current_speaker": "defense", "transcript": transcript}


def node_defense(state: SimulationState, *, emit: Optional[Callable] = None) -> dict:
    """
    Node 5: defense
    Generates defense argument with citation verification and unified formatting.
    `grounded` is propagated to the emitted event for parity with node_prosecutor.
    """
    print(f"[Orchestrator] ▶ DEFENSE (Round {state.get('round_no', 1)})")
    ctx = _defense_context(state)
    sid = state["session_id"]

    def _call():
        agent = _defense()
        return agent.generate(
            structured_facts={},
            lexigraph_result=ctx["lexigraph_output"],
            prosecution_arguments=ctx.get("last_prosecution_argument", ""),
            evidence_inventory=ctx.get("evidence_inventory", []),
            case_facts=ctx["case_facts"],
            canonical_case_file=ctx.get("canonical_case_file"),
        )

    content, citations, grounded, unverified = _generate_with_citation_check(_call, state, "defense", emit)

    if not content:
        print(f"[Orchestrator][WARN] DEFENSE round {ctx['round_no']}: grounded=False — "
              "DefenseAgent failed; output was NOT produced.")
        emit and emit(_event("warn",
                             message="Defense failed to produce output.",
                             grounded=False,
                             unverified=unverified))
    elif not grounded:
        print(f"[Orchestrator][WARN] DEFENSE round {ctx['round_no']}: grounded=False — "
              f"unverified citations remain: {unverified}")
        emit and emit(_event("warn",
                             message=f"Defense argument has unverified citations: {unverified}",
                             grounded=False,
                             unverified=unverified))

    ev_refs = extract_evidence_references(content) or link_facts_to_text(content, ctx["case_facts"])
    parsed_struct = parse_argument_structure(content)
    turn = _make_turn(
        state,
        "defense",
        content,
        citations=citations,
        evidence_refs=ev_refs,
        structured_argument=parsed_struct,
        grounded=grounded,
        unverified=unverified,
    )
    transcript = list(state.get("transcript", [])) + [turn]
    _redis_lpush(f"session:{sid}:transcript", turn)
    emit and emit(_event("agent_message", agent="defense",
                          round=state.get("round_no", 1), content=content,
                          citations=citations, evidence_refs=ev_refs,
                          grounded=grounded, unverified=unverified))

    return {"current_speaker": "judge", "transcript": transcript}


def node_judge_evaluate(state: SimulationState, *, emit: Optional[Callable] = None) -> dict:
    """
    Node 6: judge_evaluate
    Scores arguments, decides clarification needed or next round.
    """
    print(f"[Orchestrator] ▶ JUDGE EVALUATE (Round {state.get('round_no', 1)})")
    sid = state["session_id"]
    ctx = _judge_context(state)

    # Pull latest prosecution and defense turns
    p_arg = d_arg = ""
    for t in reversed(ctx["transcript"]):
        if not p_arg and t["speaker"] == "prosecutor":
            p_arg = t["content"]
        if not d_arg and t["speaker"] == "defense":
            d_arg = t["content"]
        if p_arg and d_arg:
            break

    facts_list = _get_debate_facts(state.get("case_facts", []))
    relevant_laws = state.get("lexigraph_output", {}).get("ipc_sections", [])
    inventory = state.get("evidence_inventory", [])
    holdings = state.get("holdings") or state.get("lexigraph_output", {}).get("holdings", [])

    scores_raw, question = _judge().score(
        facts_list,
        p_arg,
        d_arg,
        relevant_laws,
        evidence_inventory=inventory,
        holdings=holdings,
        canonical_case_file=ctx.get("canonical_case_file"),
    )

    # Normalize scores to 0–10 overall for each side
    p_scores = scores_raw.get("prosecution", {})
    d_scores = scores_raw.get("defense", {})
    p_total = float(p_scores.get("total", 0))
    d_total = float(d_scores.get("total", 0))
    p_avg = round(p_total / 3.0, 2)
    d_avg = round(d_total / 3.0, 2)
    overall = round((p_avg + d_avg) / 2.0, 2)

    judge_scores = {
        "prosecution": {
            "legal_validity": p_scores.get("legal_validity", 0),
            "evidence_linkage": p_scores.get("evidence_linkage", 0),
            "logic_coherence": p_scores.get("logic_coherence", 0),
            "total": p_total,
            "average": p_avg,
        },
        "defense": {
            "legal_validity": d_scores.get("legal_validity", 0),
            "evidence_linkage": d_scores.get("evidence_linkage", 0),
            "logic_coherence": d_scores.get("logic_coherence", 0),
            "total": d_total,
            "average": d_avg,
        },
        "overall": overall,
    }

    print(f"[Orchestrator] JUDGE SCORES (Round {state.get('round_no', 1)}):")
    print(f"  • Prosecution : Legal {p_scores.get('legal_validity',0)}/10, Evidence {p_scores.get('evidence_linkage',0)}/10, Logic {p_scores.get('logic_coherence',0)}/10 -> Avg: {p_avg}/10 (Total: {p_total}/30)")
    print(f"  • Defense     : Legal {d_scores.get('legal_validity',0)}/10, Evidence {d_scores.get('evidence_linkage',0)}/10, Logic {d_scores.get('logic_coherence',0)}/10 -> Avg: {d_avg}/10 (Total: {d_total}/30)")
    print(f"  • Overall Debate Quality: {overall}/10 (Sufficiency Threshold: {JUDGE_THRESHOLD})")

    # Cap clarification questions to at most 1 per round so Judge proceeds to verdict after testimony
    accused_turns_this_round = [
        t for t in state.get("transcript", [])
        if t.get("speaker") == "accused" and t.get("round_no") == state.get("round_no", 1)
    ]
    clarification_needed = bool(question) and len(accused_turns_this_round) < 1

    emit and emit(_event("judge_scores",
                          round=state.get("round_no", 1),
                          prosecution=judge_scores["prosecution"],
                          defense=judge_scores["defense"],
                          overall=overall))

    pending = list(state.get("pending_questions", []))
    if clarification_needed:
        q = Question(
            question_id=str(uuid.uuid4())[:8],
            asked_by="judge",
            to="accused",
            question=question,
            answered=False,
            answer=None,
        )
        pending.append(q)
        emit and emit(_event("judge_question", to="accused", question=question))

    return {
        "judge_scores": judge_scores,
        "clarification_needed": clarification_needed,
        "pending_questions": pending,
    }


def node_judge_question(state: SimulationState, *, emit: Optional[Callable] = None) -> dict:
    """
    Node 7: judge_question (emits question, passes through)
    """
    pending = [q for q in state.get("pending_questions", []) if not q["answered"]]
    if pending:
        q = pending[0]
        print(f"[Orchestrator] ▶ JUDGE QUESTION → Accused: '{q['question']}'")
        emit and emit(_event("judge_question", to="accused", question=q["question"]))
    return {}


def node_accused(state: SimulationState, *, emit: Optional[Callable] = None) -> dict:
    """
    Node 8: accused
    Generates testimony for each unanswered judge question.
    Consistency check is done inside AccusedAgent.
    """
    print(f"[Orchestrator] ▶ ACCUSED TESTIMONY")
    sid = state["session_id"]

    pending    = state.get("pending_questions", [])
    unanswered = [q for q in pending if not q["answered"]]
    if not unanswered:
        return {}

    question = unanswered[0]["question"]
    facts_list = state.get("case_facts", [])
    history_in_state = [
        t["content"] for t in state.get("transcript", []) if t["speaker"] == "accused"
    ]

    testimony = _accused().respond(
        session_id=sid,
        question=question,
        structured_facts=facts_list,
        prior_history=history_in_state,
    )

    # Mark question answered
    updated_pending = []
    answered = False
    for q in pending:
        if not answered and not q["answered"] and q["question"] == question:
            q = dict(q, answered=True, answer=testimony)
            answered = True
        updated_pending.append(q)

    # Only write testimony that passed accused agent's consistency check
    _redis_lpush(f"session:{sid}:testimony", {"question": question, "answer": testimony})

    turn = _make_turn(state, "accused", testimony, [])
    transcript = list(state.get("transcript", [])) + [turn]
    _redis_lpush(f"session:{sid}:transcript", turn)

    emit and emit(_event("agent_message", agent="accused",
                          round=state.get("round_no", 1), content=testimony, citations=[]))

    return {
        "transcript": transcript,
        "pending_questions": updated_pending,
        "clarification_needed": False,
    }


def node_judge_verdict(state: SimulationState, *, emit: Optional[Callable] = None) -> dict:
    """
    Node 9: judge_verdict
    Delivers final verdict via n-shot majority voting (voting.decide()).
    """
    print("[Orchestrator] ▶ JUDGE VERDICT")
    sid = state["session_id"]

    p_arg = d_arg = ""
    for t in reversed(state.get("transcript", [])):
        if not p_arg and t["speaker"] == "prosecutor": p_arg = t["content"]
        if not d_arg and t["speaker"] == "defense":    d_arg = t["content"]
        if p_arg and d_arg: break

    facts_list = state.get("case_facts", [])
    accused_history = [
        t["content"] for t in state.get("transcript", []) if t["speaker"] == "accused"
    ]
    relevant_laws = state.get("lexigraph_output", {}).get("ipc_sections", [])
    inventory = state.get("evidence_inventory", [])
    holdings = state.get("holdings") or state.get("lexigraph_output", {}).get("holdings", [])

    # verdict() delegates to voting.decide() and returns VerdictResult.to_dict()
    raw_verdict = _judge().verdict(
        structured_facts=facts_list,
        prosecution_args=p_arg,
        defense_args=d_arg,
        accused_history=accused_history,
        judge_scores=state.get("judge_scores", {}),
        relevant_laws=relevant_laws,
        evidence_inventory=inventory,
        holdings=holdings,
        canonical_case_file=get_or_build_case_file(state),
    )

    decision   = str(raw_verdict.get("decision", "NO_OPINION")).upper()
    conf_label = str(raw_verdict.get("confidence_label") or raw_verdict.get("confidence") or "medium").lower()
    agreement_rate = float(raw_verdict.get("agreement_rate", 0.0))
    reasoning  = raw_verdict.get("reasoning", "")
    vote_tally = raw_verdict.get("vote_tally", {})
    valid_votes = raw_verdict.get("valid_votes", 0)
    total_votes = raw_verdict.get("total_votes", 0)
    agree_count = raw_verdict.get("agree_count", 0)

    verdict = {
        "decision":          decision,
        "confidence":        conf_label,
        "confidence_label":  conf_label,
        "agreement_rate":    agreement_rate,
        "valid_votes":       valid_votes,
        "total_votes":       total_votes,
        "agree_count":       agree_count,
        "laws_applied":      raw_verdict.get("laws_applied", []),
        "statutes":          raw_verdict.get("statutes", []),
        "precedents":        raw_verdict.get("precedents", []),
        "holdings_relied":   raw_verdict.get("holdings_relied", []),
        "reasoning":         reasoning,
        "factors":           raw_verdict.get("factors", []),
        "open_questions":    raw_verdict.get("open_questions", []),
        "vote_tally":        vote_tally,
    }

    tally_str = " | ".join(f"{k}:{v}" for k, v in vote_tally.items()) if vote_tally else "n/a"
    valid_summary = f"{valid_votes}/{total_votes} valid, {agree_count}/{valid_votes if valid_votes else 1} agree"
    print(
        f"[Orchestrator] VERDICT: {decision}  "
        f"Confidence: {conf_label.upper()} ({valid_summary})  Tally: [{tally_str}]"
    )

    emit and emit(_event("verdict",
                          result=verdict["decision"],
                          confidence=conf_label,
                          confidence_label=conf_label,
                          agreement_rate=agreement_rate,
                          valid_votes=valid_votes,
                          total_votes=total_votes,
                          agree_count=agree_count,
                          statutes=verdict["statutes"],
                          precedents=verdict["precedents"],
                          holdings_relied=verdict["holdings_relied"],
                          vote_tally=vote_tally,
                          explanation=verdict["reasoning"]))

    return {"phase": "VERDICT", "verdict": verdict}


def node_finalize(state: SimulationState, *, emit: Optional[Callable] = None) -> dict:
    """
    Node 10: finalize
    Persist full transcript to Redis, mark DONE.
    """
    sid = state["session_id"]
    _redis_set(f"session:{sid}:state", {
        "phase": "DONE",
        "verdict": state.get("verdict"),
        "round_no": state.get("round_no"),
    })
    _redis_set(f"session:{sid}:transcript", state.get("transcript", []))
    try:
        md_p, json_p = export_transcript(state)
        print(f"[Orchestrator] Session {sid} transcript saved:\n  • {md_p}\n  • {json_p}")
    except Exception as exc:
        print(f"[Orchestrator] Session {sid} transcript export error: {exc}")
    print(f"[Orchestrator] Session {sid} finalized.")
    emit and emit(_event("phase_change", phase="DONE"))
    return {"phase": "DONE"}


def node_failed(state: SimulationState, *, emit: Optional[Callable] = None) -> dict:
    """
    Failure terminal node.
    """
    sid = state["session_id"]
    errors = state.get("errors", [])
    print(f"[Orchestrator] FAILED — {errors}")
    _redis_set(f"session:{sid}:state", {"phase": "FAILED", "errors": errors})
    emit and emit(_event("phase_change", phase="FAILED"))
    emit and emit(_event("error", message="; ".join(errors), recoverable=False))
    return {"phase": "FAILED"}


# ══════════════════════════════════════════════════════════════════════════════
# ROUTING FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def route_after_evidence(state: SimulationState) -> str:
    phase = state.get("phase", "")
    if phase == "FAILED":
        return "failed"
    verified = state.get("verified", {})
    if not verified.get("evidence", False):
        return "evidence_analyzer"   # retry
    return "lexigraph"


def route_after_lexigraph(state: SimulationState) -> str:
    phase = state.get("phase", "")
    if phase == "FAILED":
        return "failed"
    verified = state.get("verified", {})
    if not verified.get("lexigraph", False):
        return "lexigraph"           # retry
    return "prosecutor"


def route_after_judge_evaluate(state: SimulationState) -> str:
    """
    Core routing logic (rule-based, no LLM):
      clarification_needed → judge_question
      score < threshold AND rounds left → increment_round (then prosecutor)
      else → judge_verdict
    """
    round_no   = state.get("round_no", 1)
    max_rounds = state.get("max_rounds", DEFAULT_MAX_ROUNDS)

    if state.get("clarification_needed", False):
        print(f"[Orchestrator] Clarification needed from accused (Round {round_no}). Routing to judge_question.")
        return "judge_question"

    pending = [q for q in state.get("pending_questions", []) if not q.get("answered")]
    overall = state.get("judge_scores", {}).get("overall", 10.0)
    needs_more_debate = (overall < JUDGE_THRESHOLD) or bool(pending)

    if needs_more_debate and round_no < max_rounds:
        trigger_reason = f"overall score ({overall}) < threshold ({JUDGE_THRESHOLD})" if overall < JUDGE_THRESHOLD else "judge has open questions requiring further argument"
        print(
            f"[Orchestrator] Multi-round debate continuing: {trigger_reason} "
            f"and round {round_no} < max_rounds ({max_rounds}). Routing to Round {round_no + 1} for rebuttal."
        )
        return "increment_round"     # bump round_no, then re-enter prosecutor

    # Explain why debate concluded
    if round_no >= max_rounds:
        reason = f"reached maximum rounds limit ({round_no}/{max_rounds})"
    else:
        reason = f"overall debate score ({overall}) >= sufficiency threshold ({JUDGE_THRESHOLD}) with no unanswered judicial inquiries"

    stop_msg = f"Courtroom debate concluded after Round {round_no}: {reason}. Proceeding to verdict."
    print(f"[Orchestrator] ▶ {stop_msg}")

    return "judge_verdict"


def route_after_accused(state: SimulationState) -> str:
    """After accused testimony, always go back to judge_evaluate."""
    return "judge_evaluate"


# ══════════════════════════════════════════════════════════════════════════════
# GRAPH BUILDER
# ══════════════════════════════════════════════════════════════════════════════

def node_increment_round(state: SimulationState, *, emit: Optional[Callable] = None) -> dict:
    """
    Node: increment_round
    Bumps round_no by 1 before looping back to the prosecutor for another
    argument round.  This is a separate node (not a pure routing function) so
    that the state mutation is correctly checkpointed by LangGraph.
    """
    new_round = state.get("round_no", 1) + 1
    print(f"[Orchestrator] ▶ ROUND INCREMENT → round {new_round}")
    emit and emit(_event("phase_change", phase="COURTROOM", round=new_round))
    return {"round_no": new_round}


def build_graph(emit: Optional[Callable] = None):
    """
    Compile the LangGraph StateGraph.
    `emit` is injected into every node as a partial for WebSocket streaming.
    """
    from functools import partial

    def _wrap(fn):
        """Bind emit into node function."""
        return partial(fn, emit=emit)

    g = StateGraph(SimulationState)

    # Nodes
    g.add_node("init_session",      _wrap(node_init_session))
    g.add_node("evidence_analyzer", _wrap(node_evidence_analyzer))
    g.add_node("lexigraph",         _wrap(node_lexigraph))
    g.add_node("prosecutor",        _wrap(node_prosecutor))
    g.add_node("defense",           _wrap(node_defense))
    g.add_node("judge_evaluate",    _wrap(node_judge_evaluate))
    g.add_node("judge_question",    _wrap(node_judge_question))
    g.add_node("accused",           _wrap(node_accused))
    g.add_node("judge_verdict",     _wrap(node_judge_verdict))
    g.add_node("increment_round",   _wrap(node_increment_round))
    g.add_node("finalize",          _wrap(node_finalize))
    g.add_node("failed",            _wrap(node_failed))

    # Static edges
    g.add_edge(START,               "init_session")
    g.add_edge("init_session",      "evidence_analyzer")
    g.add_edge("defense",           "judge_evaluate")
    g.add_edge("judge_question",    "accused")
    g.add_edge("increment_round",   "prosecutor")   # after incrementing, re-enter prosecutor
    g.add_edge("judge_verdict",     "finalize")
    g.add_edge("finalize",          END)
    g.add_edge("failed",            END)

    # Conditional edges
    g.add_conditional_edges(
        "evidence_analyzer",
        route_after_evidence,
        {"evidence_analyzer": "evidence_analyzer", "lexigraph": "lexigraph", "failed": "failed"},
    )
    g.add_conditional_edges(
        "lexigraph",
        route_after_lexigraph,
        {"lexigraph": "lexigraph", "prosecutor": "prosecutor", "failed": "failed"},
    )
    g.add_edge("prosecutor", "defense")   # prosecutor always → defense

    g.add_conditional_edges(
        "judge_evaluate",
        route_after_judge_evaluate,
        {
            "judge_question":  "judge_question",
            "increment_round": "increment_round",
            "judge_verdict":   "judge_verdict",
        },
    )
    g.add_conditional_edges(
        "accused",
        route_after_accused,
        {"judge_evaluate": "judge_evaluate"},
    )

    return g.compile()


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def run_orchestrator(
    case_id: str,
    session_id: Optional[str] = None,
    max_rounds: int = DEFAULT_MAX_ROUNDS,
    on_event: Optional[Callable[[dict], None]] = None,
) -> dict:
    """
    Run the full MootCourt orchestration pipeline.

    Args:
        case_id:    Path to case PDF/TXT, or raw case text.
        session_id: If None, auto-generated.
        max_rounds: Maximum courtroom argument rounds.
        on_event:   Callback fn(event_dict) for WebSocket streaming.

    Returns:
        Final SimulationState dict.
    """
    if not case_id:
        raise ValueError("case_id (case file path or text) cannot be empty.")

    sid = (session_id[:8] if session_id else str(uuid.uuid4())[:8])
    emit = on_event  # can be None

    initial: SimulationState = {
        "session_id":          sid,
        "case_id":             case_id,
        "phase":               "INIT",
        "case_facts":          [],
        "evidence_inventory":  [],
        "evidence_map":        {},
        "lexigraph_output":    {},
        "holdings":            [],
        "case_context":        {},
        "verified":            {"evidence": False, "lexigraph": False},
        "round_no":            1,
        "max_rounds":          max_rounds,
        "current_speaker":     "prosecutor",
        "transcript":          [],
        "pending_questions":   [],
        "judge_scores":        {},
        "clarification_needed": False,
        "verdict":             None,
        "errors":              [],
        "_evidence_retries":   0,
        "_lexigraph_retries":  0,
    }

    graph = build_graph(emit=emit)

    print("\n" + "=" * 70)
    print(f"[Orchestrator] STARTING -- Session: {sid}  max_rounds={max_rounds}")
    print("=" * 70)

    result = graph.invoke(initial) or {}

    phase   = result.get("phase", "UNKNOWN")
    verdict = (result.get("verdict") or {}).get("decision", "N/A")
    print("\n" + "=" * 70)
    print(f"[Orchestrator] DONE -- Session: {sid}  Phase: {phase}  Verdict: {verdict}")
    print("=" * 70 + "\n")

    return result


