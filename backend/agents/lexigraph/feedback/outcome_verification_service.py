"""
outcome_verification_service.py
================================
LLM-as-judge verifier for resolved-but-unlabeled predictions.

Critical design constraint (per architecture discussion): this must NOT be the
same prompt/persona that generated the recommendation in legal_reasoning_service.py,
or it just confirms its own bias. Instead it runs a checklist-style prompt that:

  1. Checks each statutory ingredient (actus reus / mens rea) individually against
     the extracted facts — element-by-element, not "does this look right overall".
  2. Checks whether cited supporting cases are actually about this fact pattern,
     not just topically adjacent.
  3. Checks rejected_sections for anything that looks more applicable than what
     was recommended.

It deliberately does NOT re-run retrieval or re-score candidates — it only judges
the final output that was already served, using the same facts a human reviewer
would have.
"""

import json
from typing import Dict, Any, List

try:
    from config.llm_config import get_llm
except ModuleNotFoundError:
    from agents.config.llm_config import get_llm


VERDICT_SCHEMA_HINT = """
Return ONLY valid JSON matching this exact schema:

{
  "section_verdicts": [
    {
      "act": "BNS",
      "section": "101",
      "verdict": "correct" | "incorrect" | "uncertain",
      "ingredient_check": "element-by-element assessment, 1-2 sentences",
      "case_relevance_check": "assessment of cited cases, or 'no cases cited'",
      "reasoning": "1-2 sentence overall justification"
    }
  ],
  "missed_section": {
    "found": true,
    "act": "BNS",
    "section": "...",
    "reasoning": "why this rejected/omitted section may have been more applicable"
  },
  "overall_verdict": "correct" | "incorrect" | "partially_correct" | "uncertain"
}

If no rejected section looks more applicable, set "missed_section": {"found": false}.
"""


class OutcomeVerificationService:
    """Independent LLM judge for production predictions lacking human labels."""

    def __init__(self):
        try:
            self.llm = get_llm(temperature=0.0)
        except Exception as e:
            print(f"[OutcomeVerificationService] LLM init info: {e}")
            self.llm = None

    def judge_prediction(self, prediction_record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Takes a prediction record from PredictionLogger and returns a verdict
        object tagged source='llm_judge'. Caller (feedback_service) decides
        whether this gets used as the resolved label or gets overridden by
        human feedback.
        """
        query = prediction_record.get("query", "")
        facts = prediction_record.get("extracted_facts", {})
        recommended = prediction_record.get("recommended_sections") or []
        rejected = prediction_record.get("rejected_sections") or []

        if not self.llm:
            return self._fallback_verdict(recommended, reason="LLM unavailable")

        if not recommended:
            return {
                "source": "llm_judge",
                "overall_verdict": "uncertain",
                "section_verdicts": [],
                "missed_section": {"found": False},
                "note": "No sections were recommended for this query."
            }

        prompt = f"""
You are an independent legal auditor reviewing an AI system's output AFTER the fact.
You did NOT generate this recommendation — your job is to check it, not defend it.
Be skeptical. Prior confidence scores from the system should not influence your verdict.

CASE FACTS (as extracted from the user's query):
{json.dumps(facts, indent=2)}

ORIGINAL USER QUERY:
"{query}"

SECTIONS THE SYSTEM RECOMMENDED:
{json.dumps(recommended, indent=2)}

SECTIONS THE SYSTEM REJECTED OR FILTERED OUT:
{json.dumps(rejected, indent=2)}

For each recommended section, work through it element-by-element:
- Does the fact pattern actually satisfy each statutory ingredient (actus reus, mens rea,
  victim/circumstance elements), or does the recommendation just look topically plausible?
- Are any cited cases/precedents actually about this fact pattern, or only topically adjacent?
- Independently, scan the rejected sections: is there one that fits the facts better than
  what was recommended?

{VERDICT_SCHEMA_HINT}
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
            parsed["source"] = "llm_judge"
            return parsed
        except Exception as e:
            print(f"[OutcomeVerificationService] Error invoking LLM judge: {e}")
            return self._fallback_verdict(recommended, reason=f"LLM judge call failed: {e}")

    def _fallback_verdict(self, recommended: List[Dict[str, Any]], reason: str) -> Dict[str, Any]:
        return {
            "source": "llm_judge",
            "overall_verdict": "uncertain",
            "section_verdicts": [
                {
                    "act": r.get("act"),
                    "section": r.get("section"),
                    "verdict": "uncertain",
                    "ingredient_check": reason,
                    "case_relevance_check": reason,
                    "reasoning": reason,
                }
                for r in recommended
            ],
            "missed_section": {"found": False},
            "note": reason,
        }