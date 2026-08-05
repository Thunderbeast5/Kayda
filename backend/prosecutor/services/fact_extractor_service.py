"""
fact_extractor_service.py
=========================
Generic LLM-Based Legal Fact Extraction Taxonomy System.

Parses natural language user queries into a strict, generic legal fact JSON taxonomy
(Victim Attributes, Mental State, Physical Acts, Consent/Coercion, Property/Deception, Instrumentality),
with an automatic fallback to rule-based keyword extraction.
"""

import json
import re
from typing import Dict, Any

try:
    from config.llm_config import get_llm
except ModuleNotFoundError:
    from agents.config.llm_config import get_llm


FACT_TAXONOMY_SYSTEM_PROMPT = """You are a Senior Criminal Fact Extraction Specialist.
Your task is to analyze the user's factual query and extract elemental legal facts into a generic JSON taxonomy.

RULES:
1. Extract elemental LEGAL FACTS only (e.g. death, intent, consent, force, property, weapon). Do NOT guess crime sections or penal codes.
2. Do NOT hallucinate facts not stated or strongly implied.
3. Output valid JSON ONLY. No markdown wrapping, no extra text.

GENERIC LEGAL FACT TAXONOMY JSON SCHEMA:
{
  "person": {
    "victim_gender": "female" | "male" | "unspecified",
    "victim_age": integer or null,
    "marital_status": "married" | "unmarried" | "unspecified",
    "relationship_type": "spouse" | "relative_of_spouse" | "public_servant" | "authority_custody" | "stranger" | "unspecified"
  },
  "harm": {
    "death_occurred": true | false,
    "death_type": "burn" | "poison" | "asphyxia" | "injury" | "unnatural" | "natural" | "none",
    "physical_force_applied": true | false,
    "bodily_hurt_caused": true | false,
    "grievous_hurt_caused": true | false,
    "acid_or_corrosive_used": true | false
  },
  "mental_state": {
    "intent_to_cause_death": true | false,
    "knowledge_death_likely": true | false,
    "rashness_or_negligence": true | false,
    "intent_to_outrage_modesty": true | false,
    "intent_to_disrobe": true | false
  },
  "consent_and_coercion": {
    "consent_status": "freely_given" | "against_will" | "without_consent" | "consent_by_fear" | "consent_by_impersonation" | "consent_vitiated_incapacity" | "victim_under_18" | "unable_to_communicate" | "unspecified",
    "sexual_penetration": true | false,
    "disrobing_attempted": true | false,
    "coercion_or_extortion": true | false,
    "dowry_demand_made": true | false,
    "cruelty_subjected": true | false
  },
  "property_and_deception": {
    "property_involved": true | false,
    "deception_or_cheating": true | false,
    "deceitful_inducement_type": "false_marriage_promise" | "impersonation" | "false_employment" | "none",
    "wrongful_gain_or_loss": true | false
  },
  "instrumentality_and_restraint": {
    "weapons_used": [string],
    "wrongful_restraint_or_confinement": true | false,
    "communication_or_publication": true | false,
    "public_order_disruption": true | false
  },
  "marriage_duration": {
    "specified": true | false,
    "years": integer or null
  }
}
"""


