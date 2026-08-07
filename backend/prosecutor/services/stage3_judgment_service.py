"""
Stage 3: Full Context Judgment Service
=======================================
LLM reads FULL statutory text from ipc_structured.json.
Must cite exact ingredients and explain how facts satisfy them.
Agent verifies ingredient citations are present and grounded.
"""

import json
import textwrap
from typing import List, Dict, Any, Tuple, Optional

try:
    from config.llm_config import get_llm
except ModuleNotFoundError:
    from agents.config.llm_config import get_llm

from .agent_state import AgentState, AgentPerception, AgentDecision


MAX_TEXT_CHARS = 1500
MAX_RETRIES = 3


class Stage3JudgmentService:
    """
    Stage 3: Full Context Judgment
    
    For each candidate section:
    - Agent provides LLM with FULL statutory text, explanation, illustration
    - LLM must decide ACCEPTED/REJECTED with ingredient-level citation
    - Agent verifies citations are present and reasoning is grounded
    """
    
    def __init__(self, ipc_structured: List[Dict[str, Any]]):
        self.llm = get_llm(temperature=0.0, provider="groq")
        self.ipc_structured = ipc_structured
        
        # Build section ID → structured entry mapping
        self.structured_by_id: Dict[str, Dict] = {
            entry["id"]: entry
            for entry in ipc_structured
            if isinstance(entry, dict) and "id" in entry
        }
        
        print(f"[Stage3] Loaded {len(self.structured_by_id)} structured IPC sections")
    
    def judge_sections(self, state: AgentState) -> bool:
        """
        Main Stage 3 execution - judges all candidate sections.
        
        Returns:
            True if at least one section confirmed
        """
        if not state.candidate_section_ids:
            print("[Stage3] ERROR: No candidate sections from Stage 2")
            return False
        
        candidate_list = sorted(state.candidate_section_ids)
        
        print(f"\n{'='*80}")
        print(f"[Stage3] AGENT PERCEIVING: Full context judgment")
        print(f"[Stage3] Candidate sections: {len(candidate_list)}")
        print(f"[Stage3] Sections: {candidate_list}")
        print(f"{'='*80}")
        
        # Build full context block from ipc_structured.json
        context_block = self._build_structured_context(candidate_list)
        
        if not context_block:
            print("[Stage3] ERROR: Could not build context block")
            return False
        
        # Run RL loop for judgment
        confirmed = self._judge_with_rl_loop(
            state=state,
            section_ids=candidate_list,
            context_block=context_block
        )
        
        if not confirmed:
            print(f"\n[Stage3] ✗ FAILED: No sections confirmed")
            return False
        
        state.confirmed_sections = confirmed
        print(f"\n[Stage3] ✓ SUCCESS: Confirmed {len(confirmed)} sections")
        print(f"[Stage3] Sections: {list(confirmed.keys())}")
        return True
    
    def _build_structured_context(self, section_ids: List[str]) -> str:
        """
        Build full statutory context block for candidate sections.
        Includes text, explanation, illustration, exception, proviso.
        """
        parts = []
        
        for sec_id in section_ids:
            entry = self.structured_by_id.get(sec_id)
            if not entry:
                print(f"[Stage3] WARNING: {sec_id} not found in ipc_structured.json")
                continue
            
            sec_num = entry.get("section_number", "")
            title = entry.get("section_title", sec_id)
            text = (entry.get("text", "") or "").strip()[:MAX_TEXT_CHARS]
            
            expl = entry.get("explanation", []) or []
            illus = entry.get("illustration", []) or []
            exc = entry.get("exception", []) or []
            proviso = entry.get("proviso", []) or []
            
            block = [
                f"\n{'='*70}",
                f"{sec_id} — Section {sec_num} — {title}",
                f"{'='*70}",
                f"STATUTORY TEXT:\n{text}"
            ]
            
            if expl:
                block.append(f"\nEXPLANATION:\n" + "\n".join(str(e) for e in expl)[:500])
            
            if illus:
                block.append(f"\nILLUSTRATION:\n" + "\n".join(str(i) for i in illus)[:500])
            
            if exc:
                block.append(f"\nEXCEPTION:\n" + "\n".join(str(e) for e in exc)[:400])
            
            if proviso:
                block.append(f"\nPROVISO:\n" + "\n".join(str(p) for p in proviso)[:300])
            
            parts.append("\n".join(block))
        
        return "\n\n".join(parts)
    
    def _judge_with_rl_loop(
        self,
        state: AgentState,
        section_ids: List[str],
        context_block: str
    ) -> Dict[str, Dict[str, Any]]:
        """
        RL loop for full context judgment.
        
        Returns:
            Dict of confirmed sections: {section_id: candidate_dict}
        """
        id_list_str = ", ".join(section_ids)
        penalty_block = ""
        
        for attempt in range(1, MAX_RETRIES + 1):
            print(f"\n[Stage3] Attempt {attempt}/{MAX_RETRIES}")
            
            # LLM call
            raw_response = self._call_llm(
                query=state.raw_query,
                facts=state.complainant_facts,
                context_block=context_block,
                id_list_str=id_list_str,
                penalty_block=penalty_block
            )
            
            # Agent verification
            success, confirmed, perception = self._verify_response(
                raw_response=raw_response,
                attempt=attempt,
                section_ids=set(section_ids)
            )
            
            # Log perception
            state.log(perception)
            
            if success:
                print(f"[Stage3] ✓ REWARD → Confirmed: {list(confirmed.keys())}")
                return confirmed
            else:
                penalty_block = perception.penalty_message
                print(f"[Stage3] ✗ PENALIZE → {perception.reasoning[:100]}")
        
        print(f"[Stage3] ✗ All retries exhausted")
        return {}
    
    def _call_llm(
        self,
        query: str,
        facts: str,
        context_block: str,
        id_list_str: str,
        penalty_block: str
    ) -> str:
        """Call LLM for full context judgment with ingredient citation."""
        prompt = textwrap.dedent(f"""
        You are a senior criminal law prosecutor evaluating whether statutory sections
        apply to a case for OPPOSING anticipatory bail.
        
        The statutory text below is taken DIRECTLY from ipc_structured.json.
        You MUST ground EVERY decision in this text - do not recall IPC sections from memory.
        
        QUERY (full case):
        {query[:800]}
        
        CASE FACTS (prosecution side):
        {facts[:600]}
        
        FULL STATUTORY CONTEXT (from ipc_structured.json):
        {context_block}
        
        TASK:
        For EACH section listed below, decide ACCEPTED or REJECTED.
        
        For ACCEPTED sections (prosecution can use to oppose bail):
        - 'ingredient': Copy the EXACT statutory ingredient phrase from the text above.
          This must be a direct quote from the statutory text, not a paraphrase.
          Examples: "whoever subjects a woman to cruelty", "demand of dowry", 
          "criminal intimidation", "dishonestly induces delivery of property"
        - 'reasoning': One clear sentence explaining how the case facts prima facie 
          satisfy this ingredient. Quote or closely paraphrase the relevant statutory line.
        
        For REJECTED sections:
        - 'ingredient': Leave empty ("")
        - 'reasoning': One sentence explaining which statutory ingredient is NOT met 
          by the facts, or why the section doesn't apply.
        
        PROSECUTOR STANCE:
        - You are arguing AGAINST bail - look for sections that establish gravity of offence
        - If statutory ingredients are prima facie present, ACCEPT the section
        - Only REJECT if ingredients clearly don't match the facts
        
        Sections to evaluate: {id_list_str}
        
        {penalty_block}
        
        Return ONLY a JSON array - no preamble, no markdown, no text outside JSON:
        [
          {{
            "id": "IPC_XXX",
            "verdict": "ACCEPTED",
            "ingredient": "exact ingredient phrase from statutory text above",
            "reasoning": "one sentence citing ingredient and how facts satisfy it"
          }},
          {{
            "id": "IPC_YYY",
            "verdict": "REJECTED",
            "ingredient": "",
            "reasoning": "one sentence explaining which ingredient is not met"
          }}
        ]
        
        Every section in [{id_list_str}] MUST have exactly one entry.
        No section may be omitted.
        """).strip()
        
        try:
            response = self.llm.invoke(prompt)
            return response.content.strip()
        except Exception as e:
            print(f"[Stage3] LLM call failed: {e}")
            return "[]"
    
    def _verify_response(
        self,
        raw_response: str,
        attempt: int,
        section_ids: set
    ) -> Tuple[bool, Dict[str, Dict[str, Any]], AgentPerception]:
        """
        Agent verifies LLM judgment response.
        
        Returns:
            (success, confirmed_sections_dict, perception)
        """
        step = f"Stage3_attempt{attempt}"
        
        # Parse JSON array of objects
        parsed = self._parse_json_object_list(raw_response)
        
        if not parsed:
            return False, {}, AgentPerception(
                step=step,
                observation=f"LLM returned unparseable output: {raw_response[:100]}",
                reasoning="Cannot parse JSON array of objects from LLM response - format violation",
                decision=AgentDecision.PENALIZE,
                penalty_message=(
                    "PENALTY: Your response was not valid JSON.\n"
                    "Return ONLY a JSON array of objects as specified.\n"
                    "No preamble, no markdown, no explanation outside the JSON.\n"
                    "Each object must have: id, verdict, ingredient, reasoning"
                )
            )
        
        # Validate each judgment
        issues = []
        accepted_items = []
        
        for item in parsed:
            if not isinstance(item, dict):
                issues.append("Non-dict item in array - expected object with id, verdict, etc.")
                continue
            
            sec_id = str(item.get("id", "")).strip()
            verdict = str(item.get("verdict", "")).upper().strip()
            reasoning = str(item.get("reasoning", "")).strip()
            ingredient = str(item.get("ingredient", "")).strip()
            
            # Check 1: Section ID must be one we asked about
            if sec_id not in section_ids:
                issues.append(
                    f"'{sec_id}' was not in the sections asked for evaluation. "
                    f"Do not add or remove sections."
                )
                continue
            
            # Check 2: Verdict must be ACCEPTED or REJECTED
            if verdict not in ("ACCEPTED", "REJECTED"):
                issues.append(
                    f"'{sec_id}': verdict must be exactly 'ACCEPTED' or 'REJECTED', "
                    f"got '{verdict}'"
                )
                continue
            
            # Check 3: ACCEPTED requires non-empty ingredient
            if verdict == "ACCEPTED":
                if not ingredient:
                    issues.append(
                        f"'{sec_id}': ACCEPTED verdict but 'ingredient' field is empty. "
                        f"You MUST cite the specific statutory ingredient from the text. "
                        f"This is mandatory for prosecution arguments."
                    )
                    continue
                
                # Check 4: Reasoning must be substantive
                if len(reasoning) < 20:
                    issues.append(
                        f"'{sec_id}': reasoning is too brief ('{reasoning}'). "
                        f"Provide a full sentence linking the statutory ingredient to the facts."
                    )
                    continue
                
                accepted_items.append(item)
                print(f"[Stage3] ✓ ACCEPTED {sec_id}: ingredient='{ingredient[:60]}' | reason='{reasoning[:80]}'")
            else:
                print(f"[Stage3] ✗ REJECTED {sec_id}: {reasoning[:80]}")
        
        # If there are issues, PENALIZE
        if issues:
            return False, {}, AgentPerception(
                step=step,
                observation=f"LLM response had {len(issues)} issue(s): {issues[:3]}",
                reasoning=(
                    f"Agent found violations in LLM output: {issues}. "
                    f"LLM must fix these before sections can be accepted."
                ),
                decision=AgentDecision.PENALIZE,
                penalty_message=(
                    "PENALTY: The following issues were found in your response:\n"
                    + "\n".join(f"  - {issue}" for issue in issues)
                    + "\n\nFix ALL issues and resubmit the complete JSON array for ALL sections. "
                    "Do not omit any section."
                )
            )
        
        # Build confirmed sections dict
        confirmed: Dict[str, Dict[str, Any]] = {}
        for item in accepted_items:
            sec_id = item["id"]
            confirmed[sec_id] = {
                "section_id": sec_id,
                "ingredient": item.get("ingredient", ""),
                "reasoning": item.get("reasoning", ""),
                "verdict": "ACCEPTED",
                "confidence": 0.85,
                "structured": self.structured_by_id.get(sec_id, {})
            }
        
        # SUCCESS - REWARD
        return True, confirmed, AgentPerception(
            step=step,
            observation=(
                f"LLM accepted {len(accepted_items)} sections, "
                f"rejected {len(parsed) - len(accepted_items)}"
            ),
            reasoning=(
                f"All {len(accepted_items)} accepted items passed agent verification. "
                f"Confirmed: {list(confirmed.keys())}. Rewarding."
            ),
            decision=AgentDecision.REWARD,
            metadata={"confirmed": list(confirmed.keys())}
        )
    
    def _parse_json_object_list(self, text: str) -> Optional[List[Dict]]:
        """Parse JSON array of objects from LLM response."""
        import re
        
        # Strip markdown fences
        cleaned = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE).strip()
        cleaned = cleaned.replace("```", "").strip()
        
        # Find JSON array
        match = re.search(r"\[.*?\]", cleaned, re.DOTALL)
        if not match:
            return None
        
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass
        
        return None
