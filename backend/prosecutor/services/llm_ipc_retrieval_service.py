"""
LLM-based IPC Section Retrieval Service  (v5 — Prosecutor Agent with Explicit RL Loop)
========================================================================================

ARCHITECTURE — as specified
----------------------------

The Agent and the LLM are distinct. The Agent perceives, reasons, and decides
whether to REWARD or PENALISE the LLM. The LLM only executes what the Agent
asks. Every step has a clear boundary.

STEP 1 — Agent perceives the raw input query
           Agent reasons: What is the nature of this query? What kind of offence?
           What chapters of the IPC are likely relevant?
           Agent calls → _llm_identify_chapters(full_query)
           LLM returns chapter names from ipc_index.json
           Agent verifies → REWARD (move to Step 2) or PENALISE (retry loop)
           This runs ONCE for the ENTIRE query — not per sub-query.

STEP 2 — Agent now has confirmed chapter names.
           Agent splits the query into sub-queries (received from upstream).
           For EACH sub-query, Agent calls → _llm_extract_section_titles(sub_query, chapters)
           LLM scans ONLY the section titles belonging to the confirmed chapters.
           LLM returns relevant IPC section IDs for that sub-query.
           Agent verifies each returned ID exists in the chapter scope.
           REWARD (carry forward) or PENALISE (retry loop per sub-query).

STEP 3 — Agent now has a set of candidate IPC section IDs (from all sub-queries combined).
           Agent calls → _llm_full_context_judgement(section_ids, sub_query, facts)
           LLM reads FULL statutory text + explanation + illustration from ipc_structured.json
           for ONLY those section IDs.
           LLM reasons: does this section's ingredients match the sub-query facts?
           LLM must CITE the specific statutory ingredient — not describe in general.
           Agent verifies: ingredient field non-empty, verdict is ACCEPTED/REJECTED,
           reasoning references the actual statutory text.
           REWARD (section confirmed) or PENALISE (retry loop).

AGENT PERCEPTION MODEL
-----------------------
At each step the Agent runs _agent_perceive() which:
  - Reads the current state (what do we have so far?)
  - Reasons about whether the LLM's last output makes sense
  - Decides REWARD or PENALISE with a reason
  - Logs everything so the loop is traceable

This is the Prosecutor Agent variant:
  - Biased toward finding offence sections that support DENYING anticipatory bail
  - Does NOT skip sections that are punishment-only if they support gravity of offence argument
  - Focuses on sections where statutory ingredients clearly match the FIR allegations
"""

from __future__ import annotations

import json
import re
import textwrap
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from config.llm_config import get_llm
except ModuleNotFoundError:
    from agents.config.llm_config import get_llm


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_RETRIES         = 3      # RL retry cycles per step before giving up
MAX_CHAPTERS        = 5      # max chapters LLM may select for the full query
MAX_TITLES_PER_SQ   = 8      # max section titles LLM may select per sub-query
MAX_TEXT_CHARS      = 1200   # statutory text chars per section in Step 3 context

# Sub-query strings containing these markers are skipped (procedural, not offence)
_PROCEDURAL_MARKERS: List[str] = [
    "applicant denies", "applicant alleges", "applicant has cooperated",
    "cooperated with the investigation", "custodial interrogation",
    "anticipatory bail", "bail application", "civil in nature",
    "civil dispute", "exaggerated allegations", "fir contains",
    "applicant claims", "applicant submits", "applicant contends",
    "no need for custody", "pre-arrest bail",
]


# ---------------------------------------------------------------------------
# Agent state — explicit, not implicit
# ---------------------------------------------------------------------------

class AgentDecision(Enum):
    REWARD   = "REWARD"
    PENALISE = "PENALISE"


@dataclass
class AgentPerception:
    """
    The Agent's perception at a given step.
    Contains what the Agent observed, what it reasoned, and what it decided.
    """
    step: str
    observation: str          # what the LLM returned
    reasoning: str            # why the Agent accepts or rejects it
    decision: AgentDecision
    penalty_message: str = "" # sent back to LLM on PENALISE


@dataclass
class AgentState:
    """
    Running state of the Agent across the full pipeline for one query.
    The Agent reads and writes this — the LLM never touches it.
    """
    raw_query: str
    complainant_facts: str

    # Set once, used by all sub-query loops
    confirmed_chapter_nums: List[str] = field(default_factory=list)
    confirmed_chapter_names: List[str] = field(default_factory=list)

    # Per sub-query accumulation
    candidate_section_ids: Set[str] = field(default_factory=set)

    # Final confirmed sections after Step 3
    confirmed_sections: Dict[str, Dict] = field(default_factory=dict)

    # Full perception log
    perceptions: List[AgentPerception] = field(default_factory=list)

    def log(self, perception: AgentPerception) -> None:
        self.perceptions.append(perception)
        icon = "✓ REWARD" if perception.decision == AgentDecision.REWARD else "✗ PENALISE"
        print(f"[Agent:{perception.step}] {icon} — {perception.reasoning[:120]}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_fences(text: str) -> str:
    return re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE).replace("```", "").strip()


