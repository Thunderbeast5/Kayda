import json
import re
from typing import Dict, Any, List

try:
    from config.llm_config import get_llm
except ModuleNotFoundError:
    from agents.config.llm_config import get_llm

"""
query_expansion_service.py
===========================
REVERTED FROM QueryDecompositionService — see lexigraph_agent.py header note.

QueryDecompositionService asked one large LLM call to freely invent OFFENCE,
AGGRAVATION, MITIGATION, EVIDENCE_PRESUMPTION and CONSTITUTIONAL sub-queries
in a single shot. Despite an alias/overlap grounding filter, it kept
hallucinating — mostly AGGRAVATION/MITIGATION items that "sounded right" for
the offence type but were never actually stated in the case facts, and
occasional OFFENCE items for concepts only loosely related to the raw text.

This service replaces it with a narrower, more controllable pipeline that
still returns the SAME typed sub_queries contract the agent already routes
on (OFFENCE / AGGRAVATION / MITIGATION / EVIDENCE_PRESUMPTION / CONSTITUTIONAL
/ PROCEDURAL), so lexigraph_agent.py needed no changes beyond swapping which
service produces it:

  1. OFFENCE      — deterministic rule-based canonical-phrase expansion
                     (broadened to the full legal domain, not just offences
                     against women) PLUS a constrained LLM call that may only
                     paraphrase offences QueryUnderstandingService already
                     identified — it is explicitly forbidden from adding a new
                     offence concept. Both sources are then passed through the
                     same alias/overlap grounding filter QueryDecomposition
                     used, so a hallucinated OFFENCE still gets dropped even if
                     the LLM invents one anyway.
  2. AGGRAVATION /
     MITIGATION    — passed through VERBATIM from
                     QueryUnderstandingService.aggravating_factors /
                     mitigating_factors. No LLM rewriting happens here at all,
                     which removes the biggest hallucination surface
                     (freely-generated "facts that sound plausible for this
                     offence type") entirely.
  3. CONSTITUTIONAL — always includes the Article 21 personal-liberty ground
                     that is relevant to essentially every anticipatory-bail
                     matter; priority shifts with role. This is a fixed,
                     legally uncontroversial string, not an LLM invention.
  4. EVIDENCE_PRESUMPTION — only added when a known statutory-presumption
                     trigger (e.g. dowry death, abetment of suicide) is
                     literally present in the case facts.
  5. PROCEDURAL    — always exactly one entry: "anticipatory bail
                     application". The agent hard-injects BNSS 482 for this
                     downstream regardless, so this entry is structural, not
                     a retrieval risk.

Sub-query types
---------------
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

VALID_TYPES = {"OFFENCE", "EVIDENCE_PRESUMPTION", "CONSTITUTIONAL", "PROCEDURAL", "AGGRAVATION", "MITIGATION"}
NON_OFFENCE_TYPES = {"EVIDENCE_PRESUMPTION", "CONSTITUTIONAL", "PROCEDURAL", "AGGRAVATION", "MITIGATION"}

# ---------------------------------------------------------------------------
# NOTE: _LEGAL_STOPWORDS and _EXPANSION_ALIASES have been removed.
#
# They implemented a word-overlap grounding filter designed for short label
# queries ("cheating by inducing delivery of property"). For element-description
# queries that use statutory vocabulary ("fiduciary", "misappropriated",
# "entrusted"), word overlap with everyday fact language ("diverted",
# "shell accounts", "fictitious scheme") is near-zero even when the query is
# exactly correct. The alias map tried to bridge this with ~30 handcrafted
# token pairs — not scalable across the full IPC.
#
# Hallucination prevention now lives where it belongs:
#   • Rule-based queries: fire only on literal trigger words in raw text.
#   • LLM queries: sanitised (section refs stripped, length-checked) then
#     deduplicated — no word-overlap gate.
#   • Downstream: fact-relevance filter in lexigraph_agent Step 3 uses
#     embedding similarity to cull irrelevant sections after Pinecone retrieval.

# ---------------------------------------------------------------------------
# Deterministic OFFENCE expansion rules — broadened across the full legal
# domain. Each rule fires on a small set of raw-fact trigger words and adds
# canonical, formally-phrased OFFENCE query strings. These never depend on
# the LLM, so they can't hallucinate — they can only fire on words that are
# already literally in the case facts.
# ---------------------------------------------------------------------------
_OFFENCE_RULES: List[Dict[str, Any]] = [
    # -- Women-safety / stalking / cyberstalking ---------------------------
    {
        "triggers": ["following", "calling", "monitoring", "social media", "messages",
                     "stalking", "tracking", "boyfriend", "ex-partner"],
        "queries": [
            "stalking and following woman repeatedly or monitoring electronic communication",
            "cyber stalking and sending threatening electronic messages to woman",
            "criminal intimidation and persistent unwanted following of female victim",
        ],
    },
    # -- Criminal intimidation / threats ------------------------------------
    {
        "triggers": ["threatened", "threatening", "threat", "kill", "harm", "coercion"],
        "queries": [
            "criminal intimidation threatening injury to person reputation or property",
            "threatening to kill or cause grievous hurt to victim if reported",
        ],
    },
    # -- Trespass / house-breaking ------------------------------------------
    {
        "triggers": ["entered", "house", "trespass", "home", "forcibly", "break-in", "broke into"],
        "queries": [
            "house trespass with intent to commit offence or assault",
            "lurking house trespass after preparation for hurt or assault",
            "house-breaking by night or day with criminal intent",
        ],
    },
    # -- Rape / sexual violence ----------------------------------------------
    {
        "triggers": ["rape", "sexual intercourse", "penetrat"],
        "queries": [
            "sexual intercourse with a woman against her will or without her consent",
            "penetration against the will of the woman or obtained by putting her in fear of death or hurt",
            "sexual assault causing grievous bodily harm or death of the victim",
        ],
    },
    # -- Sexual assault / modesty ---------------------------------------------
    {
        "triggers": ["sexual assault", "modesty", "assaulted", "touched"],
        "queries": [
            "assault or criminal force to woman with intent to outrage modesty",
            "sexual harassment and physical assault against woman",
        ],
    },
    # -- Dowry ------------------------------------------------------------------
    {
        "triggers": ["dowry"],
        "queries": [
            "death of woman caused by burns or bodily injury within seven years of marriage preceded by demand for dowry",
            "husband or relatives of husband subjecting woman to cruelty or harassment in connection with demand for dowry",
        ],
    },
    # -- Homicide / violent offences causing death -----------------------------
    {
        "triggers": ["murder", "death", "died", "fatal", "killed", "shoot", "shoots", "shot",
                     "stab", "stabbed", "strangle", "poison", "firearm", "gun", "pistol",
                     "rifle", "weapon"],
        "queries": [
            # Element-description vocabulary matching IPC 299/300 text
            "act done with intention of causing death or with knowledge that death is likely to result",
            "bodily injury inflicted with intention sufficient in ordinary course to cause death",
            "causing death by shooting stabbing or use of a deadly weapon with intention to kill",
        ],
    },
    # -- Attempt to murder / grievous hurt short of death ----------------------
    {
        "triggers": ["attempt to murder", "attempted to kill", "survived the attack",
                     "hurt", "assault", "beat", "beaten", "grievous"],
        "queries": [
            "act done with intention to cause death where death does not result amounting to attempt",
            "voluntarily causing hurt or grievous bodily harm by use of a dangerous weapon or means",
        ],
    },
    # -- Marriage / domestic ------------------------------------------------------
    {
        "triggers": ["married woman", "wife", "domestic", "husband", "partner"],
        "queries": [
            "offences relating to marriage and cruelty to married woman",
            "husband or partner subjecting woman to domestic abuse and harassment",
        ],
    },
    # -- Minor / child ------------------------------------------------------------
    {
        "triggers": ["minor", "child", "girl", "boy"],
        "queries": [
            "kidnapping and abduction of minor child from lawful guardianship",
            "offence against minor child under child-protection statutory provisions",
        ],
    },
    # -- Kidnapping / abduction (any victim) ---------------------------------------
    {
        "triggers": ["kidnapping", "kidnapped", "abduct"],
        "queries": [
            "kidnapping and abduction from lawful guardianship",
            "abduction of person for forced marriage or wrongful confinement",
        ],
    },
    # -- Acid attack --------------------------------------------------------------
    {
        "triggers": ["acid attack", "acid", "corrosive"],
        "queries": [
            "voluntarily causing grievous hurt by use of acid or corrosive substance",
            "acid attack causing disfigurement to victim",
        ],
    },
    # -- Cheating / fraud -----------------------------------------------------------
    {
        "triggers": ["cheat", "cheating", "deceit", "deceive", "false promise", "induce",
                     "induced", "inducement", "dishonest", "misrepresent", "fraud",
                     "fraudulent", "scam"],
        "queries": [
            # Use statutory element vocabulary, not section labels, so embeddings
            # land close to the actual IPC 415/420 section text in the Pinecone index.
            "dishonestly inducing a person to deliver property by deceiving with false representations",
            "person induced to hand over money or property through fraudulent misrepresentation of material facts",
            "delivery of property obtained by deception through false promise of profit or guaranteed return",
        ],
    },
    # -- Criminal breach of trust / investment fraud ---------------------------------
    {
        "triggers": ["invest", "investment", "returns", "repay", "diverted", "diversion",
                     "misappropriat", "entrust", "entrusted", "breach of trust",
                     "joint business", "business venture", "money trail"],
        "queries": [
            # Cheating-via-investment path: false promises to induce delivery of funds
            "person induced to invest money through false promises of guaranteed returns funds diverted for personal use",
            # CBT path: fiduciary / employment entrustment then misappropriation
            "property entrusted to a person in a fiduciary or employment capacity dishonestly misappropriated or converted",
            # Diversion path: received money then failed to account or repay
            "money received for a specific purpose converted to personal use without accounting or repayment",
        ],
    },
    # -- Forgery -------------------------------------------------------------------
    {
        "triggers": ["forged", "forgery", "fake document", "counterfeit", "fabricated document"],
        "queries": ["forgery for the purpose of cheating and using a forged document as genuine"],
    },
    # -- Cheque dishonour / NI Act ---------------------------------------------------
    {
        "triggers": ["cheque", "bounce", "dishonour", "dishonor", "ni act", "negotiable instrument"],
        "queries": [
            "cheque returned unpaid by bank due to insufficiency of funds in drawer's account",
            "drawer of cheque liable where cheque dishonoured for want of funds to discharge legally enforceable debt",
        ],
    },
    # -- Theft / robbery / dacoity ----------------------------------------------------
    {
        "triggers": ["theft", "stole", "stolen", "robbery", "robbed", "dacoity", "snatched", "snatching"],
        "queries": [
            "theft of movable property dishonestly taken without consent",
            "robbery or dacoity involving use of force or fear of instant hurt",
        ],
    },
    # -- Extortion -----------------------------------------------------------------
    {
        "triggers": ["extort", "extortion", "ransom"],
        "queries": ["extortion by putting a person in fear of injury to deliver property"],
    },
    # -- Mischief / property damage ---------------------------------------------------
    {
        "triggers": ["damaged", "destroyed", "vandal", "arson", "set fire", "torched"],
        "queries": ["mischief causing damage or destruction to property"],
    },
    # -- Cyber crime ------------------------------------------------------------------
    {
        "triggers": ["hacked", "hacking", "unauthorised access", "unauthorized access",
                     "data breach", "phishing", "online fraud"],
        "queries": [
            "unauthorised access to computer resource and hacking",
            "cheating by personation using computer resource or communication device",
        ],
    },
    {
        "triggers": ["morphed", "obscene", "nude photo", "explicit images", "revenge porn"],
        "queries": ["publishing or transmitting obscene or sexually explicit material in electronic form"],
    },
    # -- Public order ------------------------------------------------------------------
    {
        "triggers": ["riot", "mob", "unlawful assembly", "communal", "religious hatred"],
        "queries": [
            "rioting by unlawful assembly using force or violence",
            "promoting enmity between groups on grounds of religion or community",
        ],
    },
    # -- Defamation -----------------------------------------------------------------
    {
        "triggers": ["defamation", "defamatory", "slander", "reputation harmed"],
        "queries": ["defamation by making or publishing imputation harming reputation"],
    },
    # -- Corruption / bribery ----------------------------------------------------------
    {
        "triggers": ["bribe", "bribery", "gratification", "public servant", "kickback"],
        "queries": ["criminal misconduct by public servant accepting illegal gratification"],
    },
    # -- Narcotics -----------------------------------------------------------------
    {
        "triggers": ["narcotic", "drugs", "ndps", "contraband", "peddling", "smuggling drugs"],
        "queries": ["possession or trafficking of narcotic drugs and psychotropic substances"],
    },
    # -- Human trafficking -----------------------------------------------------------
    {
        "triggers": ["trafficking", "trafficked", "sold her", "bonded labour", "forced labour"],
        "queries": ["human trafficking for exploitation or forced labour"],
    },
]

# ---------------------------------------------------------------------------
# Statutory-presumption triggers — deliberately narrow. Only fires an
# EVIDENCE_PRESUMPTION sub-query when the literal trigger concept is present,
# since this type skips ingredient validation downstream and goes straight to
# a Neo4j text search.
# ---------------------------------------------------------------------------
_PRESUMPTION_TRIGGERS: Dict[str, str] = {
    "dowry": "presumption as to dowry death where woman dies within seven years of marriage",
    "suicide": "presumption as to abetment of suicide by married woman subjected to cruelty",
    "rape": "presumption as to absence of consent in certain prosecutions for sexual offences",
}

_SECTION_PATTERN = re.compile(
    r'\b(?:BNS|IPC|Section|Sec|Art|Article|BNSS|CRPC|BSA|IEA|POCSO|DPA)\s*\d+[A-Z]?\b',
    re.IGNORECASE,
)


class QueryExpansionService:
    """
    QueryExpansionService

    Now the sole query-analysis component feeding retrieval (Query
    Decomposition reverted — see module docstring). Produces the same typed
    "sub_queries" contract QueryDecompositionService used to produce, so
    lexigraph_agent.py's downstream routing (Pinecone vs. direct-Neo4j vs.
    hard-injected PROCEDURAL) needed no changes beyond the service swap.

    Your responsibilities, in priority order:
      1. Generate grounded OFFENCE search queries — pure legal concepts,
         terminology, and crime elements. DO NOT guess or invent section
         numbers (BNS/IPC/Articles); citation resolution is the retrieval
         engine's job.
      2. Pass AGGRAVATION/MITIGATION facts through unchanged from
         QueryUnderstandingService — never compose new ones.
      3. Attach the standing CONSTITUTIONAL/EVIDENCE_PRESUMPTION/PROCEDURAL
         scaffolding described in the module docstring.
    """

    def __init__(self):
        self.llm = get_llm(temperature=0.0)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def expand_query(
        self,
        qu_input: Dict[str, Any],
        raw_query: str = "",
        role: str = "neutral",
    ) -> Dict[str, Any]:
        """
        Takes structured QueryUnderstandingService output (+ the original raw
        case-fact text and requesting role) and returns typed sub_queries:
        {"sub_queries": [{"type": ..., "query": ..., "priority": ...}, ...]}
        """
        grounding_text = raw_query or qu_input.get("expanded_query", "")
        raw_text_lower = (
            f"{qu_input.get('expanded_query', '')} "
            f"{' '.join(qu_input.get('offences', []))} "
            f"{' '.join(qu_input.get('keywords', []))} "
            f"{grounding_text}"
        ).lower()

        # -- 1. OFFENCE: expanded_query anchor + deterministic rules + LLM paraphrase --------
        #
        # The expanded_query from QueryUnderstandingService is a legally precise,
        # fact-grounded sentence.  Embedding it produces a vector that sits closer
        # to the actual IPC section text in Pinecone than any short label phrase,
        # so it is injected first at priority 1 and is exempt from the grounding
        # filter (it IS the grounding text).
        expanded_q = str(qu_input.get("expanded_query") or "").strip()
        seed_offence_queries: List[str] = []
        if expanded_q and expanded_q != grounding_text:
            # Only add when QUS produced something richer than the raw query
            seed_offence_queries.append(expanded_q)

        rule_based = self._rule_based_offence_expansions(raw_text_lower)
        llm_based  = self._llm_offence_expansions(qu_input)

        # Collect all OFFENCE candidates: seed + rule-based + LLM.
        # No word-overlap grounding filter — see module-level note.
        # Sanitise: strip any section refs the LLM slipped in, length-check,
        # then deduplicate across all three sources.
        def _sanitise(q: str) -> str:
            q = _SECTION_PATTERN.sub("", q)
            return re.sub(r"\s+", " ", q).strip()

        seen_q: set = set()
        seed_lower = expanded_q.lower()
        if seed_lower:
            seen_q.add(seed_lower)

        all_candidates = (
            [_sanitise(q) for q in rule_based]
            + [_sanitise(q) for q in llm_based]
        )
        deduped_expansions: List[str] = []
        for q in all_candidates:
            if not q:
                continue
            k = q.lower()
            # Basic sanity: 2-20 words, not already seen
            word_count = len(q.split())
            if word_count < 2 or word_count > 20:
                continue
            if k not in seen_q:
                seen_q.add(k)
                deduped_expansions.append(q)

        offence_queries = seed_offence_queries + deduped_expansions

        if not offence_queries:
            offence_queries = [self._fallback_offence(qu_input, grounding_text)]

        final_offence_queries = offence_queries[:7]
        print(f"[QueryExpansionService] OFFENCE queries -> Pinecone ({len(final_offence_queries)}):")
        for _q in final_offence_queries:
            print(f"  * {_q}")

        sub_queries: List[Dict[str, Any]] = [
            {"type": "OFFENCE", "query": q, "priority": 1} for q in final_offence_queries
        ]

        # -- 2. AGGRAVATION / MITIGATION: verbatim pass-through, no LLM rewrite ---
        for factor in qu_input.get("aggravating_factors", []):
            f = str(factor).strip()
            if f:
                sub_queries.append({"type": "AGGRAVATION", "query": f, "priority": 1})
        for factor in qu_input.get("mitigating_factors", []):
            f = str(factor).strip()
            if f:
                sub_queries.append({"type": "MITIGATION", "query": f, "priority": 2})

        # -- 3. CONSTITUTIONAL: fixed personal-liberty ground, role-weighted -----
        if role == "defense":
            constitutional_priority = 1
        elif role == "prosecutor":
            constitutional_priority = 3
        else:
            constitutional_priority = 2
        sub_queries.append({
            "type": "CONSTITUTIONAL",
            "query": "personal liberty and protection against arbitrary arrest article 21",
            "priority": constitutional_priority,
        })

        # -- 4. EVIDENCE_PRESUMPTION: narrow literal triggers only ----------------
        seen_presumptions = set()
        for trigger, presumption_query in _PRESUMPTION_TRIGGERS.items():
            if trigger in raw_text_lower and presumption_query not in seen_presumptions:
                seen_presumptions.add(presumption_query)
                sub_queries.append({
                    "type": "EVIDENCE_PRESUMPTION",
                    "query": presumption_query,
                    "priority": 2,
                })

        # -- 5. PROCEDURAL: always exactly one --------------------------------
        sub_queries.append({
            "type": "PROCEDURAL",
            "query": "anticipatory bail application",
            "priority": 1,
        })

        return {"sub_queries": sub_queries}

    # ------------------------------------------------------------------
    # Step 1a: deterministic rule-based OFFENCE expansion
    # ------------------------------------------------------------------
    def _rule_based_offence_expansions(self, raw_text_lower: str) -> List[str]:
        expansions: List[str] = []
        for rule in _OFFENCE_RULES:
            if any(trigger in raw_text_lower for trigger in rule["triggers"]):
                expansions.extend(rule["queries"])
        return expansions

    # ------------------------------------------------------------------
    # Step 1b: constrained LLM paraphrase of ALREADY-IDENTIFIED offences
    # ------------------------------------------------------------------
    def _llm_offence_expansions(self, qu_input: Dict[str, Any]) -> List[str]:
        identified_offences = qu_input.get("offences") or []
        if not identified_offences:
            # Nothing to paraphrase — skip the LLM call rather than let it
            # freely invent an offence with no anchor at all.
            return []

        prompt = f"""You are QueryExpansionService, a legal-retrieval component of Kayda AI.

