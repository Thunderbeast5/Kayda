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
        self.llm = get_llm(temperature=0.0)

    def analyze_case(
        self,
        user_query: str,
        ranked_candidates: List[Dict[str, Any]],
        similar_cases: List[Dict[str, Any]] = None,
        supporting_graph: Dict[str, List[str]] = None
    ) -> Dict[str, Any]:
        """
        Analyzes the user's factual query against candidate legal sections, similar cases,
        supporting constitutional articles, evidence types, and legal principles.
        Returns a structured case_analysis object.
        """
        similar_cases = similar_cases or []
        supporting_graph = supporting_graph or {}

        supporting_articles = supporting_graph.get("articles") or []
        supporting_evidence = supporting_graph.get("evidence") or []
        supporting_principles = supporting_graph.get("principles") or []

        if not ranked_candidates and not similar_cases:
            return {
                "user_query": user_query,
                "recommended_sections": [],
                "similar_cases": [],
                "supporting_articles": supporting_articles,
                "supporting_evidence": supporting_evidence,
                "supporting_principles": supporting_principles,
                "rejected_sections": []
            }

        # Format candidates for LLM context
        candidates_summary = []
        for c in ranked_candidates:
            candidates_summary.append({
                "section": c.get("section", ""),
                "title": c.get("title", ""),
                "description": c.get("description", ""),
                "punishment": c.get("punishment", ""),
                "confidence": c.get("confidence", 0.0),
                "graph_verified": c.get("graph_verified", False)
            })

        # Format similar cases for LLM context
        cases_summary = []
        for cs in similar_cases:
            cases_summary.append({
                "case_name": cs.get("case_name") or cs.get("title") or "",
                "court": cs.get("court", "Supreme Court"),
                "year": cs.get("year", ""),
                "similarity": cs.get("similarity") or cs.get("vector_similarity", 0.0),
                "facts": cs.get("facts", "")[:300],
                "reasoning": cs.get("reasoning", "")[:300],
                "judgment_summary": cs.get("judgment_summary", "")[:300]
            })

        prompt = f"""
You are LegalReasoningEngine for Kayda AI, an expert legal reasoning system for Indian Criminal Law.

Your responsibility is to analyze the user's factual query against the retrieved candidate legal sections, supporting constitutional articles, evidence types, legal principles, and similar Supreme Court precedent cases.

USER QUERY:
"{user_query}"

CANDIDATE LEGAL SECTIONS (listed in descending order of retrieval confidence):
{json.dumps(candidates_summary, indent=2)}

SIMILAR SUPREME COURT CASES (PRECEDENTS):
{json.dumps(cases_summary, indent=2)}

SUPPORTING GRAPH ELEMENTS:
Articles: {json.dumps(supporting_articles)}
Evidence: {json.dumps(supporting_evidence)}
Principles: {json.dumps(supporting_principles)}

Evaluate each candidate section and similar case:
1. For each candidate section that has legal relevance to the facts, return it in "recommended_sections". Include:
   - "section": section code/name (e.g., "BNS 80", "BNS 84")
   - "title": section title
   - "confidence": float (e.g. 0.72)
   - "applicability": 1-sentence description of the legal role (e.g., "Primary offence: dowry death.", "Continuous dowry demands indicate cruelty.")
   - "reason": concise explanation of factual alignment
   - "supporting_facts": array of facts from query
   - "missing_evidence": array of missing evidence needed
   - "decision_reason": reason for recommendation
2. For each similar case, evaluate its precedent applicability and provide concise reasoning.

Return ONLY valid JSON matching the following exact schema:

{{
  "recommended_sections": [
    {{
      "section": "...",
      "title": "...",
      "confidence": 0.95,
      "applicability": "...",
      "reason": "...",
      "supporting_facts": ["..."],
      "missing_evidence": ["..."],
      "decision_reason": "..."
    }}
  ],
  "similar_cases": [
    {{
      "case_name": "...",
      "court": "...",
      "similarity": 0.94,
      "reasoning": "...",
      "judgment_summary": "..."
    }}
  ],
  "supporting_articles": {json.dumps(supporting_articles)},
  "supporting_evidence": {json.dumps(supporting_evidence)},
  "supporting_principles": {json.dumps(supporting_principles)},
  "rejected_sections": []
}}
"""

        try:
            response = self.llm.invoke(prompt)
            content = response.content.strip()

            cleaned = re.sub(r"^```(?:json)?|```$", "", content, flags=re.MULTILINE).strip()
            parsed = json.loads(cleaned)

            rec = parsed.get("recommended_sections") or []
            cases_out = parsed.get("similar_cases") or cases_summary
            arts_out = parsed.get("supporting_articles") or supporting_articles
            ev_out = parsed.get("supporting_evidence") or supporting_evidence
            prin_out = parsed.get("supporting_principles") or supporting_principles
            rej = parsed.get("rejected_sections") or []

            return {
                "user_query": user_query,
                "recommended_sections": rec,
                "similar_cases": cases_out,
                "supporting_articles": arts_out,
                "supporting_evidence": ev_out,
                "supporting_principles": prin_out,
                "rejected_sections": rej
            }

        except Exception as e:
            print(f"[LegalReasoningService] Error during LLM generation: {e}")
            return self._normalize_fallback(user_query, ranked_candidates, similar_cases, supporting_graph)

    def _normalize_fallback(
        self,
        user_query: str,
        ranked_candidates: List[Dict[str, Any]],
        similar_cases: List[Dict[str, Any]] = None,
        supporting_graph: Dict[str, List[str]] = None
    ) -> Dict[str, Any]:
        similar_cases = similar_cases or []
        supporting_graph = supporting_graph or {}

        recommended = []
        for c in ranked_candidates:
            recommended.append({
                "section": c.get("section", ""),
                "title": c.get("title", ""),
                "confidence": c.get("confidence", 0.0),
                "applicability": f"Statutory elements align with {c.get('title', '')}.",
                "graph_verified": c.get("graph_verified", False),
                "reason": f"Factual statements indicate possible elements of {c.get('title', '')}.",
                "supporting_facts": [user_query],
                "missing_evidence": [
                    "Medical examination records",
                    "Witness statements",
                    "Documentary proof"
                ],
                "ambiguities": [],
                "validation": {
                    "required_elements": [
                        {
                            "element": "Retrieved candidate",
                            "satisfied": True,
                            "evidence_or_reason": "Retrieved as a candidate by semantic search."
                        }
                    ],
                    "recommend_section": True
                },
                "decision_reason": "Recommended by default fallback.",
                "override_reason": ""
            })

        formatted_cases = []
        for cs in similar_cases:
            formatted_cases.append({
                "case_name": cs.get("case_name") or cs.get("title") or "Supreme Court Case",
                "court": cs.get("court", "Supreme Court of India"),
                "similarity": cs.get("similarity") or cs.get("vector_similarity", 0.85),
                "reasoning": cs.get("reasoning") or cs.get("facts") or "Semantically relevant precedent case.",
                "judgment_summary": cs.get("judgment_summary") or cs.get("reasoning") or ""
            })

        return {
            "user_query": user_query,
            "recommended_sections": recommended,
            "similar_cases": formatted_cases,
            "supporting_articles": supporting_graph.get("articles") or [],
            "supporting_evidence": supporting_graph.get("evidence") or [],
            "supporting_principles": supporting_graph.get("principles") or [],
            "rejected_sections": []
        }
