"""
query_decomposition_service.py
================================
Replaces QueryExpansionService entirely.

Instead of hardcoded keyword triggers that fire on surface word matches,
this service uses the LLM to holistically understand the case facts and
decompose them into TYPED legal sub-queries. Each sub-query has a type
that controls how the agent retrieves and validates results for it.

Sub-query types:
  OFFENCE              → Pinecone vector search; results must pass ingredient validation.
  EVIDENCE_PRESUMPTION → Neo4j direct traversal for evidentiary/presumption nodes (BSA/IEA).
                         Results skip ingredient validation.
  CONSTITUTIONAL       → Neo4j direct traversal for constitutional articles.
                         Results skip ingredient validation.
  PROCEDURAL           → Auto-resolved to BNSS 482 / CrPC 438; never touches Pinecone.
                         Results skip ingredient validation.
  AGGRAVATION          → A fact stated in the case that INCREASES bail risk or offence
                         gravity (e.g. threats to witnesses, flight risk, violent conduct).
                         Results skip ingredient validation.
  MITIGATION           → A fact stated in the case that SUPPORTS bail grant (e.g. accused
                         cooperated with investigation, no prior record, family ties).
                         Results skip ingredient validation.

The agent reads sub_query["type"] and routes accordingly.
"""

import json
import re
from typing import Dict, Any, List

try:
    from config.llm_config import get_llm
except ModuleNotFoundError:
    from agents.config.llm_config import get_llm

# Valid sub-query types the LLM is allowed to produce.
VALID_TYPES = {"OFFENCE", "EVIDENCE_PRESUMPTION", "CONSTITUTIONAL", "PROCEDURAL", "AGGRAVATION", "MITIGATION"}

# Types whose Pinecone results skip ingredient validation in the agent.
NON_OFFENCE_TYPES = {"EVIDENCE_PRESUMPTION", "CONSTITUTIONAL", "PROCEDURAL", "AGGRAVATION", "MITIGATION"}


