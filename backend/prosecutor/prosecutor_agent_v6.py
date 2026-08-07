"""
Prosecutor Agent v6 - Multi-Stage Reasoning with Reinforcement Learning
========================================================================

Architecture:
- Agent perceives, reasons, decides (REWARD/PENALIZE)
- LLM executes function calls based on provided data
- 3 distinct stages with explicit RL loops

Stage 1: Chapter Identification (query-level, once)
Stage 2: Section Title Extraction (per sub-query)
Stage 3: Full Context Judgment (ingredient-level validation)
"""

import json
import sys
from pathlib import Path
from typing import Dict, Any, List

# Path setup
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Services
from prosecutor.services.agent_state import AgentState
from prosecutor.services.stage1_chapter_service import Stage1ChapterService
from prosecutor.services.stage2_section_service import Stage2SectionService
from prosecutor.services.stage3_judgment_service import Stage3JudgmentService

# Query decomposition
try:
    from prosecutor.services.query_expansion_service import QueryExpansionService
    from prosecutor.services.query_understanding_service import QueryUnderstandingService
except ImportError:
    from services.query_expansion_service import QueryExpansionService
    from services.query_understanding_service import QueryUnderstandingService


class ProsecutorAgentV6:
    """
    Prosecutor Agent with Multi-Stage Reasoning and RL Loops
    
    This agent opposes anticipatory bail by:
    1. Identifying relevant IPC chapters
    2. Extracting relevant sections from those chapters
    3. Validating sections with ingredient-level citation
    
    At each stage, the Agent verifies LLM output and provides
    reinforcement learning feedback (REWARD/PENALIZE).
    """
    
    def __init__(self, prosecutor_dir: Path = None):
        if prosecutor_dir is None:
            prosecutor_dir = Path(__file__).resolve().parent
        
        self.prosecutor_dir = prosecutor_dir
        
        # Load IPC data
        ipc_index_path = prosecutor_dir / "ipc_index.json"
        ipc_structured_path = prosecutor_dir / "ipc_structured.json"
        
        print(f"[ProsecutorAgent] Loading IPC data from {prosecutor_dir}")
        
        with open(ipc_index_path, "r", encoding="utf-8") as f:
            self.ipc_index = json.load(f)
        
        with open(ipc_structured_path, "r", encoding="utf-8") as f:
            self.ipc_structured = json.load(f)
        
        print(f"[ProsecutorAgent] Loaded {len(self.ipc_index)} index entries")
        print(f"[ProsecutorAgent] Loaded {len(self.ipc_structured)} structured sections")
        
        # Initialize stage services
        self.stage1_service = Stage1ChapterService(self.ipc_index)
        self.stage2_service = Stage2SectionService(self.ipc_index)
        self.stage3_service = Stage3JudgmentService(self.ipc_structured)
        
        # Query processing services
        self.query_understanding_service = QueryUnderstandingService()
        self.query_expansion_service = QueryExpansionService()
        
        print(f"[ProsecutorAgent] Initialization complete")
    
    def process_query(
        self,
        query: str,
        role: str = "prosecutor",
        top_k: int = 20
    ) -> Dict[str, Any]:
        """
        Main entry point for prosecutor agent.
        
        Args:
            query: Full case query/facts
            role: "prosecutor" (default) or "defense"
            top_k: Number of top sections to return
        
        Returns:
            Dict with retrieval_results in Pinecone-compatible format
        """
        print(f"\n{'='*90}")
        print(f"PROSECUTOR AGENT V6 - MULTI-STAGE REASONING")
        print(f"{'='*90}")
        print(f"Query: {query[:150]}...")
        print(f"Role: {role}")
        print(f"{'='*90}\n")
        
        # Extract complainant facts (strip defense narrative)
        complainant_facts = self._extract_complainant_facts(query)
        
        # Initialize agent state
        state = AgentState(
            raw_query=query,
            complainant_facts=complainant_facts
        )
        
        # Query understanding & decomposition
        print(f"[ProsecutorAgent] Query Understanding & Decomposition...")
        qu_result = self.query_understanding_service.analyze_query(query)
        expansion_result = self.query_expansion_service.expand_query(qu_result, query, role)
        sub_queries = expansion_result.get("sub_queries", [])
        
        # Filter to OFFENCE sub-queries only
        offence_sub_queries = [
            sq for sq in sub_queries 
            if sq.get("type") == "OFFENCE"
        ]
        
        if not offence_sub_queries:
            print("[ProsecutorAgent] No OFFENCE sub-queries found")
            return {"retrieval_results": []}
        
        print(f"[ProsecutorAgent] Processing {len(offence_sub_queries)} OFFENCE sub-queries")
        
        # ================================================================
        # STAGE 1: Chapter Identification (once for entire query)
        # ================================================================
        print(f"\n{'#'*80}")
        print(f"STAGE 1: CHAPTER IDENTIFICATION")
        print(f"{'#'*80}")
        
        success = self.stage1_service.identify_chapters(state)
        
        if not success:
            print("[ProsecutorAgent] Stage 1 FAILED - aborting pipeline")
            return {"retrieval_results": []}
        
        # ================================================================
        # STAGE 2: Section Title Extraction (per sub-query)
        # ================================================================
        print(f"\n{'#'*80}")
        print(f"STAGE 2: SECTION TITLE EXTRACTION")
        print(f"{'#'*80}")
        
        success = self.stage2_service.extract_sections(state, offence_sub_queries)
        
        if not success:
            print("[ProsecutorAgent] Stage 2 FAILED - aborting pipeline")
            return {"retrieval_results": []}
        
        # ================================================================
        # STAGE 3: Full Context Judgment (ingredient validation)
        # ================================================================
        print(f"\n{'#'*80}")
        print(f"STAGE 3: FULL CONTEXT JUDGMENT")
        print(f"{'#'*80}")
        
        success = self.stage3_service.judge_sections(state)
        
        if not success:
            print("[ProsecutorAgent] Stage 3 FAILED - no sections confirmed")
            return {"retrieval_results": []}
        
        # ================================================================
        # BUILD OUTPUT
        # ================================================================
        print(f"\n{'='*90}")
        print(f"PIPELINE COMPLETE")
        print(f"{'='*90}")
        print(f"Confirmed sections: {len(state.confirmed_sections)}")
        print(f"Sections: {list(state.confirmed_sections.keys())}")
        
        # Print perception log
        print(state.get_perception_summary())
        
        # Build Pinecone-compatible output
        retrieval_results = self._build_retrieval_results(
            state=state,
            sub_queries=offence_sub_queries,
            top_k=top_k
        )
        
        return {"retrieval_results": retrieval_results}
    
    def _build_retrieval_results(
        self,
        state: AgentState,
        sub_queries: List[Dict[str, Any]],
        top_k: int
    ) -> List[Dict[str, Any]]:
        """
        Build retrieval_results in Pinecone-compatible format.
        """
        results = []
        
        # Per sub-query results
        for sq in sub_queries:
            sq_text = sq.get("query", "")
            matches = []
            
            for sec_id, cand in state.confirmed_sections.items():
                structured = cand.get("structured", {})
                
                # Parse act and section number from ID (e.g., "IPC_498A" → "IPC", "498A")
                parts = sec_id.split("_", 1)
                act = parts[0] if len(parts) == 2 else "IPC"
                section_num = parts[1] if len(parts) == 2 else sec_id
                
                matches.append({
                    "id": sec_id,
                    "score": cand.get("confidence", 0.85),
                    "metadata": {
                        "section": section_num,
                        "section_num": section_num,
                        "act": act,
                        "title": structured.get("section_title", ""),
                        "description": structured.get("text", ""),
                        "full_text": structured.get("text", ""),
                        "explanation": structured.get("explanation", []),
                        "illustration": structured.get("illustration", []),
                        "exception": structured.get("exception", []),
                        "chapter": structured.get("chapter", ""),
                        "chapter_title": structured.get("chapter_title", ""),
                        "is_offense": True,
                        "reasoning": cand.get("reasoning", ""),
                        "ingredient": cand.get("ingredient", ""),
                    }
                })
            
            results.append({
                "query": sq_text,
                "sub_query_type": "OFFENCE",
                "matches": sorted(matches, key=lambda m: m["score"], reverse=True)[:top_k]
            })
        
        # Merged result across all sub-queries
        all_matches = []
        seen_ids = set()
        
        for sec_id, cand in state.confirmed_sections.items():
            if sec_id in seen_ids:
                continue
            seen_ids.add(sec_id)
            
            structured = cand.get("structured", {})
            parts = sec_id.split("_", 1)
            act = parts[0] if len(parts) == 2 else "IPC"
            section_num = parts[1] if len(parts) == 2 else sec_id
            
            all_matches.append({
                "id": sec_id,
                "score": cand.get("confidence", 0.85),
                "metadata": {
                    "section": section_num,
                    "section_num": section_num,
                    "act": act,
                    "title": structured.get("section_title", ""),
                    "description": structured.get("text", ""),
                    "full_text": structured.get("text", ""),
                    "explanation": structured.get("explanation", []),
                    "illustration": structured.get("illustration", []),
                    "exception": structured.get("exception", []),
                    "chapter": structured.get("chapter", ""),
                    "chapter_title": structured.get("chapter_title", ""),
                    "is_offense": True,
                    "reasoning": cand.get("reasoning", ""),
                    "ingredient": cand.get("ingredient", ""),
                }
            })
        
        all_matches = sorted(all_matches, key=lambda m: m["score"], reverse=True)[:top_k]
        
        results.append({
            "query": "[ALL SUB-QUERIES MERGED]",
            "sub_query_type": "OFFENCE",
            "matches": all_matches
        })
        
        return results
    
    def _extract_complainant_facts(self, query: str) -> str:
        """
        Extract complainant/prosecution facts, strip defense narrative.
        """
        cutoff_phrases = [
            "the applicant denies", "applicant denies", "applicant submits",
            "applicant states", "applicant claims", "applicant contends",
            "he denies", "she denies", "accused denies", "accused submits",
        ]
        
        query_lower = query.lower()
        cut_at = len(query)
        
        for phrase in cutoff_phrases:
            idx = query_lower.find(phrase)
            if 0 < idx < cut_at:
                cut_at = idx
        
        trimmed = query[:cut_at].strip()
        
        if cut_at < len(query):
            print(f"[ProsecutorAgent] Stripped defense narrative ({len(query) - cut_at} chars)")
        
        return trimmed if trimmed else query


# ================================================================
# TEST FUNCTION
# ================================================================

def test_prosecutor_agent():
    """Test the prosecutor agent with a sample query."""
    
    test_query = """
    A man threatened his wife for dowry. He demanded Rs. 5 lakhs and gold jewelry.
    When she refused, he beat her and threatened to kill her. He also threatened
    her parents. The wife filed a complaint with the police.
    """
    
    print("="*90)
    print("TESTING PROSECUTOR AGENT V6")
    print("="*90)
    
    agent = ProsecutorAgentV6()
    result = agent.process_query(test_query)
    
    print("\n" + "="*90)
    print("FINAL RESULTS")
    print("="*90)
    
    for res in result.get("retrieval_results", []):
        print(f"\nQuery: {res['query']}")
        print(f"Matches: {len(res['matches'])}")
        for match in res['matches'][:5]:
            print(f"  - {match['id']}: {match['metadata']['title'][:80]}")
            print(f"    Ingredient: {match['metadata'].get('ingredient', '')[:80]}")
            print(f"    Reasoning: {match['metadata'].get('reasoning', '')[:80]}")


if __name__ == "__main__":
    test_prosecutor_agent()
