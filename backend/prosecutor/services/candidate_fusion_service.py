"""
Candidate Fusion Service

Merges candidates from LLM retrieval and Neo4j retrieval with weighted scoring.

Fusion Strategy:
----------------
1. Receive candidates from both LLM and Neo4j retrieval
2. Match equivalent sections (normalize IPC/BNS identifiers)
3. Compute final score:
   FinalScore = 0.35 × LLMScore + 0.65 × GraphScore

4. Remove sections with:
   - High LLM confidence BUT negligible graph support (likely hallucination)
   - Low scores from both sources (noise)

5. Return ranked, deduplicated candidate list

This makes Neo4j the primary authority while preserving LLM's ability
to surface edge cases the graph traversal might miss.
"""

from typing import Dict, Any, List, Set
import re


class CandidateFusionService:
    """
    Fuses LLM-retrieved and Neo4j-retrieved candidates with graph-dominant weighting.
    
    Implements:
    - Candidate normalization and matching
    - Weighted score combination (Graph > LLM)
    - Hallucination filtering (high LLM, no graph support)
    - Deduplication
    """
    
    # Weighting: Graph is primary authority
    WEIGHT_LLM = 0.35
    WEIGHT_GRAPH = 0.65
    
    # Thresholds - adjusted for sparse graph
    MIN_FINAL_SCORE = 0.20  # Lowered from 0.30 to accommodate sparse graph relationships
    MIN_GRAPH_SUPPORT = 0.15  # Lowered from 0.20 - minimum graph score for high-LLM sections
    
    def __init__(self):
        pass
    
    def fuse_candidates(
        self,
        llm_candidates: List[Dict[str, Any]],
        neo4j_candidates: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Main fusion method.
        
        Parameters
        ----------
        llm_candidates : list of dict
            From LLMIPCRetrievalService, each with:
            - section: str (e.g., "IPC_302")
            - relevance_score: float
            - act: str
            - section_num: str
        
        neo4j_candidates : list of dict
            From Neo4jRetrievalService, each with:
            - act: str
            - section: str (section number)
            - graph_score: float
            - evidence: dict
        
        Returns
        -------
        dict with:
            - fused_candidates: list of merged, scored, ranked candidates
            - fusion_stats: dict with counts and diagnostics
        """
        print(
            f"\n[CandidateFusionService] Fusing {len(llm_candidates)} LLM candidates "
            f"with {len(neo4j_candidates)} Neo4j candidates..."
        )
        
        # Normalize identifiers
        llm_normalized = self._normalize_llm_candidates(llm_candidates)
        neo4j_normalized = self._normalize_neo4j_candidates(neo4j_candidates)
        
        # Debug: Show what we're comparing
        print("[CandidateFusionService] LLM keys:", [c["key"] for c in llm_normalized[:5]])
        print("[CandidateFusionService] Neo4j keys:", [c["key"] for c in neo4j_normalized[:5]])
        
        # Build unified candidate map
        candidate_map: Dict[str, Dict[str, Any]] = {}
        
        # Add LLM candidates
        for cand in llm_normalized:
            key = cand["key"]
            candidate_map[key] = {
                "act": cand["act"],
                "section": cand["section"],
                "section_key": key,
                "llm_score": cand["llm_score"],
                "graph_score": 0.0,  # Will be updated if Neo4j has it
                "sources": ["llm"],
                "llm_data": cand,
                "neo4j_data": None,
            }
        
        # Merge Neo4j candidates
        for cand in neo4j_normalized:
            key = cand["key"]
            if key in candidate_map:
                # Already have LLM result - merge
                candidate_map[key]["graph_score"] = cand["graph_score"]
                candidate_map[key]["sources"].append("neo4j")
                candidate_map[key]["neo4j_data"] = cand
            else:
                # Neo4j only
                candidate_map[key] = {
                    "act": cand["act"],
                    "section": cand["section"],
                    "section_key": key,
                    "llm_score": 0.0,
                    "graph_score": cand["graph_score"],
                    "sources": ["neo4j"],
                    "llm_data": None,
                    "neo4j_data": cand,
                }
        
        # Compute final scores
        fused = self._compute_final_scores(list(candidate_map.values()))
        
        # Apply filters
        filtered = self._apply_filters(fused)
        
        # Sort by final score descending
        filtered.sort(key=lambda x: x["final_score"], reverse=True)
        
        # Generate stats
        stats = self._generate_stats(fused, filtered, llm_candidates, neo4j_candidates)
        
        print(
            f"[CandidateFusionService] Fusion complete: "
            f"{len(filtered)} candidates after filtering"
        )
        
        return {
            "fused_candidates": filtered,
            "fusion_stats": stats,
        }
    
    def _normalize_llm_candidates(
        self, candidates: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Normalize LLM candidate format.
        
        Converts "IPC_302" → ("IPC", "302", "IPC 302")
        """
        normalized = []
        
        for cand in candidates:
            # Extract act and section from various formats
            section_id = cand.get("section", "")
            
            # Pattern: "IPC_302" or "IPC 302"
            act = cand.get("act", "")
            section_num = cand.get("section_num", "")
            
            if not act and "_" in section_id:
                # Parse "IPC_302" format
                parts = section_id.split("_", 1)
                act = parts[0].upper()
                section_num = parts[1] if len(parts) > 1 else ""
            elif not section_num:
                # Fallback
                section_num = section_id.replace(f"{act}_", "").strip()
            
            if not act or not section_num:
                continue
            
            key = self._make_key(act, section_num)
            
            normalized.append({
                "key": key,
                "act": act,
                "section": section_num,
                "llm_score": float(cand.get("relevance_score", 0.7)),
                "original": cand,
            })
        
        return normalized
    
    def _normalize_neo4j_candidates(
        self, candidates: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Normalize Neo4j candidate format.
        
        Already in ("IPC", "302") format from Neo4j retrieval.
        """
        normalized = []
        
        for cand in candidates:
            act = cand.get("act", "").upper()
            section = cand.get("section", "").strip()
            
            if not act or not section:
                continue
            
            key = self._make_key(act, section)
            
            normalized.append({
                "key": key,
                "act": act,
                "section": section,
                "graph_score": float(cand.get("graph_score", 0.0)),
                "evidence": cand.get("evidence", {}),
                "original": cand,
            })
        
        return normalized
    
    def _make_key(self, act: str, section: str) -> str:
        """
        Create normalized key for section matching.
        
        Handles:
        - IPC/BNS variations
        - Section number normalization (498A vs 498-A vs 498_A)
        """
        act = act.upper().strip()
        section = section.upper().strip()
        
        # Normalize section number: remove hyphens, underscores, spaces
        section = re.sub(r"[-_\s]", "", section)
        
        key = f"{act}_{section}"
        return key
    
    def _compute_final_scores(
        self, candidates: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Compute weighted final score for each candidate.
        
        FinalScore = 0.35 × LLMScore + 0.65 × GraphScore
        """
        for cand in candidates:
            llm_score = cand.get("llm_score", 0.0)
            graph_score = cand.get("graph_score", 0.0)
            
            final_score = (
                self.WEIGHT_LLM * llm_score +
                self.WEIGHT_GRAPH * graph_score
            )
            
            cand["final_score"] = final_score
            cand["score_breakdown"] = {
                "llm_score": llm_score,
                "graph_score": graph_score,
                "llm_weight": self.WEIGHT_LLM,
                "graph_weight": self.WEIGHT_GRAPH,
                "final": final_score,
            }
        
        return candidates
    
    def _apply_filters(
        self, candidates: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Apply filtering rules:
        
        1. Remove sections with final_score < MIN_FINAL_SCORE
        2. Remove sections with high LLM score but negligible graph support
           (likely hallucinations or irrelevant matches)
        """
        filtered = []
        
        for cand in candidates:
            final_score = cand.get("final_score", 0.0)
            llm_score = cand.get("llm_score", 0.0)
            graph_score = cand.get("graph_score", 0.0)
            
            # Filter 1: Absolute minimum score
            if final_score < self.MIN_FINAL_SCORE:
                print(
                    f"[CandidateFusionService] Filter: {cand['section_key']} "
                    f"below minimum score ({final_score:.3f} < {self.MIN_FINAL_SCORE})"
                )
                continue
            
            # Filter 2: High LLM, low graph = potential hallucination
            if llm_score > 0.7 and graph_score < self.MIN_GRAPH_SUPPORT:
                print(
                    f"[CandidateFusionService] Filter: {cand['section_key']} "
                    f"high LLM ({llm_score:.3f}) but no graph support ({graph_score:.3f})"
                )
                continue
            
            filtered.append(cand)
        
        return filtered
    
    def _generate_stats(
        self,
        pre_filter: List[Dict[str, Any]],
        post_filter: List[Dict[str, Any]],
        llm_raw: List[Dict[str, Any]],
        neo4j_raw: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Generate fusion statistics for debugging."""
        
        # Count sources
        llm_only = sum(1 for c in pre_filter if c["sources"] == ["llm"])
        neo4j_only = sum(1 for c in pre_filter if c["sources"] == ["neo4j"])
        both = sum(1 for c in pre_filter if len(c["sources"]) == 2)
        
        filtered_count = len(pre_filter) - len(post_filter)
        
        return {
            "llm_input": len(llm_raw),
            "neo4j_input": len(neo4j_raw),
            "total_unique": len(pre_filter),
            "llm_only": llm_only,
            "neo4j_only": neo4j_only,
            "both_sources": both,
            "filtered_out": filtered_count,
            "final_count": len(post_filter),
        }
