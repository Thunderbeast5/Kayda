"""
query_decomposition_service.py
================================
Decomposes raw case-fact queries into TYPED legal sub-queries.

Sub-query types:
  OFFENCE              → Pinecone vector search (IPC-only index); results go through
                         Neo4j verification + BNS crosswalk.
  EVIDENCE_PRESUMPTION → Neo4j direct text-search for BSA/IEA presumption nodes.
                         Never sent to Pinecone. Skips ingredient validation.
  CONSTITUTIONAL       → Neo4j direct text-search for constitutional articles.
                         Never sent to Pinecone. Skips ingredient validation.
  PROCEDURAL           → Auto-resolved to BNSS 482; never touches Pinecone.
                         Skips ingredient validation.
  AGGRAVATION          → A fact from the case that INCREASES bail risk.
                         Sent to Pinecone (IPC index) for supporting-section retrieval.
  MITIGATION           → A fact from the case that SUPPORTS bail grant.
                         Sent to Pinecone (IPC index) for supporting-section retrieval.
"""

import json
import re
from typing import Dict, Any, List

try:
    from config.llm_config import get_llm
except ModuleNotFoundError:
    from agents.config.llm_config import get_llm

VALID_TYPES = {"OFFENCE", "EVIDENCE_PRESUMPTION", "CONSTITUTIONAL", "PROCEDURAL", "AGGRAVATION", "MITIGATION"}
NON_OFFENCE_TYPES = {"EVIDENCE_PRESUMPTION", "CONSTITUTIONAL", "PROCEDURAL", "AGGRAVATION", "MITIGATION"}

# Legal stopwords — stripped before word-overlap calculation so expansions like
# "cruelty by husband towards woman" aren't penalised for containing "towards"/"woman".
_LEGAL_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "with", "in", "to", "for", "that",
    "by", "on", "at", "if", "not", "as", "any", "all", "from", "into", "after",
    "before", "upon", "who", "which", "towards", "against", "between", "under",
    "over", "about", "its", "their", "this", "these", "those", "is", "are",
    "was", "were", "be", "been", "being", "have", "has", "had", "do", "does",
    "did", "will", "would", "could", "should", "may", "might", "shall",
    "he", "she", "it", "they", "him", "her", "them", "his", "her", "its",
    "our", "your", "my", "we", "you", "i",
    # Generic legal qualifiers — stripped only when they truly cannot distinguish
    # a grounded query from a hallucinated one.  "criminal", "offence", and
    # "property" are intentionally NOT stripped — they are load-bearing in
    # canonical legal phrases like "criminal breach of trust" and "delivery of
    # property", and removing them collapses legitimate offence queries below
    # the 0.25 overlap threshold.
    "person", "injury", "accused", "complainant", "applicant", "act", "law",
    # Generic financial words — appear across cheating, breach of trust, cheque, AND
    # investment fraud cases; cannot ground any specific offence type on their own.
    "funds", "money", "amount", "payment",
}