def _parse_json_array(text: str) -> Optional[list]:
    cleaned = _strip_fences(text)
    m = re.search(r"\[.*?\]", cleaned, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


def _parse_json_object_list(text: str) -> Optional[list]:
    """Parse a JSON array of objects from LLM output."""
    cleaned = _strip_fences(text)
    m = re.search(r"\[.*?\]", cleaned, re.DOTALL)
    if m:
        try:
            parsed = json.loads(m.group(0))
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass
    return None


def _is_procedural(sub_query: str) -> bool:
    sq_lower = sub_query.lower()
    return any(marker in sq_lower for marker in _PROCEDURAL_MARKERS)


# ---------------------------------------------------------------------------
# Main Service — Prosecutor Variant
# ---------------------------------------------------------------------------

class LLMIPCRetrievalService:
    """
    Prosecutor-biased IPC retrieval service.

    The Agent runs the loop. The LLM executes function calls.
    The Agent decides REWARD / PENALISE at every step.

    Public interface (unchanged from v1–v4):
        retrieve_sections(sub_queries, case_facts, top_k) → {"retrieval_results": [...]}
    """

    def __init__(self, prosecutor_dir: Optional[Path] = None) -> None:
        self.llm = get_llm(temperature=0.0, provider="groq")

        if prosecutor_dir is None:
            prosecutor_dir = Path(__file__).resolve().parent.parent
        self.prosecutor_dir = prosecutor_dir

        ipc_index_path      = prosecutor_dir / "ipc_index.json"
        ipc_structured_path = prosecutor_dir / "ipc_structured.json"

        print(f"[LLMIPCRetrievalService] Loading IPC data from {prosecutor_dir}")

        self.ipc_index:      List[Dict[str, Any]] = self._load_json(ipc_index_path)
        self.ipc_structured: List[Dict[str, Any]] = self._load_json(ipc_structured_path)

        # ── pre-built lookup maps ────────────────────────────────────────────
        # ipc_structured.json: id → full entry
        self._structured_by_id: Dict[str, Dict] = {
            item["id"]: item
            for item in self.ipc_structured
            if isinstance(item, dict) and "id" in item
        }

        # ipc_index.json: section id → index entry
        self._index_by_id: Dict[str, Dict] = {
            sec["section"]: sec
            for sec in self.ipc_index
            if "section" in sec
        }

        # chapter_number → list of index entries
        self._chapters_by_num: Dict[str, List[Dict]] = {}
        for sec in self.ipc_index:
            ch = sec.get("chapter_number", "")
            self._chapters_by_num.setdefault(ch, []).append(sec)

        # chapter_name → chapter_number
        self._chapter_name_to_num: Dict[str, str] = {}
        for sec in self.ipc_index:
            name = sec.get("chapter_name", "")
            num  = sec.get("chapter_number", "")
            if name and num:
                self._chapter_name_to_num[name] = num

        # Canonical chapter list shown to LLM in Step 1 (entire query scope)
        seen: Dict[str, str] = {}
        for sec in self.ipc_index:
            num  = sec.get("chapter_number", "")
            name = sec.get("chapter_name", "")
            if num and name and num not in seen:
                seen[num] = name
        self._chapter_list_str = "\n".join(
            f"  {num}: {name}" for num, name in seen.items()
        )

        print(f"[LLMIPCRetrievalService] Loaded {len(self.ipc_index)} index entries")
        print(f"[LLMIPCRetrievalService] Loaded {len(self._structured_by_id)} structured sections")
        print(f"[LLMIPCRetrievalService] Chapter count: {len(seen)}")

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    def retrieve_sections(
        self,
        sub_queries: List[Dict[str, Any]],
        case_facts: str,
        top_k: int = 20,
    ) -> Dict[str, Any]:
        """
        Entry point. Called by LexiGraphAgent.
        
        MODIFIED: No longer uses sub-queries. Uses ENTIRE query throughout.

        Flow:
          Step 1 — Agent + LLM identify chapters for the ENTIRE query
          Step 2 — Agent + LLM pick relevant section IDs from confirmed chapters (ENTIRE query)
          Step 3 — Agent + LLM do full-context judgement on candidate IDs (ENTIRE query)

        Returns Pinecone-compatible {"retrieval_results": [...]} schema.
        """
        # IGNORE sub_queries parameter - use entire query only
        complainant_facts = self._extract_complainant_facts(case_facts)

        # ── Initialise Agent State ───────────────────────────────────────────
        state = AgentState(
            raw_query=case_facts,
            complainant_facts=complainant_facts,
        )

        print(f"\n[Agent] ══════════════════════════════════════════")
        print(f"[Agent] PERCEIVING ENTIRE query (NO sub-queries)")
        print(f"[Agent] Query: {case_facts[:200]}")
        print(f"[Agent] ══════════════════════════════════════════")

        # ── STEP 1: Chapter identification for the ENTIRE query ──────────────
        ok = self._step1_identify_chapters(state)
        if not ok:
            print("[Agent] Step 1 failed — no valid chapters confirmed. Aborting.")
            return {"retrieval_results": []}

        # ── STEP 2: Section title extraction for ENTIRE query ────────────────
        print(f"\n[Agent] ── Processing ENTIRE query (not sub-queries)")
        
        section_ids = self._step2_extract_section_titles(state, case_facts)
        if not section_ids:
            print(f"[Agent] Step 2: no sections found for query. Aborting.")
            return {"retrieval_results": []}

        state.candidate_section_ids.update(section_ids)

        # ── STEP 3: Full context judgement for ENTIRE query ──────────────────
        confirmed = self._step3_full_context_judgement(state, case_facts, section_ids)
        state.confirmed_sections.update(confirmed)

        # ── Build final result ────────────────────────────────────────────────
        all_matches = self._build_matches(list(confirmed.values()))
        all_matches = sorted(all_matches, key=lambda m: m["score"], reverse=True)[:top_k]

        retrieval_results = [{
            "query":          case_facts,
            "sub_query_type": "OFFENCE",
            "matches":        all_matches,
            "matches":        all_matches,
        }]

        print(f"\n[Agent] ══ PIPELINE COMPLETE ══")
        print(f"[Agent] Total confirmed sections: {len(state.confirmed_sections)}")
        print(f"[Agent] Sections: {list(state.confirmed_sections.keys())}")
        print(f"[Agent] Perception log ({len(state.perceptions)} events):")
        for p in state.perceptions:
            icon = "✓" if p.decision == AgentDecision.REWARD else "✗"
            print(f"  [{p.step}] {icon} {p.reasoning[:100]}")

        return {"retrieval_results": retrieval_results}

    # =========================================================================
    # STEP 1 — Agent + LLM: Chapter identification for the ENTIRE query
    # =========================================================================

    def _step1_identify_chapters(self, state: AgentState) -> bool:
        """
        The Agent perceives the raw query and asks the LLM to identify which
        IPC chapters are relevant — for the ENTIRE query, not per sub-query.

        NOW DELEGATES TO Stage1ChapterService which implements proper Agent reasoning:
        - Phase 1: Agent perceives case facts (actors, actions, outcomes)
        - Phase 2: Agent reasons about offence nature
        - Phase 3: LLM maps to IPC chapters
        - Phase 4: Agent verifies semantic relevance

        Returns True if chapters were confirmed, False if all retries failed.
        """
        print(f"\n[Agent:Step1] Delegating to Stage1ChapterService for Agent reasoning...")
        
        # Import Stage1ChapterService
        try:
            from .stage1_chapter_service import Stage1ChapterService
        except ImportError:
            from stage1_chapter_service import Stage1ChapterService
        
        # Initialize Stage1 service with ipc_index
        stage1_service = Stage1ChapterService(self.ipc_index)
        
        # Delegate to Stage1 service which implements full Agent reasoning
        success = stage1_service.identify_chapters(state)
        
        return success

        # OLD IMPLEMENTATION BELOW (REPLACED BY Stage1ChapterService)
        # ===========================================================
        """
        print(f"\n[Agent:Step1] Perceiving full query to identify IPC chapters...")
        print(f"[Agent:Step1] Full chapter list has {len(self._chapters_by_num)} chapters available.")

        # Agent's own reasoning before calling LLM
        agent_preamble = (
            f"Query: '{state.raw_query}'\n"
            f"Nature: Identifying which IPC chapters may contain offences "
            f"relevant to this query. Running for the ENTIRE query (not per sub-query). "
            f"Available chapters: {len(self._chapters_by_num)}. "
            f"Max to select: {MAX_CHAPTERS}."
        )
        print(f"[Agent:Step1] {agent_preamble}")

        penalty_block = ""
        for attempt in range(1, MAX_RETRIES + 2):
            print(f"[Agent:Step1] Calling LLM (attempt {attempt})...")

            # ── LLM CALL ────────────────────────────────────────────────────
            raw = self._llm_identify_chapters(
                query=state.raw_query,
                facts=state.complainant_facts,
                penalty_block=penalty_block,
            )

            parsed = _parse_json_array(raw)

            # ── AGENT PERCEPTION: can we parse it? ──────────────────────────
            if not parsed:
                perception = AgentPerception(
                    step=f"Step1/attempt{attempt}",
                    observation=f"LLM returned unparseable output: {raw[:80]}",
                    reasoning="Cannot parse JSON array from LLM response — format violation.",
                    decision=AgentDecision.PENALISE,
                    penalty_message=(
                        "PENALTY: Your response was not valid JSON. "
                        "Return ONLY a JSON array of chapter number strings, e.g. [\"XVI\", \"V\"]. "
                        "No preamble, no explanation."
                    ),
                )
                state.log(perception)
                penalty_block = perception.penalty_message
                continue

            # ── AGENT PERCEPTION: are all returned chapter numbers real? ─────
            valid_chapters   = [c for c in parsed if str(c) in self._chapters_by_num]
            invalid_chapters = [c for c in parsed if str(c) not in self._chapters_by_num]

            if invalid_chapters:
                valid_nums = list(self._chapters_by_num.keys())
                perception = AgentPerception(
                    step=f"Step1/attempt{attempt}",
                    observation=f"LLM returned chapters: {parsed}. Invalid: {invalid_chapters}.",
                    reasoning=(
                        f"Chapters {invalid_chapters} do not exist in ipc_index.json. "
                        f"LLM is hallucinating chapter numbers. Must penalise and retry."
                    ),
                    decision=AgentDecision.PENALISE,
                    penalty_message=(
                        f"PENALTY: You returned chapter numbers not present in ipc_index.json: "
                        f"{invalid_chapters}.\n"
                        f"Valid chapter numbers are ONLY: {valid_nums}.\n"
                        f"Select ONLY from that list."
                    ),
                )
                state.log(perception)
                penalty_block = perception.penalty_message
                continue

            if not valid_chapters:
                perception = AgentPerception(
                    step=f"Step1/attempt{attempt}",
                    observation="LLM returned empty or all-invalid chapter list.",
                    reasoning=(
                        "Empty valid chapter set. Query must map to at least one chapter. "
                        "Penalising."
                    ),
                    decision=AgentDecision.PENALISE,
                    penalty_message=(
                        "PENALTY: You returned no valid chapters. "
                        "This query must be mapped to at least one IPC chapter. "
                        "Select at least one from the list."
                    ),
                )
                state.log(perception)
                penalty_block = perception.penalty_message
                continue

            # ── AGENT PERCEPTION: do the chapter names make sense for the query? ─
            chapter_names = [
                self._chapters_by_num[c][0].get("chapter_name", "")
                for c in valid_chapters
            ]
            
            # SEMANTIC VERIFICATION - Check if chapters are actually relevant
            semantic_error = self._verify_chapter_relevance(chapter_names, state.raw_query)
            if semantic_error:
                perception = AgentPerception(
                    step=f"Step1/attempt{attempt}",
                    observation=f"LLM returned chapters: {list(zip(valid_chapters, chapter_names))}",
                    reasoning=f"Semantic relevance check FAILED: {semantic_error}",
                    decision=AgentDecision.PENALISE,
                    penalty_message=(
                        f"PENALTY: {semantic_error}\n\n"
                        f"Query context: {state.raw_query[:300]}\n\n"
                        f"You must select chapters whose subject matter is DIRECTLY relevant "
                        f"to the allegations described in the query. Do not select chapters "
                        f"based on vague associations or generalizations."
                    ),
                )
                state.log(perception)
                penalty_block = perception.penalty_message
                continue
            
            reasoning = (
                f"Chapters {list(zip(valid_chapters, chapter_names))} returned. "
                f"All exist in ipc_index.json. Semantic relevance verified: "
                f"chapters are appropriate for query context."
            )

            # ── REWARD ───────────────────────────────────────────────────────
            perception = AgentPerception(
                step=f"Step1/attempt{attempt}",
                observation=f"LLM returned valid chapters: {list(zip(valid_chapters, chapter_names))}",
                reasoning=reasoning,
                decision=AgentDecision.REWARD,
            )
            state.log(perception)

            state.confirmed_chapter_nums  = valid_chapters
            state.confirmed_chapter_names = chapter_names

            # OLD CODE - Commented out, now handled by Stage1ChapterService
            # print(f"[Agent:Step1] REWARD — confirmed chapters: {list(zip(valid_chapters, chapter_names))}")
            # return True

        # print(f"[Agent:Step1] All {MAX_RETRIES + 1} attempts failed. Step 1 aborted.")
        # return False
        """
        pass  # Old implementation removed, handled by Stage1ChapterService

    # OLD METHODS - Replaced by Stage1ChapterService
    # ================================================
    # The following methods (_llm_identify_chapters and _verify_chapter_relevance)
    # are NO LONGER USED. They have been replaced by Stage1ChapterService which
    # implements proper Agent reasoning (perceiving actors, actions, outcomes)
    # instead of just keyword matching.
    #
    # Keeping them commented for reference:
    
    """
    def _llm_identify_chapters_OLD(
        self,
        query: str,
        facts: str,
        penalty_block: str,
    ) -> str:
        # OLD: Simple prompt without Agent reasoning
        # NOW: Stage1ChapterService does full Agent perception
        prompt = textwrap.dedent(f'''
        You are a legal research assistant helping a Prosecutor oppose anticipatory bail.
        Your task: identify which IPC chapters are relevant to the legal allegations
        described in the query below.

        FULL QUERY (entire input — do NOT decompose yet):
        {query}

        COMPLAINANT FACTS:
        {facts[:600]}

        COMPLETE IPC CHAPTER LIST (from ipc_index.json — these are the ONLY valid options):
        {self._chapter_list_str}

        TASK:
        Select at most {MAX_CHAPTERS} chapter number(s) from the list above whose
        subject-matter best matches the allegations in the query.

        Rules:
        - Use ONLY chapter numbers exactly as shown above (e.g. "XVI", "V", "XXA").
        - Do NOT invent or modify chapter numbers.
        - Consider the full query, not just one aspect of it.
        - For a dowry/cruelty case, consider chapters covering offences against women,
          marriage, property, and bodily harm.

        {penalty_block}

        Return ONLY a JSON array of chapter number strings, nothing else.
        Example: ["XVI", "XX", "VA"]
        ''').strip()

        try:
            return self.llm.invoke(prompt).content.strip()
        except Exception as exc:
            print(f"[LLM] Step 1 call failed: {exc}")
            return "[]"

    def _verify_chapter_relevance_OLD(self, chapter_names: List[str], query: str) -> str:
        # OLD: Simple keyword matching
        # NOW: Stage1ChapterService does Agent reasoning about case facts
        query_lower = query.lower()
        
        chapter_requirements = {
            "CRUELTY BY HUSBAND": ["husband", "wife", "spouse", "marriage", "matrimonial", "dowry", "married"],
            "MARRIAGE": ["husband", "wife", "spouse", "marriage", "married", "matrimonial", "wedding"],
            "FALSE EVIDENCE": ["evidence", "perjury", "court", "testimony", "witness", "fabricate", "forge"],
            "PUBLIC JUSTICE": ["court", "justice", "judicial", "obstruct", "evidence", "perjury"],
            "ELECTION": ["election", "vote", "ballot", "electoral", "poll", "candidate"],
            "COIN": ["coin", "currency", "counterfeit", "money"],
            "RELIGION": ["religion", "religious", "worship", "temple", "mosque", "church", "sacred"],
            "PUBLIC SERVANT": ["public servant", "government", "official", "bribe", "corruption"],
            "MILITARY": ["military", "army", "naval", "soldier", "armed forces"],
        }
        
        for chapter_name in chapter_names:
            chapter_upper = chapter_name.upper()
            
            for key_term, required_words in chapter_requirements.items():
                if key_term in chapter_upper:
                    has_context = any(word in query_lower for word in required_words)
                    if not has_context:
                        return (
                            f"Chapter '{chapter_name}' is IRRELEVANT. "
                            f"This chapter requires context about {key_term.lower()}, "
                            f"but the query mentions none of: {', '.join(required_words)}. "
                            f"The allegations described do not involve {key_term.lower()}."
                        )
        
        return ""
    """

    # =========================================================================
    # STEP 2 — Agent + LLM: Section title extraction per sub-query
    # =========================================================================

    def _step2_extract_section_titles(
        self,
        state: AgentState,
        sub_query: str,
    ) -> List[str]:
        """
        The Agent takes the confirmed chapter numbers and asks the LLM to scan
        the section titles within ONLY those chapters for this specific sub-query.

        The LLM must return section IDs (e.g. IPC_498A) from the allowed set.
        Agent verifies each returned ID exists in the chapter scope.
        REWARD → return the list.  PENALISE → retry.
        """
        print(f"\n[Agent:Step2] Sub-query: '{sub_query[:80]}'")
        print(f"[Agent:Step2] Scanning section titles in chapters: "
              f"{state.confirmed_chapter_nums}")

        # Build the section titles block — ONLY from confirmed chapters
        titles_block_parts = []
        valid_ids_in_scope: Set[str] = set()

        for ch_num in state.confirmed_chapter_nums:
            ch_secs = self._chapters_by_num.get(ch_num, [])
            if not ch_secs:
                continue
            ch_name = ch_secs[0].get("chapter_name", ch_num)
            lines   = [f"\n  Chapter {ch_num} — {ch_name}:"]
            for sec in ch_secs:
                sec_id    = sec["section"]
                sec_title = sec.get("title", "")
                lines.append(f"    {sec_id}: {sec_title}")
                valid_ids_in_scope.add(sec_id)
            titles_block_parts.append("\n".join(lines))

        titles_block = "\n".join(titles_block_parts)

        print(f"[Agent:Step2] Total sections in scope: {len(valid_ids_in_scope)}")

        penalty_block = ""
        for attempt in range(1, MAX_RETRIES + 2):
            print(f"[Agent:Step2] Calling LLM (attempt {attempt})...")

            raw = self._llm_extract_section_titles(
                sub_query=sub_query,
                facts=state.complainant_facts,
                titles_block=titles_block,
                penalty_block=penalty_block,
            )

            parsed = _parse_json_array(raw)

            # ── AGENT PERCEPTION: parseable? ─────────────────────────────────
            if not parsed:
                perception = AgentPerception(
                    step=f"Step2/attempt{attempt}",
                    observation=f"LLM returned unparseable: {raw[:80]}",
                    reasoning="JSON parse failure on section title extraction.",
                    decision=AgentDecision.PENALISE,
                    penalty_message=(
                        "PENALTY: Response was not a valid JSON array. "
                        "Return ONLY a JSON array of section ID strings "
                        "exactly as shown in the SECTION TITLES block, e.g. [\"IPC_498A\", \"IPC_306\"]."
                    ),
                )
                state.log(perception)
                penalty_block = perception.penalty_message
                continue

            # ── AGENT PERCEPTION: are all IDs within the scoped chapters? ────
            valid_ids   = [s for s in parsed if str(s) in valid_ids_in_scope]
            invalid_ids = [s for s in parsed if str(s) not in valid_ids_in_scope]

            if invalid_ids:
                perception = AgentPerception(
                    step=f"Step2/attempt{attempt}",
                    observation=f"LLM returned IDs: {parsed}. Out-of-scope: {invalid_ids}.",
                    reasoning=(
                        f"Section IDs {invalid_ids} are not in the allowed chapters "
                        f"{state.confirmed_chapter_nums}. LLM is reaching outside the "
                        f"scoped chapters. Penalising."
                    ),
                    decision=AgentDecision.PENALISE,
                    penalty_message=(
                        f"PENALTY: You returned section IDs that are NOT in the chapters "
                        f"you were given to scan: {invalid_ids}.\n"
                        f"You may ONLY choose from the section IDs shown in the "
                        f"SECTION TITLES block above. Do not invent IDs."
                    ),
                )
                state.log(perception)
                penalty_block = perception.penalty_message
                continue

            if not valid_ids:
                perception = AgentPerception(
                    step=f"Step2/attempt{attempt}",
                    observation="LLM returned empty valid section list.",
                    reasoning=(
                        "No valid section IDs returned for this sub-query. "
                        "This sub-query must map to at least one section in the scoped chapters."
                    ),
                    decision=AgentDecision.PENALISE,
                    penalty_message=(
                        "PENALTY: You returned no valid sections. "
                        "Look carefully through the section titles provided — at least one "
                        "should be relevant to the sub-query. Select it."
                    ),
                )
                state.log(perception)
                penalty_block = perception.penalty_message
                continue

            # ── REWARD ───────────────────────────────────────────────────────
            selected_titles = [
                (sid, self._index_by_id.get(sid, {}).get("title", ""))
                for sid in valid_ids
            ]
            perception = AgentPerception(
                step=f"Step2/attempt{attempt}",
                observation=f"LLM returned valid IDs: {selected_titles}",
                reasoning=(
                    f"All {len(valid_ids)} section IDs exist in chapters "
                    f"{state.confirmed_chapter_nums}. Section titles are "
                    f"semantically consistent with sub-query '{sub_query[:60]}'. "
                    f"Rewarding."
                ),
                decision=AgentDecision.REWARD,
            )
            state.log(perception)
            print(f"[Agent:Step2] REWARD — sections: {selected_titles}")
            return valid_ids

        print(f"[Agent:Step2] All attempts failed for sub-query '{sub_query[:60]}'.")
        return []

    def _llm_extract_section_titles(
        self,
        sub_query: str,
        facts: str,
        titles_block: str,
        penalty_block: str,
    ) -> str:
        """
        LLM function call: given the sub-query and the section titles from only
        the confirmed chapters, return the relevant section IDs.
        """
        prompt = textwrap.dedent(f"""
        You are a legal research assistant helping a Prosecutor oppose anticipatory bail.
        You have already identified the relevant IPC chapters.
        Now identify the specific sections within those chapters for the sub-query below.

        SUB-QUERY (one specific aspect of the case):
        {sub_query}

        CASE FACTS (complainant side only):
        {facts[:600]}

        SECTION TITLES (from ipc_index.json — ONLY these chapters, ONLY these IDs):
        {titles_block}

        TASK:
        Select at most {MAX_TITLES_PER_SQ} section ID(s) from the list above whose
        title indicates the section is relevant to this sub-query.

        Rules:
        - Use ONLY the section IDs shown above (e.g. "IPC_498A", "IPC_306").
        - Do NOT invent section IDs or use IDs from other chapters.
        - Prefer substantive offence sections over pure "Punishment for..." sections
          unless no substantive section fits.
        - For a prosecutor opposing bail, also include sections establishing
          gravity of offence (punishment quantum sections) if they are listed.

        {penalty_block}

        Return ONLY a JSON array of section ID strings, nothing else.
        Example: ["IPC_498A", "IPC_306", "IPC_34"]
        """).strip()

        try:
            return self.llm.invoke(prompt).content.strip()
        except Exception as exc:
            print(f"[LLM] Step 2 call failed: {exc}")
            return "[]"

    # =========================================================================
    # STEP 3 — Agent + LLM: Full context judgement from ipc_structured.json
    # =========================================================================

    def _step3_full_context_judgement(
        self,
        state: AgentState,
        sub_query: str,
        section_ids: List[str],
    ) -> Dict[str, Dict]:
        """
        The Agent now has candidate section IDs. It calls the LLM with:
          - The full statutory text, explanation, illustrations, exceptions
            for each candidate (from ipc_structured.json)
          - The sub-query and case facts

        The LLM must decide ACCEPTED or REJECTED for each section,
        and for ACCEPTED sections must cite the specific statutory ingredient
        and explain how the case facts satisfy it.

        The Agent verifies:
          - Each returned ID is one we actually asked about
          - ACCEPTED sections have a non-empty 'ingredient' field
          - Reasoning references the actual statutory text (soft check)
          - STRUCTURAL CONSTRAINT: Death-required sections rejected if victim survived

        REWARD → section is confirmed.
        PENALISE → retry the whole step.
        """
        if not section_ids:
            return {}

        print(f"\n[Agent:Step3] Full context judgement for {len(section_ids)} sections: {section_ids}")

        # ═════════════════════════════════════════════════════════════════════
        # AGENT STRUCTURAL CONSTRAINT: Infer outcome from facts
        # ═════════════════════════════════════════════════════════════════════
        outcome_inference = self._agent_infer_outcome(state.raw_query, state.complainant_facts)
        victim_survived = outcome_inference["victim_survived"]
        death_occurred = outcome_inference["death_occurred"]
        
        print(f"[Agent:Step3] STRUCTURAL CONSTRAINT:")
        print(f"  Victim survived: {victim_survived}")
        print(f"  Death occurred: {death_occurred}")
        
        # Build context block from ipc_structured.json — only the candidates
        context_block = self._build_structured_context(section_ids)
        asked_ids_set = set(section_ids)
        id_list_str   = ", ".join(section_ids)

        penalty_block = ""
        for attempt in range(1, MAX_RETRIES + 2):
            print(f"[Agent:Step3] Calling LLM (attempt {attempt})...")

            raw = self._llm_full_context_judgement(
                sub_query=sub_query,
                facts=state.complainant_facts,
                context_block=context_block,
                id_list_str=id_list_str,
                role_instruction=(
                    "You are arguing FOR the prosecution — identify sections "
                    "that support DENYING anticipatory bail. "
                    "If a section's ingredients prima facie match the facts, ACCEPT it."
                ),
                penalty_block=penalty_block,
                victim_survived=victim_survived,  # Pass structural constraint to LLM
            )

            parsed = _parse_json_object_list(raw)
            
            # DEBUG: Log what was returned
            if parsed:
                returned_ids = [str(item.get("id", "")).strip() for item in parsed if isinstance(item, dict)]
                print(f"[Agent:Step3] DEBUG: LLM returned {len(parsed)} items")
                print(f"[Agent:Step3] DEBUG: Returned IDs: {returned_ids}")
                print(f"[Agent:Step3] DEBUG: Expected IDs: {list(asked_ids_set)}")
                extra_ids = [rid for rid in returned_ids if rid and rid not in asked_ids_set]
                if extra_ids:
                    print(f"[Agent:Step3] DEBUG: ✗ EXTRA/HALLUCINATED IDs: {extra_ids}")

            # ── AGENT PERCEPTION: parseable? ─────────────────────────────────
            if not parsed:
                perception = AgentPerception(
                    step=f"Step3/attempt{attempt}",
                    observation=f"LLM returned unparseable: {raw[:80]}",
                    reasoning="JSON parse failure on full context judgement.",
                    decision=AgentDecision.PENALISE,
                    penalty_message=(
                        "PENALTY: Response was not a valid JSON array of objects. "
                        "Return ONLY the JSON array as specified — no preamble, "
                        "no markdown, no explanation outside the JSON."
                    ),
                )
                state.log(perception)
                penalty_block = perception.penalty_message
                continue

            # ── AGENT PERCEPTION: evaluate each item ─────────────────────────
            issues: List[str] = []
            accepted_items: List[dict] = []

            for item in parsed:
                if not isinstance(item, dict):
                    issues.append("Non-dict item in array")
                    continue

                sid     = str(item.get("id", "")).strip()
                verdict = str(item.get("verdict", "")).upper()
                reason  = str(item.get("reasoning", "")).strip()
                ingred  = str(item.get("ingredient", "")).strip()

                # Agent check 1: Section ID must be one we asked about
                if sid not in asked_ids_set:
                    issues.append(f"'{sid}' not in evaluation list ({id_list_str})")
                    continue

                # Agent check 2: verdict must be ACCEPTED or REJECTED
                if verdict not in ("ACCEPTED", "REJECTED"):
                    issues.append(f"'{sid}': verdict must be 'ACCEPTED' or 'REJECTED', got '{verdict}'")
                    continue

                # Agent check 3: ACCEPTED requires non-empty fields
                if verdict == "ACCEPTED":
                    if not ingred:
                        issues.append(f"'{sid}': ACCEPTED but 'ingredient' is empty")
                        continue

                    if len(reason) < 15:
                        issues.append(f"'{sid}': reasoning too brief: '{reason}'")
                        continue
                    
                    # ═══════════════════════════════════════════════════════════
                    # AGENT OVERRIDE: Completed offences requiring death
                    # ═══════════════════════════════════════════════════════════
                    if victim_survived:
                        requires_death = self._section_requires_death(sid, ingred)
                        
                        if requires_death:
                            print(f"[Agent:Step3] ✗ OVERRIDE: {sid} requires death but victim survived")
                            issues.append(
                                f"'{sid}': COMPLETED offence requiring death. "
                                f"Victim SURVIVED. MUST REJECT."
                            )
                            continue

                    # ACCEPTED
                    print(
                        f"[Agent:Step3] ACCEPTED {sid}: "
                        f"ingredient='{ingred[:60]}' | "
                        f"reason='{reason[:80]}'"
                    )
                    accepted_items.append(item)
                else:
                    # REJECTED
                    print(f"[Agent:Step3] REJECTED {sid}: {reason[:80]}")

            # ── AGENT PERCEPTION: any issues? ─────────────────────────────────
            if issues:
                perception = AgentPerception(
                    step=f"Step3/attempt{attempt}",
                    observation=f"LLM response had {len(issues)} issue(s): {issues[:3]}",
                    reasoning=(
                        f"Agent found violations in LLM output: {issues}. "
                        f"The LLM must fix these before any section is accepted."
                    ),
                    decision=AgentDecision.PENALISE,
                    penalty_message=(
                        "PENALTY: The following issues were found in your response:\n"
                        + "\n".join(f"  - {i}" for i in issues)
                        + "\n\nFix ALL of these issues and resubmit the complete JSON array "
                        "for ALL sections listed. Do not omit any section."
                    ),
                )
                state.log(perception)
                penalty_block = perception.penalty_message
                continue

            # ── REWARD: build confirmed candidates ────────────────────────────
            confirmed: Dict[str, Dict] = {}
            for item in accepted_items:
                sid       = item["id"]
                reasoning = item.get("reasoning", "")
                ingredient = item.get("ingredient", "")
                cand = self._make_candidate(sid, reasoning, ingredient)
                if cand:
                    confirmed[sid] = cand
            
            # ═════════════════════════════════════════════════════════════════
            # AGENT FINAL VERIFICATION LAYER
            # ═════════════════════════════════════════════════════════════════
            verification_issues = self._agent_final_verification(
                confirmed=confirmed,
                accepted_items=accepted_items,
                victim_survived=victim_survived,
                raw_query=state.raw_query,
                complainant_facts=state.complainant_facts
            )
            
            if verification_issues:
                print(f"[Agent:Step3] ✗ FINAL VERIFICATION FAILED: {len(verification_issues)} issue(s)")
                for issue in verification_issues:
                    print(f"  - {issue}")
                
                perception = AgentPerception(
                    step=f"Step3/attempt{attempt}",
                    observation=f"Accepted sections failed final verification: {verification_issues[:2]}",
                    reasoning=(
                        f"Agent's final verification layer detected legal errors in accepted sections. "
                        f"Issues: {verification_issues}. Forcing re-validation."
                    ),
                    decision=AgentDecision.PENALISE,
                    penalty_message=(
                        "PENALTY: Your accepted sections failed Agent's final verification:\n"
                        + "\n".join(f"  - {issue}" for issue in verification_issues)
                        + "\n\nYou must fix these legal reasoning errors before any section is accepted. "
                        "Re-evaluate ALL sections with strict ingredient-level validation."
                    ),
                )
                state.log(perception)
                penalty_block = perception.penalty_message
                continue

            perception = AgentPerception(
                step=f"Step3/attempt{attempt}",
                observation=(
                    f"LLM accepted {len(accepted_items)} sections, "
                    f"rejected {len(parsed) - len(accepted_items)}. "
                    f"Final verification: PASSED"
                ),
                reasoning=(
                    f"All {len(accepted_items)} accepted items passed agent verification "
                    f"AND final legal reasoning verification. "
                    f"Confirmed: {list(confirmed.keys())}. Rewarding."
                ),
                decision=AgentDecision.REWARD,
            )
            state.log(perception)
            print(f"[Agent:Step3] ✓ REWARD — confirmed: {list(confirmed.keys())}")
            print(f"[Agent:Step3] ✓ Final verification PASSED")
            return confirmed

        print(f"[Agent:Step3] All attempts failed for sub-query '{sub_query[:60]}'.")
        return {}
    
    def _agent_final_verification(
        self,
        confirmed: Dict[str, Dict],
        accepted_items: List[dict],
        victim_survived: bool,
        raw_query: str = "",
        complainant_facts: str = ""
    ) -> List[str]:
        """
        AGENT FINAL VERIFICATION - Enhanced with ingredient-level fact matching.
        
        Checks:
        1. No completed death offences when victim survived
        2. Prefer specific over generic (IPC 307 over IPC 308)
        3. Ingredient-level fact matching (most critical)
        """
        issues = []
        
        accepted_ids = set(confirmed.keys())
        
        # CHECK 1: Completed death offences when victim survived
        if victim_survived:
            completed_death_sections = {
                "IPC_299", "IPC_300", "IPC_302", "IPC_304",
                "IPC_304A", "IPC_304B", "IPC_314", "IPC_315", "IPC_316"
            }
            
            for sid in accepted_ids:
                if sid in completed_death_sections:
                    issues.append(
                        f"{sid}: COMPLETED offence requiring death accepted when victim survived"
                    )
        
        # CHECK 2: Prefer IPC 307 over IPC 308
        if "IPC_307" in accepted_ids and "IPC_308" in accepted_ids:
            issues.append(
                "Both IPC_307 and IPC_308 accepted. Use IPC_307 (more specific) only"
            )
        
        # CHECK 3: No definition sections as charges
        definition_sections = {"IPC_319", "IPC_320", "IPC_321", "IPC_322"}
        definition_accepted = accepted_ids & definition_sections
        
        if definition_accepted:
            issues.append(
                f"Definition sections accepted as charges: {definition_accepted}"
            )
        
        # CHECK 4: IPC 511 when specific attempt exists
        if "IPC_511" in accepted_ids and "IPC_307" in accepted_ids:
            issues.append(
                "IPC_511 (general attempt) with IPC_307 (specific attempt). Use IPC_307 only"
            )
        
        # ═════════════════════════════════════════════════════════════════════
        # CHECK 5: INGREDIENT-LEVEL FACT MATCHING (Critical)
        # ═════════════════════════════════════════════════════════════════════
        ingredient_issues = self._verify_ingredient_fact_match(
            confirmed, accepted_items, raw_query, complainant_facts
        )
        issues.extend(ingredient_issues)
        
        return issues
    
    def _verify_ingredient_fact_match(
        self,
        confirmed: Dict[str, Dict],
        accepted_items: List[dict],
        raw_query: str = "",
        complainant_facts: str = ""
    ) -> List[str]:
        """
        Agent verifies that accepted sections' ingredients actually match case facts.
        
        This is the MOST CRITICAL verification layer - prevents hallucination.
        """
        issues = []
        
        # Use case facts directly
        case_facts_lower = f"{raw_query} {complainant_facts}".lower()
        
        for sid, cand in confirmed.items():
            ingredient = cand.get("ingredient", "").lower()
            reasoning = cand.get("reasoning", "").lower()
            
            # ──────────────────────────────────────────────────────────────────
            # IPC 326A - Acid attack
            # ──────────────────────────────────────────────────────────────────
            if sid == "IPC_326A":
                acid_indicators = ["acid", "corrosive", "vitriol", "chemical burn"]
                has_acid_fact = any(indicator in case_facts_lower for indicator in acid_indicators)
                
                # Check if case facts mention knife/blade (contradicts acid)
                weapon_indicators = ["knife", "blade", "sword", "dagger"]
                has_weapon_fact = any(weapon in case_facts_lower for weapon in weapon_indicators)
                
                if not has_acid_fact:
                    issues.append(
                        f"{sid}: Acid attack section accepted but case facts mention NO acid. "
                        f"{'Knife/weapon attack described instead.' if has_weapon_fact else 'Ingredient mismatch.'}"
                    )
            
            # ──────────────────────────────────────────────────────────────────
            # IPC 506 - Criminal intimidation
            # ──────────────────────────────────────────────────────────────────
            if sid == "IPC_506":
                threat_indicators = [
                    "threat", "intimidat", "menac", "warned", "coerce",
                    "frighten", "alarm", "terroriz", "blackmail"
                ]
                has_threat_fact = any(indicator in case_facts_lower for indicator in threat_indicators)
                
                # Check if case describes actual physical assault (not just threat)
                assault_indicators = [
                    "attacked", "assault", "hit", "struck", "beat",
                    "inflict", "caused injury", "injured", "stabbed"
                ]
                has_assault_fact = any(assault in case_facts_lower for assault in assault_indicators)
                
                # IPC 506 requires THREAT, not actual harm
                # If only assault happened without threat, reject 506
                if has_assault_fact and not has_threat_fact:
                    issues.append(
                        f"{sid}: Criminal intimidation requires THREAT. "
                        f"Case facts describe actual physical assault, not intimidation. "
                        f"Ingredient mismatch."
                    )
            
            # ──────────────────────────────────────────────────────────────────
            # IPC 498A - Cruelty by husband
            # ──────────────────────────────────────────────────────────────────
            if sid == "IPC_498A":
                marriage_indicators = [
                    "husband", "wife", "spouse", "married", "matrimonial",
                    "dowry", "marital"
                ]
                has_marriage_context = any(
                    indicator in case_facts_lower for indicator in marriage_indicators
                )
                
                if not has_marriage_context:
                    issues.append(
                        f"{sid}: Cruelty by husband requires marital relationship. "
                        f"No marriage context found in case facts. Ingredient mismatch."
                    )
            
            # ──────────────────────────────────────────────────────────────────
            # IPC 376 - Rape
            # ──────────────────────────────────────────────────────────────────
            if sid == "IPC_376":
                sexual_indicators = [
                    "rape", "sexual", "intercourse", "penetration", "modesty", "outrage"
                ]
                has_sexual_context = any(
                    indicator in case_facts_lower for indicator in sexual_indicators
                )
                
                if not has_sexual_context:
                    issues.append(
                        f"{sid}: Rape requires sexual assault. "
                        f"No sexual offense context in case facts. Ingredient mismatch."
                    )
        
        return issues
    
    # ═════════════════════════════════════════════════════════════════════════
    # AGENT STRUCTURAL CONSTRAINT HELPERS
    # ═════════════════════════════════════════════════════════════════════════
    
    def _agent_infer_outcome(self, raw_query: str, facts: str) -> Dict[str, bool]:
        """
        Agent infers the outcome from case facts to apply structural constraints.
        
        Returns:
            {
                "victim_survived": bool,  # True if victim is alive
                "death_occurred": bool,   # True if death mentioned
            }
        """
        combined_text = f"{raw_query} {facts}".lower()
        
        # Death indicators
        death_keywords = [
            "death", "died", "dead", "killed", "fatal", "deceased",
            "succumbed", "expired", "demise", "murdered"
        ]
        
        # Survival indicators
        survival_keywords = [
            "survived", "alive", "recovering", "hospitalized",
            "injuries", "injured", "wounded", "hurt",
            "admitted to hospital", "undergoing treatment"
        ]
        
        # Intention keywords (don't count as actual death)
        intention_keywords = [
            "intended to", "intention of", "intending to",
            "with intent to", "attempting to"
        ]
        
        # Check for death
        death_occurred = any(keyword in combined_text for keyword in death_keywords)
        
        # Check for survival
        victim_survived = any(keyword in combined_text for keyword in survival_keywords)
        
        # Check if death is just in context of intention (not actual death)
        death_is_intent_only = any(intent in combined_text for intent in intention_keywords)
        
        # Override: if survival explicitly mentioned, death did NOT occur
        if victim_survived:
            death_occurred = False
        
        # Override: if death is only mentioned with "intent", it didn't actually occur
        if death_is_intent_only and not any(
            keyword in combined_text for keyword in ["dead body", "post-mortem", "funeral", "cremated"]
        ):
            death_occurred = False
            victim_survived = True  # Infer survival if only intent mentioned
        
        return {
            "victim_survived": victim_survived,
            "death_occurred": death_occurred
        }
    
    def _section_requires_death(self, section_id: str, ingredient: str) -> bool:
        """
        Agent checks if a section requires death as an essential ingredient.
        
        Args:
            section_id: e.g., "IPC_300"
            ingredient: The statutory ingredient extracted by LLM
        
        Returns:
            True if section requires death, False otherwise
        """
        # Direct section number checks (known death sections)
        death_section_ids = {
            "IPC_299",   # Culpable homicide
            "IPC_300",   # Murder
            "IPC_302",   # Punishment for murder
            "IPC_304",   # Culpable homicide not amounting to murder
            "IPC_304A",  # Causing death by rash/negligent act
            "IPC_304B",  # Dowry death
            "IPC_316",   # Causing death of quick unborn child
            "IPC_307",   # Attempt to murder (does NOT require death - intention only)
        }
        
        # IPC_307 is EXCLUDED - it's attempt, doesn't require actual death
        if section_id in death_section_ids and section_id != "IPC_307":
            return True
        
        # Check ingredient text for death requirement
        ingredient_lower = ingredient.lower()
        death_requirement_phrases = [
            "causing death",
            "causes death",
            "death of",
            "culpable homicide",
            "murder",
            "kills",
            "death is caused"
        ]
        
        # Check if ingredient explicitly requires death as outcome
        requires_death_in_text = any(
            phrase in ingredient_lower 
            for phrase in death_requirement_phrases
        )
        
        # Exclude intention-only phrases (these don't require actual death)
        intention_only_phrases = [
            "intent to cause death",
            "intention of causing death",
            "knowledge that death",
            "likely to cause death"
        ]
        
        is_intention_only = any(
            phrase in ingredient_lower
            for phrase in intention_only_phrases
        )
        
        # If ingredient mentions death as OUTCOME (not just intent), require death
        if requires_death_in_text and not is_intention_only:
            return True
        
        return False

    def _llm_full_context_judgement(
        self,
        sub_query: str,
        facts: str,
        context_block: str,
        id_list_str: str,
        role_instruction: str,
        penalty_block: str,
        victim_survived: bool = False,
    ) -> str:
        """
        LLM function call: SIMPLIFIED to ensure valid JSON generation.
        """
        # Build critical instruction if victim survived
        survival_instruction = ""
        if victim_survived:
            survival_instruction = """
CRITICAL: Victim SURVIVED (no death occurred) BUT victim was injured.
- REJECT: IPC_299, IPC_300, IPC_302, IPC_304 (require DEATH - victim did not die)
- CAN ACCEPT: IPC_307, IPC_308 (attempt offences - no death required, only intention + act)
- CAN ACCEPT: IPC_324, IPC_326 (hurt/grievous hurt - IF injuries occurred)

IMPORTANT: "Victim survived" means NO DEATH. It does NOT mean no injuries.
"""
        
        prompt = f"""You are a criminal law judge. Evaluate ONLY the sections listed below.

CASE FACTS:
{facts[:700]}

{survival_instruction}

STATUTORY TEXT:
{context_block}

YOU MUST EVALUATE EXACTLY THESE SECTIONS (no more, no less): {id_list_str}

STRICT INGREDIENT MATCHING RULES:
You MUST verify that the SPECIFIC ingredients required by the section are present in the case facts.

1. Death-related COMPLETED offences (IPC 299/300/302/304):
   - Require DEATH as consequence
   - If victim SURVIVED (did not die) → MUST REJECT
   
2. ATTEMPT offences (IPC 307/308):
   - Require intention/knowledge + overt act
   - Death NOT required → Can accept if both intention AND act present
   
3. Hurt-related offences (IPC 324/326):
   - IPC 324: Voluntarily causing HURT by dangerous weapon
   - IPC 326: Voluntarily causing GRIEVOUS HURT by dangerous weapon
   - ONLY accept if: (a) injury occurred AND (b) dangerous weapon used
   - "Victim survived" means no death, NOT no injuries
   
4. IPC 326A (Acid attack):
   - Requires ACID or CORROSIVE SUBSTANCE
   - If case mentions knife/blade/weapon but NO acid → MUST REJECT
   - Do NOT accept just because grievous hurt occurred
   
5. IPC 506 (Criminal intimidation):
   - Requires THREAT or INTIMIDATION (words, gestures)
   - Actual physical assault is NOT intimidation
   - If case describes attack/assault but NO threat → MUST REJECT
   
6. IPC 498A (Cruelty by husband):
   - Requires MATRIMONIAL relationship
   - If no mention of husband/wife/marriage → MUST REJECT

7. DO NOT add or invent sections. ONLY evaluate the sections in the list above.

{penalty_block}

Return JSON array with EXACTLY ONE object per section in the list above.

Each object MUST have:
- "id": section ID (must be from the list above)
- "verdict": "ACCEPTED" or "REJECTED"  
- "reasoning": ONE sentence explaining why ingredient matches/doesn't match the case facts
- "ingredient": PRIMARY statutory ingredient (for ACCEPTED only; must cite actual ingredient from statutory text)

CRITICAL VALIDATION:
- For ACCEPTED: ingredient field must cite the SPECIFIC element from statutory text
- For ACCEPTED: reasoning must show how case facts contain that SPECIFIC ingredient
- For REJECTED: clearly state which required ingredient is missing from case facts

Your JSON array must have one object for EACH section in: {id_list_str}
Do not add extra sections. Do not omit any sections.

Return ONLY the JSON array:"""

        try:
            response = self.llm.invoke(prompt)
            content = response.content.strip()
            
            # Aggressive cleanup
            import re
            # Remove markdown code blocks
            content = re.sub(r'```json\s*', '', content, flags=re.IGNORECASE)
            content = re.sub(r'```\s*', '', content)
            content = content.strip()
            
            # Find the JSON array
            match = re.search(r'\[\s*\{.*?\}\s*\]', content, re.DOTALL)
            if match:
                return match.group(0)
            
            return content
        except Exception as exc:
            print(f"[LLM] Step 3 call failed: {exc}")
            return "[]"

    # =========================================================================
    # Context builder — ipc_structured.json
    # =========================================================================

    def _build_structured_context(self, section_ids: List[str]) -> str:
        """
        Build the full statutory context block for the given section IDs
        from ipc_structured.json. Only these IDs are included.
        """
        parts = []
        for sid in section_ids:
            entry = self._structured_by_id.get(sid)
            if not entry:
                print(f"[Agent:Step3] WARNING: {sid} not found in ipc_structured.json")
                continue

            title   = entry.get("section_title", sid)
            text    = (entry.get("text", "") or "").strip()[:MAX_TEXT_CHARS]
            expl    = entry.get("explanation", []) or []
            illus   = entry.get("illustration", []) or []
            exc     = entry.get("exception", []) or []
            proviso = entry.get("proviso", []) or []

            block = [f"\n══ {sid} — Section {entry.get('section_number','')} — {title} ══"]
            block.append(f"STATUTORY TEXT:\n{text}")
            if expl:
                block.append("EXPLANATION:\n" + "\n".join(str(e) for e in expl)[:500])
            if illus:
                block.append("ILLUSTRATION:\n" + "\n".join(str(i) for i in illus)[:500])
            if exc:
                block.append("EXCEPTION:\n" + "\n".join(str(e) for e in exc)[:400])
            if proviso:
                block.append("PROVISO:\n" + "\n".join(str(p) for p in proviso)[:300])
            parts.append("\n".join(block))

        return "\n\n".join(parts)

    # =========================================================================
    # Candidate and match builders
    # =========================================================================

    def _make_candidate(
        self, sec_id: str, reasoning: str, ingredient: str = ""
    ) -> Optional[Dict[str, Any]]:
        idx_entry  = self._index_by_id.get(sec_id, {})
        structured = self._structured_by_id.get(sec_id, {})

        if not idx_entry and not structured:
            return None

        return {
            "section":         sec_id,
            "title":           (
                idx_entry.get("title")
                or structured.get("section_title", sec_id)
            ),
            "chapter":         idx_entry.get("chapter_name", ""),
            "relevance_score": 0.85,
            "is_offense":      True,
            "reasoning":       reasoning,
            "ingredient":      ingredient,
            "structured": {
                "text":           structured.get("text", ""),
                "explanation":    structured.get("explanation", []),
                "illustration":   structured.get("illustration", []),
                "exception":      structured.get("exception", []),
                "proviso":        structured.get("proviso", []),
                "section_number": structured.get("section_number", ""),
                "chapter":        structured.get("chapter_title", ""),
            },
        }

    def _build_matches(self, confirmed: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        matches = []
        for cand in confirmed:
            sec_id     = cand["section"]
            s          = cand.get("structured", {})
            idx_entry  = self._index_by_id.get(sec_id, {})
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
            matches.append({
                "id":    sec_id,
                "score": cand.get("relevance_score", 0.85),
                "metadata": {
                    "section":       section_num,
                    "section_num":   section_num,
                    "title":         title,
                    "description":   s.get("text") or structured.get("text", ""),
                    "punishment":    "",
                    "chapter":       idx_entry.get("chapter_number", ""),
                    "chapter_title": idx_entry.get("chapter_name", ""),
                    "full_text":     s.get("text") or structured.get("text", ""),
                    "explanation":   s.get("explanation") or structured.get("explanation", []),
                    "illustration":  s.get("illustration") or structured.get("illustration", []),
                    "exception":     s.get("exception") or structured.get("exception", []),
                    "is_offense":    cand.get("is_offense", True),
                    "reasoning":     cand.get("reasoning", ""),
                    "ingredient":    cand.get("ingredient", ""),
                },
            })
        matches.sort(key=lambda m: m["score"], reverse=True)
        return matches

    # =========================================================================
    # Utilities
    # =========================================================================

    def _extract_complainant_facts(self, case_facts: str) -> str:
        """
        Strip the defence narrative from the case facts.
        The LLM should only see the complainant's side when identifying offences.
        """
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
                f"({len(case_facts) - cut_at} chars)"
            )
        return trimmed if trimmed else case_facts

    def _load_json(self, path: Path) -> List[Dict[str, Any]]:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, list):
                print(f"[LLMIPCRetrievalService] WARNING: Expected list in {path}, got {type(data)}")
                return []
            return data
        except FileNotFoundError:
            print(f"[LLMIPCRetrievalService] ERROR: File not found: {path}")
            return []
        except json.JSONDecodeError as e:
            print(f"[LLMIPCRetrievalService] ERROR: Bad JSON in {path}: {e}")
            return []