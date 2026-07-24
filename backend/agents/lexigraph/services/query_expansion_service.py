import json
import re
import sys
from pathlib import Path
from typing import Dict, Any

try:
    from config.llm_config import get_llm
except ModuleNotFoundError:
    from agents.config.llm_config import get_llm


class QueryExpansionService:
    """
    QueryExpansionService
    
    A specialized legal retrieval component of Kayda AI.
    Your ONLY responsibility is to generate multiple semantically diverse search queries
    from the structured legal concepts produced by QueryUnderstandingService.
    """

    def __init__(self):
        # Using temperature=0.0 for deterministic expansions
        self.llm = get_llm(temperature=0.0)

    def expand_query(self, qu_input: Dict[str, Any]) -> Dict[str, Any]:
        """
        Takes structured query understanding output and generates semantically diverse search queries
        enriched with formal statutory legal terminology.
        """
        raw_text = f"{qu_input.get('expanded_query', '')} {' '.join(qu_input.get('offences', []))} {' '.join(qu_input.get('keywords', []))}".lower()

        # Step 2 Legal Terminology Expansion Rules
        legal_expansions = []
        if "rape" in raw_text or "sexual intercourse" in raw_text:
            legal_expansions.extend([
                "sexual intercourse without consent",
                "offence against woman rape BNS provisions",
                "sexual violence and forced sexual intercourse BNS 63 BNS 64 BNS 66",
                "punishment for rape causing death or persistent vegetative state BNS 66"
            ])
        if "sexual assault" in raw_text or "modesty" in raw_text:
            legal_expansions.extend([
                "assault or criminal force to woman with intent to outrage modesty",
                "sexual harassment and assault against woman BNS 74 BNS 75"
            ])
        if "dowry" in raw_text:
            legal_expansions.extend([
                "dowry death death of woman within seven years of marriage BNS 80",
                "cruelty by husband or relative of husband for dowry demand BNS 84"
            ])
        if "murder" in raw_text or "death" in raw_text or "died" in raw_text or "fatal" in raw_text:
            legal_expansions.extend([
                "culpable homicide amounting to murder causing death BNS 101 BNS 103",
                "causing death of victim BNS 66 BNS 105"
            ])
        if "married woman" in raw_text or "wife" in raw_text:
            legal_expansions.extend([
                "offences relating to marriage cruelty to married woman",
                "sexual intercourse with married woman BNS 67 BNS 84"
            ])
        if "minor" in raw_text or "child" in raw_text:
            legal_expansions.extend([
                "kidnapping of minor child protection provisions BNS 137 BNS 140",
                "offence against minor child POCSO BNS child provisions"
            ])
        if "kidnapping" in raw_text or "kidnapped" in raw_text or "abduct" in raw_text:
            legal_expansions.extend([
                "kidnapping and abduction from lawful guardianship BNS 137 BNS 140",
                "kidnapping minor for marriage BNS 137"
            ])
        if "acid attack" in raw_text or "acid" in raw_text:
            legal_expansions.extend([
                "voluntarily causing grievous hurt by use of acid BNS 124",
                "acid attack provisions on woman BNS 124"
            ])
        if "domestic violence" in raw_text or "cruelty" in raw_text:
            legal_expansions.extend([
                "husband or relative subjecting woman to cruelty BNS 84",
                "domestic abuse and harassment of married woman BNS 84"
            ])

        prompt = f"""
You are QueryExpansionService, a specialized legal retrieval component of Kayda AI.

Your ONLY responsibility is to generate multiple semantically diverse search queries from the structured legal concepts produced by QueryUnderstandingService.

You are NOT a legal reasoning engine.

TASKS
1. Generate FIVE search queries focused on key statutory legal aspects.
2. Use formal legal terminology (e.g., "sexual intercourse without consent", "dowry death", "culpable homicide", "kidnapping of minor").
3. Include relevant BNS section markers (e.g. BNS 63, BNS 66, BNS 80, BNS 101, BNS 103) if relevant to the facts.

Return ONLY valid JSON matching:
{{
    "search_queries": [
        "...",
        "...",
        "...",
        "...",
        "..."
    ]
}}

Input JSON:
{json.dumps(qu_input, indent=2)}
"""

        try:
            response = self.llm.invoke(prompt)
            content = response.content.strip()
            cleaned_content = re.sub(r"^```(?:json)?|```$", "", content, flags=re.MULTILINE).strip()
            parsed_json = json.loads(cleaned_content)
            llm_queries = list(parsed_json.get("search_queries") or [])
        except Exception as e:
            print(f"[QueryExpansionService] Error during LLM generation: {e}")
            llm_queries = []

        all_queries = legal_expansions + llm_queries + [qu_input.get("expanded_query", "")]
        
        # Deduplicate while preserving order
        unique_queries = []
        seen = set()
        for q in all_queries:
            q_clean = str(q).strip()
            if q_clean and q_clean.lower() not in seen:
                seen.add(q_clean.lower())
                unique_queries.append(q_clean)

        return {
            "search_queries": unique_queries[:8]
        }

    def _normalize_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        queries = list(data.get("search_queries") or [])
        return {"search_queries": [str(q).strip() for q in queries]}

    def _get_empty_response(self) -> Dict[str, Any]:
        return {"search_queries": ["Legal search query"]}