class QueryDecompositionService:
    """
    LLM-driven legal query decomposition.

    Takes the structured output of QueryUnderstandingService plus the raw
    query and produces a list of typed sub-queries that the agent uses for
    targeted, type-aware retrieval. Zero hardcoded keyword rules.
    """

    def __init__(self):
        self.llm = get_llm(temperature=0.0)

    def decompose(self, qu_result: Dict[str, Any], raw_query: str, role: str = "neutral") -> Dict[str, Any]:
        """
        Main entry point.

        Args:
            qu_result:  Output of QueryUnderstandingService.analyze_query()
            raw_query:  The original user query string.
            role:       "prosecutor" | "defense" | "neutral" — shapes retrieval
                        priority only. Never changes what the facts say.

        Returns:
            {
                "sub_queries": [
                    {
                        "type": "OFFENCE" | "EVIDENCE_PRESUMPTION" | "CONSTITUTIONAL"
                                | "PROCEDURAL" | "AGGRAVATION" | "MITIGATION",
                        "query": "<search string for this sub-query>",
                        "priority": 1 | 2 | 3   (1 = highest)
                    },
                    ...
                ]
            }
        """
        role_instruction = self._role_instruction(role)
        prompt = self._build_prompt(qu_result, raw_query, role_instruction)

        try:
            response = self.llm.invoke(prompt)
            content = response.content.strip()

            # Strip markdown fences if present
            cleaned = re.sub(r"^```(?:json)?|```$", "", content, flags=re.MULTILINE).strip()

            json_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
            if not json_match:
                print("[QueryDecompositionService] No JSON found in LLM response; using fallback.")
                return self._fallback(raw_query)

            parsed = json.loads(json_match.group(0))
            sub_queries = self._validate_and_clean(parsed.get("sub_queries") or [])

            if not sub_queries:
                print("[QueryDecompositionService] LLM returned empty sub_queries; using fallback.")
                return self._fallback(raw_query)

            # Always ensure PROCEDURAL is present (anticipatory bail context is constant)
            if not any(sq["type"] == "PROCEDURAL" for sq in sub_queries):
                sub_queries.append({
                    "type": "PROCEDURAL",
                    "query": "anticipatory bail application",
                    "priority": 1
                })

            print(f"[QueryDecompositionService] Decomposed into {len(sub_queries)} sub-queries:")
            for sq in sub_queries:
                print(f"  [{sq['type']}] (p{sq['priority']}) {sq['query']}")

            return {"sub_queries": sub_queries}

        except json.JSONDecodeError as e:
            print(f"[QueryDecompositionService] JSON parse error: {e}")
            return self._fallback(raw_query)
        except Exception as e:
            print(f"[QueryDecompositionService] LLM error: {e}")
            return self._fallback(raw_query)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _role_instruction(self, role: str) -> str:
        """
        Role only affects PRIORITY of sub-queries — it never changes what
        the facts say or inverts them. Factual sub-queries must always
        reflect the facts as stated.
        """
        if role == "prosecutor":
            return (
                "ROLE: PROSECUTION (opposing anticipatory bail).\n"
                "Priority guidance: Give priority 1 to OFFENCE sub-queries and any "
                "AGGRAVATION sub-queries. Give priority 2 to EVIDENCE_PRESUMPTION. "
                "Give priority 3 to MITIGATION and CONSTITUTIONAL sub-queries.\n"
                "CRITICAL: Do NOT invent aggravating facts that are not stated. "
                "If the facts say the accused cooperated, that is a MITIGATION — "
                "do not convert it to an AGGRAVATION."
            )
        if role == "defense":
            return (
                "ROLE: DEFENSE (seeking anticipatory bail).\n"
                "Priority guidance: Give priority 1 to MITIGATION and CONSTITUTIONAL "
                "sub-queries. Give priority 2 to PROCEDURAL. Give priority 3 to OFFENCE.\n"
                "CRITICAL: Do NOT invent mitigating facts that are not stated. "
                "Report every fact exactly as stated — aggravating facts remain AGGRAVATION."
            )
        return (
            "ROLE: NEUTRAL.\n"
            "Assign priority based on legal significance regardless of prosecution or defense angle."
        )

    def _build_prompt(self, qu_result: Dict[str, Any], raw_query: str, role_instruction: str) -> str:
        return f"""
You are QueryDecompositionService, a legal retrieval component of Kayda AI.

Your ONLY job is to read a set of case facts and decompose them into TYPED legal
sub-queries for targeted retrieval. Every sub-query must be grounded in what the
facts actually state — never inferred, never inverted, never role-biased.

{role_instruction}

---
SUB-QUERY TYPES — use exactly these strings:

  OFFENCE
    A specific substantive criminal act the facts prima facie disclose.

    RULE — GROUP BY LEGAL CONCEPT, NOT BY SENTENCE CLAUSE:
    Count DISTINCT OFFENCE CONCEPTS, not adjectives or clauses. "Physical cruelty"
    and "mental cruelty" are TWO FACETS OF ONE OFFENCE CONCEPT (cruelty by
    husband/relatives) — that is ONE sub-query, not two. Do not split a single
    offence into one sub-query per adjective, per verb, or per sentence fragment.
    A new sub-query is warranted only when the facts disclose a LEGALLY DISTINCT
    concept (e.g. cruelty vs. dowry demand vs. criminal intimidation are three
    distinct concepts → three sub-queries).

    RULE — NO HALLUCINATED OFFENCES:
    Only generate an OFFENCE sub-query for conduct that is EXPLICITLY stated in
    the raw query. Never infer or add an offence concept (e.g. "assault",
    "stalking", "outraging modesty") merely because it commonly co-occurs with
    the stated facts in similar cases. If it is not in the text, it does not
    exist for this case.

    RULE — STATUTORY CONCEPT LANGUAGE + LEGAL SYNONYM EXPANSION:
    Query text must be phrased the way the offence is legally defined and
    indexed in the retrieval database — NOT as a reworded restatement of the
    sentence in the raw query. A paraphrase of the facts ("threatened his wife
    with dire consequences") is semantically distant from how the offence is
    indexed ("criminal intimidation — threat of injury to person, property, or
    reputation to cause alarm or compel an act") and will retrieve poorly even
    though it looks accurate to a human reader.

    CRITICAL — SYNONYM EXPANSION:
    Each query MUST expand key fact-pattern words into their full legal synonym
    chain so that the embedding retrieval reaches the correct statutory section.
    The fact pattern uses everyday language; the index is built from statutory
    text and legal definitions. You must bridge that gap by including synonyms,
    related legal terms, and statutory elements in the query string.

    HOW TO EXPAND — think in three layers for every key concept:
      Layer 1 — What the fact says:          "financial manager"
      Layer 2 — Legal synonyms:              "employee, agent, clerk, servant"
      Layer 3 — Statutory elements:          "entrustment, dominion over property,
                                              fiduciary capacity, in the way of business"
    Fold all three layers into the query string.

    Another example:
      Layer 1 — What the fact says:          "manipulated financial records"
      Layer 2 — Legal synonyms:              "falsification, fabrication, alteration"
      Layer 3 — Statutory elements:          "books of accounts, ledger, financial
                                              statement, concealment, false entry"
    Query: "falsification of accounts books of account ledger false entry
            fabrication concealment financial statement"

    GOOD vs BAD query text examples:
      BAD:  "Subjected his wife to physical cruelty"
      BAD:  "Subjected his wife to mental cruelty"
      GOOD: "cruelty by husband or relatives of husband towards a woman,
             physical and mental" (ONE query covering both facets)

      BAD:  "Threatened his wife with dire consequences"
      GOOD: "criminal intimidation, threat of injury to person or reputation
             to cause alarm or compel an act"

      BAD:  "Repeatedly demanded additional dowry"
      GOOD: "dowry demand and harassment for dowry by husband or relatives"

      BAD:  "misappropriation of funds by financial manager"
      GOOD: "criminal breach of trust by employee agent clerk manager servant
             entrustment dominion over property fiduciary capacity dishonest
             misappropriation in the way of business"

      BAD:  "manipulation of financial records to conceal transactions"
      GOOD: "falsification of accounts books of account ledger false entry
             fabrication alteration concealment financial statement"

    Be precise about conduct, victim, and mental element, but express it in
    the vocabulary a statute/index entry would use — not the vocabulary of
    the fact pattern. Always include legal synonyms and statutory elements.

    NOTE ON SECTIONS: Do not name a section here. Which exact IPC/BNS section(s)
    ultimately apply is decided downstream by validating retrieval results
    against the FULL case context — your job is only to produce concept-accurate,
    synonym-rich queries that maximize correct recall.

  EVIDENCE_PRESUMPTION
    A statutory evidentiary presumption or burden-of-proof rule the facts trigger.
    Example: presumption under dowry death provisions, presumption of mens rea.

  CONSTITUTIONAL
    A constitutional provision the bail question engages.
    Example: personal liberty, right against self-incrimination.

  PROCEDURAL
    The procedural provision under which anticipatory bail is sought.
    Exactly ONE per decomposition (BNSS 482 / CrPC 438 equivalent).

  AGGRAVATION
    A fact STATED IN THE QUERY that increases bail risk or offence gravity.
    Examples: accused threatened witnesses, accused absconded, accused has prior record.
    CRITICAL: Only use this type if the fact is explicitly stated as an aggravating
    circumstance. Never convert a neutral or mitigating fact into AGGRAVATION.

  MITIGATION
    A fact STATED IN THE QUERY that supports bail grant.
    Examples: accused cooperated with investigation, no prior criminal record,
    accused is sole breadwinner, accused has strong community ties.
    CRITICAL: Only use this type if the fact is explicitly stated. Never invent
    mitigating facts. If the facts say "cooperated with investigation" → MITIGATION.

---
CARDINAL RULES:

1. ONE OFFENCE sub-query per distinct OFFENCE CONCEPT, not per clause/adjective.
   Do not split one concept (e.g. cruelty) into multiple queries just because
   it is described with multiple adjectives (physical, mental). Do not combine
   two legally distinct concepts (e.g. cruelty and dowry demand) into one query
   either. If the facts disclose 5 legally distinct concepts, write 5 — no more,
   no fewer, and never invent a 6th that isn't stated.

   IMPORTANT — falsification is DISTINCT from criminal breach of trust:
   When facts state both (a) misappropriation AND (b) manipulation/alteration
   of records/accounts/documents to conceal it, these are TWO legally distinct
   offence concepts requiring TWO separate sub-queries:
     Sub-query 1: Criminal Breach of Trust (the misappropriation)
     Sub-query 2: Falsification of accounts / false entry in books of account
                  (the concealment act — maps to BNS 344 / IPC 477A)
   If the concealment involved creation of a false document with intent to
   cheat a specific person, also add:
     Sub-query 3: Forgery for purpose of cheating / making false document
                  (maps to BNS 338 / IPC 468)
   Do NOT collapse all three into one query. Do NOT omit the falsification
   query just because it is secondary to the misappropriation.

2. Facts are SACRED. Report every fact exactly as stated. Never invert meaning,
   and never add conduct that is not stated (no hallucinated offences).
   "Has cooperated" → MITIGATION. "Has not cooperated" → AGGRAVATION.
   "Threatened victim" → OFFENCE (criminal intimidation) AND possibly AGGRAVATION.
   "Denies allegations" → neutral, skip it.

3. No section numbers, act names, or article numbers in query text. Use legal
   CONCEPT language as the retrieval index would phrase it — not a paraphrase
   of the raw query's sentence structure. See GOOD vs BAD examples above.

4. priority: 1 = must retrieve, 2 = important, 3 = supplementary.

5. Return ONLY valid JSON. No markdown, no explanation.

---
WORKED EXAMPLES (study both before decomposing):

EXAMPLE 1 — Matrimonial / domestic violence:

Raw query: "The applicant seeks anticipatory bail after an FIR alleges that he,
along with his family members, subjected his wife to physical and mental
cruelty, repeatedly demanded additional dowry, and threatened her with dire
consequences if the demand was not fulfilled; the applicant denies the
allegations, claims the complaint was filed due to matrimonial discord, and
states that he has cooperated with the investigation."

CORRECT decomposition — note how "dire consequences" becomes statutory
intimidation language, "physical and mental" is ONE concept not two queries,
and NO assault/stalking are invented:

{{
  "sub_queries": [
    {{"type": "OFFENCE", "query": "cruelty by husband or relatives of husband towards a woman, physical and mental", "priority": 1}},
    {{"type": "OFFENCE", "query": "dowry demand and harassment for dowry by husband or relatives", "priority": 1}},
    {{"type": "OFFENCE", "query": "criminal intimidation, threat of injury to cause alarm or compel an act", "priority": 1}},
    {{"type": "EVIDENCE_PRESUMPTION", "query": "presumption as to dowry harassment or cruelty", "priority": 2}},
    {{"type": "MITIGATION", "query": "accused cooperated with investigation", "priority": 1}},
    {{"type": "PROCEDURAL", "query": "anticipatory bail application", "priority": 1}}
  ]
}}

EXAMPLE 2 — Financial crime / corporate fraud (study the synonym expansion carefully):

Raw query: "The applicant seeks anticipatory bail after an FIR alleges that,
while acting as a financial manager of a private company, he misappropriated
company funds amounting to Rs 18 lakh for personal use and manipulated
financial records to conceal the transactions; the applicant argues that the
discrepancies are accounting errors, has no criminal record, and has joined
the investigation."

CORRECT decomposition — note three things:
  (a) "financial manager" expands to the full statutory synonym chain:
      employee, agent, clerk, servant, entrustment, dominion over property,
      fiduciary capacity — because the index uses those terms, not "manager".
  (b) "manipulated financial records" expands to falsification language:
      books of account, ledger, false entry, fabrication, concealment —
      because IPC 477A / BNS 336 is indexed under those terms, not "records".
  (c) "accounting errors" is the accused's DEFENCE, not a fact to encode.

{{
  "sub_queries": [
    {{"type": "OFFENCE", "query": "criminal breach of trust by employee agent clerk manager servant entrustment dominion over property fiduciary capacity dishonest misappropriation in the way of business", "priority": 1}},
    {{"type": "OFFENCE", "query": "falsification of accounts books of account ledger false entry fabrication alteration concealment financial statement", "priority": 1}},
    {{"type": "OFFENCE", "query": "making false document or false entry in books of account with intent to defraud or conceal misappropriation forgery for purpose of cheating", "priority": 1}},
    {{"type": "MITIGATION", "query": "accused has no prior criminal record", "priority": 2}},
    {{"type": "MITIGATION", "query": "accused cooperated with investigation joined investigation", "priority": 2}},
    {{"type": "PROCEDURAL", "query": "anticipatory bail application", "priority": 1}}
  ]
}}

Note what IS and IS NOT in the correct output:
  - "falsification of accounts" IS present because "manipulated financial
    records to conceal the transactions" is explicitly stated — this maps
    directly to the offence of falsification of accounts / false entry in
    books of account. Always include this when record manipulation is stated.
  - "forgery for cheating" (BNS 338 equivalent) MAY be present if the facts
    describe creation of a false document with intent to deceive — but in this
    example it is not separately stated, so it is not added.
  - "cheating" as a standalone offence is NOT present because no victim was
    induced to deliver property — misappropriation from an employer is CBT,
    not cheating. Do not conflate the two.
  - "manipulation of financial records" as a raw paraphrase is NOT present —
    it is replaced with the statutory synonym chain (falsification, books of
    account, ledger, false entry, fabrication, concealment).
  - "accounting errors" is the accused's defence claim — neutral, not a sub-query.

---
INPUT:

Raw query:
"{raw_query}"

QueryUnderstandingService output:
{json.dumps(qu_result, indent=2)}

---
OUTPUT FORMAT (strict):

{{
  "sub_queries": [
    {{
      "type": "OFFENCE",
      "query": "...",
      "priority": 1
    }},
    ...
  ]
}}
"""

    def _validate_and_clean(self, raw: List[Any]) -> List[Dict[str, Any]]:
        """
        Validates each sub-query dict from the LLM. Drops malformed entries,
        normalises the type field, caps priority at 1-3.
        """
        cleaned = []
        seen_queries = set()
        for item in raw:
            if not isinstance(item, dict):
                continue
            q_type = str(item.get("type") or "").strip().upper()
            q_text = str(item.get("query") or "").strip()
            q_priority = item.get("priority", 2)

            if q_type not in VALID_TYPES:
                print(f"[QueryDecompositionService] Dropping sub-query with unknown type '{q_type}'")
                continue
            if not q_text:
                continue

            # Normalise priority
            try:
                q_priority = max(1, min(3, int(q_priority)))
            except (ValueError, TypeError):
                q_priority = 2

            # Strip any section numbers that slipped in despite instructions
            q_text = re.sub(
                r'\b(?:BNS|IPC|BNSS|CRPC|BSA|IEA|POCSO|DPA|Section|Sec|Art|Article)\s*\d+[A-Za-z]?\b',
                '', q_text, flags=re.IGNORECASE
            )
            q_text = re.sub(r'\s+', ' ', q_text).strip()

            if not q_text or q_text.lower() in seen_queries:
                continue
            seen_queries.add(q_text.lower())

            cleaned.append({
                "type": q_type,
                "query": q_text,
                "priority": q_priority
            })

        return cleaned

    def _fallback(self, raw_query: str) -> Dict[str, Any]:
        """
        Minimal safe fallback when LLM fails — uses the raw query as a single
        OFFENCE sub-query plus the mandatory PROCEDURAL entry.
        """
        return {
            "sub_queries": [
                {
                    "type": "OFFENCE",
                    "query": raw_query,
                    "priority": 1
                },
                {
                    "type": "PROCEDURAL",
                    "query": "anticipatory bail application",
                    "priority": 1
                }
            ]
        }