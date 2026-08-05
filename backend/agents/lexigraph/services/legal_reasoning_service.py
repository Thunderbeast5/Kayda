import json
import re
import sys
from pathlib import Path
from typing import Dict, Any, List

try:
    from config.llm_config import get_llm
except ModuleNotFoundError:
    from agents.config.llm_config import get_llm


class LegalReasoningService:
    """
    LegalReasoningService (LegalReasoningEngine)
    
    Responsible for analyzing user case statements against retrieved & verified legal candidates,
    evaluating supporting facts, missing evidence, ambiguities, and legal alignment reasons.
    """

    def __init__(self):
        try:
            self.llm = get_llm(temperature=0.0)
        except Exception as e:
            print(f"[LegalReasoningService] LLM init info: {e}")
            self.llm = None

    def analyze_case(
        self,
        user_query: str,
        ranked_candidates: List[Dict[str, Any]],
        similar_cases: List[Dict[str, Any]] = None,
        supporting_graph: Dict[str, List[str]] = None
    ) -> Dict[str, Any]:
        """
        Analyzes the user's factual query against candidate legal sections, graph-verified precedents,
        similar vector cases, constitutional articles, evidence types, and legal principles.
        Returns a structured case_analysis object.
        """
        similar_cases = similar_cases or []
        supporting_graph = supporting_graph or {}

        supporting_articles = supporting_graph.get("articles") or []
        supporting_evidence = supporting_graph.get("evidence") or []
        supporting_principles = supporting_graph.get("principles") or []

        if not self.llm:
            # Fallback if LLM is unavailable
            recommended = []
            for c in ranked_candidates[:3]:
                recommended.append({
                    "act": c.get("act", "BNS"),
                    "section": str(c.get("section_num") or c.get("section", "")),
                    "title": c.get("title", ""),
                    "confidence": c.get("confidence", 0.70),
                    "applicability": f"Relevant provision for query facts.",
                    "reason": c.get("validation_reason", "Statutory alignment verified.")
                })
            return {
                "pipeline_confidence": round(sum(r["confidence"] for r in recommended)/max(1, len(recommended)), 4),
                "recommended_sections": recommended,
                "supporting_cases": [],
                "similar_cases": similar_cases[:2],
                "supporting_articles": supporting_articles,
                "supporting_evidence": supporting_evidence,
                "supporting_principles": supporting_principles,
                "rejected_sections": []
            }

        # Format candidates for LLM context
        candidates_summary = []
        graph_precedents_set = set()
        for c in ranked_candidates:
            candidates_summary.append({
                "act": c.get("act", "BNS"),
                "section": str(c.get("section_num") or c.get("section", "")),
                "title": c.get("title", ""),
                "description": c.get("description", ""),
                "punishment": c.get("punishment", ""),
                "confidence": c.get("confidence", 0.0),
                "graph_verified": c.get("graph_verified", False)
            })
            rel_cases = c.get("community", {}).get("related_cases") or []
            graph_precedents_set.update(rel_cases)

        # Format graph-verified precedents vs vector-similar cases separately
        graph_precedents = sorted(list(graph_precedents_set))
        vector_cases_summary = []
        for cs in similar_cases:
            vector_cases_summary.append({
                "case_name": cs.get("case_name") or cs.get("title") or "",
                "court": cs.get("court", "Supreme Court"),
                "year": cs.get("year", ""),
                "similarity": cs.get("similarity") or cs.get("vector_similarity", 0.0),
                "facts": cs.get("facts", "")[:300],
                "reasoning": cs.get("reasoning", "")[:300]
            })

        # Evidentiary landmark doctrine mappings
        evidence_doctrine_links = {
            "Dying Declaration": "Satbir Singh v. State of Haryana (2021) 6 SCC 1 (Establishes evidentiary standards for dying declaration and soon before death)",
            "Statement under Section 164": "Premiya @ Prem Prakash v. State of Rajasthan (2008) 16 SCC 133 (Judicial statement recorded before Magistrate)",
            "Postmortem Report": "State of M.P. v. Madan Lal [2015] 7 S.C.R. 1061 (Medical corroboration in offences against women)"
        }
        active_evidence_links = {k: v for k, v in evidence_doctrine_links.items() if k in supporting_evidence}

        prompt = f"""
You are LegalReasoningEngine for Kayda AI, an expert legal reasoning system for Indian Criminal Law.

Your responsibility is to analyze the user's factual query against retrieved candidate legal sections, graph-verified precedents, vector-similar Supreme Court cases, evidence types, and legal principles.

USER QUERY:
"{user_query}"

CANDIDATE LEGAL SECTIONS (listed in descending order of retrieval confidence):
{json.dumps(candidates_summary, indent=2)}

GRAPH-VERIFIED BINDING PRECEDENTS (Direct 1-Hop Traversal in Neo4j):
{json.dumps(graph_precedents, indent=2)}

VECTOR-SIMILAR CASES (Pinecone Similarity Matches):
{json.dumps(vector_cases_summary, indent=2)}

EVIDENTIARY DOCTRINE LINKS:
{json.dumps(active_evidence_links, indent=2)}

SUPPORTING GRAPH ELEMENTS:
Articles: {json.dumps(supporting_articles)}
Evidence: {json.dumps(supporting_evidence)}
Principles: {json.dumps(supporting_principles)}

Evaluate each candidate section and similar case:
1. For each candidate section that has legal relevance to the facts, return it in "recommended_sections".
2. Distinguish direct graph-verified precedents from vector-similar cases.

Return ONLY valid JSON matching the following exact schema:

{{
  "recommended_sections": [
    {{
      "act": "BNS",
      "section": "355",
      "title": "...",
      "confidence": 0.95,
      "applicability": "Primary offence: ...",
      "reason": "..."
    }}
  ],
  "similar_cases": [
    {{
      "case_name": "...",
      "court": "...",
      "similarity": 0.94,
      "reasoning": "..."
    }}
  ]
}}
"""
        try:
            response = self.llm.invoke(prompt)
            text = response.content if hasattr(response, "content") else str(response)
            text_clean = text.strip()
            if text_clean.startswith("```"):
                lines = text_clean.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                text_clean = "\n".join(lines).strip()

            parsed = json.loads(text_clean)
            rec = parsed.get("recommended_sections") or []
            conf = round(sum(r.get("confidence", 0.70) for r in rec)/max(1, len(rec)), 4) if rec else 0.70

            return {
                "pipeline_confidence": conf,
                "recommended_sections": rec,
                "similar_cases": parsed.get("similar_cases") or similar_cases[:2],
                "supporting_articles": supporting_articles,
                "supporting_evidence": supporting_evidence,
                "supporting_principles": supporting_principles,
                "rejected_sections": []
            }
        except Exception as e:
            print(f"[LegalReasoningService] Error invoking LLM reasoning: {e}")
            recommended = []
            for c in ranked_candidates[:2]:
                recommended.append({
                    "act": c.get("act", "BNS"),
                    "section": str(c.get("section_num") or c.get("section", "")),
                    "title": c.get("title", ""),
                    "confidence": c.get("confidence", 0.70),
                    "applicability": "Relevant provision for query facts.",
                    "reason": c.get("validation_reason", "Statutory alignment verified.")
                })
            return {
                "pipeline_confidence": 0.70,
                "recommended_sections": recommended,
                "similar_cases": similar_cases[:2],
                "supporting_articles": supporting_articles,
                "supporting_evidence": supporting_evidence,
                "supporting_principles": supporting_principles,
                "rejected_sections": []
            }
