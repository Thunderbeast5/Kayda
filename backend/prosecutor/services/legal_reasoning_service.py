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
    
    Analyzes user case statements against retrieved & verified legal candidates,
    evaluating supporting facts, missing evidence, ambiguities, and legal alignment.
    Enforces dynamic prosecutorial priority and clean JSON parsing across all domain types.
    """

    def __init__(self):
        try:
            self.llm = get_llm(temperature=0.0)
        except Exception as e:
            print(f"[LegalReasoningService] LLM init info: {e}")
            self.llm = None

    def _extract_clean_json(self, raw_text: str) -> Dict[str, Any]:
        """Extracts and parses JSON safely, handling preambles, fences, or prose."""
        cleaned = raw_text.strip()
        
        if "```" in cleaned:
            cleaned = re.sub(r"```(?:json)?\n?(.*?)\n?```", r"\1", cleaned, flags=re.DOTALL).strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        raise ValueError(f"Could not extract valid JSON from LLM output. Snippet: {raw_text[:250]}...")

    def _apply_prosecutorial_reranking(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Dynamically prioritizes procedural bail opposition and substantive offence sections 
        without hardcoded biases toward specific act types.
        """
        procedural_bail = {"482", "438", "437", "439"}

        def calculate_priority(c: Dict[str, Any]) -> float:
            sec = str(c.get("section_num") or c.get("section") or "").strip()
            score = float(c.get("confidence", 0.70))
            
            # Procedural bail provisions maintain high structural weight
            if sec in procedural_bail:
                score += 0.15
            else:
                # Substantive offences maintain their intrinsic vector + ingredient score
                score += 0.10
            return score

        return sorted(candidates, key=calculate_priority, reverse=True)

    def analyze_case(
        self,
        user_query: str,
        ranked_candidates: List[Dict[str, Any]],
        similar_cases: List[Dict[str, Any]] = None,
        supporting_graph: Dict[str, List[str]] = None
    ) -> Dict[str, Any]:
        """
        Analyzes factual query against candidate sections and supporting graph elements.
        Returns a structured case_analysis object.
        """
        similar_cases = similar_cases or []
        supporting_graph = supporting_graph or {}

        supporting_articles = supporting_graph.get("articles") or []
        supporting_evidence = supporting_graph.get("evidence") or []
        supporting_principles = supporting_graph.get("principles") or []

        ranked_candidates = self._apply_prosecutorial_reranking(ranked_candidates)

        if not self.llm:
            recommended = []
            for c in ranked_candidates[:3]:
                recommended.append({
                    "act": c.get("act", "BNS"),
                    "section": str(c.get("section_num") or c.get("section", "")),
                    "title": c.get("title", ""),
                    "confidence": c.get("confidence", 0.70),
                    "applicability": "Primary substantive or procedural section identified.",
                    "reason": c.get("validation_reason", "Statutory alignment verified.")
                })
            return {
                "pipeline_confidence": round(sum(r["confidence"] for r in recommended)/max(1, len(recommended)), 4),
                "recommended_sections": recommended,
                "theory_of_case": "The prosecution opposes pre-arrest bail based on gravity of offence, custodial interrogation necessity, and witness protection requirements.",
                "opening_argument": "May it please the Court, the prosecution strongly opposes the grant of anticipatory bail in view of the prima facie statutory violations and investigation needs.",
                "supporting_cases": [],
                "similar_cases": similar_cases[:2],
                "supporting_articles": supporting_articles,
                "supporting_evidence": supporting_evidence,
                "supporting_principles": supporting_principles,
                "rejected_sections": []
            }

        candidates_summary = []
        graph_precedents_set = set()
        for c in ranked_candidates:
            candidates_summary.append({
                "act": c.get("act", "BNS"),
                "section": str(c.get("section_num") or c.get("section", "")),
                "title": c.get("title", ""),
                "description": c.get("description", ""),
                "confidence": c.get("confidence", 0.0),
            })
            rel_cases = c.get("community", {}).get("related_cases") or []
            graph_precedents_set.update(rel_cases)

        graph_precedents = sorted(list(graph_precedents_set))
        vector_cases_summary = [
            {
                "case_name": cs.get("case_name") or cs.get("title") or "",
                "court": cs.get("court", "Supreme Court"),
                "year": cs.get("year", ""),
                "similarity": cs.get("similarity") or cs.get("vector_similarity", 0.0),
                "facts": cs.get("facts", "")[:300]
            }
            for cs in similar_cases
        ]

        prompt = f"""
You are LegalReasoningEngine for Kayda AI, an expert legal system for Indian Criminal Law.

CRITICAL INSTRUCTION: You MUST return strictly pure JSON. Do not include preambles, natural language intros, or markdown blocks outside the JSON object.

USER QUERY:
"{user_query}"

CANDIDATE LEGAL SECTIONS (ordered by relevance):
{json.dumps(candidates_summary, indent=2)}

GRAPH-VERIFIED BINDING PRECEDENTS:
{json.dumps(graph_precedents, indent=2)}

VECTOR-SIMILAR CASES:
{json.dumps(vector_cases_summary, indent=2)}

SUPPORTING GRAPH ELEMENTS:
Articles: {json.dumps(supporting_articles)}
Evidence: {json.dumps(supporting_evidence)}
Principles: {json.dumps(supporting_principles)}

Evaluate the case facts and return JSON with this EXACT structure:
{{
  "recommended_sections": [
    {{
      "act": "IPC or BNS or POCSO or DPA or BNSS or CrPC",
      "section": "...",
      "title": "...",
      "confidence": 0.95,
      "applicability": "Specific legal application based on facts.",
      "reason": "Direct evidence or statutory rationale."
    }}
  ],
  "theory_of_case": "Summary of prosecution stance emphasizing offence gravity, evidence collection, and custodial necessity.",
  "opening_argument": "Spoken court opposition argument citing relevant sections and binding precedents.",
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
            
            parsed = self._extract_clean_json(text)
            rec = parsed.get("recommended_sections") or []
            conf = round(sum(r.get("confidence", 0.70) for r in rec)/max(1, len(rec)), 4) if rec else 0.70

            return {
                "pipeline_confidence": conf,
                "recommended_sections": rec,
                "theory_of_case": parsed.get("theory_of_case", ""),
                "opening_argument": parsed.get("opening_argument", ""),
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
                    "applicability": "Relevant provision identified from query context.",
                    "reason": c.get("validation_reason", "Statutory alignment verified.")
                })
            return {
                "pipeline_confidence": 0.70,
                "recommended_sections": recommended,
                "theory_of_case": "The prosecution opposes anticipatory bail in light of the allegation details and necessity for effective investigation.",
                "opening_argument": "May it please the Court, we oppose the grant of pre-arrest bail having regard to the nature of charges and necessity of custodial interrogation.",
                "similar_cases": similar_cases[:2],
                "supporting_articles": supporting_articles,
                "supporting_evidence": supporting_evidence,
                "supporting_principles": supporting_principles,
                "rejected_sections": []
            }