"""
enrich_scenarios_dataset.py
===========================
Refined benchmark scenario enrichment script.

Applies the following high-precision evaluation fields to every scenario:
- difficulty
- expected_top1
- expected_top3
- expected_rejected_sections
- expected_evidence
- expected_landmark_cases
- expected_constitution_articles
- expected_legal_principles
- expected_fact_extraction (structured legal fact tags)
- expected_ingredient_validation (specific statutory element keys)
- expected_confidence_range (calibrated [min, max])
- expected_community (GDS community cluster ID)
- expected_pipeline_stage (stage tracking dict)
"""

import sys
import re
import json
from pathlib import Path

EVIDENCE_TYPE_MAP = {
    "post-mortem": "Postmortem Report",
    "post mortem": "Postmortem Report",
    "autopsy": "Postmortem Report",
    "fsl": "FSL Report",
    "forensic": "FSL Report",
    "ballistic": "FSL Report",
    "dna": "DNA Report",
    "weapon": "Weapon Recovery Memo",
    "panchnama": "Inquest Report",
    "inquest": "Inquest Report",
    "eyewitness": "Witness Statement",
    "witness": "Witness Statement",
    "statement": "Witness Statement",
    "dying declaration": "Dying Declaration",
    "cctv": "CCTV Footage",
    "video": "CCTV Footage",
    "camera": "CCTV Footage",
    "audio": "Audio Recording",
    "call": "Call Detail Records (CDR)",
    "cdr": "Call Detail Records (CDR)",
    "phone": "Call Detail Records (CDR)",
    "whatsapp": "WhatsApp Chats",
    "chat": "WhatsApp Chats",
    "bank": "Bank Transaction",
    "financial": "Bank Transaction",
    "receipt": "Bank Transaction",
    "marriage": "Marriage Certificate",
    "wedding": "Marriage Certificate",
    "birth": "Birth Certificate",
    "age": "Birth Certificate",
    "medical": "Medical Report",
    "injury": "Medical Report",
    "doctor": "Medical Report",
    "hospital": "Medical Report"
}

def map_required_evidence(evidence_list):
    mapped = []
    for item in evidence_list:
        item_lower = item.lower()
        matched = False
        for kw, canonical in EVIDENCE_TYPE_MAP.items():
            if kw in item_lower:
                if canonical not in mapped:
                    mapped.append(canonical)
                matched = True
        if not matched and len(item) < 40:
            if item not in mapped:
                mapped.append(item)
    if not mapped:
        mapped = ["Witness Statement", "Medical Report"]
    return mapped

def extract_case_names(landmark_cases_list):
    names = []
    for item in landmark_cases_list:
        match = re.match(r"^([^,]+)", item)
        if match:
            cname = match.group(1).strip()
            if cname not in names:
                names.append(cname)
        else:
            names.append(item)
    return names

def derive_difficulty(scenario):
    if scenario["is_negative_example"]:
        return "Hard"
    
    cat = scenario["category"]
    bns = scenario["expected_bns_sections"]
    notes = scenario.get("notes", "").lower()
    
    if len(bns) > 2 or "exception" in notes or "boundary" in notes:
        return "Hard"
    if cat in ["Murder", "Sexual Offences", "Dowry Death"] and ("rarest of rare" in notes or "constitutional" in notes):
        return "Judge"
    if len(bns) == 2:
        return "Medium"
    return "Easy"

def derive_constitution_articles(category, facts, landmark_cases):
    cat_lower = category.lower()
    facts_lower = facts.lower()
    articles = []
    
    # Only populate constitution articles where landmark constitutional rulings or rights explicitly apply
    if "murder" in cat_lower and ("death penalty" in facts_lower or "rarest of rare" in str(landmark_cases).lower()):
        articles.append("Article 21 - Right to Life and Personal Liberty")
    elif "dowry" in cat_lower or "cruelty" in cat_lower:
        articles.append("Article 14 - Right to Equality")
        articles.append("Article 21 - Protection of Life and Personal Liberty")
    elif "defamation" in cat_lower:
        articles.append("Article 19(1)(a) - Freedom of Speech and Expression")
        articles.append("Article 21 - Protection of Reputation and Privacy")
    elif "sexual" in cat_lower and ("rape" in facts_lower or "dignity" in facts_lower):
        articles.append("Article 21 - Protection of Life and Dignity")
        
    return articles