class FactExtractorService:
    """Generic LLM & Rule-Based Legal Fact Taxonomy Extractor."""

    def __init__(self):
        try:
            self.llm = get_llm(temperature=0.0)
        except Exception as e:
            print(f"[FactExtractorService] LLM init info: {e}")
            self.llm = None

    def extract_facts(self, query: str) -> Dict[str, Any]:
        """
        Extracts generic legal facts into a unified taxonomy dictionary.
        Uses LLM structured extraction first; falls back to rule-based taxonomy if LLM fails.
        """
        if self.llm:
            try:
                return self._extract_facts_llm(query)
            except Exception as e:
                print(f"[FactExtractorService] LLM fact extraction warning ({e}); utilizing rule-based taxonomy fallback.")

        return self._extract_facts_rules(query)

    def _extract_facts_llm(self, query: str) -> Dict[str, Any]:
        prompt = f"{FACT_TAXONOMY_SYSTEM_PROMPT}\n\nUSER QUERY:\n\"{query}\"\n\nJSON OUTPUT:"
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

        # Robust JSON extraction — use raw_decode to stop at first complete object,
        # ignoring any trailing text or extra objects the LLM appends.
        json_match = re.search(r'\{', text_clean)
        if json_match:
            try:
                decoder = json.JSONDecoder()
                data, _ = decoder.raw_decode(text_clean, json_match.start())
            except json.JSONDecodeError:
                raise ValueError("No valid JSON object found in LLM response")
        else:
            raise ValueError("No JSON object found in LLM response")

        person = data.get("person") or {}
        harm = data.get("harm") or {}
        mens = data.get("mental_state") or {}
        consent = data.get("consent_and_coercion") or {}
        prop = data.get("property_and_deception") or {}
        inst = data.get("instrumentality_and_restraint") or {}
        m_dur = data.get("marriage_duration") or {}

        dur_spec = bool(m_dur.get("specified"))
        raw_years = m_dur.get("years")
        dur_years = int(raw_years) if (raw_years is not None and isinstance(raw_years, (int, float)) and raw_years >= 0) else None
        if dur_years is not None:
            dur_spec = True

        # Flattened canonical fact taxonomy object compatible with validator fact_keys
        return {
            # Person attributes
            "victim_gender": person.get("victim_gender", "unspecified"),
            "victim_age": person.get("victim_age"),
            "marital_status": person.get("marital_status", "unspecified"),
            "relationship_type": person.get("relationship_type", "unspecified"),

            # Physical Harm & Acts
            "death": bool(harm.get("death_occurred")),
            "death_type": harm.get("death_type", "none"),
            "physical_force_or_assault": bool(harm.get("physical_force_applied")),
            "bodily_hurt_caused": bool(harm.get("bodily_hurt_caused")),
            "grievous_hurt_or_disfigurement": bool(harm.get("grievous_hurt_caused")),
            "acid_or_corrosive": bool(harm.get("acid_or_corrosive_used")),

            # Mental state
            "intent_to_kill": bool(mens.get("intent_to_cause_death")),
            "knowledge_death_likely": bool(mens.get("knowledge_death_likely")),
            "rashness_or_negligence": bool(mens.get("rashness_or_negligence")),
            "inappropriate_touch_or_modesty": bool(mens.get("intent_to_outrage_modesty")),
            "disrobing_attempt": bool(mens.get("intent_to_disrobe")),

            # Consent & Coercion
            "consent_status": consent.get("consent_status", "unspecified"),
            "sexual_penetration": bool(consent.get("sexual_penetration")),
            "absence_of_consent": consent.get("consent_status") in ("against_will", "without_consent", "consent_by_fear", "consent_vitiated_incapacity") or bool(consent.get("sexual_penetration")),
            "coercion_or_extortion": bool(consent.get("coercion_or_extortion")),
            "dowry_demand": bool(consent.get("dowry_demand_made")),
            "cruelty_or_harassment": bool(consent.get("cruelty_subjected")),

            # Property & Deception
            "property_involved": bool(prop.get("property_involved")),
            "deception_or_cheating": bool(prop.get("deception_or_cheating")),
            "deceitful_inducement_type": prop.get("deceitful_inducement_type", "none"),
            "wrongful_gain_or_loss": bool(prop.get("wrongful_gain_or_loss")),

            # Instrumentality & Restraint
            "weapons": inst.get("weapons_used") or [],
            "kidnapping_or_abduction": bool(inst.get("wrongful_restraint_or_confinement")),
            "communication_or_publication": bool(inst.get("communication_or_publication")),
            "public_order_disruption": bool(inst.get("public_order_disruption")),

            # Marriage Duration
            "marriage_duration_specified": dur_spec,
            "marriage_duration_years": dur_years,

            "extraction_mode": "llm_taxonomy"
        }

    def _extract_facts_rules(self, query: str) -> Dict[str, Any]:
        q_lower = query.lower()

        # --- Existing detections (offences against women, dowry, assault, violence, etc.) ---
        is_female = any(w in q_lower for w in ["woman", "female", "wife", "girl", "mother", "daughter", "sister", "she", "her"])
        is_married = any(w in q_lower for w in ["married", "husband", "wife", "in-laws", "marriage", "matrimonial", "dowry"])

        death = any(w in q_lower for w in ["death", "died", "killed", "murder", "unnatural death", "homicide", "body", "deceased", "burned"])
        burn_death = any(w in q_lower for w in ["burn", "fire", "flames", "kerosene"])
        
        dur_spec = False
        duration_years = None
        m_dur = re.search(r"(\d+)\s*years?\s*of\s*marriage", q_lower) or re.search(r"married\s*for\s*(\d+)\s*years?", q_lower)
        if m_dur:
            try:
                duration_years = int(m_dur.group(1))
                dur_spec = True
            except ValueError:
                pass

        lethal_act = any(w in q_lower for w in ["kerosene", "set on fire", "burned alive", "stabbed", "shot", "strangled", "poisoned", "murdered", "intent to kill"])
        dowry = any(w in q_lower for w in ["dowry", "demands", "money demand", "cash demand", "vehicle demand"])
        cruelty = any(w in q_lower for w in ["cruelty", "harassment", "torture", "beaten", "harassed", "abuse", "repeatedly"])
        assault = any(w in q_lower for w in ["assault", "force", "grabbed", "pushed", "struck", "slapped", "beaten", "hit"])
        modesty = any(w in q_lower for w in ["modesty", "inappropriate", "touch", "touched", "groped", "molested", "indecent", "embraced"])
        disrobing = any(w in q_lower for w in ["disrobe", "remove clothes", "clothes", "naked", "strip", "undress"])
        penetration = any(w in q_lower for w in ["penetrat", "intercourse", "raped", "rape", "sexual assault", "penetrated"])
        consent_explicitly_given = any(w in q_lower for w in ["consensual", "with consent", "with her consent", "voluntarily"])
        consent_explicitly_absent = any(w in q_lower for w in ["against her will", "without consent", "forcibly", "forced", "against his will", "against their will"])
        consent_absent = consent_explicitly_absent and not consent_explicitly_given
        acid = any(w in q_lower for w in ["acid", "corrosive", "chemical attack"])
        grievous_hurt = any(w in q_lower for w in ["grievous hurt", "disfigurement", "permanent scar", "blinded", "burns"])
        kidnapping = any(w in q_lower for w in ["kidnap", "abduct", "confinement", "detained", "hostage"])

        # --- NEW: Cheating / Fraud / Financial Offences (anticipatory bail context) ---
        # Detect deception or cheating (covers fraud, misrepresentation, inducement, etc.)
        cheating = any(w in q_lower for w in [
            "cheat", "cheating", "fraud", "fraudulent", "dishonest", "misrepresent",
            "false promise", "induce", "inducement", "scam", "deceit", "deceive"
        ])
        # Detect property / money involvement (including currency amounts)
        property_involved = any(w in q_lower for w in [
            "property", "money", "funds", "investment", "returns", "financial",
            "₹", "lakh", "crore", "payment", "transaction", "amount"
        ]) or cheating  # cheating almost always involves property
        # Detect wrongful gain or loss (diversion, misappropriation, etc.)
        wrongful_gain = any(w in q_lower for w in [
            "wrongful", "diverted", "misappropriat", "loss", "gain", "profit",
            "conversion", "embezzle", "pocket", "misuse"
        ])

        # Dowry also implies property involvement and possibly wrongful gain
        if dowry:
            property_involved = True
            wrongful_gain = True

        # Return the flattened fact dictionary with all flags
        return {
            "victim_gender": "female" if is_female else "unspecified",
            "victim_age": None,
            "marital_status": "married" if is_married else "unspecified",
            "relationship_type": "spouse" if is_married else "unspecified",
            "death": death,
            "death_type": "burn" if (death and burn_death) else ("unnatural" if death else "none"),
            "physical_force_or_assault": assault,
            "bodily_hurt_caused": assault or death,
            "grievous_hurt_or_disfigurement": grievous_hurt,
            "acid_or_corrosive": acid,
            "intent_to_kill": lethal_act,
            "knowledge_death_likely": lethal_act or death,
            "rashness_or_negligence": False,
            "inappropriate_touch_or_modesty": modesty,
            "disrobing_attempt": disrobing,
            "consent_status": "without_consent" if consent_absent else ("freely_given" if consent_explicitly_given else "unspecified"),
            "sexual_penetration": penetration,
            "absence_of_consent": consent_absent,
            "coercion_or_extortion": dowry or cruelty,
            "dowry_demand": dowry,
            "cruelty_or_harassment": cruelty,
            "property_involved": property_involved,              # UPDATED
            "deception_or_cheating": cheating,                   # UPDATED
            "deceitful_inducement_type": "false_marriage_promise" if (cheating and "marriage" in q_lower) else ("none"),
            "wrongful_gain_or_loss": wrongful_gain,              # UPDATED
            "weapons": ["kerosene/fire"] if burn_death else [],
            "kidnapping_or_abduction": kidnapping,
            "communication_or_publication": False,
            "public_order_disruption": False,
            "marriage_duration_specified": dur_spec,
            "marriage_duration_years": duration_years,
            "extraction_mode": "rules_taxonomy_fallback"
        }