# Canonical OFFENCE query forms — phrased using the vocabulary of the statutory
# definition (not the section label), so embeddings land close to the actual IPC
# section text in the Pinecone index.
# CRITICAL: these are PHRASINGS only — not permission to add an offence unless
# the corresponding trigger concept is EXPLICITLY present in the raw case facts.
_LEGAL_EXPANSION_NOTE = """
CANONICAL QUERY FORMS — use these phrasings when the raw facts describe the concept.
These are phrased in the vocabulary of the statutory definition, not the section name.

  [facts say: cruelty / domestic violence / mental harassment of wife]
      → OFFENCE: "husband or relatives subjecting woman to wilful conduct causing grave injury or danger to life or health"
      → OFFENCE: "coercing woman or her relatives to meet unlawful demand for property or valuable security"  (only if demand also stated)

  [facts say: dowry demand / dowry harassment]
      → OFFENCE: "death of woman caused by burns or bodily injury within seven years of marriage preceded by demand for dowry"
      → OFFENCE: "husband or relatives subjecting married woman to cruelty or harassment in connection with demand for dowry"

  [facts say: cheating / false promises / fraudulent inducement / misrepresentation to obtain money]
      → OFFENCE: "dishonestly inducing a person to deliver property by deceiving with false representations"
      → OFFENCE: "person induced to hand over money or property through fraudulent misrepresentation of material facts"

  [facts say: investment fraud / false promise of returns / funds diverted]
      → OFFENCE: "person induced to invest money through false promises of guaranteed returns funds diverted for personal use"

  [facts say: misappropriation / embezzlement / diversion of entrusted funds in employment or fiduciary capacity]
      → OFFENCE: "property entrusted to a person in a fiduciary or employment capacity dishonestly misappropriated or converted"

  [facts say: forged / manipulated / falsified financial records or accounts]
      → OFFENCE: "employee making false entries in accounts or books of employer with intent to defraud"

  [facts say: threats / intimidation / threatening with harm — ONLY if EXPLICITLY stated]
      → OFFENCE: "threatening a person with injury to body reputation or property to cause alarm or compel an act"

  [facts say: kidnapping / abduction / unlawful detention of person]
      → OFFENCE: "taking or enticing a minor or person out of keeping of lawful guardian without consent"

  [facts say: rape / sexual assault / non-consensual intercourse]
      → OFFENCE: "sexual intercourse with a woman against her will or without her consent"

  [facts say: assault / physical violence / causing bodily hurt]
      → OFFENCE: "voluntarily causing bodily hurt or grievous hurt by use of instrument or dangerous means"

  [facts say: extortion / threatening for money / coercion for payment]
      → OFFENCE: "putting a person in fear of injury and thereby dishonestly inducing delivery of property or valuable thing"

  [facts say: murder / killing / culpable homicide]
      → OFFENCE: "act done with intention of causing death or with knowledge that death is the likely result"

  [facts say: cheque bounce / dishonour of cheque / NI Act offence]
      → OFFENCE: "cheque returned unpaid by bank due to insufficiency of funds in drawer account to discharge a legally enforceable debt"

DO NOT use any mapping above if the corresponding concept is NOT present in the raw facts.
Each OFFENCE must map to exactly ONE concept actually present in the facts.
"""

# Alias map: maps every meaningful content token in a canonical OFFENCE query back to
# the raw-fact concept tokens it represents.  Used in _post_process to avoid
# dropping legitimate legal-form expansions as hallucinations.
# Format: alias_token → set of raw-fact tokens that justify its presence.
_EXPANSION_ALIASES: dict = {
    # cheating by inducing delivery of property
    "inducing":   {"induced", "induce", "misrepresentation", "false", "promise", "promised",
                   "guaranteed", "guarantees", "deceit", "deceived", "defraud", "fraud",
                   "invest", "invested", "investment"},
    # 'delivery' = handing over money/property following inducement.
    # Must resolve on payment-action words only — NOT generic monetary amounts
    # like 'lakh'/'crore' which also appear in cheque-bounce / breach-of-trust facts.
    "delivery":   {"induced", "paid", "invest", "invested", "payment", "deliver",
                   "transferred", "remitted", "deposited", "handed"},
    # criminal breach of trust — resolve only with fiduciary/employment words
    "entrusted":  {"trust", "entrusted", "employer", "employee", "servant",
                   "fiduciary", "custod", "deputed", "manager", "director"},
    "servant":    {"employee", "servant", "manager", "director", "officer", "trustee"},
    # falsification of accounts — resolve on record-manipulation words
    "falsification": {"falsif", "manipulated", "forged", "fabricated", "tampered",
                      "altered", "falsified"},
    "accounts":   {"account", "accounts", "records", "books", "ledger", "entries",
                   "financial", "transaction", "transactions"},
    # criminal intimidation — only resolve when threats are explicitly stated
    "intimidation": {"threaten", "threatened", "threats", "dire", "consequences",
                     "coerce", "coerced", "warned", "intimidat"},
    "threat":     {"threaten", "threatened", "threats", "dire", "consequences",
                   "intimidat", "warned"},
    # cruelty
    "towards":    {"wife", "woman", "complainant", "victim", "her"},
    # breach of trust / diversion
    "divert":     {"diverted", "diversion", "siphon", "siphoned", "personal", "misuse"},
    "misappropriate": {"misappropriated", "diverted", "siphoned", "embezzled"},
    # generic expansion words that appear in canonical forms but not in raw facts
    "lawful":     {"guardian", "parent", "custody", "child", "minor", "abduct", "kidnap"},
    "guardianship": {"guardian", "parent", "child", "minor"},
    "penetration": {"rape", "sexual", "assault", "intercourse"},
    "grievous":   {"hurt", "injury", "assault", "beat", "attack", "harm"},
    "imputation": {"defam", "slander", "false", "allegation"},
    "unlawful":   {"riot", "mob", "assembly", "gathering"},
    "insufficiency": {"bounce", "dishonour", "cheque", "neft", "rtgs", "ni act", "negotiable"},
    "amounting":  {"murder", "kill", "homicide", "death"},
    "extort":     {"extortion", "threaten", "fear", "coercion"},
}