def derive_legal_principles(category, facts, is_neg):
    if is_neg:
        return ["Absence of Actus Reus", "Voluntary Action of Deceased/Victim", "Failure of Statutory Ingredients"]
    
    cat_lower = category.lower()
    principles = ["Actus Reus", "Mens Rea"]
    
    if "murder" in cat_lower:
        principles.extend(["Intention to Cause Death", "Culpable Homicide", "Doctrine of Premeditation"])
    elif "dowry" in cat_lower:
        principles.extend(["Presumption of Dowry Death", "Cruelty Soon Before Death", "Unnatural Death within 7 Years"])
    elif "cruelty" in cat_lower:
        principles.extend(["Wilful Conduct Driving to Suicide", "Harassment for Unlawful Demand", "Domestic Cruelty"])
    elif "theft" in cat_lower:
        principles.extend(["Dishonest Intention to Take Movable Property", "Absence of Consent", "Moving Property"])
    elif "robbery" in cat_lower:
        principles.extend(["Theft by Violence or Fear of Instant Hurt", "Extortion under Fear", "Use of Force"])
    elif "extortion" in cat_lower:
        principles.extend(["Intentionally Putting in Fear of Injury", "Dishonest Inducement", "Delivery of Property"])
    elif "cheating" in cat_lower:
        principles.extend(["Deceitful Inducement", "Fraudulent/Dishonest Intention at Inception", "Wrongful Loss"])
    elif "kidnapping" in cat_lower:
        principles.extend(["Taking/Enticing Minor out of Lawful Guardianship", "Without Guardian Consent"])
    elif "defamation" in cat_lower:
        principles.extend(["Harm to Reputation", "Publication of Defamatory Matter", "Exceptions to Defamation"])
    elif "intimidation" in cat_lower:
        principles.extend(["Threat of Injury to Person/Property", "Intent to Cause Alarm", "Criminal Intimidation"])
    elif "assault" in cat_lower:
        principles.extend(["Criminal Force", "Outraging Modesty of Woman", "Apprehension of Violence"])
    elif "sexual" in cat_lower:
        principles.extend(["Absence of Consent", "Sexual Penetration", "Vitiating Consent Circumstance", "Protection of Female Safety"])
        
    return principles

def derive_structured_fact_extraction(category, facts):
    """Generates structured legal fact tags rather than plain sentence strings."""
    f_lower = facts.lower()
    tags = []
    
    # Intent / Mental State
    if any(w in f_lower for w in ["planning", "premeditated", "planned", "weeks of"]):
        tags.append("premeditation")
    if any(w in f_lower for w in ["shoot", "shoots", "stab", "stabs", "kill", "firearm", "pistol", "gun"]):
        tags.append("intent to kill")
        tags.append("use of lethal weapon")
    if any(w in f_lower for w in ["dispute", "land", "feud", "grudge", "money"]):
        tags.append("motive: dispute")
    if any(w in f_lower for w in ["death", "died", "fatal", "killed", "burned alive"]):
        tags.append("death of victim")
    if any(w in f_lower for w in ["burn", "fire", "kerosene"]):
        tags.append("unnatural death by burning")
    if any(w in f_lower for w in ["dowry", "demands", "cash"]):
        tags.append("dowry demand")
    if any(w in f_lower for w in ["harass", "beaten", "torture", "cruelty"]):
        tags.append("cruelty by husband/relatives")
    if any(w in f_lower for w in ["pocket", "bag", "conceal", "stole", "takes"]):
        tags.append("dishonest taking of property")
    if any(w in f_lower for w in ["without consent", "against her will", "forcibly"]):
        tags.append("absence of consent")
    if any(w in f_lower for w in ["knife", "weapon", "gun", "pistol"]):
        tags.append("use of weapon")
    if any(w in f_lower for w in ["threat", "threatened", "kill", "harm"]):
        tags.append("threat of injury")
    if any(w in f_lower for w in ["promise of marriage", "false promise", "cheated"]):
        tags.append("deceitful inducement")
    if any(w in f_lower for w in ["girl", "minor", "child", "17-year-old", "under 18"]):
        tags.append("minor victim")
    if any(w in f_lower for w in ["newspaper", "published", "post", "social media"]):
        tags.append("publication of defamatory matter")

    if not tags:
        tags = ["elemental legal facts present", "acts committed"]
    return tags

