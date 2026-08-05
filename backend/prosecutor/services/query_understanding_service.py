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

    Converts raw case-fact text into structured legal concepts that feed the
    QueryExpansionService prompt (Query Decomposition was reverted — see
    lexigraph_agent.py header note — because it hallucinated offences and
    aggravating/mitigating facts not present in the input; this service and
    QueryExpansionService are now the sole query-analysis stage).

    Domain scope
    ------------
    Kayda AI now runs anticipatory-bail analysis across the ENTIRE Indian
    criminal-law domain, not just offences against women/children. This
    service must recognise and extract concepts across all major offence
    families: violent/human-body offences, property offences, matrimonial/
    women-and-children offences, financial crime, cyber crime, public-order
    offences, corruption, and narcotics. The `offences` examples and
    `primary_intent_community` taxonomy below have been broadened accordingly.

    What this service produces and where each field is consumed
    -----------------------------------------------------------
    offences                → injected as JSON context into the QES prompt so the
                              LLM knows which substantive offences have been
                              identified before it writes OFFENCE sub-queries.
    keywords                → injected into the QES prompt (same reason) + logged
                              by pipeline_debug_service.log_query for tracing.
    expanded_query           → injected into the QES prompt as a semantically
                              richer restatement of the raw facts, and used as
                              the grounding text for the anti-hallucination
                              overlap filter in QueryExpansionService.
    aggravating_factors      → passed through VERBATIM (no further LLM rewriting)
                              into AGGRAVATION sub-queries by QueryExpansionService.
                              Each entry MUST be a fact explicitly stated in the
                              raw query — never inferred, generalised, or invented.
    mitigating_factors       → same contract as aggravating_factors, for facts
                              that support granting anticipatory bail.
    crime_type               → injected into the QES prompt so it knows whether to
                              generate one or multiple OFFENCE sub-queries.
    primary_intent_community → logged by pipeline_debug_service.log_query only.
                              It is NOT used in Pinecone retrieval (IPC-only index
                              has no community namespace) and NOT used by
                              community_retrieval_service in the current pipeline.
                              We still produce it so the debug trace is
                              meaningful, but we do NOT apply brittle keyword
                              rules to force-override the LLM's answer, except
                              for a narrow safety-override list below.

    Design principles
    -----------------
    - No hardcoded keyword rules that break outside the original offence domain.
    - The LLM decides community; we only fall back to "general_offences" when
      the LLM returns nothing or an invalid value.
    - The women_offences / children_offences safety overrides are kept ONLY for
      specific unambiguous markers where mis-classification has downstream
      legal-safety implications (e.g. DPA / POCSO sections being missed).
    - Aggravating/mitigating factors must be extraction, not composition: the
      LLM is instructed to lift facts near-verbatim from the case text, never
      to synthesise a fact that "would make sense" given the offence type.
    """

    _VALID_COMMUNITIES = frozenset({
        "women_offences", "children_offences", "human_body_offences",
        "property_offences", "financial_crime", "cyber_crime",
        "public_order_offences", "corruption_offences", "narcotics_offences",
        "general_offences",
    })

    # Only these markers trigger a hard override of the LLM community choice.
    # They represent cases where mis-classification has downstream legal safety
    # implications (e.g., DPA / POCSO sections being missed). Deliberately kept
    # narrow — broad keyword overrides are exactly what caused hallucination-
    # adjacent misrouting before, so new entries should only be added for
    # similarly unambiguous, high-stakes markers.
    _SAFETY_OVERRIDE_SIGNALS: Dict[str, str] = {
        # signal_substring : community_to_force
        "rape":               "women_offences",
        "sexual assault":     "women_offences",
        "acid attack":        "women_offences",
        "outrage of modesty": "women_offences",
        "pocso":              "children_offences",
        "child sexual":       "children_offences",
    }

    def __init__(self):
        self.llm = get_llm(temperature=0.0)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def analyze_query(self, query: str) -> Dict[str, Any]:
        """
        Analyzes the case facts and returns a structured dict for QES consumption.
        """
        prompt = f"""You are QueryUnderstandingService, a legal NLP component for Indian criminal law,
supporting anticipatory-bail analysis across the FULL breadth of Indian criminal law —
not only offences against women and children.

Your task: read the case facts below and extract structured legal concepts.
This output will be used by a downstream query expansion step — be accurate, concise,
and NEVER invent a detail that is not explicitly present in the facts.

