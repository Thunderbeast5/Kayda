import json
import re
import sys
from pathlib import Path
from typing import Dict, Any

try:
    from config.llm_config import get_llm
except ModuleNotFoundError:
    from agents.config.llm_config import get_llm


class QueryUnderstandingService:
    """
    QueryUnderstandingService
    
    A specialized legal NLP component of Kayda AI.
    Your ONLY responsibility is to understand the user's legal query and convert it into
    structured legal concepts for downstream semantic retrieval.
    """

    def __init__(self):
        # Using temperature=0.0 for deterministic legal analysis
        self.llm = get_llm(temperature=0.0)

    def analyze_query(self, query: str) -> Dict[str, Any]:
        """
        Analyzes the user's statement and returns a structured dictionary matching the required schema.
        """
        prompt = f"""
You are QueryUnderstandingService, a specialized legal NLP component of Kayda AI.

Your ONLY responsibility is to understand the user's legal query and convert it into structured legal concepts for downstream semantic retrieval.

You are NOT a legal reasoning engine.

TASKS
1. Determine whether the query describes:
   - "Single offence"
   - "Multiple offences"
   - "Unknown offence"
   Assign this to the "crime_type" field.

2. Identify every possible offence using plain legal concepts.
   Examples: Cruelty, Dowry Demand, Assault, Kidnapping, Murder, Theft, Cheating, Criminal Intimidation, Stalking, Sexual Harassment, Domestic Violence, Rape, Dowry Death, Acid Attack.
   List them in the "offences" array.

3. Extract important legal keywords suitable for semantic vector search.
   List them in the "keywords" array.

4. Rewrite the user's query into a legally descriptive sentence preserving the original meaning.
   Assign this to the "expanded_query" field.

5. Identify the primary legal community / category intended by the query from the following options:
   - "women_offences"
   - "children_offences"
   - "human_body_offences"
   - "property_offences"
   - "financial_crime"
   - "cyber_crime"
   - "general_offences"
   Assign this to the "primary_intent_community" field.

Return ONLY valid JSON matching the format below. Do not wrap the JSON in HTML, markdown, or explain your output.

Output Schema:
{{
    "crime_type": "",
    "offences": [],
    "keywords": [],
    "expanded_query": "",
    "primary_intent_community": ""
}}

User statement to analyze:
"{query}"
"""

        try:
            response = self.llm.invoke(prompt)
            content = response.content.strip()
            
            # Remove markdown code block wrappers if present
            cleaned_content = re.sub(r"^```(?:json)?|```$", "", content, flags=re.MULTILINE).strip()
            
            parsed_json = json.loads(cleaned_content)
            
            return self._normalize_response(parsed_json, query)
        except Exception as e:
            print(f"[QueryUnderstandingService] Error during LLM generation or JSON parsing: {e}")
            return self._get_empty_response(query)

    def _detect_rule_community(self, query: str) -> str:
        q = query.lower()
        if any(w in q for w in ["rape", "sexual", "dowry", "cruelty", "modesty", "married woman", "wife", "domestic violence", "outrage", "acid attack"]):
            return "women_offences"
        if any(w in q for w in ["minor", "child", "children", "infant", "kidnap", "abduct"]):
            return "children_offences"
        if any(w in q for w in ["murder", "homicide", "death", "killed", "die", "hurt", "injury", "assault"]):
            return "human_body_offences"
        if any(w in q for w in ["theft", "stole", "robbery", "burglary", "extortion", "trespass", "almirah", "housebreak"]):
            return "property_offences"
        if any(w in q for w in ["forgery", "counterfeit", "cheating", "fraud", "fake note", "currency"]):
            return "financial_crime"
        if any(w in q for w in ["cyber", "hacking", "computer", "phishing", "online fraud"]):
            return "cyber_crime"
        return "general_offences"

    def _normalize_response(self, data: Dict[str, Any], raw_query: str = "") -> Dict[str, Any]:
        community = str(data.get("primary_intent_community") or "").strip()
        rule_community = self._detect_rule_community(raw_query)
        if not community or community not in ["women_offences", "children_offences", "human_body_offences", "property_offences", "financial_crime", "cyber_crime", "general_offences"]:
            community = rule_community
        # Override rule: if raw query explicitly has rape/dowry/married woman, ensure women_offences is primary
        if rule_community == "women_offences":
            community = "women_offences"

        return {
            "crime_type": str(data.get("crime_type") or "Single offence"),
            "offences": list(data.get("offences") or []),
            "keywords": list(data.get("keywords") or []),
            "expanded_query": str(data.get("expanded_query") or raw_query),
            "primary_intent_community": community
        }

    def _get_empty_response(self, raw_query: str = "") -> Dict[str, Any]:
        community = self._detect_rule_community(raw_query)
        return {
            "crime_type": "Single offence",
            "offences": [],
            "keywords": [],
            "expanded_query": raw_query,
            "primary_intent_community": community
        }