def derive_specific_ingredient_validation(expected_bns, category, is_neg):
    """Generates specific statutory ingredient element keys rather than generic Actus/Mens/Circumstance."""
    validation = {}
    cat_lower = category.lower()
    
    for sec in expected_bns:
        sec_key = "BNS " + sec if not sec.startswith("BNS") else sec
        if is_neg:
            if "murder" in cat_lower:
                validation[sec_key] = {"death_of_person": False, "intent_to_cause_death": False, "causal_connection": False}
            elif "dowry" in cat_lower:
                validation[sec_key] = {"unnatural_death": False, "dowry_demand": False, "cruelty_soon_before_death": False}
            elif "theft" in cat_lower:
                validation[sec_key] = {"taking_without_consent": False, "dishonest_intention": False}
            elif "kidnap" in cat_lower:
                validation[sec_key] = {"taking_minor_out_of_custody": False, "absence_of_guardian_consent": False}
            else:
                validation[sec_key] = {"actus_reus_satisfied": False, "mens_rea_satisfied": False}
        else:
            if "murder" in cat_lower or "103" in sec or "101" in sec or "105" in sec:
                validation[sec_key] = {
                    "death_of_person": True,
                    "intent_to_cause_death": True,
                    "premeditation": True,
                    "causal_connection": True
                }
            elif "dowry" in cat_lower or "80" in sec:
                validation[sec_key] = {
                    "unnatural_death": True,
                    "woman_victim": True,
                    "within_7_years_marriage": True,
                    "dowry_demand": True,
                    "cruelty_soon_before_death": True
                }
            elif "cruelty" in cat_lower or "85" in sec:
                validation[sec_key] = {
                    "married_woman": True,
                    "husband_or_relative": True,
                    "cruelty_or_harassment": True,
                    "coercion_for_property": True
                }
            elif "theft" in cat_lower or "303" in sec:
                validation[sec_key] = {
                    "movable_property": True,
                    "dishonest_intention": True,
                    "taking_without_consent": True,
                    "moving_property": True
                }
            elif "robbery" in cat_lower or "309" in sec:
                validation[sec_key] = {
                    "theft_committed": True,
                    "instant_death_hurt_or_fear": True,
                    "voluntary_force_or_restraint": True
                }
            elif "extortion" in cat_lower or "308" in sec:
                validation[sec_key] = {
                    "fear_of_injury": True,
                    "dishonest_inducement": True,
                    "delivery_of_property": True
                }
            elif "cheating" in cat_lower or "318" in sec:
                validation[sec_key] = {
                    "deceitful_inducement": True,
                    "dishonest_intention_at_inception": True,
                    "wrongful_loss": True
                }
            elif "kidnap" in cat_lower or "137" in sec:
                validation[sec_key] = {
                    "minor_victim": True,
                    "lawful_guardianship": True,
                    "taking_without_consent": True
                }
            elif "defamation" in cat_lower or "356" in sec:
                validation[sec_key] = {
                    "defamatory_imputation": True,
                    "intent_to_harm_reputation": True,
                    "publication": True
                }
            elif "intimidation" in cat_lower or "351" in sec:
                validation[sec_key] = {
                    "threat_of_injury": True,
                    "intent_to_cause_alarm": True,
                    "person_or_property": True
                }
            elif "assault" in cat_lower or "130" in sec or "74" in sec:
                validation[sec_key] = {
                    "assault_or_criminal_force": True,
                    "woman_victim": True,
                    "intent_to_outrage_modesty": True
                }
            elif "sexual" in cat_lower or "63" in sec or "64" in sec:
                validation[sec_key] = {
                    "female_victim": True,
                    "sexual_penetration": True,
                    "absence_of_consent": True
                }
            else:
                validation[sec_key] = {
                    "actus_reus_satisfied": True,
                    "mens_rea_satisfied": True,
                    "statutory_ingredients_met": True
                }
    if not validation:
        validation["BNS Boundary Section"] = {
            "actus_reus_satisfied": False,
            "mens_rea_satisfied": False
        }
    return validation