TASKS
1. crime_type: "Single offence", "Multiple offences", or "Unknown offence".
2. offences: list every substantive offence the facts describe, using plain legal names.
   Draw from the FULL domain, e.g.:
     Violent/human-body: Murder, Attempt to Murder, Culpable Homicide, Assault,
       Voluntarily Causing Hurt, Grievous Hurt, Wrongful Restraint, Wrongful Confinement,
       Causing Death by Negligence.
     Matrimonial/women & children: Cruelty, Dowry Demand, Dowry Death, Domestic Violence,
       Rape, Sexual Harassment, Stalking, Acid Attack, Kidnapping, Child Sexual Abuse,
       Human Trafficking.
     Property: Theft, Robbery, Dacoity, Criminal Trespass, House-breaking, Mischief,
       Extortion.
     Financial: Cheating, Criminal Breach of Trust, Forgery, Cheque Dishonour,
       Criminal Conspiracy to Defraud, Money Laundering.
     Cyber: Unauthorized Access/Hacking, Identity Theft, Cyberstalking,
       Obscene Electronic Transmission, Online Fraud/Phishing.
     Public order/corruption/narcotics: Rioting, Unlawful Assembly, Promoting Enmity
       Between Groups, Defamation, Bribery, Criminal Misconduct by Public Servant,
       Possession/Trafficking of Narcotic Drugs.
   List ONLY offences whose elements are actually described in the facts — do not add
   an offence just because a related one is present (e.g. do not add "Criminal
   Intimidation" unless a threat is explicitly stated).
3. keywords: 6–12 legal keywords for semantic search (offence terms, legal concepts,
   not generic words like "accused" or "police").
4. expanded_query: one legally precise sentence summarising the facts, preserving
   every material detail (amounts, relationships, mechanism of offence, defences raised).
5. aggravating_factors: facts EXPLICITLY stated in the case that would weigh AGAINST
   granting anticipatory bail — e.g. flight risk, threats to witnesses, tampering with
   evidence, brutality/premeditation, repeat/habitual offending, absconding, prior
   criminal record, position of dominance over victim, large financial amounts involved.
   Each entry must closely paraphrase an actual stated fact. Return [] if none stated.
   NEVER invent an aggravating fact merely because it is typical for this offence type.
6. mitigating_factors: facts EXPLICITLY stated in the case that support GRANTING
   anticipatory bail — e.g. cooperation with investigation, no criminal antecedents,
   claim of false implication, matrimonial/business/civil dispute framing, settlement
   or compromise, delay in filing FIR, medical condition, minor/peripheral role, age,
   documentary (non-custodial) nature of remaining evidence. Each entry must closely
   paraphrase an actual stated fact. Return [] if none stated.
   NEVER invent a mitigating fact merely because it is typical for this offence type.
7. primary_intent_community: the single best-fit category for the facts:
   "women_offences" | "children_offences" | "human_body_offences" |
   "property_offences" | "financial_crime" | "cyber_crime" |
   "public_order_offences" | "corruption_offences" | "narcotics_offences" |
   "general_offences"

Return ONLY valid JSON. No markdown, no explanation.

Schema:
{{
    "crime_type": "",
    "offences": [],
    "keywords": [],
    "expanded_query": "",
    "aggravating_factors": [],
    "mitigating_factors": [],
    "primary_intent_community": ""
}}

Case facts:
"{query}"
"""
        try:
            response = self.llm.invoke(prompt)
            content  = response.content.strip()

            cleaned = re.sub(r"^```(?:json)?|```$", "", content, flags=re.MULTILINE).strip()
            json_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group(0))
                return self._normalize(parsed, query)
            print("[QueryUnderstandingService] No JSON found in LLM response.")
            return self._empty(query)

        except json.JSONDecodeError as e:
            print(f"[QueryUnderstandingService] JSON parse error: {e}")
            return self._empty(query)
        except Exception as e:
            print(f"[QueryUnderstandingService] LLM error: {e}")
            return self._empty(query)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _normalize(self, data: Dict[str, Any], raw_query: str) -> Dict[str, Any]:
        """
        Merge LLM output with minimal guard-rails:
          1. Trust the LLM's community if it returned a valid value.
          2. Fall back to "general_offences" if not.
          3. Apply a hard override ONLY for a small set of safety-critical signals
             (rape, POCSO, acid attack, child sexual abuse) where misclassification
             would cause the pipeline to miss mandatory protective statutes.
          4. Coerce aggravating/mitigating factors to clean string lists — drop
             empty/non-string entries rather than guessing at intent.
        """
        llm_community = str(data.get("primary_intent_community") or "").strip().lower()
        community = llm_community if llm_community in self._VALID_COMMUNITIES else "general_offences"

        # Safety overrides — must stay, but scope is intentionally narrow
        q_lower = raw_query.lower()
        for signal, forced_community in self._SAFETY_OVERRIDE_SIGNALS.items():
            if signal in q_lower:
                community = forced_community
                break

        aggravating = [
            str(f).strip() for f in (data.get("aggravating_factors") or [])
            if str(f).strip()
        ]
        mitigating = [
            str(f).strip() for f in (data.get("mitigating_factors") or [])
            if str(f).strip()
        ]

        return {
            "crime_type":               str(data.get("crime_type") or "Single offence"),
            "offences":                 list(data.get("offences") or []),
            "keywords":                 list(data.get("keywords") or []),
            "expanded_query":           str(data.get("expanded_query") or raw_query),
            "aggravating_factors":      aggravating,
            "mitigating_factors":       mitigating,
            "primary_intent_community": community,
        }

    def _empty(self, raw_query: str) -> Dict[str, Any]:
        """Fallback when LLM fails entirely — returns safe defaults."""
        return {
            "crime_type":               "Single offence",
            "offences":                 [],
            "keywords":                 [],
            "expanded_query":           raw_query,
            "aggravating_factors":      [],
            "mitigating_factors":       [],
            "primary_intent_community": "general_offences",
        }