Your ONLY responsibility: generate semantically diverse search-query PARAPHRASES of
the offences already identified below, using formal statutory legal terminology.

CRITICAL DIRECTIVES:
- You may ONLY paraphrase offences from the "offences" list below. Do NOT introduce
  any offence concept that is not already in that list.
- Focus STRICTLY on legal concepts, crime elements, synonyms, and formal statutory
  terminology (e.g., "dowry death", "cruelty by husband", "sexual assault outraging
  modesty").
- DO NOT invent, guess, or include any section numbers or article numbers (such as
  BNS 80, IPC 304B, Article 21). Section resolution is handled downstream.
- Each query must be ≤12 words.

Return ONLY valid JSON matching:
{{
    "search_queries": ["...", "...", "..."]
}}

Identified offences: {json.dumps(identified_offences)}
Keywords: {json.dumps(qu_input.get("keywords", []))}
Case summary: {qu_input.get("expanded_query", "")}
"""
        try:
            response = self.llm.invoke(prompt)
            content = response.content.strip()
            cleaned_content = re.sub(r"^```(?:json)?|```$", "", content, flags=re.MULTILINE).strip()
            json_match = re.search(r'\{.*\}', cleaned_content, re.DOTALL)
            if not json_match:
                print("[QueryExpansionService] No JSON object found in LLM response")
                return []
            parsed_json = json.loads(json_match.group(0))
            return [str(q) for q in (parsed_json.get("search_queries") or [])]
        except json.JSONDecodeError as e:
            print(f"[QueryExpansionService] JSON parsing error: {e}")
            return []
        except Exception as e:
            print(f"[QueryExpansionService] Error during LLM generation: {e}")
            return []

    # ------------------------------------------------------------------
    # Fallback: rule-based single-offence derivation, used only when every
    # candidate above is dropped as ungrounded (e.g. very sparse case facts).
    # ------------------------------------------------------------------
    def _fallback_offence(self, qu_input: Dict[str, Any], grounding_text: str) -> str:
        if qu_input.get("offences"):
            return str(qu_input["offences"][0]).strip().lower()

        q = grounding_text.lower()
        if "murder" in q or "culpable homicide" in q or "killed" in q:
            return "culpable homicide amounting to murder"
        if "rape" in q or "sexual assault" in q:
            return "sexual assault by penetration without consent"
        if "kidnap" in q or "abduct" in q:
            return "kidnapping or abduction from lawful guardianship"
        if "dowry" in q:
            return "dowry demand and harassment"
        if "cruelty" in q or "domestic violence" in q:
            return "cruelty by husband towards woman"
        if "cheque" in q or "dishonour" in q or "bounce" in q:
            return "dishonour of cheque for insufficiency of funds"
        if "breach of trust" in q or "misappropriat" in q or "embezzl" in q:
            return "criminal breach of trust by employee servant"
        if "cheat" in q or "fraud" in q or "deceiv" in q:
            return "cheating by inducing delivery of property"
        if "theft" in q or "robbery" in q or "dacoity" in q:
            return "theft or robbery of movable property"
        if "hack" in q or "unauthorised access" in q or "unauthorized access" in q:
            return "unauthorised access to computer resource"
        return "criminal offence against person or property"