def derive_calibrated_confidence_range(difficulty, is_neg):
    if is_neg:
        return [0.10, 0.35]
    if difficulty == "Easy":
        return [0.90, 1.00]
    elif difficulty == "Medium":
        return [0.82, 0.95]
    elif difficulty == "Hard":
        return [0.68, 0.85]
    else:  # Judge
        return [0.70, 0.88]

def derive_expected_community(category):
    cat_lower = category.lower()
    if "murder" in cat_lower:
        return "homicide"
    elif "dowry" in cat_lower or "cruelty" in cat_lower:
        return "dowry_and_matrimonial"
    elif "sexual" in cat_lower or "assault" in cat_lower:
        return "women_offences"
    elif any(k in cat_lower for k in ["theft", "robbery", "extortion", "cheating"]):
        return "property_offences"
    elif "kidnap" in cat_lower:
        return "body_offences"
    elif "defamation" in cat_lower or "intimidation" in cat_lower:
        return "speech_offences"
    return "general_offences"

def derive_pipeline_stage(is_neg):
    if is_neg:
        return {
            "pinecone": True,
            "graph": True,
            "community": True,
            "llm_reasoning": False
        }
    return {
        "pinecone": True,
        "graph": True,
        "community": True,
        "llm_reasoning": True
    }

def py_repr(val):
    if val is True:
        return "True"
    elif val is False:
        return "False"
    elif val is None:
        return "None"
    elif isinstance(val, str):
        return repr(val)
    elif isinstance(val, (int, float)):
        return str(val)
    elif isinstance(val, list):
        items = [py_repr(item) for item in val]
        return "[" + ", ".join(items) + "]"
    elif isinstance(val, dict):
        items = [f"{py_repr(k)}: {py_repr(v)}" for k, v in val.items()]
        return "{" + ", ".join(items) + "}"
    return repr(val)


