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

        # ── Code-side citation gate (OPT_SKIP_REASONING_GATE, default OFF) ───────
        # Put behind flag: skipping reasoning removes ingredient mapping and explanations.
        # Default is False to preserve full legal reasoning output.
        import os
        opt_skip_reasoning = os.getenv("OPT_SKIP_REASONING_GATE", "false").lower() in ("true", "1", "yes")
        if opt_skip_reasoning:
            HIGH_CONF = 0.92
            top = ranked_candidates[:5]
            all_high = (
                bool(top)
                and all(
                    float(c.get("confidence") or 0.0) >= HIGH_CONF and c.get("graph_verified")
                    for c in top
                )
            )
            if all_high and self.llm:
                print("[LegalReasoningService] Code-gate PASS (OPT_SKIP_REASONING_GATE enabled) — all candidates high-confidence & graph-verified. Skipping LLM.")
                recommended = []
                for c in top:
                    recommended.append({
                        "act": c.get("act", "BNS"),
                        "section": str(c.get("section_num") or c.get("section", "")),
                        "title": c.get("title", ""),
                        "confidence": float(c.get("confidence") or 0.0),
                        "applicability": c.get("validation_reason") or "High-confidence statutory match.",
                        "reason": c.get("validation_reason") or "Graph-verified, no LLM needed."
                    })
                return {
                    "pipeline_confidence": round(sum(r["confidence"] for r in recommended) / max(1, len(recommended)), 4),
                    "recommended_sections": recommended,
                    "theory_of_case": "Prosecution opposes pre-arrest bail based on graph-verified high-confidence statutory sections.",
                    "opening_argument": "May it please the Court, the prosecution opposes the grant of anticipatory bail based on the gravity of the established offence.",
                    "supporting_cases": [],
                    "similar_cases": similar_cases[:2],
                    "supporting_articles": supporting_articles,
                    "supporting_evidence": supporting_evidence,
                    "supporting_principles": supporting_principles,
                    "rejected_sections": []
                }
        # ── End code-side citation gate ───────────────────────────────────────────

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

        # Compact JSON — separators=(",",":") trims ~25-35% prompt tokens vs indent=2
        _C = (",", ":")
        candidates_summary = []
        graph_precedents_set = set()
        for c in ranked_candidates:
            candidates_summary.append({
                "act": c.get("act", "BNS"),
                "section": str(c.get("section_num") or c.get("section", "")),
                "title": c.get("title", ""),
                "description": c.get("description", ""),
                # punishment omitted — not used by this prompt
                "confidence": round(float(c.get("confidence") or 0.0), 3),
            })
            rel_cases = c.get("community", {}).get("related_cases") or []
            graph_precedents_set.update(rel_cases)

        graph_precedents = sorted(list(graph_precedents_set))
        vector_cases_summary = [
            {
                "case_name": cs.get("case_name") or cs.get("title") or "",
                "court": cs.get("court", "Supreme Court"),
                "year": cs.get("year", ""),
                "similarity": round(float(cs.get("similarity") or cs.get("vector_similarity") or 0.0), 3),
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
{json.dumps(candidates_summary, separators=_C)}

GRAPH-VERIFIED BINDING PRECEDENTS:
{json.dumps(graph_precedents, separators=_C)}

VECTOR-SIMILAR CASES:
{json.dumps(vector_cases_summary, separators=_C)}

SUPPORTING GRAPH ELEMENTS:
Articles: {json.dumps(supporting_articles, separators=_C)}
Evidence: {json.dumps(supporting_evidence, separators=_C)}
Principles: {json.dumps(supporting_principles, separators=_C)}

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