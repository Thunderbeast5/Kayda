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

    def analyze_case(self, user_query: str, ranked_candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyzes the user's factual query against the ranked candidate legal sections.
        Returns a structured case_analysis object.
        """
        if not ranked_candidates:
            return {
                "user_query": user_query,
                "recommended_sections": [],
                "rejected_sections": []
            }

        # Format candidates for LLM context (including description and punishment)
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

        # Debug: print exact retrieved context before sending to the LLM
        print("\n[LegalReasoningService] Retrieved context (pre-LLM debug):", flush=True)
        for doc in ranked_candidates:
            print("=" * 80, flush=True)
            print(f"{doc.get('section', '')}: {doc.get('title', '')}", flush=True)
            print({k: v for k, v in doc.items() if k not in ("section", "title")}, flush=True)

        prompt = f"""
You are LegalReasoningEngine for Kayda AI, an expert legal reasoning system for Indian Criminal Law.

Your ONLY responsibility is to analyze the user's factual query against the retrieved candidate legal sections and produce a structured case analysis.

For each candidate legal section provided, evaluate:
1. "reason": A concise, clear explanation of how the facts in the user query align with the legal elements of this section.
2. "supporting_facts": List of specific factual statements from the user query supporting this section.
3. "missing_evidence": List of essential evidentiary items (e.g. medical examination, witness statements, documents, digital evidence) needed to strengthen this section's applicability.
4. "ambiguities": List of factual or legal ambiguities in the user's statement relevant to this section.
5. "validation": A fact-to-element validation object containing:
   - "required_elements": An array of dictionaries, each containing:
     - "element": Brief description of the required legal element (e.g., "Theft of property", "Violence or threat of instant hurt to a person").
     - "satisfied": boolean indicating whether this element is supported by the facts in the user query.
     - "evidence_or_reason": Specific fact or legal reasoning showing why it is/is not satisfied.
   - "recommend_section": boolean set to true if and only if ALL essential elements are satisfied. If any required element is unsatisfied or missing, set to false.
6. "decision_reason": A detailed explanation of why this section is recommended or rejected based on the validation elements.
7. "override_reason": If this section is recommended (satisfied) but a candidate section with HIGHER retrieval confidence (which is listed earlier in the candidate sections list) is rejected/not recommended, write an explicit reason explaining why this section was recommended while the higher-ranked one was bypassed. If a higher-ranked section is rejected, explain the factual/legal reasons why it was rejected. Otherwise, if there is no override (e.g., it is the top candidate, or all higher-ranked candidates are also recommended), set to an empty string.

CRITICAL LEGAL DISTINCTIONS TO ENFORCE:
- Distinguish between violence/force against PROPERTY (e.g., using a crowbar to break open an almirah, lock, or safe) and violence/force/hurt/restraint/threats against PERSONS.
- Robbery (e.g., BNS 309 / IPC 390/392) generally requires theft or extortion accompanied by violence, hurt, wrongful restraint, or fear of instant hurt/death/restraint to a person. Breaking an almirah with a crowbar is property damage, NOT violence to a person. If no person was harmed, threatened, or wrongfully restrained, reject Robbery (recommend_section: false).
- Assault for theft (e.g., BNS 134 / IPC 356) requires actual assault or criminal force against a person in an attempt to commit theft. If no person was assaulted or threatened, reject it (recommend_section: false).
- Dowry Death (e.g., BNS 80 / IPC 304B) requires: (a) death caused by burns/bodily injury or occurring otherwise than under normal circumstances, (b) within 7 years of marriage, (c) showing she was subjected to cruelty/harassment by husband/relative for dowry soon before death. If the facts contain a married woman dying after dowry harassment, it is highly relevant. If details like "within 7 years" or "soon before death" are unspecified, highlight these as ambiguities but recommend it if the core facts are strongly supportive, or explicitly record why you choose to reject/recommend it.

USER QUERY:
"{user_query}"

CANDIDATE LEGAL SECTIONS (listed in descending order of retrieval confidence):
{json.dumps(candidates_summary, indent=2)}

Return ONLY valid JSON matching the following exact format without any markdown wrapper or explanation:

{{
  "user_query": "{user_query}",
  "sections": [
    {{
      "section": "...",
      "title": "...",
      "confidence": 0.96,
      "graph_verified": true,
      "reason": "...",
      "supporting_facts": [
        "..."
      ],
      "missing_evidence": [
        "..."
      ],
      "ambiguities": [
        "..."
      ],
      "validation": {{
        "required_elements": [
          {{
            "element": "...",
            "satisfied": true,
            "evidence_or_reason": "..."
          }}
        ],
        "recommend_section": true
      }},
      "decision_reason": "...",
      "override_reason": "..."
    }}
  ]
}}
"""

        try:
            response = self.llm.invoke(prompt)
            content = response.content.strip()

            # Clean markdown JSON block formatting if present
            cleaned = re.sub(r"^```(?:json)?|```$", "", content, flags=re.MULTILINE).strip()
            parsed = json.loads(cleaned)

            # Flatten check in case LLM wrapped it under "case_analysis"
            if "case_analysis" in parsed:
                parsed = parsed["case_analysis"]

            if "recommended_sections" in parsed or "rejected_sections" in parsed:
                rec = parsed.get("recommended_sections") or []
                rej = parsed.get("rejected_sections") or []
                rec.sort(key=lambda x: x.get("confidence", 0.0), reverse=True)
                rej.sort(key=lambda x: x.get("confidence", 0.0), reverse=True)
                return {
                    "user_query": user_query,
                    "recommended_sections": rec,
                    "rejected_sections": rej
                }

            if "sections" in parsed:
                recommended = []
                rejected = []
                for s in parsed["sections"]:
                    val = s.get("validation") or {}
                    if val.get("recommend_section", True):
                        recommended.append(s)
                    else:
                        rejected.append(s)
                
                # Sort both by confidence in descending order
                recommended.sort(key=lambda x: x.get("confidence", 0.0), reverse=True)
                rejected.sort(key=lambda x: x.get("confidence", 0.0), reverse=True)

                return {
                    "user_query": user_query,
                    "recommended_sections": recommended,
                    "rejected_sections": rejected
                }

            return self._normalize_fallback(user_query, ranked_candidates)

        except Exception as e:
            print(f"[LegalReasoningService] Error during LLM generation: {e}")
            return self._normalize_fallback(user_query, ranked_candidates)

    def _normalize_fallback(self, user_query: str, ranked_candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
        recommended = []
        for c in ranked_candidates:
            recommended.append({
                "section": c.get("section", ""),
                "title": c.get("title", ""),
                "confidence": c.get("confidence", 0.0),
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
        return {
            "user_query": user_query,
            "recommended_sections": recommended,
            "rejected_sections": []
        }
