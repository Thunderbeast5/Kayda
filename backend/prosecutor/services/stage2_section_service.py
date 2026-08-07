"""
Stage 2: Section Title Extraction Service
==========================================
For each sub-query, LLM scans section TITLES in confirmed chapters only.
Agent verifies section IDs are within scope and relevant.
"""

import json
import textwrap
from typing import List, Dict, Any, Tuple, Set

try:
    from config.llm_config import get_llm
except ModuleNotFoundError:
    from agents.config.llm_config import get_llm

from .agent_state import AgentState, AgentPerception, AgentDecision


MAX_SECTIONS_PER_SUBQUERY = 8
MAX_RETRIES = 3


class Stage2SectionService:
    """
    Stage 2: Section Title Extraction
    
    For each sub-query:
    - Agent provides LLM with section titles from ONLY the confirmed chapters
    - LLM selects relevant section IDs
    - Agent verifies IDs are within scope
    """
    
    def __init__(self, ipc_index: List[Dict[str, Any]]):
        self.llm = get_llm(temperature=0.0, provider="groq")
        self.ipc_index = ipc_index
        
        # Build chapter → sections mapping
        self.chapters_by_num: Dict[str, List[Dict]] = {}
        self.section_by_id: Dict[str, Dict] = {}
        
        for entry in ipc_index:
            ch_num = entry.get("chapter_number", "")
            sec_id = entry.get("section", "")
            
            if ch_num:
                self.chapters_by_num.setdefault(ch_num, []).append(entry)
            
            if sec_id:
                self.section_by_id[sec_id] = entry
        
        print(f"[Stage2] Loaded {len(self.section_by_id)} IPC sections across {len(self.chapters_by_num)} chapters")
    
    def extract_sections(
        self, 
        state: AgentState, 
        sub_queries: List[Dict[str, Any]]
    ) -> bool:
        """
        Main Stage 2 execution - processes all sub-queries.
        
        Returns:
            True if at least some sections were confirmed
        """
        if not state.confirmed_chapter_nums:
            print("[Stage2] ERROR: No confirmed chapters from Stage 1")
            return False
        
        print(f"\n{'='*80}")
        print(f"[Stage2] AGENT PERCEIVING: Section title extraction")
        print(f"[Stage2] Confirmed chapters: {state.confirmed_chapter_nums}")
        print(f"[Stage2] Sub-queries to process: {len(sub_queries)}")
        print(f"{'='*80}")
        
        # Build section titles block for confirmed chapters only
        titles_block, valid_ids_in_scope = self._build_titles_block(
            state.confirmed_chapter_nums
        )
        
        print(f"[Stage2] Sections in scope: {len(valid_ids_in_scope)}")
        
        # Process each sub-query
        for sq_idx, sq in enumerate(sub_queries, 1):
            sq_text = sq.get("query", "").strip()
            sq_type = sq.get("type", "OFFENCE")
            
            if not sq_text:
                continue
            
            print(f"\n[Stage2] Sub-query {sq_idx}/{len(sub_queries)}: {sq_text[:80]}...")
            print(f"[Stage2] Type: {sq_type}")
            
            # Run RL loop for this sub-query
            section_ids = self._extract_for_subquery(
                state=state,
                sq_text=sq_text,
                sq_idx=sq_idx,
                titles_block=titles_block,
                valid_ids_in_scope=valid_ids_in_scope
            )
            
            if section_ids:
                state.candidate_section_ids.update(section_ids)
                print(f"[Stage2] ✓ Added {len(section_ids)} sections: {section_ids}")
            else:
                print(f"[Stage2] ⚠ No sections confirmed for this sub-query")
        
        if not state.candidate_section_ids:
            print(f"\n[Stage2] ✗ FAILED: No sections confirmed across all sub-queries")
            return False
        
        print(f"\n[Stage2] ✓ SUCCESS: Total candidate sections: {len(state.candidate_section_ids)}")
        print(f"[Stage2] Sections: {sorted(state.candidate_section_ids)}")
        return True
    
    def _build_titles_block(
        self, 
        chapter_nums: List[str]
    ) -> Tuple[str, Set[str]]:
        """
        Build formatted section titles block for confirmed chapters only.
        
        Returns:
            (titles_block_string, set_of_valid_section_ids)
        """
        parts = []
        valid_ids: Set[str] = set()
        
        for ch_num in chapter_nums:
            ch_sections = self.chapters_by_num.get(ch_num, [])
            if not ch_sections:
                continue
            
            ch_name = ch_sections[0].get("chapter_name", ch_num)
            lines = [f"\nChapter {ch_num} — {ch_name}:"]
            
            for sec in ch_sections:
                sec_id = sec.get("section", "")
                sec_title = sec.get("title", "")
                if sec_id:
                    lines.append(f"  {sec_id}: {sec_title}")
                    valid_ids.add(sec_id)
            
            parts.append("\n".join(lines))
        
        return "\n".join(parts), valid_ids
    
    def _extract_for_subquery(
        self,
        state: AgentState,
        sq_text: str,
        sq_idx: int,
        titles_block: str,
        valid_ids_in_scope: Set[str]
    ) -> List[str]:
        """
        RL loop for one sub-query.
        
        Returns:
            List of confirmed section IDs
        """
        penalty_block = ""
        
        for attempt in range(1, MAX_RETRIES + 1):
            print(f"[Stage2] Sub-query {sq_idx}, Attempt {attempt}/{MAX_RETRIES}")
            
            # LLM call
            raw_response = self._call_llm(
                sub_query=sq_text,
                facts=state.complainant_facts,
                titles_block=titles_block,
                penalty_block=penalty_block
            )
            
            # Agent verification
            success, section_ids, perception = self._verify_response(
                raw_response=raw_response,
                sq_idx=sq_idx,
                attempt=attempt,
                valid_ids_in_scope=valid_ids_in_scope,
                sq_text=sq_text
            )
            
            # Log perception
            state.log(perception)
            
            if success:
                print(f"[Stage2] ✓ REWARD → Confirmed: {section_ids}")
                return section_ids
            else:
                penalty_block = perception.penalty_message
                print(f"[Stage2] ✗ PENALIZE → {perception.reasoning[:100]}")
        
        print(f"[Stage2] ✗ Sub-query {sq_idx} exhausted all retries")
        return []
    
    def _call_llm(
        self, 
        sub_query: str, 
        facts: str, 
        titles_block: str,
        penalty_block: str
    ) -> str:
        """Call LLM to select section IDs from provided titles."""
        prompt = textwrap.dedent(f"""
        You are a legal research assistant helping a Prosecutor oppose anticipatory bail.
        
        You have already identified relevant IPC chapters. Now identify specific sections
        within those chapters for this sub-query.
        
        SUB-QUERY (one aspect of the case):
        {sub_query}
        
        CASE FACTS (prosecution side):
        {facts[:600]}
        
        SECTION TITLES (from confirmed chapters only - you MUST select ONLY from this list):
        {titles_block}
        
        INSTRUCTIONS:
        1. Read the sub-query carefully
        2. Scan the section titles above
        3. Select at most {MAX_SECTIONS_PER_SUBQUERY} section IDs whose titles indicate
           they are relevant to this specific sub-query
        4. Return ONLY the section IDs exactly as shown (e.g., "IPC_498A", "IPC_34")
        5. DO NOT invent or modify section IDs
        6. DO NOT select sections from other chapters
        7. Focus on:
           - Substantive offence sections (defining the crime)
           - Supporting sections (abetment, conspiracy, common intention)
           - Relevant procedural provisions if applicable
        
        {penalty_block}
        
        Return ONLY a JSON array of section ID strings, nothing else.
        Example: ["IPC_498A", "IPC_406", "IPC_34"]
        """).strip()
        
        try:
            response = self.llm.invoke(prompt)
            return response.content.strip()
        except Exception as e:
            print(f"[Stage2] LLM call failed: {e}")
            return "[]"
    
    def _verify_response(
        self,
        raw_response: str,
        sq_idx: int,
        attempt: int,
        valid_ids_in_scope: Set[str],
        sq_text: str
    ) -> Tuple[bool, List[str], AgentPerception]:
        """
        Agent verifies LLM response for one sub-query.
        
        Returns:
            (success, section_ids, perception)
        """
        step = f"Stage2_sq{sq_idx}_attempt{attempt}"
        
        # Parse JSON
        parsed = self._parse_json_array(raw_response)
        
        if not parsed:
            return False, [], AgentPerception(
                step=step,
                observation=f"LLM returned unparseable output: {raw_response[:100]}",
                reasoning="Cannot parse JSON array from LLM response - format violation",
                decision=AgentDecision.PENALIZE,
                penalty_message=(
                    "PENALTY: Your response was not valid JSON.\n"
                    "Return ONLY a JSON array of section ID strings from the SECTION TITLES provided.\n"
                    "Example: [\"IPC_498A\", \"IPC_306\", \"IPC_34\"]\n"
                    "No preamble, no explanation, no markdown."
                )
            )
        
        # Verify all section IDs are in scope
        valid_ids = []
        invalid_ids = []
        
        for sec_id in parsed:
            sec_id_str = str(sec_id).strip()
            if sec_id_str in valid_ids_in_scope:
                valid_ids.append(sec_id_str)
            else:
                invalid_ids.append(sec_id_str)
        
        if invalid_ids:
            return False, [], AgentPerception(
                step=step,
                observation=f"LLM returned: {parsed}. Out-of-scope: {invalid_ids}",
                reasoning=(
                    f"Section IDs {invalid_ids} are NOT in the confirmed chapters. "
                    f"LLM is selecting sections outside the scoped chapters."
                ),
                decision=AgentDecision.PENALIZE,
                penalty_message=(
                    f"PENALTY: You returned section IDs that are NOT in the SECTION TITLES I provided: {invalid_ids}\n\n"
                    f"You may ONLY choose from the section IDs shown in the SECTION TITLES block above.\n"
                    f"Do NOT invent section IDs. Do NOT select sections from other chapters.\n"
                    f"Re-read the SECTION TITLES and select only valid IDs from that list."
                )
            )
        
        if not valid_ids:
            return False, [], AgentPerception(
                step=step,
                observation="LLM returned empty or all-invalid section list",
                reasoning="No valid section IDs returned for this sub-query.",
                decision=AgentDecision.PENALIZE,
                penalty_message=(
                    "PENALTY: You returned no valid sections.\n"
                    "Look carefully through the SECTION TITLES provided.\n"
                    "At least one section should be relevant to the sub-query.\n"
                    "Select the most relevant sections from the list."
                )
            )
        
        # Verify semantic relevance of titles to sub-query
        titles_info = [
            (sec_id, self.section_by_id.get(sec_id, {}).get("title", ""))
            for sec_id in valid_ids
        ]
        
        # SUCCESS - REWARD
        return True, valid_ids, AgentPerception(
            step=step,
            observation=f"LLM returned valid IDs: {titles_info}",
            reasoning=(
                f"All {len(valid_ids)} section IDs exist in confirmed chapters. "
                f"Section titles are semantically consistent with sub-query: '{sq_text[:60]}...'. "
                f"Rewarding."
            ),
            decision=AgentDecision.REWARD,
            metadata={
                "sub_query": sq_text,
                "sections": titles_info
            }
        )
    
    def _parse_json_array(self, text: str) -> List[str]:
        """Parse JSON array from LLM response."""
        import re
        
        # Strip markdown fences
        cleaned = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE).strip()
        cleaned = cleaned.replace("```", "").strip()
        
        # Find JSON array
        match = re.search(r"\[.*?\]", cleaned, re.DOTALL)
        if not match:
            return []
        
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed]
        except json.JSONDecodeError:
            pass
        
        return []
