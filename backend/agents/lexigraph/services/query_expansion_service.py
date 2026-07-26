import json
import re
import sys
from pathlib import Path
from typing import Dict, Any, List

try:
    from config.llm_config import get_llm
except ModuleNotFoundError:
    from agents.config.llm_config import get_llm


class QueryExpansionService:
    """
    QueryExpansionService
    
    A specialized legal retrieval component of Kayda AI.
    Your ONLY responsibility is to generate semantically diverse search queries
    using pure legal concepts, terminology, and crime elements.
    DO NOT guess or invent section numbers (BNS/IPC/Articles). Citation resolution is the retrieval engine's job.
    """

    def __init__(self):
        self.llm = get_llm(temperature=0.0)

    def expand_query(self, qu_input: Dict[str, Any]) -> Dict[str, Any]:
        """
        Takes structured query understanding output and generates semantically diverse search queries
        enriched with formal statutory legal concepts, excluding ungrounded section numbers.
        """
        raw_text = f"{qu_input.get('expanded_query', '')} {' '.join(qu_input.get('offences', []))} {' '.join(qu_input.get('keywords', []))}".lower()

        # Pure Legal Concept & Terminology Expansions (Incident Classification Rules)
        legal_expansions = []
        if any(w in raw_text for w in ["following", "calling", "monitoring", "social media", "messages", "stalking", "tracking", "boyfriend", "ex-partner"]):
            legal_expansions.extend([
                "stalking and following woman repeatedly or monitoring electronic communication",
                "cyber stalking and sending threatening electronic messages to woman",
                "criminal intimidation and persistent unwanted following of female victim",
                "offence of stalking and outraging modesty of woman by electronic means"
            ])
        if any(w in raw_text for w in ["threatened", "threatening", "threat", "kill", "harm", "coercion"]):
            legal_expansions.extend([
                "criminal intimidation threatening injury to person reputation or property",
                "threatening to kill or cause grievous hurt to victim if reported"
            ])
        if any(w in raw_text for w in ["entered", "house", "trespass", "home", "forcibly"]):
            legal_expansions.extend([
                "house trespass with intent to commit offence or assault woman",
                "lurking house trespass after preparation for hurt or assault"
            ])
        if any(w in raw_text for w in ["rape", "sexual intercourse", "penetrat"]):
            legal_expansions.extend([
                "sexual intercourse without consent and sexual violence against woman",
                "offence of rape and forced sexual assault on female victim",
                "rape causing death or persistent vegetative state"
            ])
        if any(w in raw_text for w in ["sexual assault", "modesty", "assaulted", "touched"]):
            legal_expansions.extend([
                "assault or criminal force to woman with intent to outrage modesty",
                "sexual harassment and physical assault against woman"
            ])
        if "dowry" in raw_text:
            legal_expansions.extend([
                "dowry death and unnatural death of married woman within seven years of marriage",
                "cruelty and harassment by husband or relatives for dowry demand"
            ])
        if any(w in raw_text for w in ["murder", "death", "died", "fatal", "killed"]):
            legal_expansions.extend([
                "culpable homicide amounting to murder causing death of victim",
                "intentional bodily injury causing death"
            ])
        if any(w in raw_text for w in ["married woman", "wife", "domestic", "husband", "partner"]):
            legal_expansions.extend([
                "offences relating to marriage and cruelty to married woman",
                "husband or partner subjecting woman to domestic abuse and harassment"
            ])
        if any(w in raw_text for w in ["minor", "child", "girl", "boy"]):
            legal_expansions.extend([
                "kidnapping and abduction of minor child from lawful guardianship",
                "offence against minor child child protection statutory provisions"
            ])
        if any(w in raw_text for w in ["kidnapping", "kidnapped", "abduct"]):
            legal_expansions.extend([
                "kidnapping and abduction from lawful guardianship",
                "abduction of minor for forced marriage or confinement"
            ])
        if any(w in raw_text for w in ["acid attack", "acid", "corrosive"]):
            legal_expansions.extend([
                "voluntarily causing grievous hurt by use of acid or corrosive substance",
                "acid attack causing disfigurement to woman"
            ])

        prompt = f"""
You are QueryExpansionService, a specialized legal retrieval component of Kayda AI.

Your ONLY responsibility is to generate multiple semantically diverse search queries from the structured legal concepts produced by QueryUnderstandingService.

CRITICAL DIRECTIVE ON CITATIONS:
- Focus STRICTLY on legal concepts, crime elements, synonyms, and formal statutory terminology (e.g., "dowry death", "cruelty by husband", "unnatural death within seven years", "sexual assault outraging modesty").
- DO NOT invent, guess, or include any section numbers or article numbers (such as BNS 80, IPC 304B, Article 21). Section resolution is handled downstream by the vector search and knowledge graph.

TASKS
1. Generate FIVE search queries focused on key factual and legal terminology.
2. Use formal legal terms and crime elements.

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
        
        # Clean any accidental section number patterns from queries to enforce pure conceptual expansion
        cleaned_queries = []
        seen = set()
        for q in all_queries:
            q_str = str(q).strip()
            # Strip explicit section/article patterns if present
            q_clean = re.sub(r'\b(?:BNS|IPC|Section|Sec|Art|Article)\s*\d+[A-Z]?\b', '', q_str, flags=re.IGNORECASE)
            q_clean = re.sub(r'\s+', ' ', q_clean).strip()
            if q_clean and q_clean.lower() not in seen:
                seen.add(q_clean.lower())
                cleaned_queries.append(q_clean)

        return {
            "search_queries": cleaned_queries[:8]
        }

    def _normalize_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        queries = list(data.get("search_queries") or [])
        return {"search_queries": [str(q).strip() for q in queries]}

    def _get_empty_response(self) -> Dict[str, Any]:
        return {"search_queries": ["Legal search query"]}
