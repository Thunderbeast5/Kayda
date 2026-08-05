"""
LLM-based IPC Section Retrieval Service  (v3 — ReAct Agent)
=============================================================

Architecture
------------
For EACH sub-query the service runs a ReAct (Reason + Act) agent loop.
The agent has a scratchpad, a set of tools it can call, and full autonomy
over which tool to call next and why.  The pipeline from v2 becomes the
agent's *toolbox* — the LLM decides the order and repetition.

ReAct loop (per sub-query)
--------------------------
  THOUGHT  →  ACTION (tool call)  →  OBSERVATION (tool result)
     ↑_______________________________________________|
  ... repeat until the agent emits  ACTION: submit_answer

Tools available to the agent
-----------------------------
  search_chapters(query)
      The agent passes a free-form search hint; the tool returns all 26
      chapter names so the agent can pick from the canonical list.

  get_section_titles(chapter_names: list)
      Returns section IDs + titles for the given chapters (penalised
      sections are hidden).

  get_section_detail(section_ids: list)
      Fetches full statutory text + explanation + illustration + exception
      from ipc_structured.json for each requested section.

  submit_answer(accepted: list, reasoning: str)
      The agent calls this when it is confident.  Triggers Step-4 final
      verification and ends the loop.

  give_up()
      The agent calls this when it genuinely cannot find a match.

Reward / penalise
-----------------
  When submit_answer sections fail final verification the agent is told
  which failed and why, and the loop continues (up to MAX_AGENT_STEPS).
  Accepted sections accumulate in global_confirmed across sub-queries.

Public interface
----------------
  Identical to v1/v2 — callers (LexiGraphAgent, CandidateFusionService)
  need no changes.
"""

from __future__ import annotations

import json
import re
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from config.llm_config import get_llm
except ModuleNotFoundError:
    from agents.config.llm_config import get_llm


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_AGENT_STEPS  = 12    # max Thought→Action→Observation iterations per sub-query
MAX_RETRIES      = 2     # how many times submit_answer may fail before give_up

# Sub-query keywords that are procedural / non-substantive — skipped entirely.
_PROCEDURAL_MARKERS: List[str] = [
    "applicant denies", "applicant alleges", "applicant has cooperated",
    "cooperated with the investigation", "custodial interrogation",
    "anticipatory bail", "bail application", "civil in nature",
    "civil dispute", "exaggerated allegations", "fir contains",
    "applicant claims", "applicant submits", "applicant contends",
    "no need for custody", "pre-arrest bail",
]

# Canonical chapter list — exact strings from ipc_index.json.
_ALL_CHAPTERS: List[str] = [
    "INTRODUCTION",
    "GENERAL EXPLANATIONS",
    "OF PUNISHMENTS",
    "GENERAL EXCEPTIONS",
    "OF ABETMENT",
    "CRIMINAL CONSPIRACY",
    "OF OFFENCES AGAINST THE STATE",
    "OF OFFENCES RELATING TO THE ARMY, NAVY AND AIR FORCE",
    "OF OFFENCES AGAINST THE PUBLIC TRANQUILITY",
    "OF OFFENCES BY OR RELATING TO PUBLIC SERVANTS",
    "OF ELECTIONS",
    "OF CONTEMPTS OF THE LAWFUL AUTHORITY OF PUBLIC SERVANTS",
    "OF FALSE EVIDENCE AND OFFENCES AGAINST PUBLIC JUSTICE",
    "OF OFFENCES RELATING TO COIN AND GOVERNMENT STAMPS",
    "OF OFFENCES RELATING TO WEIGHTS AND MEASURES",
    "OF OFFENCES AFFECTING THE PUBLIC HEALTH, SAFETY, CONVENIENCE, DECENCY AND MORALS",
    "OF OFFENCES RELATING TO RELIGION",
    "OF OFFENCES AFFECTING THE HUMAN BODY",
    "OF OFFENCES AGAINST PROPERTY",
    "OF OFFENCES RELATING TO DOCUMENTS AND TO PROPERTY MARKS",
    "OF THE CRIMINAL BREACH OF CONTRACTS OF SERVICE",
    "OF OFFENCES RELATING TO MARRIAGE",
    "OF CRUELTY BY HUSBAND OR RELATIVES OF HUSBAND",
    "OF DEFAMATION",
    "OR CRIMINAL INTIMIDATION, INSULT AND ANNOYANCE",   # typo in source data kept
    "OF ATTEMPTS TO COMMIT OFFENCES",
]