def main():
    raw_path = Path("context/agent_context/scenarios_data.py")
    raw_text = raw_path.read_text(encoding="utf-8")
    
    cleaned = re.sub(r'\bfalse\b', 'False', raw_text)
    cleaned = re.sub(r'\btrue\b', 'True', cleaned)
    cleaned = re.sub(r'\bnull\b', 'None', cleaned)

    local_env = {}
    exec(cleaned, local_env)
    scenarios = local_env["SCENARIOS"]
    
    print(f"Refining {len(scenarios)} scenarios with high-precision evaluation metadata...")

    lines = []
    lines.append('# -*- coding: utf-8 -*-')
    lines.append('"""')
    lines.append('BNS/IPC Legal-Mapping Benchmark — Refined Evaluation Scenario Dataset (Phase 6)')
    lines.append('=============================================================================')
    lines.append('Ground-truth benchmark scenarios for evaluating legal GraphRAG & AI reasoning.')
    lines.append('Contains comprehensive evaluation metadata: difficulty, top predictions,')
    lines.append('rejected sections, landmark cases, constitutional articles, structured legal fact tags,')
    lines.append('specific statutory ingredient validation schemas, calibrated confidence intervals,')
    lines.append('expected community cluster IDs, and pipeline stage execution flags.')
    lines.append('"""')
    lines.append('')
    lines.append('SCENARIOS = [')

    for s in scenarios:
        sid = s["id"]
        cat = s["category"]
        facts = s["facts"]
        exp_bns = s["expected_bns_sections"]
        exp_ipc = s["expected_ipc_sections"]
        req_ev = s["required_evidence"]
        cases = s["landmark_cases"]
        is_neg = bool(s["is_negative_example"])
        notes = s["notes"]

        diff = derive_difficulty(s)
        
        if is_neg:
            top1 = None
            top3 = []
        else:
            top1 = "BNS " + exp_bns[0] if exp_bns else "BNS 101"
            top3 = ["BNS " + sec for sec in exp_bns]

        rejected = s.get("expected_rejected_sections") or []
        mapped_ev = map_required_evidence(req_ev)
        case_names = extract_case_names(cases)
        const_arts = derive_constitution_articles(cat, facts, cases)
        principles = derive_legal_principles(cat, facts, is_neg)
        
        # Refined Fields
        structured_facts = derive_structured_fact_extraction(cat, facts)
        specific_ing_val = derive_specific_ingredient_validation(exp_bns, cat, is_neg)
        calibrated_conf = derive_calibrated_confidence_range(diff, is_neg)
        exp_community = derive_expected_community(cat)
        pipeline_stage = derive_pipeline_stage(is_neg)

        # Build python snippet for scenario
        lines.append('    {')
        lines.append(f'        "id": {py_repr(sid)},')
        lines.append(f'        "category": {py_repr(cat)},')
        lines.append(f'        "facts": {py_repr(facts)},')
        lines.append(f'        "expected_bns_sections": {py_repr(exp_bns)},')
        lines.append(f'        "expected_ipc_sections": {py_repr(exp_ipc)},')
        lines.append(f'        "required_evidence": {py_repr(req_ev)},')
        lines.append(f'        "landmark_cases": {py_repr(cases)},')
        lines.append(f'        "is_negative_example": {py_repr(is_neg)},')
        lines.append(f'        "notes": {py_repr(notes)},')
        
        # Refined Evaluation Fields
        lines.append(f'        "difficulty": {py_repr(diff)},')
        lines.append(f'        "expected_top1": {py_repr(top1)},')
        lines.append(f'        "expected_top3": {py_repr(top3)},')
        lines.append(f'        "expected_rejected_sections": {py_repr(rejected)},')
        lines.append(f'        "expected_evidence": {py_repr(mapped_ev)},')
        lines.append(f'        "expected_landmark_cases": {py_repr(case_names)},')
        lines.append(f'        "expected_constitution_articles": {py_repr(const_arts)},')
        lines.append(f'        "expected_legal_principles": {py_repr(principles)},')
        lines.append(f'        "expected_fact_extraction": {py_repr(structured_facts)},')
        lines.append(f'        "expected_ingredient_validation": {py_repr(specific_ing_val)},')
        lines.append(f'        "expected_confidence_range": {py_repr(calibrated_conf)},')
        lines.append(f'        "expected_community": {py_repr(exp_community)},')
        lines.append(f'        "expected_pipeline_stage": {py_repr(pipeline_stage)}')
        lines.append('    },')

    lines.append(']')
    lines.append('')

    content = "\n".join(lines)
    
    path1 = Path("context/agent_context/scenarios_data.py")
    path1.write_text(content, encoding="utf-8")
    print(f"Successfully updated: {path1.resolve()} ({len(content)} bytes)")

    path2 = Path("data/scenarios_data.py")
    path2.parent.mkdir(parents=True, exist_ok=True)
    path2.write_text(content, encoding="utf-8")
    print(f"Successfully saved copy to: {path2.resolve()} ({len(content)} bytes)")

if __name__ == "__main__":
    main()