class QueryDecompositionService:
    def __init__(self):
        self.llm = get_llm(temperature=0.0)

    def decompose(self, qu_result: Dict[str, Any], raw_query: str, role: str = "neutral") -> Dict[str, Any]:
        role_instruction = self._role_instruction(role)
        prompt = self._build_prompt(qu_result, raw_query, role_instruction)

        try:
            response = self.llm.invoke(prompt)
            content = response.content.strip()

            print(f"[QueryDecompositionService] Raw LLM response (first 500 chars):\n{content[:500]}...")

            # Strip markdown fences
            cleaned = re.sub(r"^```(?:json)?|```$", "", content, flags=re.MULTILINE).strip()

            # Find the first JSON object
            json_match = re.search(r'\{', cleaned)
            if not json_match:
                print("[QueryDecompositionService] No JSON found in response; using fallback.")
                return self._fallback(raw_query)

            try:
                decoder = json.JSONDecoder()
                parsed, _ = decoder.raw_decode(cleaned, json_match.start())
            except json.JSONDecodeError as e:
                print(f"[QueryDecompositionService] JSON parse error: {e}; using fallback.")
                return self._fallback(raw_query)

            raw_sub_queries = parsed.get("sub_queries") or []
            sub_queries = self._validate_and_clean(raw_sub_queries)

            if not sub_queries:
                print("[QueryDecompositionService] Empty sub_queries after validation; using fallback.")
                return self._fallback(raw_query)

            # Drop hallucinated OFFENCE queries — MUST run before the fallback-injection checks
            # so that only genuinely low-overlap queries are replaced by the fallback.
            sub_queries = self._post_process(sub_queries, raw_query)

            # Now inject fallbacks only if the LLM (post-filtering) produced none
            if not any(sq["type"] == "OFFENCE" for sq in sub_queries):
                fallback_offence = self._derive_offence_from_query(raw_query)
                print(f"[QueryDecompositionService] No OFFENCE survived; injecting fallback: '{fallback_offence}'")
                sub_queries.append({
                    "type": "OFFENCE",
                    "query": fallback_offence,
                    "priority": 1
                })

            if not any(sq["type"] == "PROCEDURAL" for sq in sub_queries):
                sub_queries.append({
                    "type": "PROCEDURAL",
                    "query": "anticipatory bail application",
                    "priority": 1
                })

            print(f"[QueryDecompositionService] Final {len(sub_queries)} sub-queries:")
            for sq in sub_queries:
                print(f"  [{sq['type']}] (p{sq['priority']}) {sq['query']}")

            return {"sub_queries": sub_queries}

        except Exception as e:
            print(f"[QueryDecompositionService] Unexpected error: {e}")
            return self._fallback(raw_query)

    # ------------------------------------------------------------------
    # Role instruction
    # ------------------------------------------------------------------
    def _role_instruction(self, role: str) -> str:
        if role == "prosecutor":
            return (
                "ROLE: PROSECUTION (opposing anticipatory bail).\n"
                "Priority 1 for OFFENCE and AGGRAVATION; priority 2 for EVIDENCE_PRESUMPTION; "
                "priority 3 for MITIGATION and CONSTITUTIONAL.\n"
                "Do NOT invent aggravating facts not present in the case."
            )
        elif role == "defense":
            return (
                "ROLE: DEFENSE (seeking anticipatory bail).\n"
                "Priority 1 for MITIGATION and CONSTITUTIONAL; priority 2 for PROCEDURAL; "
                "priority 3 for OFFENCE.\n"
                "Do NOT invent mitigating facts not present in the case."
            )
        else:
            return "ROLE: NEUTRAL. Assign priority by legal significance."

    # ------------------------------------------------------------------
    # Prompt builder
    # ------------------------------------------------------------------
    def _build_prompt(self, qu_result: Dict[str, Any], raw_query: str, role_instruction: str) -> str:
        return f"""You are QueryDecompositionService, a legal retrieval component for Indian criminal law.

Your ONLY task: read the case facts and decompose them into TYPED legal sub-queries.
Each sub-query must be grounded ONLY in what the facts explicitly state.
Do NOT invent any offence, fact, or allegation absent from the raw query.

{role_instruction}

{_LEGAL_EXPANSION_NOTE}

SUB-QUERY TYPES:
- OFFENCE              : substantive criminal act to retrieve from the IPC vector index
- EVIDENCE_PRESUMPTION : statutory presumption (BSA/IEA) relevant to the case
- CONSTITUTIONAL       : constitutional provision (e.g., personal liberty, article 21)
- PROCEDURAL           : bail provision — always exactly ONE: "anticipatory bail application"
- AGGRAVATION          : a fact explicitly stated in the case that increases bail risk
- MITIGATION           : a fact explicitly stated in the case that supports bail grant

STRICT RULES:
1. OFFENCE queries: ≤12 words, use the canonical forms listed above, include actors
   (e.g., "husband and relatives") ONLY if explicitly named in the raw facts.
2. Generate ONLY offences whose triggering concept is EXPLICITLY present in the raw facts.
   - "criminal intimidation" → ONLY if threats/intimidation are explicitly stated
   - "dishonour of cheque" → ONLY if a bounced cheque or NI Act offence is explicitly stated
   - "criminal breach of trust" → ONLY if the accused was entrusted with funds in a
     fiduciary/employment capacity AND misappropriated them; NOT for a joint-venture dispute
3. Distinguish "cheating by inducing delivery of property" (false promises to obtain money
   from a victim) from "criminal breach of trust" (diversion of funds entrusted by an
   employer/client in a fiduciary relationship).  Apply whichever FITS — not both unless
   the facts clearly support both.
4. AGGRAVATION items must include specific facts: amounts (₹ figures, lakh, crore),
   the mechanism of fraud, and flight/evidence-tampering risk if stated.
5. MITIGATION items must quote or closely paraphrase actual stated facts only.
6. No section numbers in any query string.
7. Return ONLY valid JSON with a "sub_queries" array — no other text.

--- EXAMPLE 1 (matrimonial — family named + explicit threats) ---
Raw: "The applicant seeks anticipatory bail after an FIR alleges that he, along with his
family members, subjected his wife to physical and mental cruelty, repeatedly demanded
additional dowry, and threatened her with dire consequences if the demand was not
fulfilled; the applicant denies the allegations, claims the complaint was filed due to
matrimonial discord, and states that he has cooperated with the investigation."

Analysis: Facts contain → cruelty ✓, dowry demand ✓, threats/dire consequences ✓
          Family named ✓, no cheque, no financial fraud, no murder.

Output:
{{
  "sub_queries": [
    {{"type": "OFFENCE",              "query": "husband or relatives subjecting woman to wilful conduct causing grave injury or danger to life or health", "priority": 1}},
    {{"type": "OFFENCE",              "query": "husband or relatives subjecting married woman to cruelty or harassment in connection with demand for dowry", "priority": 1}},
    {{"type": "OFFENCE",              "query": "threatening a person with injury to body reputation or property to cause alarm or compel an act",           "priority": 1}},
    {{"type": "EVIDENCE_PRESUMPTION", "query": "presumption as to dowry harassment where woman subjected to cruelty before death",                         "priority": 2}},
    {{"type": "AGGRAVATION",          "query": "accused threatened wife with dire consequences for dowry non-payment", "priority": 1}},
    {{"type": "MITIGATION",           "query": "accused cooperated with investigation",                      "priority": 2}},
    {{"type": "MITIGATION",           "query": "complaint alleged to be filed due to matrimonial discord",   "priority": 3}},
    {{"type": "PROCEDURAL",           "query": "anticipatory bail application",                              "priority": 1}}
  ]
}}

--- EXAMPLE 2 (investment fraud — false promises, no threats, no fiduciary relationship) ---
Raw: "The applicant seeks anticipatory bail after an FIR alleges that he induced the
complainant to invest ₹40 lakh in a joint business venture by making false promises of
guaranteed returns, diverted the funds for personal use, and failed to repay the
investment; the applicant contends that the dispute arises out of a failed commercial
agreement, has cooperated with the investigation, and has no previous criminal antecedents."

Analysis: Facts contain → false promises to invest ✓ (cheating), diversion for personal use ✓
          No threats stated (no criminal intimidation), no cheque mentioned,
          joint venture = NOT a fiduciary/employment trust relationship,
          no family members, no dowry, no physical violence.
          OFFENCE queries must use statutory element vocabulary, not section labels.

Output:
{{
  "sub_queries": [
    {{"type": "OFFENCE",    "query": "person induced to invest money through false promises of guaranteed returns funds diverted for personal use", "priority": 1}},
    {{"type": "OFFENCE",    "query": "dishonestly inducing a person to deliver property by deceiving with false representations", "priority": 1}},
    {{"type": "AGGRAVATION","query": "accused induced complainant to invest ₹40 lakh through false promises of guaranteed returns", "priority": 1}},
    {{"type": "AGGRAVATION","query": "accused diverted invested funds for personal use and failed to repay", "priority": 1}},
    {{"type": "MITIGATION", "query": "accused cooperated with investigation",             "priority": 2}},
    {{"type": "MITIGATION", "query": "accused has no previous criminal antecedents",      "priority": 2}},
    {{"type": "MITIGATION", "query": "dispute alleged to arise from failed commercial agreement", "priority": 3}},
    {{"type": "PROCEDURAL", "query": "anticipatory bail application",                    "priority": 1}}
  ]
}}

--- EXAMPLE 3 (financial misappropriation inside employment — trust relationship) ---
Raw: "The applicant seeks anticipatory bail after an FIR alleges that, while acting as a
financial manager of a private company, he misappropriated company funds amounting to
Rs 18 lakh for personal use and manipulated financial records to conceal the
transactions; the applicant argues that the discrepancies are accounting errors, has no
criminal record, and has joined the investigation."

Analysis: Facts contain → employee entrusted with company funds ✓ (criminal breach of trust),
          falsified records ✓, no threats, no investment fraud, no dowry.

Output:
{{
  "sub_queries": [
    {{"type": "OFFENCE",    "query": "property entrusted to a person in a fiduciary or employment capacity dishonestly misappropriated or converted", "priority": 1}},
    {{"type": "OFFENCE",    "query": "employee making false entries in accounts or books of employer with intent to defraud",                         "priority": 1}},
    {{"type": "AGGRAVATION","query": "accused misappropriated company funds of Rs 18 lakh for personal use", "priority": 1}},
    {{"type": "AGGRAVATION","query": "accused manipulated financial records to conceal transactions", "priority": 1}},
    {{"type": "MITIGATION", "query": "accused has no prior criminal record",                  "priority": 2}},
    {{"type": "MITIGATION", "query": "accused cooperated with investigation",                 "priority": 2}},
    {{"type": "PROCEDURAL", "query": "anticipatory bail application",                        "priority": 1}}
  ]
}}

--- NOW DECOMPOSE THE FOLLOWING ---

Raw query:
"{raw_query}"

QueryUnderstanding output:
{json.dumps(qu_result, indent=2)}

Output JSON:
"""

    # ------------------------------------------------------------------
    # Validation and cleaning
    # ------------------------------------------------------------------
    def _validate_and_clean(self, raw: List[Any]) -> List[Dict[str, Any]]:
        cleaned = []
        seen = set()
        for item in raw:
            if not isinstance(item, dict):
                continue
            q_type = str(item.get("type") or "").strip().upper()
            q_text = str(item.get("query") or "").strip()
            q_priority = item.get("priority", 2)

            if q_type not in VALID_TYPES:
                print(f"[QueryDecompositionService] Dropping unknown type '{q_type}': {q_text}")
                continue
            if not q_text:
                continue

            try:
                q_priority = max(1, min(3, int(q_priority)))
            except (TypeError, ValueError):
                q_priority = 2

            # Strip section references from query text
            q_text = re.sub(
                r'\b(?:BNS|IPC|BNSS|CRPC|BSA|IEA|POCSO|DPA|Section|Sec|Art|Article)\s*\d+[A-Za-z]?\b',
                '', q_text, flags=re.IGNORECASE
            )
            q_text = re.sub(r'\s+', ' ', q_text).strip()

            if not q_text:
                continue

            key = (q_type, q_text.lower())
            if key in seen:
                continue
            seen.add(key)

            cleaned.append({"type": q_type, "query": q_text, "priority": q_priority})
        return cleaned

    # ------------------------------------------------------------------
    # Post-processing: drop hallucinated OFFENCE queries
    # ------------------------------------------------------------------
    def _post_process(self, sub_queries: List[Dict[str, Any]], raw_query: str) -> List[Dict[str, Any]]:
        """
        Drop OFFENCE sub-queries whose core legal concept has no grounding in the raw
        query.

        Algorithm
        ---------
        1. Tokenise both the raw query and the OFFENCE query (strip stopwords).
        2. For each token in the OFFENCE query that is NOT directly in the raw tokens,
           check whether any of its known aliases (from _EXPANSION_ALIASES) ARE in the
           raw tokens.  If so, treat the expansion token as resolved.
        3. Compute "resolved overlap" = (directly matched + alias-resolved) / total query tokens.
        4. Threshold = 0.25 — at least one meaningful core concept must be present
           either literally or via alias.

        This means:
          - "cheating by inducing delivery of property" is kept when raw facts contain
            "induced / invest / false / promises" (inducing → alias, delivery → alias).
          - "criminal intimidation by threat of injury" is DROPPED when raw facts
            contain no threat/intimidation concept at all.
          - "dishonour of cheque" is DROPPED when no cheque is mentioned.
        """
        raw_tokens = {
            w for w in re.findall(r'\b\w+\b', raw_query.lower())
            if w not in _LEGAL_STOPWORDS and len(w) > 2
        }

        filtered = []
        for sq in sub_queries:
            if sq["type"] != "OFFENCE":
                # Non-OFFENCE types always pass through — grounded in facts or structural.
                filtered.append(sq)
                continue

            q_tokens = [
                w for w in re.findall(r'\b\w+\b', sq["query"].lower())
                if w not in _LEGAL_STOPWORDS and len(w) > 2
            ]

            if not q_tokens:
                print(f"[QueryDecompositionService] Dropping empty OFFENCE tokens: '{sq['query']}'")
                continue

            # Word-count sanity
            if len(q_tokens) < 2:
                print(f"[QueryDecompositionService] Dropping too-short OFFENCE query: '{sq['query']}'")
                continue
            if len(q_tokens) > 15:
                print(f"[QueryDecompositionService] Dropping too-long OFFENCE query: '{sq['query']}'")
                continue

            resolved = 0
            for tok in q_tokens:
                if tok in raw_tokens:
                    resolved += 1
                else:
                    # Check alias resolution: if any alias for this token exists in
                    # the raw fact tokens, the expansion is considered grounded.
                    aliases = _EXPANSION_ALIASES.get(tok, set())
                    if aliases & raw_tokens:
                        resolved += 1

            overlap = resolved / len(q_tokens)

            if overlap < 0.25:
                print(
                    f"[QueryDecompositionService] Dropping hallucinated OFFENCE "
                    f"(resolved_overlap={overlap:.2f}): '{sq['query']}'"
                )
                continue

            print(
                f"[QueryDecompositionService] Keeping OFFENCE "
                f"(resolved_overlap={overlap:.2f}): '{sq['query']}'"
            )
            filtered.append(sq)

        return filtered

    # ------------------------------------------------------------------
    # Fallback helpers
    # ------------------------------------------------------------------
    def _derive_offence_from_query(self, raw_query: str) -> str:
        """
        Rule-based fallback: derive the single most likely OFFENCE query from raw facts.
        Order matters — more specific patterns should come before generic ones.
        """
        q = raw_query.lower()

        # --- Violent / person offences ---
        if "murder" in q or "culpable homicide" in q or "killed" in q:
            return "culpable homicide amounting to murder"
        if "rape" in q or "sexual assault" in q or "non-consensual" in q:
            return "sexual assault by penetration without consent"
        if "kidnap" in q or "abduct" in q:
            return "kidnapping or abduction from lawful guardianship"
        if "extort" in q:
            return "extortion by putting person in fear of injury"
        if ("hurt" in q or "assault" in q or "beat" in q or "stab" in q
                or "shot" in q or "shoot" in q):
            return "voluntarily causing hurt or grievous hurt"

        # --- Matrimonial / domestic offences ---
        if "cruelty" in q or "domestic violence" in q or "mental harassment" in q:
            if "family" in q or "relatives" in q or "in-law" in q:
                return "cruelty by husband and relatives towards woman"
            return "cruelty by husband towards woman"
        if "dowry" in q:
            if "family" in q or "relatives" in q or "in-law" in q:
                return "dowry demand and harassment by husband and relatives"
            return "dowry demand and harassment"

        # --- Financial offences: distinguish trust vs cheating ---
        # Criminal breach of trust: accused was ENTRUSTED (employer/employee/fiduciary)
        if ("breach of trust" in q or "misappropriat" in q or "embezzl" in q
                or ("entrust" in q and ("funds" in q or "money" in q or "amount" in q))):
            return "criminal breach of trust by employee servant"
        if "falsif" in q or "manipulated financial records" in q or "forged account" in q:
            return "falsification of accounts by employee"
        # Cheating: false promises / inducement to hand over money (investment fraud,
        # joint venture fraud, guaranteed-return fraud, etc.)
        if ("cheating" in q or "fraud" in q or "deceiv" in q
                or "false promises" in q or "guaranteed returns" in q
                or "induced" in q or "misrepresent" in q
                or ("invest" in q and ("false" in q or "promise" in q or "lakh" in q
                                       or "crore" in q or "returns" in q))):
            return "cheating by inducing delivery of property"

        # --- Threats (only if explicitly stated) ---
        if "threaten" in q or "intimidat" in q or "dire consequences" in q:
            return "criminal intimidation by threat of injury"

        # --- Cheque / NI Act ---
        if "cheque" in q or "dishonour" in q or "bounce" in q:
            return "dishonour of cheque for insufficiency of funds"

        return "criminal offence against person or property"

    def _fallback(self, raw_query: str) -> Dict[str, Any]:
        offence = self._derive_offence_from_query(raw_query)
        print(f"[QueryDecompositionService] Full fallback triggered; offence='{offence}'")
        return {
            "sub_queries": [
                {"type": "OFFENCE",    "query": offence,                       "priority": 1},
                {"type": "PROCEDURAL", "query": "anticipatory bail application","priority": 1},
            ]
        }