_CHAPTER_LIST_STR = "\n".join(f"  {i+1:2d}. {ch}" for i, ch in enumerate(_ALL_CHAPTERS))

# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _strip_fences(text: str) -> str:
    return re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE).replace("```", "").strip()

def _extract_json_object(text: str) -> Optional[dict]:
    cleaned = _strip_fences(text)
    m = re.search(r"\{.*?\}", cleaned, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None

def _is_procedural(sub_query: str) -> bool:
    sq_lower = sub_query.lower()
    return any(marker in sq_lower for marker in _PROCEDURAL_MARKERS)


# ---------------------------------------------------------------------------
# AgentScratchpad — tracks the full Thought/Action/Observation history
# ---------------------------------------------------------------------------

class AgentScratchpad:
    """Maintains the running log shown back to the agent each turn."""

    def __init__(self) -> None:
        self._entries: List[str] = []

    def add(self, role: str, content: str) -> None:
        self._entries.append(f"[{role}]\n{content.strip()}")

    def render(self) -> str:
        return "\n\n".join(self._entries)

    def __len__(self) -> int:
        return len(self._entries)


# ---------------------------------------------------------------------------
# Main service
# ---------------------------------------------------------------------------

class LLMIPCRetrievalService:
    """
    ReAct-agent-driven IPC section retrieval service.
    Public interface unchanged from v1/v2.
    """

    def __init__(self, prosecutor_dir: Optional[Path] = None) -> None:
        self.llm = get_llm(temperature=0.0, provider="ollama")

        if prosecutor_dir is None:
            prosecutor_dir = Path(__file__).resolve().parent.parent

        self.prosecutor_dir = prosecutor_dir
        ipc_index_path      = prosecutor_dir / "ipc_index.json"
        ipc_structured_path = prosecutor_dir / "ipc_structured.json"

        print(f"[LLMIPCRetrievalService] Loading IPC data from {prosecutor_dir}")

        self.ipc_index:      List[Dict[str, Any]] = self._load_json(ipc_index_path)
        self.ipc_structured: List[Dict[str, Any]] = self._load_json(ipc_structured_path)

        # ── lookup maps built once ──────────────────────────────────────────
        self._structured_by_id: Dict[str, Dict[str, Any]] = {
            item["id"]: item
            for item in self.ipc_structured
            if isinstance(item, dict) and "id" in item
        }
        self._chapters: Dict[str, List[Dict[str, Any]]] = {}
        for sec in self.ipc_index:
            ch = sec.get("chapter_name", "UNKNOWN")
            self._chapters.setdefault(ch, []).append(sec)

        self._title_to_section: Dict[str, Dict[str, Any]] = {
            sec["title"]: sec for sec in self.ipc_index if "title" in sec
        }

        print(f"[LLMIPCRetrievalService] Loaded {len(self.ipc_index)} sections from ipc_index.json")
        print(f"[LLMIPCRetrievalService] Loaded {len(self._structured_by_id)} sections from ipc_structured.json")

    # =========================================================================
    # Public API
    # =========================================================================

    def retrieve_sections(
        self,
        sub_queries: List[Dict[str, Any]],
        case_facts: str,
        top_k: int = 20,
    ) -> Dict[str, Any]:
        """
        Main entry point.  Returns:
            {"retrieval_results": [{"query", "sub_query_type", "matches": [...]}]}
        Each match: {"id": "IPC_503", "score": float, "metadata": {...}}
        """
        if not sub_queries:
            return {"retrieval_results": []}

        complainant_facts = self._extract_complainant_facts(case_facts)
        retrieval_results: List[Dict[str, Any]] = []
        global_confirmed:  Dict[str, Dict[str, Any]] = {}

        for sq in sub_queries:
            sq_text = sq.get("query", "").strip()
            sq_type = sq.get("type", "OFFENCE")

            if sq_type != "OFFENCE":
                continue
            if _is_procedural(sq_text):
                print(f"[LLMIPCRetrievalService] Skipping procedural sub-query: {sq_text[:80]}")
                continue

            print(f"\n[LLMIPCRetrievalService] ── Agent starting on: {sq_text[:80]}")

            confirmed = self._run_agent(
                sub_query=sq_text,
                complainant_facts=complainant_facts,
                global_confirmed=global_confirmed,
            )
            global_confirmed.update(confirmed)

            matches = self._build_matches(list(confirmed.values()))
            retrieval_results.append({
                "query":          sq_text,
                "sub_query_type": sq_type,
                "matches":        matches,
            })

        all_matches = self._build_matches(list(global_confirmed.values()))
        all_matches = sorted(all_matches, key=lambda m: m["score"], reverse=True)[:top_k]

        if all_matches:
            retrieval_results.append({
                "query":          "[ALL SUB-QUERIES MERGED]",
                "sub_query_type": "OFFENCE",
                "matches":        all_matches,
            })

        print(f"\n[LLMIPCRetrievalService] Total confirmed sections: {len(global_confirmed)}")
        return {"retrieval_results": retrieval_results}

    # =========================================================================
    # ReAct agent core
    # =========================================================================

    def _run_agent(
        self,
        sub_query: str,
        complainant_facts: str,
        global_confirmed: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        """
        Run the ReAct loop for one sub-query.
        Returns confirmed section dict (section_id → metadata).
        """
        scratchpad      = AgentScratchpad()
        confirmed:       Dict[str, Dict[str, Any]] = {}
        penalised_secs:  Set[str] = set()
        submit_attempts: int      = 0

        # ── system prompt seen by the agent every turn ─────────────────────
        system_prompt = self._build_system_prompt(sub_query, complainant_facts)

        for step in range(1, MAX_AGENT_STEPS + 1):
            print(f"[LLMIPCRetrievalService]   Agent step {step}/{MAX_AGENT_STEPS}")

            # Build the full prompt: system + scratchpad + "now think"
            user_turn = self._build_user_turn(scratchpad, step)
            full_prompt = system_prompt + "\n\n" + user_turn

            # ── LLM call ───────────────────────────────────────────────────
            try:
                raw = self.llm.invoke(full_prompt).content.strip()
            except Exception as exc:
                print(f"[LLMIPCRetrievalService]   LLM error at step {step}: {exc}")
                break

            print(f"[LLMIPCRetrievalService]   Agent raw output: {raw[:300]}")
            scratchpad.add("AGENT", raw)

            # ── parse Thought + Action ─────────────────────────────────────
            thought, action_name, action_input = self._parse_agent_output(raw)

            if not action_name:
                # Agent produced no parseable action — nudge it
                obs = "ERROR: Could not parse your action. Please follow the format exactly."
                scratchpad.add("OBSERVATION", obs)
                continue

            print(f"[LLMIPCRetrievalService]   Thought: {thought[:120]}")
            print(f"[LLMIPCRetrievalService]   Action:  {action_name}({str(action_input)[:120]})")

            # ── dispatch to tool ───────────────────────────────────────────
            if action_name == "search_chapters":
                obs = self._tool_search_chapters(action_input)

            elif action_name == "get_section_titles":
                chapter_names = action_input if isinstance(action_input, list) else [action_input]
                obs = self._tool_get_section_titles(chapter_names, penalised_secs, global_confirmed)

            elif action_name == "get_section_detail":
                section_ids = action_input if isinstance(action_input, list) else [action_input]
                obs = self._tool_get_section_detail(section_ids)

            elif action_name == "submit_answer":
                # action_input is expected to be {"accepted": [...], "reasoning": "..."}
                submit_attempts += 1
                accepted_ids = []
                agent_reasoning = ""
                if isinstance(action_input, dict):
                    accepted_ids    = action_input.get("accepted", [])
                    agent_reasoning = action_input.get("reasoning", "")
                elif isinstance(action_input, list):
                    accepted_ids = action_input

                verified_ok, verified_fail, obs = self._tool_submit_answer(
                    section_ids=accepted_ids,
                    sub_query=sub_query,
                    complainant_facts=complainant_facts,
                    agent_reasoning=agent_reasoning,
                )

                for sec_id in verified_ok:
                    cand = self._make_candidate(sec_id, agent_reasoning)
                    if cand:
                        confirmed[sec_id] = cand

                for sec_id in verified_fail:
                    penalised_secs.add(sec_id)

                scratchpad.add("OBSERVATION", obs)

                # If all submitted were accepted, or too many retries → stop
                if verified_ok and not verified_fail:
                    print(f"[LLMIPCRetrievalService]   Agent finished: accepted {list(confirmed.keys())}")
                    break
                if submit_attempts >= MAX_RETRIES and confirmed:
                    print(f"[LLMIPCRetrievalService]   Agent max retries reached, keeping partial results")
                    break
                # Otherwise let the agent keep reasoning
                continue

            elif action_name == "give_up":
                print(f"[LLMIPCRetrievalService]   Agent gave up on sub-query")
                scratchpad.add("OBSERVATION", "Acknowledged. No sections submitted for this sub-query.")
                break

            else:
                obs = f"ERROR: Unknown action '{action_name}'. Valid actions: search_chapters, get_section_titles, get_section_detail, submit_answer, give_up."

            scratchpad.add("OBSERVATION", obs)

        return confirmed

    # =========================================================================
    # Prompt builders
    # =========================================================================

    def _build_system_prompt(self, sub_query: str, complainant_facts: str) -> str:
        return textwrap.dedent(f"""
        You are an expert Indian criminal lawyer and legal research agent.
        Your task is to find the MOST RELEVANT IPC sections that apply to the sub-query below,
        keeping the overall case facts in mind.

        ═══════════════════════════════════════════════════════════════════
        SUB-QUERY  (the specific allegation you must find a section for)
        ───────────────────────────────────────────────────────────────────
        {sub_query}

        OVERALL CASE FACTS  (complainant side only — defence stripped)
        ───────────────────────────────────────────────────────────────────
        {complainant_facts[:700]}
        ═══════════════════════════════════════════════════════════════════

        You have exactly FIVE tools. Call them in any order, as many times as you need.

        ┌─────────────────────────────────────────────────────────────────┐
        │ TOOL 1:  search_chapters                                        │
        │   Input: a short search hint string                             │
        │   Returns: the full list of 26 IPC chapter names               │
        │   Use when: you want to see all available chapters              │
        ├─────────────────────────────────────────────────────────────────┤
        │ TOOL 2:  get_section_titles                                     │
        │   Input: JSON array of exact chapter name strings               │
        │   Returns: section IDs + titles in those chapters               │
        │   Use when: you have chosen chapter(s) and want their sections  │
        ├─────────────────────────────────────────────────────────────────┤
        │ TOOL 3:  get_section_detail                                     │
        │   Input: JSON array of section IDs  e.g. ["IPC_503","IPC_506"] │
        │   Returns: full statutory text, explanation, illustration,      │
        │            exception for each section                           │
        │   Use when: you want to verify a section's exact ingredients    │
        ├─────────────────────────────────────────────────────────────────┤
        │ TOOL 4:  submit_answer                                          │
        │   Input: {{"accepted": ["IPC_X","IPC_Y"], "reasoning": "..."}}  │
        │   Returns: verification result — which passed, which failed     │
        │   Use when: you are confident the sections fit the sub-query    │
        ├─────────────────────────────────────────────────────────────────┤
        │ TOOL 5:  give_up                                                │
        │   Input: "no match found"                                       │
        │   Use when: after thorough search no section applies            │
        └─────────────────────────────────────────────────────────────────┘

        STRICT OUTPUT FORMAT — every response must follow this exactly:

        Thought: <your legal reasoning — what you know so far and what you plan to do next>
        Action: <tool_name>
        Action Input: <the input — a string OR a valid JSON object/array>

        RULES
        ─────
        1. Always write Thought before Action.
        2. Never skip get_section_detail before submit_answer — read the full
           statutory text first so you know the ingredients precisely.
        3. A section qualifies PRIMA FACIE — you do not need proof beyond doubt.
        4. Do not submit punishment-only sections (titles starting "Punishment for").
        5. Consider related sections: abetment (IPC 107-116), conspiracy (IPC 120A-B),
           attempt (IPC 511) if the main offence is not complete.
        6. If submit_answer returns failures, reason about WHY and try different sections.
        7. Call give_up only after genuinely exhausting alternatives.
        """).strip()

    def _build_user_turn(self, scratchpad: AgentScratchpad, step: int) -> str:
        if len(scratchpad) == 0:
            return "Begin. Write your first Thought and Action."
        return (
            "─── Scratchpad so far ───\n"
            + scratchpad.render()
            + f"\n\n─── Step {step}: continue ───\n"
            "Write your next Thought and Action."
        )

    # =========================================================================
    # Agent output parser
    # =========================================================================

    def _parse_agent_output(
        self, raw: str
    ) -> Tuple[str, Optional[str], Any]:
        """
        Parse:
            Thought: ...
            Action: tool_name
            Action Input: ...

        Returns (thought, action_name, action_input).
        action_input is a Python object (dict/list/str) if parseable, else raw string.
        """
        thought      = ""
        action_name  = None
        action_input: Any = None

        # Extract Thought
        tm = re.search(r"Thought\s*:\s*(.+?)(?=Action\s*:|$)", raw, re.DOTALL | re.IGNORECASE)
        if tm:
            thought = tm.group(1).strip()

        # Extract Action name
        am = re.search(r"Action\s*:\s*(\w+)", raw, re.IGNORECASE)
        if am:
            action_name = am.group(1).strip()

        # Extract Action Input
        aim = re.search(r"Action\s+Input\s*:\s*(.+)", raw, re.DOTALL | re.IGNORECASE)
        if aim:
            raw_input = aim.group(1).strip()
            # Try JSON parse first
            cleaned = _strip_fences(raw_input)
            try:
                action_input = json.loads(cleaned)
            except (json.JSONDecodeError, ValueError):
                # Try to extract embedded JSON object or array
                obj = _extract_json_object(cleaned)
                if obj is not None:
                    action_input = obj
                else:
                    arr_m = re.search(r"\[.*?\]", cleaned, re.DOTALL)
                    if arr_m:
                        try:
                            action_input = json.loads(arr_m.group(0))
                        except json.JSONDecodeError:
                            action_input = raw_input
                    else:
                        action_input = raw_input

        return thought, action_name, action_input

    # =========================================================================
    # Tools
    # =========================================================================

    def _tool_search_chapters(self, query: Any) -> str:
        """Return all canonical chapter names."""
        return (
            "Here are all 26 IPC chapters. Choose from these EXACT names:\n\n"
            + _CHAPTER_LIST_STR
        )

    def _tool_get_section_titles(
        self,
        chapter_names: List[str],
        penalised_secs: Set[str],
        global_confirmed: Dict[str, Dict[str, Any]],
    ) -> str:
        """Return section IDs + titles for requested chapters, hiding penalised ones."""
        # Validate chapter names (fuzzy-tolerant: case-insensitive)
        valid_chapters = []
        lower_map = {ch.lower(): ch for ch in _ALL_CHAPTERS}
        for name in chapter_names:
            canonical = lower_map.get(name.strip().lower())
            if canonical:
                valid_chapters.append(canonical)
            else:
                # Partial match fallback
                for ch in _ALL_CHAPTERS:
                    if name.strip().lower() in ch.lower():
                        valid_chapters.append(ch)
                        break

        if not valid_chapters:
            return (
                "ERROR: None of the chapter names matched the canonical list. "
                "Call search_chapters to see the full list, then use exact names."
            )

        lines = []
        for ch in valid_chapters:
            secs = self._chapters.get(ch, [])
            lines.append(f"\n[{ch}]")
            shown = 0
            for sec in secs:
                sid = sec["section"]
                if sid in penalised_secs:
                    continue
                marker = " ← already confirmed" if sid in global_confirmed else ""
                lines.append(f"  {sid}: {sec['title']}{marker}")
                shown += 1
            if shown == 0:
                lines.append("  (all sections in this chapter are penalised or already confirmed)")

        return "\n".join(lines)

    def _tool_get_section_detail(self, section_ids: List[str]) -> str:
        """Return full statutory context for each requested section."""
        if not section_ids:
            return "ERROR: No section IDs provided."

        parts = []
        for sid in section_ids:
            sid = sid.strip()
            structured = self._structured_by_id.get(sid)
            if not structured:
                # Try case-insensitive
                sid_up = sid.upper()
                structured = next(
                    (v for k, v in self._structured_by_id.items() if k.upper() == sid_up),
                    None,
                )
            if not structured:
                parts.append(f"[{sid}] ERROR: Section not found in ipc_structured.json")
                continue

            title = structured.get("section_title", sid)
            text  = structured.get("text", "").strip()
            expl  = structured.get("explanation", [])
            illus = structured.get("illustration", [])
            exc   = structured.get("exception", [])

            block = [f"══ {sid} — {title} ══"]
            block.append(f"STATUTORY TEXT:\n{text[:900]}")
            if expl:
                block.append("EXPLANATION:\n" + "\n".join(expl)[:400])
            if illus:
                block.append("ILLUSTRATION:\n" + "\n".join(illus)[:400])
            if exc:
                block.append("EXCEPTION:\n" + "\n".join(exc)[:300])
            parts.append("\n".join(block))

        return "\n\n".join(parts)

    def _tool_submit_answer(
        self,
        section_ids: List[str],
        sub_query: str,
        complainant_facts: str,
        agent_reasoning: str,
    ) -> Tuple[List[str], List[str], str]:
        """
        Final verification gate.  For each submitted section, the LLM
        does a focused ingredient check.  Returns (ok_ids, fail_ids, observation).
        """
        if not section_ids:
            return [], [], "ERROR: submit_answer called with empty accepted list."

        ok:   List[str] = []
        fail: List[str] = []
        detail_lines:   List[str] = []

        for sid in section_ids:
            sid = sid.strip()
            structured = self._structured_by_id.get(sid, {})
            title      = structured.get("section_title", sid)
            text       = structured.get("text", "").strip()
            expl       = "\n".join(structured.get("explanation", []))
            illus      = "\n".join(structured.get("illustration", []))
            exc        = "\n".join(structured.get("exception", []))

            context_parts = [f"STATUTORY TEXT:\n{text[:800]}"]
            if expl:  context_parts.append(f"EXPLANATION:\n{expl[:300]}")
            if illus: context_parts.append(f"ILLUSTRATION:\n{illus[:300]}")
            if exc:   context_parts.append(f"EXCEPTION:\n{exc[:200]}")
            full_context = "\n\n".join(context_parts)

            verify_prompt = textwrap.dedent(f"""
            You are a senior criminal judge doing a prima facie charge-framing check.

            SECTION: {sid} — {title}
            {full_context}

            SUB-QUERY:
            {sub_query}

            CASE FACTS (complainant side):
            {complainant_facts[:500]}

            AGENT'S REASONING:
            {agent_reasoning[:300]}

            TASK: For each essential ingredient of the section, state whether it is
            plausibly present in the facts (prima facie standard — not proof beyond doubt).
            Then give a final ACCEPTED or REJECTED verdict.

            Return ONLY this JSON:
            {{
              "section": "{sid}",
              "verdict": "ACCEPTED" or "REJECTED",
              "ingredient_check": [
                {{"ingredient": "...", "present": true/false, "basis": "..."}}
              ],
              "reasoning": "one sentence"
            }}
            """).strip()

            try:
                raw   = self.llm.invoke(verify_prompt).content
                parsed = _extract_json_object(raw)

                if parsed:
                    verdict   = str(parsed.get("verdict", "REJECTED")).upper()
                    reasoning = parsed.get("reasoning", "")
                    checks    = parsed.get("ingredient_check", [])
                    present   = sum(1 for c in checks if c.get("present") is True)
                    score     = (present / len(checks)) if checks else 0.5
                else:
                    verdict   = "ACCEPTED" if "ACCEPTED" in raw.upper() and "REJECTED" not in raw.upper() else "REJECTED"
                    reasoning = ""
                    score     = 0.65 if verdict == "ACCEPTED" else 0.3

                if verdict == "ACCEPTED":
                    ok.append(sid)
                    detail_lines.append(f"  ✓ {sid} ACCEPTED  (score={score:.2f}) — {reasoning}")
                    # Store score and reasoning for build_matches later
                    if sid in self._structured_by_id:
                        self._structured_by_id[sid]["_agent_score"]     = round(score, 3)
                        self._structured_by_id[sid]["_agent_reasoning"] = reasoning
                else:
                    fail.append(sid)
                    detail_lines.append(f"  ✗ {sid} REJECTED — {reasoning}")

            except Exception as exc_err:
                print(f"[LLMIPCRetrievalService]   Verify error [{sid}]: {exc_err}")
                ok.append(sid)   # conservative: keep on error
                detail_lines.append(f"  ? {sid} kept (verification error)")

        obs_lines = ["Verification results:"] + detail_lines
        if fail:
            obs_lines.append(
                "\nThe REJECTED sections did NOT satisfy all ingredients prima facie. "
                "Reason about what ingredient was missing, then try a different section."
            )
        if ok:
            obs_lines.append(f"\n{len(ok)} section(s) confirmed. You may call submit_answer again for additional sections, or stop.")

        return ok, fail, "\n".join(obs_lines)

    # =========================================================================
    # Candidate builder (used after submit_answer confirms a section)
    # =========================================================================

    def _make_candidate(self, sec_id: str, reasoning: str) -> Optional[Dict[str, Any]]:
        idx_entry  = self._find_in_index(sec_id) or {}
        structured = self._structured_by_id.get(sec_id, {})

        score = structured.get("_agent_score", 0.75)
        agent_reasoning = structured.get("_agent_reasoning", reasoning)

        return {
            "section":         sec_id,
            "title":           idx_entry.get("title", structured.get("section_title", sec_id)),
            "chapter":         idx_entry.get("chapter_name", ""),
            "relevance_score": score,
            "is_offense":      True,
            "reasoning":       agent_reasoning,
            "structured": {
                "text":           structured.get("text", ""),
                "explanation":    structured.get("explanation", []),
                "illustration":   structured.get("illustration", []),
                "exception":      structured.get("exception", []),
                "section_number": structured.get("section_number", ""),
                "chapter":        structured.get("chapter_title", ""),
            },
        }

    # =========================================================================
    # Result formatting  (Pinecone-compatible schema)
    # =========================================================================

    def _build_matches(self, confirmed: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        matches = []
        for cand in confirmed:
            sec_id = cand["section"]
            s = cand.get("structured", {})
            idx_entry  = self._find_in_index(sec_id) or {}
            structured = self._structured_by_id.get(sec_id, {})

            section_num = (
                s.get("section_number")
                or structured.get("section_number", "")
                or sec_id.replace("IPC_", "")
            )
            title = (
                idx_entry.get("title", "")
                or structured.get("section_title", "")
                or cand.get("title", "")
            )
            chapter_num  = idx_entry.get("chapter_number", "")
            chapter_name = idx_entry.get("chapter_name", "")
            full_text    = s.get("text") or structured.get("text", "")
            explanation  = s.get("explanation") or structured.get("explanation", [])
            illustration = s.get("illustration") or structured.get("illustration", [])
            exception    = s.get("exception") or structured.get("exception", [])

            matches.append({
                "id":    sec_id,
                "score": cand.get("relevance_score", 0.75),
                "metadata": {
                    "section":       section_num,
                    "section_num":   section_num,
                    "title":         title,
                    "description":   full_text,
                    "punishment":    "",
                    "chapter":       chapter_num,
                    "chapter_title": chapter_name,
                    "full_text":     full_text,
                    "explanation":   explanation,
                    "illustration":  illustration,
                    "exception":     exception,
                    "is_offense":    cand.get("is_offense", True),
                    "reasoning":     cand.get("reasoning", ""),
                },
            })

        matches.sort(key=lambda m: m["score"], reverse=True)
        return matches

    # =========================================================================
    # Utilities
    # =========================================================================

    def _extract_complainant_facts(self, case_facts: str) -> str:
        cutoff_phrases = [
            "the applicant denies", "applicant denies", "applicant submits",
            "applicant states", "applicant claims", "applicant contends",
            "he denies", "she denies", "accused denies", "accused submits",
            "accused states", "accused claims", "the accused denies",
            "it is submitted by the applicant",
        ]
        facts_lower = case_facts.lower()
        cut_at = len(case_facts)
        for phrase in cutoff_phrases:
            idx = facts_lower.find(phrase)
            if 0 < idx < cut_at:
                cut_at = idx

        trimmed = case_facts[:cut_at].strip()
        if cut_at < len(case_facts):
            print(
                f"[LLMIPCRetrievalService] Stripped defence narrative "
                f"({len(case_facts) - cut_at} chars, cut at "
                f"'{case_facts[cut_at:cut_at+40].strip()}')"
            )
        return trimmed if trimmed else case_facts

    def _load_json(self, path: Path) -> List[Dict[str, Any]]:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, list):
                print(f"[LLMIPCRetrievalService] WARNING: Expected list in {path}")
                return []
            return data
        except FileNotFoundError:
            print(f"[LLMIPCRetrievalService] ERROR: File not found: {path}")
            return []
        except json.JSONDecodeError as e:
            print(f"[LLMIPCRetrievalService] ERROR: Bad JSON in {path}: {e}")
            return []

    def _find_in_index(self, section_id: str) -> Optional[Dict[str, Any]]:
        sid = section_id.strip().upper()
        for sec in self.ipc_index:
            if str(sec.get("section", "")).strip().upper() == sid:
                return sec
        return None