"""
Stage 1: Chapter Identification with Agent Reasoning
====================================================
Agent REASONS about case facts, then uses LLM to verify chapter relevance.
No keyword matching - pure legal reasoning based on actual events.
"""

import json
import textwrap
from typing import List, Dict, Any, Tuple

try:
    from config.llm_config import get_llm
except ModuleNotFoundError:
    from agents.config.llm_config import get_llm

# Import AgentPerception and AgentDecision from the main service
try:
    from .llm_ipc_retrieval_service import AgentPerception, AgentDecision
except ImportError:
    from llm_ipc_retrieval_service import AgentPerception, AgentDecision


MAX_CHAPTERS = 5
MAX_RETRIES = 3


class Stage1ChapterService:
    """
    Stage 1: Agent Reasoning → Chapter Identification
    
    Phase 1: Agent perceives and reasons about case facts
    Phase 2: Agent identifies plausible offence categories
    Phase 3: LLM maps categories to IPC chapter names
    Phase 4: Agent verifies semantic relevance
    """
    
    def __init__(self, ipc_index: List[Dict[str, Any]]):
        self.llm = get_llm(temperature=0.0, provider="groq")
        self.ipc_index = ipc_index
        
        # Build chapter mapping: name → number
        self.chapter_name_to_num: Dict[str, str] = {}
        self.chapter_num_to_name: Dict[str, str] = {}
        
        seen_chapters: Dict[str, str] = {}
        for entry in ipc_index:
            ch_num = entry.get("chapter_number", "")
            ch_name = entry.get("chapter_name", "")
            if ch_num and ch_name and ch_num not in seen_chapters:
                seen_chapters[ch_num] = ch_name
                self.chapter_name_to_num[ch_name] = ch_num
                self.chapter_num_to_name[ch_num] = ch_name
        
        # Create formatted chapter list for LLM
        self.chapter_list_str = "\n".join(
            f"  {num}: {name}" 
            for num, name in sorted(seen_chapters.items())
        )
        
        print(f"[Stage1] Loaded {len(seen_chapters)} IPC chapters")
    
    def identify_chapters(self, state) -> bool:
        """
        Main Stage 1 execution: Agent reasons about facts, then verifies chapter selections.
        
        Args:
            state: AgentState object from llm_ipc_retrieval_service (has raw_query, confirmed_chapter_nums, etc.)
        
        Flow:
        1. Agent perceives case facts (actors, actions, outcomes, context)
        2. Agent reasons about plausible offence categories
        3. LLM maps to specific IPC chapters
        4. Agent verifies semantic relevance
        
        Returns:
            True if chapters confirmed, False if failed
        """
        print(f"\n{'='*80}")
        print(f"[Stage1] PHASE 1: AGENT REASONING")
        print(f"[Stage1] Query: {state.raw_query[:120]}...")
        print(f"{'='*80}")
        
        # PHASE 1: Agent perceives and reasons about case facts
        case_analysis = self._agent_reason_about_facts(state.raw_query)
        
        if not case_analysis:
            print("[Stage1] ✗ Agent failed to analyze case facts")
            return False
        
        # Log Agent's reasoning
        print(f"\n[Stage1] AGENT PERCEPTION:")
        print(f"  Actors: {case_analysis.get('actors', 'Unknown')}")
        print(f"  Actions: {case_analysis.get('actions', 'Unknown')}")
        print(f"  Outcome: {case_analysis.get('outcome', 'Unknown')}")
        print(f"  Context: {case_analysis.get('context', 'Unknown')}")
        print(f"\n[Stage1] AGENT REASONING:")
        print(f"  Offence Nature: {case_analysis.get('offence_nature', 'Unknown')}")
        print(f"  Plausible Categories: {', '.join(case_analysis.get('plausible_categories', []))}")
        
        # PHASE 2: Map Agent's reasoning to IPC chapters
        penalty_block = ""
        
        for attempt in range(1, MAX_RETRIES + 1):
            print(f"\n[Stage1] PHASE 2: LLM CHAPTER MAPPING (Attempt {attempt}/{MAX_RETRIES})")
            
            # LLM maps Agent's reasoning to chapter names
            raw_response = self._call_llm_for_chapters(
                case_analysis=case_analysis,
                penalty_block=penalty_block
            )
            
            # Agent verifies LLM's selection
            success, chapter_nums, chapter_names, perception = self._verify_chapter_selection(
                raw_response=raw_response,
                case_analysis=case_analysis,
                attempt=attempt
            )
            
            # Log perception
            state.log(perception)
            
            if success:
                # REWARD: Store confirmed chapters
                state.confirmed_chapter_nums = chapter_nums
                state.confirmed_chapter_names = chapter_names
                print(f"\n[Stage1] ✓ REWARD → Confirmed chapters:")
                for num, name in zip(chapter_nums, chapter_names):
                    print(f"    {num}: {name}")
                return True
            else:
                # PENALISE: Prepare penalty message for next iteration
                penalty_block = perception.penalty_message
                print(f"\n[Stage1] ✗ PENALISE → {perception.reasoning[:100]}")
        
        # All retries exhausted
        print(f"\n[Stage1] ✗ FAILED: All {MAX_RETRIES} attempts exhausted")
        return False
    
    def _agent_reason_about_facts(self, query: str) -> Dict[str, Any]:
        """
        PHASE 1: Agent extracts STRUCTURED FACTS ONLY (no premature labeling).
        
        Returns raw observable facts with explicit boolean flags.
        NO offence_nature label - LLM will reason directly from facts to chapters.
        """
        prompt = textwrap.dedent(f"""
        You are a legal fact analyzer. Extract ONLY the observable facts from this case.
        DO NOT label offence types. DO NOT suggest IPC chapters. Just describe what happened.
        
        CASE FACTS:
        {query}
        
        Extract and return a JSON object with:
        {{
            "actors": "who was involved (roles/relationships)",
            "actions": ["specific action 1", "specific action 2", ...],
            "outcome": "what resulted (injuries/death/other harm)",
            "context": "where/when/circumstances",
            "explicit_elements": {{
                "physical_harm": boolean,
                "death_occurred": boolean,
                "weapon_used": "type if mentioned, else null",
                "sexual_nature": boolean,
                "property_involved": boolean,
                "threat_or_intimidation": boolean,
                "marriage_relationship": boolean,
                "public_servant_involved": boolean,
                "child_involved": boolean
            }}
        }}
        
        CRITICAL RULES:
        - Base extraction ONLY on explicitly stated facts
        - DO NOT infer actions that aren't mentioned
        - DO NOT add legal interpretations
        - For explicit_elements, mark true ONLY if clearly stated in facts
        - actions must be a LIST of specific verbs/actions
        
        Return ONLY the JSON object.
        """).strip()
        
        try:
            response = self.llm.invoke(prompt)
            content = response.content.strip()
            
            # Parse JSON
            import re
            cleaned = re.sub(r"```(?:json)?", "", content, flags=re.IGNORECASE).strip()
            match = re.search(r'\{.*\}', cleaned, re.DOTALL)
            
            if not match:
                print(f"[Stage1] Fact extraction failed: no JSON found")
                return {}
            
            analysis = json.loads(match.group(0))
            
            # Ensure actions is always a list
            if "actions" in analysis and not isinstance(analysis["actions"], list):
                analysis["actions"] = [str(analysis["actions"])]
            
            return analysis
            
        except Exception as e:
            print(f"[Stage1] Fact extraction failed: {e}")
            return {}
    
    def _call_llm_for_chapters(self, case_analysis: Dict[str, Any], penalty_block: str) -> str:
        """
        PHASE 2: LLM reasons DIRECTLY from structured facts to IPC chapters.
        
        NO intermediate labels - reasons from raw facts + explicit_elements.
        """
        actors = case_analysis.get("actors", "Unknown")
        actions = case_analysis.get("actions", [])
        outcome = case_analysis.get("outcome", "Unknown")
        context = case_analysis.get("context", "Unknown")
        explicit_elements = case_analysis.get("explicit_elements", {})
        
        # Format explicit elements
        elements_lines = []
        for key, value in explicit_elements.items():
            elements_lines.append(f"  - {key}: {value}")
        elements_str = "\n".join(elements_lines) if elements_lines else "  (none extracted)"
        
        # Format actions list
        if isinstance(actions, list):
            actions_str = "\n".join(f"  - {action}" for action in actions) if actions else "  (none extracted)"
        else:
            actions_str = f"  - {actions}"
        
        prompt = textwrap.dedent(f"""
        You are selecting IPC chapters based on case facts.
        
        CASE FACTS (structured extraction):
        
        Actors: {actors}
        
        Actions:
{actions_str}
        
        Outcome: {outcome}
        
        Context: {context}
        
        Explicit Elements (from facts):
{elements_str}
        
        ════════════════════════════════════════════════════════════════════
        AVAILABLE IPC CHAPTERS (your ONLY valid options):
        ════════════════════════════════════════════════════════════════════
        {self.chapter_list_str}
        
        TASK:
        Select at most {MAX_CHAPTERS} chapter NAMES from the list above that match the case facts.
        
        REASONING RULES (based on explicit_elements):
        
        1. IF physical_harm=true OR death_occurred=true:
           → MUST include "OF OFFENCES AFFECTING THE HUMAN BODY" (Chapter XVI)
        
        2. IF sexual_nature=true:
           → MUST include "OF OFFENCES AFFECTING THE HUMAN BODY" (Chapter XVI)
           (Sexual offences are in this chapter)
        
        3. IF marriage_relationship=true:
           → MUST include "OF CRUELTY BY HUSBAND OR RELATIVES OF HUSBAND" (Chapter XXA)
        
        4. IF property_involved=true:
           → MUST include "OF OFFENCES AGAINST PROPERTY" (Chapter XVII)
        
        5. IF threat_or_intimidation=true AND physical_harm=false:
           → MAY include "OR CRIMINAL INTIMIDATION, INSULT AND ANNOYANCE" (Chapter XXII)
           NOTE: Chapter name starts with OR not OF!
           → But if actual assault occurred, Chapter XVI is primary
        
        6. DO NOT select chapters based on vague associations:
           - Don't select marriage chapters unless marriage_relationship=true
           - Don't select property chapters unless property_involved=true
           - Don't select election chapters unless context mentions elections
        
        CRITICAL: Use EXACT chapter names from the list above.
        Common mistake: "OF CRIMINAL INTIMIDATION..." is WRONG
        Correct name: "OR CRIMINAL INTIMIDATION, INSULT AND ANNOYANCE"
        
        {penalty_block}
        
        Return ONLY a JSON array of chapter NAMES exactly as shown above.
        Example: ["OF OFFENCES AFFECTING THE HUMAN BODY", "OF CRUELTY BY HUSBAND OR RELATIVES OF HUSBAND"]
        
        NO explanations. NO chapter numbers. ONLY the exact chapter names from the list.
        """).strip()
        
        try:
            response = self.llm.invoke(prompt)
            return response.content.strip()
        except Exception as e:
            print(f"[Stage1] LLM call failed: {e}")
            return "[]"
    
    def _verify_chapter_selection(
        self, 
        raw_response: str, 
        case_analysis: Dict[str, Any],
        attempt: int
    ) -> Tuple[bool, List[str], List[str], AgentPerception]:
        """
        PHASE 3: Agent verifies that LLM's chapter selection makes sense
        given the case facts and Agent's reasoning.
        
        Returns:
            (success, chapter_nums, chapter_names, perception)
        """
        step = f"Stage1_attempt{attempt}"
        
        # Parse JSON
        parsed = self._parse_json_array(raw_response)
        
        if not parsed:
            return False, [], [], AgentPerception(
                step=step,
                observation=f"LLM returned unparseable output: {raw_response[:100]}",
                reasoning="Cannot parse JSON array from LLM response - format violation",
                decision=AgentDecision.PENALISE,
                penalty_message=(
                    "PENALTY: Your response was not valid JSON.\n"
                    "Return ONLY a JSON array of chapter NAME strings from the provided list.\n"
                    "Example: [\"OF OFFENCES RELATING TO MARRIAGE\", \"OF OFFENCES AFFECTING THE HUMAN BODY\"]\n"
                    "No preamble, no explanation, no markdown."
                )
            )
        
        # Verify all chapter names exist in the provided list
        valid_names = []
        invalid_names = []
        
        for name in parsed:
            name_str = str(name).strip()
            if name_str in self.chapter_name_to_num:
                valid_names.append(name_str)
            else:
                invalid_names.append(name_str)
        
        if invalid_names:
            valid_list = list(self.chapter_name_to_num.keys())
            return False, [], [], AgentPerception(
                step=step,
                observation=f"LLM returned: {parsed}. Invalid names: {invalid_names}",
                reasoning=(
                    f"Chapter names {invalid_names} do NOT exist in the provided chapter list. "
                    f"LLM is inventing or misremembering chapter names."
                ),
                decision=AgentDecision.PENALISE,
                penalty_message=(
                    f"PENALTY: You returned chapter names that were NOT in the provided list: {invalid_names}\n\n"
                    f"You MUST select ONLY from the exact chapter names I provided.\n"
                    f"Valid chapter names are:\n{chr(10).join('  - ' + name for name in sorted(valid_list))}\n\n"
                    f"Do NOT invent, modify, or guess chapter names. Copy them exactly as shown."
                )
            )
        
        if not valid_names:
            return False, [], [], AgentPerception(
                step=step,
                observation="LLM returned empty or all-invalid chapter list",
                reasoning="No valid chapters returned. Query must map to at least one chapter.",
                decision=AgentDecision.PENALISE,
                penalty_message=(
                    "PENALTY: You returned no valid chapters.\n"
                    "Every criminal query must map to at least one IPC chapter.\n"
                    "Analyze the query carefully and select relevant chapters from the provided list."
                )
            )
        
        # CRITICAL: Verify semantic relevance using Agent's reasoning
        semantic_issue = self._agent_verify_relevance(valid_names, case_analysis)
        
        if semantic_issue:
            return False, [], [], AgentPerception(
                step=step,
                observation=f"LLM returned valid chapters: {valid_names}",
                reasoning=semantic_issue,
                decision=AgentDecision.PENALISE,
                penalty_message=(
                    f"PENALTY: {semantic_issue}\n\n"
                    f"AGENT'S REASONING ABOUT THIS CASE:\n"
                    f"- Actors: {case_analysis.get('actors', 'Unknown')}\n"
                    f"- Actions: {case_analysis.get('actions', 'Unknown')}\n"
                    f"- Outcome: {case_analysis.get('outcome', 'Unknown')}\n"
                    f"- Offence Nature: {case_analysis.get('offence_nature', 'Unknown')}\n"
                    f"- Plausible Categories: {', '.join(case_analysis.get('plausible_categories', []))}\n\n"
                    f"Select chapters that match the ACTUAL case facts and offence nature.\n"
                    f"Do NOT select chapters for events that did not occur."
                )
            )
        
        # Map names to numbers
        chapter_nums = [self.chapter_name_to_num[name] for name in valid_names]
        
        # SUCCESS - REWARD
        return True, chapter_nums, valid_names, AgentPerception(
            step=step,
            observation=f"LLM returned valid chapters: {list(zip(chapter_nums, valid_names))}",
            reasoning=(
                f"All {len(valid_names)} chapter names exist in provided list. "
                f"Semantic relevance verified against Agent's reasoning: "
                f"Offence nature is {case_analysis.get('offence_nature', 'Unknown')}, "
                f"outcome is {case_analysis.get('outcome', 'Unknown')}. "
                f"Selected chapters {valid_names} match the actual case facts. Rewarding."
            ),
            decision=AgentDecision.REWARD,
            metadata={"chapters": list(zip(chapter_nums, valid_names))}
        )
    
    def _agent_verify_relevance(
        self, 
        chapter_names: List[str], 
        case_analysis: Dict[str, Any]
    ) -> str:
        """
        PHASE 4: Agent verifies using explicit_elements (strict fact-based checks).
        
        Returns: Error message if irrelevant, empty string if OK
        """
        explicit_elements = case_analysis.get('explicit_elements', {})
        outcome = case_analysis.get('outcome', '')
        actors = case_analysis.get('actors', '')
        actions = case_analysis.get('actions', [])
        
        # ═════════════════════════════════════════════════════════════════
        # POSITIVE REQUIREMENT: Sexual nature → MUST have Human Body chapter
        # ═════════════════════════════════════════════════════════════════
        if explicit_elements.get("sexual_nature"):
            human_body_chapter = "OF OFFENCES AFFECTING THE HUMAN BODY"
            if human_body_chapter not in chapter_names:
                return (
                    f"MISSING REQUIRED CHAPTER: '{human_body_chapter}'\n"
                    f"Reason: explicit_elements shows sexual_nature=true\n"
                    f"Sexual offences MUST use Chapter XVI (Human Body)."
                )
        
        # ═════════════════════════════════════════════════════════════════
        # POSITIVE REQUIREMENT: Physical harm → MUST have Human Body chapter
        # ═════════════════════════════════════════════════════════════════
        if explicit_elements.get("physical_harm"):
            human_body_chapter = "OF OFFENCES AFFECTING THE HUMAN BODY"
            if human_body_chapter not in chapter_names:
                return (
                    f"MISSING REQUIRED CHAPTER: '{human_body_chapter}'\n"
                    f"Reason: explicit_elements shows physical_harm=true\n"
                    f"Physical violence MUST use Chapter XVI."
                )
        
        # ═════════════════════════════════════════════════════════════════
        # NEGATIVE CHECK: Marriage chapters require marriage context
        # ═════════════════════════════════════════════════════════════════
        matrimonial_chapters = [
            "OF OFFENCES RELATING TO MARRIAGE",
            "OF CRUELTY BY HUSBAND OR RELATIVES OF HUSBAND"
        ]
        
        matrimonial_selected = [ch for ch in chapter_names if ch in matrimonial_chapters]
        
        if matrimonial_selected and not explicit_elements.get("marriage_relationship"):
            # Double-check with text markers
            matrimonial_markers = [
                "husband", "wife", "spouse", "marriage", "matrimonial", 
                "dowry", "married", "in-laws", "domestic"
            ]
            
            actors_str = str(actors).lower()
            actions_str = " ".join(actions) if isinstance(actions, list) else str(actions).lower()
            
            has_marriage_context = any(
                marker in actors_str or marker in actions_str 
                for marker in matrimonial_markers
            )
            
            if not has_marriage_context:
                return (
                    f"INVALID CHAPTERS: {matrimonial_selected}\n"
                    f"Reason: marriage_relationship=false and no marriage context\n"
                    f"Actors: {actors}\n"
                    f"These chapters require matrimonial relationship."
                )
        
        # ═════════════════════════════════════════════════════════════════
        # NEGATIVE CHECK: Property chapter requires property context
        # ═════════════════════════════════════════════════════════════════
        property_chapter = "OF OFFENCES AGAINST PROPERTY"
        
        if property_chapter in chapter_names and not explicit_elements.get("property_involved"):
            property_markers = [
                "theft", "steal", "stole", "rob", "cheat", "fraud", "money",
                "property", "trespass", "investment", "breach of trust", "financial"
            ]
            
            actions_str = " ".join(actions) if isinstance(actions, list) else str(actions).lower()
            outcome_str = str(outcome).lower()
            
            has_property_context = any(
                marker in actions_str or marker in outcome_str
                for marker in property_markers
            )
            
            if not has_property_context:
                return (
                    f"INVALID CHAPTER: '{property_chapter}'\n"
                    f"Reason: property_involved=false\n"
                    f"Actions: {actions}\n"
                    f"This chapter requires property crime elements."
                )
        
        # All checks passed
        return ""
                return (
                    f"Chapter '{property_chapter}' requires property crime context.\n"
                    f"Offence nature is: {offence_nature}\n"
                    f"Actions are: {actions}\n"
                    f"No property crime elements present. This chapter is IRRELEVANT."
                )
        
        # Rule 4: Check for completely irrelevant chapters
        # These patterns detect common hallucination cases
        irrelevant_patterns = {
            "OF ABETMENT": ["abet", "instigat", "conspir"],
            "OF OFFENCES AGAINST THE STATE": ["war", "sedition", "government"],
            "OF ELECTIONS": ["election", "vote", "ballot"],
            "OF FALSE EVIDENCE": ["evidence", "perjury", "court", "testimony"],
            "OF OFFENCES RELATING TO COIN": ["coin", "counterfeit currency"],
        }
        
        for chapter, required_keywords in irrelevant_patterns.items():
            if chapter in chapter_names:
                # Handle actions as list or string
                actions_str = " ".join(actions) if isinstance(actions, list) else str(actions)
                actors_str = str(actors)
                outcome_str = str(outcome)
                
                full_context = f"{actors_str} {actions_str} {outcome_str}".lower()
                has_context = any(kw in full_context for kw in required_keywords)
                
                if not has_context:
                    return (
                        f"Chapter '{chapter}' is IRRELEVANT.\n"
                        f"This chapter requires context about: {', '.join(required_keywords)}\n"
                        f"Case facts: {actors}, {actions}, {outcome}\n"
                        f"No such context found."
                    )
        
        # All checks passed
        return ""
    
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
