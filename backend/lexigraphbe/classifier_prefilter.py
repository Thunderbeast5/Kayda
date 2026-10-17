"""
Local Statute Classifier & Pre-Filter Module for LexiGraph Backend.
Pre-filters 574+ IPC/BNS sections down to top candidate sections (5-10) using local TF-IDF & keyword matching.
Executes 100% locally in Python code with ZERO LLM API calls.
"""

import csv
import json
import logging
import math
import re
import threading
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Set, Tuple, Any
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

from .schemas import LegalConceptItem, LegalQueryObject, SubQueryItem


@dataclass
class SectionRule:
    """
    Statute Knowledge Base Rule definition mapping a section to its mandatory statutory ingredients,
    factual triggers, and canonical chapter/punishment metadata for data-driven verification.
    """
    section: str
    statute: str
    bns_equivalent: str
    title: str
    mandatory_ingredients: List[str]
    factual_triggers: List[str]
    chapter_number: str = "General Offence Chapter"
    chapter_title: str = "General Offences"
    punishment_minimum: Optional[str] = None
    punishment_maximum: Optional[str] = None  # Resolved via First Schedule ground truth
    fine: bool = True
    cognizable: bool = True
    bailable: bool = False
    subject_matter_scope: Optional[str] = None  # e.g., "MOVABLE_PROPERTY_ONLY"
    disqualifying_subject_matters: List[str] = field(default_factory=list)  # e.g. ["land", "plot", "real estate"]
    requires_trigger_gate: bool = False  # If True, section is eliminated when NO factual_trigger matches facts_text.
                                         # Use ONLY for sections requiring a specific life/body event that can NEVER
                                         # be described differently (death, rape, suicide).  Leave False for all
                                         # property/fraud/document offences whose vocabulary varies across cases.


STATUTE_KNOWLEDGE_BASE: List[SectionRule] = [
    SectionRule(
        section="304B",
        statute="IPC",
        bns_equivalent="80",
        title="Dowry Death",
        mandatory_ingredients=["death_of_woman", "within_7_years_of_marriage", "dowry_harassment_soon_before_death"],
        factual_triggers=["death", "deceased", "dead", "died", "suicide", "killed", "body", "post-mortem", "autopsy", "murdered"],
        chapter_number="XVI",
        chapter_title="Offences Affecting Life / Offences Against Woman",
        punishment_minimum="7 Years",
        punishment_maximum="Life Imprisonment",
        fine=True,
        cognizable=True,
        bailable=False,
        requires_trigger_gate=True,  # Death of woman is non-negotiable — if absent, section cannot apply
    ),
    SectionRule(
        section="307",
        statute="IPC",
        bns_equivalent="109",
        title="Attempt to Murder",
        mandatory_ingredients=["attempt_to_murder", "intent_to_cause_death"],
        factual_triggers=["attempt to murder", "intent to kill", "stab", "stabbed", "stabbing", "knife", "stabbed in chest", "shot", "strangled", "life-threatening", "attempted to kill", "hospitalized", "critical condition"],
        chapter_number="XVI",
        chapter_title="Offences Affecting Life",
        punishment_minimum=None,
        punishment_maximum="10 Years",
        fine=True,
        cognizable=True,
        bailable=False,
        requires_trigger_gate=True,  # Specific act of attempted killing must be present
    ),
    SectionRule(
        section="376",
        statute="IPC",
        bns_equivalent="64",
        title="Rape / Sexual Assault",
        mandatory_ingredients=["sexual_assault", "non_consensual_intercourse"],
        factual_triggers=["rape", "sexual assault", "intercourse", "sexually assaulted", "penetration", "molestation"],
        chapter_number="XVI",
        chapter_title="Sexual Offences",
        punishment_minimum="10 Years",
        punishment_maximum="Life Imprisonment",
        fine=True,
        cognizable=True,
        bailable=False,
        requires_trigger_gate=True,  # Sexual assault must be explicitly present — no vocabulary ambiguity
    ),
    SectionRule(
        section="498A",
        statute="IPC",
        bns_equivalent="85",
        title="Cruelty by Husband or Relatives",
        mandatory_ingredients=["marriage_relationship", "cruelty_or_dowry_harassment"],
        factual_triggers=["dowry", "cruelty", "harass", "torture", "in-laws", "matrimonial"],
        chapter_number="XXA",
        chapter_title="Of Cruelty by Husband or Relatives of Husband",
        punishment_minimum=None,
        punishment_maximum="3 Years",
        fine=True,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="Section 4",
        statute="Dowry Prohibition Act",
        bns_equivalent="Section 4",
        title="Penalty for demanding dowry",
        mandatory_ingredients=["unlawful_dowry_demand"],
        factual_triggers=["dowry demand", "demanded dowry", "demand of cash", "demand for property"],
        chapter_number="DP Act",
        chapter_title="Dowry Prohibition Offences",
        punishment_minimum="6 Months",
        punishment_maximum="2 Years",
        fine=True,
        cognizable=True,
        bailable=True,
    ),
    SectionRule(
        section="Section 3",
        statute="Dowry Prohibition Act",
        bns_equivalent="Section 3",
        title="Penalty for giving or taking dowry",
        mandatory_ingredients=["giving_or_taking_dowry"],
        factual_triggers=["give dowry", "given dowry", "take dowry", "took dowry", "received dowry", "paid cash"],
        chapter_number="DP Act",
        chapter_title="Dowry Prohibition Offences",
        punishment_minimum="5 Years",
        punishment_maximum="5 Years",
        fine=True,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="403",
        statute="IPC",
        bns_equivalent="314",
        title="Dishonest Misappropriation of Property",
        mandatory_ingredients=["movable_property", "dishonest_misappropriation_or_conversion"],
        factual_triggers=["misappropriated", "converted", "found property", "movable property", "money retained", "funds taken"],
        chapter_number="XVII",
        chapter_title="Offences Against Property",
        punishment_minimum=None,
        punishment_maximum="2 Years",
        fine=True,
        cognizable=False,
        bailable=True,
        subject_matter_scope="MOVABLE_PROPERTY_ONLY",
        disqualifying_subject_matters=["land", "plot", "real estate", "immovable property", "building", "flat", "field", "site"],
    ),
    SectionRule(
        section="406",
        statute="IPC",
        bns_equivalent="316",
        title="Criminal Breach of Trust",
        mandatory_ingredients=["entrustment_of_stridhan_or_property", "dishonest_misappropriation_or_refusal_to_return"],
        factual_triggers=["stridhan", "ornaments", "jewelry", "jewellery", "gold", "articles retained", "property not returned"],
        chapter_number="XVII",
        chapter_title="Criminal Breach of Trust",
        punishment_minimum=None,
        punishment_maximum="3 Years",
        fine=True,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="420",
        statute="IPC",
        bns_equivalent="318",
        title="Cheating and Dishonestly Inducing Delivery of Property",
        mandatory_ingredients=["deception_or_cheating", "dishonest_inducement_to_deliver_property"],
        # Stage 1 concept labels for land-fraud cases rarely contain "cheated" or "defrauded".
        # They use phrases like "Dishonest Transfer", "Fraudulent Sale", "Property Fraud".
        # These must be in the trigger list so the KB-driven loop in detect_factual_triggers
        # fires 420 when the concept bridge adds those terms to the facts text.
        factual_triggers=[
            "cheated", "defrauded", "deceived", "fake promise", "money induced",
            "false representation", "scam", "misrepresentation", "duped", "swindled",
            "dishonest transfer", "dishonestly transferred", "fraudulent transfer",
            "fraudulent sale", "fraudulent sale deed", "induced to sell",
            "induced to transfer", "dishonestly induced", "false title claim",
            "false ownership claim", "pretended to be owner", "fraudulently induced",
            "property fraud", "fraudulently obtained property",
        ],
        chapter_number="XVII",
        chapter_title="Offences Against Property / Cheating",
        punishment_minimum=None,
        punishment_maximum="7 Years",
        fine=True,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="468",
        statute="IPC",
        bns_equivalent="338",
        title="Forgery for Purpose of Cheating",
        mandatory_ingredients=["forgery_of_document", "intent_to_cheat"],
        factual_triggers=["forged document", "fake signature", "fabricated paper", "forgery", "falsified record"],
        chapter_number="XVIII",
        chapter_title="Offences Relating to Documents",
        punishment_minimum=None,
        punishment_maximum="7 Years",
        fine=True,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="465",
        statute="IPC",
        bns_equivalent="336",
        title="Forgery",
        mandatory_ingredients=["making_false_document", "intent_to_cause_damage_or_injury"],
        factual_triggers=["forgery", "forged", "false document", "fabricated", "counterfeit", "fake paper", "spurious"],
        chapter_number="XVIII",
        chapter_title="Offences Relating to Documents",
        punishment_minimum=None,
        punishment_maximum="2 Years",  # First Schedule IPC: 2 years or fine or both
        fine=True,
        cognizable=False,   # First Schedule: Non-cognizable
        bailable=True,      # First Schedule: Bailable
    ),
    SectionRule(
        section="423",
        statute="IPC",
        bns_equivalent="305",
        title="Dishonest or Fraudulent Execution of Deed Containing a False Statement",
        mandatory_ingredients=["execution_of_deed_or_transfer", "false_statement_of_consideration"],
        # IPC 423 targets the specific act of executing a deed that contains a false
        # statement — the characteristic act in land-fraud / sale-deed fraud cases.
        factual_triggers=[
            "false deed", "fraudulent deed", "fabricated transfer", "false consideration",
            "bogus document", "fictitious transfer",
            # Sale-deed fraud vocabulary
            "sale deed", "fraudulent sale deed", "fake sale deed", "forged sale deed",
            "executed deed", "executed sale deed", "fraudulent execution",
            "false statement in deed", "executed a false deed", "sham deed",
            "dishonest deed", "dishonest transfer", "dishonestly transferred",
            "fraudulently transferred", "fraudulent transfer", "fraudulent conveyance",
        ],
        chapter_number="XVII",
        chapter_title="Offences Relating to Property / Fraudulent Documents",
        punishment_minimum=None,
        punishment_maximum="2 Years",
        fine=True,
        cognizable=False,
        bailable=True,
    ),
    SectionRule(
        section="506",
        statute="IPC",
        bns_equivalent="351",
        title="Criminal Intimidation",
        mandatory_ingredients=["threat_of_injury_to_person_or_property"],
        factual_triggers=["threat", "threatened", "intimidat", "scared", "terrorised"],
        chapter_number="XXII",
        chapter_title="Criminal Intimidation, Insult and Annoyance",
        punishment_minimum=None,
        punishment_maximum="2 Years",
        fine=True,
        cognizable=False,
        bailable=True,
    ),
    SectionRule(
        section="323",
        statute="IPC",
        bns_equivalent="115",
        title="Voluntarily Causing Hurt",
        mandatory_ingredients=["voluntarily_causing_bodily_hurt"],
        factual_triggers=["assault", "beaten", "slapped", "physical violence", "hurt", "injured", "hit"],
        chapter_number="XVI",
        chapter_title="Voluntarily Causing Hurt",
        punishment_minimum=None,
        punishment_maximum="1 Year",
        fine=True,
        cognizable=False,
        bailable=True,
    ),
    SectionRule(
        section="324",
        statute="IPC",
        bns_equivalent="118(1)",
        title="Voluntarily Causing Hurt by Dangerous Weapons or Means",
        mandatory_ingredients=["voluntarily_causing_hurt", "dangerous_weapon_or_means"],
        factual_triggers=["knife", "kitchen knife", "blade", "stab", "stabbed", "stabbing", "dangerous weapon", "instrument for stabbing", "weapon recovered"],
        chapter_number="XVI",
        chapter_title="Offences Affecting Life / Hurt",
        punishment_minimum=None,
        punishment_maximum="3 Years",
        fine=True,
        cognizable=True,
        bailable=True,
    ),
    SectionRule(
        section="325",
        statute="IPC",
        bns_equivalent="117(2)",
        title="Voluntarily Causing Grievous Hurt",
        mandatory_ingredients=["voluntarily_causing_grievous_hurt"],
        factual_triggers=["grievous hurt", "hospitalized", "fracture", "severe injury", "serious bodily injury"],
        chapter_number="XVI",
        chapter_title="Offences Affecting Life / Hurt",
        punishment_minimum=None,
        punishment_maximum="7 Years",
        fine=True,
        cognizable=True,
        bailable=True,
    ),
    SectionRule(
        section="326",
        statute="IPC",
        bns_equivalent="118(2)",
        title="Voluntarily Causing Grievous Hurt by Dangerous Weapons or Means",
        mandatory_ingredients=["voluntarily_causing_grievous_hurt", "dangerous_weapon_or_stabbing_instrument"],
        factual_triggers=["grievous hurt", "knife", "stabbed", "kitchen knife", "hospitalized", "dangerous weapon", "stabbed with knife", "severe stab wound"],
        chapter_number="XVI",
        chapter_title="Offences Affecting Life / Hurt",
        punishment_minimum=None,
        punishment_maximum="10 Years",
        fine=True,
        cognizable=True,
        bailable=False,
    ),

    # Medical negligence causing death: death + negligent/rash medical treatment.
    # Candidate retrieval only; statutory ingredients and causation are verified downstream.
    SectionRule(
        section="304A", statute="IPC", bns_equivalent="106(1)",
        title="Causing Death by Negligence",
        mandatory_ingredients=["death", "rash_or_negligent_act", "causal_connection"],
        factual_triggers=[
            "death", "patient died", "death of patient", "medical negligence",
            "negligent treatment", "negligent medical act", "failure to provide timely treatment",
            "failure to arrange specialist", "failed to arrange timely specialist intervention", "ignored medical warnings", "ignored repeated warnings", "medical practitioner",
        ],
        chapter_number="XVI", chapter_title="Offences Affecting Life",
        punishment_minimum=None, punishment_maximum="2 Years",
        fine=True, cognizable=True, bailable=True, requires_trigger_gate=True,
    ),
    # Disappearance/destruction of evidence to screen an offender.
    # requires_trigger_gate=False: the concept label "Causing disappearance of evidence" or
    # "Destruction of document to prevent its production as evidence" already carries statutory
    # vocabulary; the BM25 index matches it. Gating on factual trigger phrases would block
    # retrieval because Stage-1 sub-queries describe the legal concept, not the raw act.
    SectionRule(
        section="201", statute="IPC", bns_equivalent="238",
        title="Causing Disappearance of Evidence of Offence",
        mandatory_ingredients=["knowledge_or_reason_to_believe_offence_committed", "causing_evidence_to_disappear_or_false_information", "intent_to_screen_offender"],
        factual_triggers=[
            "disappear", "disappearance", "destroyed evidence", "destroyed records",
            "destroyed monitoring records", "concealed evidence", "made evidence disappear",
            "tampered with evidence", "removed records", "suppressed records",
            "screen offender", "screen the offender", "screen accused",
            "destruction of document", "destroy document",
        ],
        chapter_number="XI", chapter_title="Of False Evidence and Offences Against Public Justice",
        punishment_minimum=None, punishment_maximum="As provided by IPC section 201",
        fine=True, cognizable=True, bailable=False, requires_trigger_gate=False,
    ),
    # Destruction of a document/electronic record to prevent production as evidence.
    # requires_trigger_gate=False: same reasoning as IPC 201 above.
    SectionRule(
        section="204", statute="IPC", bns_equivalent="241",
        title="Destruction of Document or Electronic Record to Prevent Its Production as Evidence",
        mandatory_ingredients=["document_or_electronic_record", "destruction_or_rendering_illegible", "intent_to_prevent_production_as_evidence"],
        factual_triggers=[
            "destruction of document", "destroyed document", "destroyed records",
            "destroyed monitoring records", "destroyed medical records",
            "destroyed hospital records", "concealed records",
            "prevent production", "prevented production", "withheld records",
            "prevent its production", "prevent production as evidence",
        ],
        chapter_number="XI", chapter_title="Of False Evidence and Offences Against Public Justice",
        punishment_minimum=None, punishment_maximum="2 Years",
        fine=True, cognizable=False, bailable=True, requires_trigger_gate=False,
    ),
    # Section 195A requires a threat; an instruction or request alone is insufficient.
    SectionRule(
        section="195A", statute="IPC", bns_equivalent="232",
        title="Threatening Any Person to Give False Evidence",
        mandatory_ingredients=["threat", "person_to_give_false_evidence"],
        factual_triggers=[
            "threatened witness", "threat to witness", "threatened staff",
            "threatened junior staff", "threat to give false evidence",
            "threatened to give false evidence",
        ],
        chapter_number="XI", chapter_title="Of False Evidence and Offences Against Public Justice",
        punishment_minimum=None, punishment_maximum="7 Years",
        fine=True, cognizable=True, bailable=False, requires_trigger_gate=True,
    ),


    # Driving-related offences must not be retrieved from medical-care negligence vocabulary.
    SectionRule(
        section="279", statute="IPC", bns_equivalent="281",
        title="Rash Driving or Riding on a Public Way",
        mandatory_ingredients=["driving_or_riding", "public_way", "rash_or_negligent_manner"],
        factual_triggers=["rash driving", "driving on a public way", "vehicle on public way", "riding on a public way"],
        chapter_number="XIII", chapter_title="Offences Relating to Public Safety",
        punishment_minimum=None, punishment_maximum="6 Months",
        fine=True, cognizable=True, bailable=True, requires_trigger_gate=True,
    ),
    # Rape provisions must not enter the shortlist from generic words such as manipulation.
    SectionRule(
        section="375", statute="IPC", bns_equivalent="63",
        title="Rape — Definition",
        mandatory_ingredients=["sexual_act_within_statutory_definition", "absence_of_valid_consent_or_other_statutory_condition"],
        factual_triggers=["rape", "sexual assault", "sexual intercourse", "penetration", "non-consensual intercourse"],
        chapter_number="XVI", chapter_title="Sexual Offences",
        punishment_minimum=None, punishment_maximum=None,
        fine=False, cognizable=True, bailable=False, requires_trigger_gate=True,
    ),
    # Section 466 is limited to specified public/court records and certificates.
    SectionRule(
        section="466", statute="IPC", bns_equivalent="337",
        title="Forgery of Record of Court or Public Register",
        mandatory_ingredients=["false_document", "record_of_court_or_public_register", "forgery"],
        factual_triggers=["court record", "record of a court", "public register", "register kept by public servant", "judicial record"],
        chapter_number="XVIII", chapter_title="Offences Relating to Documents",
        punishment_minimum=None, punishment_maximum="7 Years",
        fine=True, cognizable=True, bailable=False, requires_trigger_gate=True,
    ),

    # -----------------------------------------------------------------------
    # Noise-blocking entries — sections that BM25 retrieves from coincidental
    # term overlap but which require a domain-specific factual event absent in
    # a medical-negligence / hospital context. requires_trigger_gate=True means
    # the section is disqualified unless at least one trigger appears in gate_text.
    # -----------------------------------------------------------------------

    # IPC 169 — "Public servant unlawfully buying or bidding for property"
    # Retrieved because "officer" matches; requires an illegal property-purchase act.
    SectionRule(
        section="169", statute="IPC", bns_equivalent="169",
        title="Public Servant Unlawfully Buying or Bidding for Property",
        mandatory_ingredients=["public_servant", "purchasing_or_bidding_for_property", "prohibited_by_law_or_rules_of_conduct"],
        factual_triggers=["bought property", "purchased property", "bid for property", "public servant bought", "property purchased by officer"],
        chapter_number="IX", chapter_title="Of Offences by or Relating to Public Servants",
        punishment_minimum=None, punishment_maximum="2 Years",
        fine=True, cognizable=False, bailable=True, requires_trigger_gate=True,
    ),

    # IPC 376A — "Punishment for causing death or persistent vegetative state"
    # Retrieved from "death" + "medical"; requires a rape/sexual assault predicate.
    SectionRule(
        section="376A", statute="IPC", bns_equivalent="66",
        title="Punishment for Causing Death or Resulting in Persistent Vegetative State of Victim",
        mandatory_ingredients=["rape_or_sexual_assault_predicate", "causing_death_or_persistent_vegetative_state"],
        factual_triggers=["rape", "sexual assault", "sexually assaulted", "section 376", "gang rape", "penetration"],
        chapter_number="XVI", chapter_title="Sexual Offences",
        punishment_minimum="20 Years", punishment_maximum="Life or Death",
        fine=False, cognizable=True, bailable=False, requires_trigger_gate=True,
    ),

    # IPC 284 — "Negligent conduct with respect to poisonous substance"
    # Retrieved from "negligence" + "death"; requires a poison/toxic substance.
    SectionRule(
        section="284", statute="IPC", bns_equivalent="287",
        title="Negligent Conduct with Respect to Poisonous Substance",
        mandatory_ingredients=["poisonous_or_corrosive_substance", "negligent_handling_or_keeping"],
        factual_triggers=["poison", "poisonous substance", "toxic substance", "corrosive", "venom", "chemical hazard", "acid"],
        chapter_number="XIV", chapter_title="Of Offences Affecting the Public Health, Safety, Convenience, Decency and Morals",
        punishment_minimum=None, punishment_maximum="6 Months",
        fine=True, cognizable=False, bailable=True, requires_trigger_gate=True,
    ),

    # IPC 338 — "Causing grievous hurt by act endangering life"
    # Retrieved from "negligence" + "cause"; requires grievous hurt (not death).
    # When the patient DIED, 304A applies — not 338. Gate it on grievous hurt vocabulary.
    SectionRule(
        section="338", statute="IPC", bns_equivalent="125(b)",
        title="Causing Grievous Hurt by Act Endangering Life or Personal Safety of Others",
        mandatory_ingredients=["grievous_hurt_as_defined_in_s320", "act_endangering_life_or_personal_safety"],
        factual_triggers=["grievous hurt", "grievous injury", "permanent disability", "severe bodily injury",
                          "lost limb", "fracture", "seriously injured", "disfigured", "hospitalized for injury"],
        chapter_number="XVI", chapter_title="Of Offences Affecting the Human Body",
        punishment_minimum=None, punishment_maximum="2 Years",
        fine=True, cognizable=True, bailable=True, requires_trigger_gate=True,
    ),

    # IPC 223 — "Escape from confinement negligently suffered by public servant"
    # Retrieved from "negligence" + "evidence" (both appear in its text); requires
    # an escaped prisoner and a negligent public servant custodian — never a hospital case.
    SectionRule(
        section="223", statute="IPC", bns_equivalent="260",
        title="Escape from Confinement or Custody Negligently Suffered by Public Servant",
        mandatory_ingredients=["public_servant_legally_authorized_to_confine", "escape_of_confined_person", "negligent_sufferance_of_escape"],
        factual_triggers=["escaped from custody", "escaped from confinement", "prisoner escaped", "detainee escaped", "fled from custody"],
        chapter_number="XI", chapter_title="Of False Evidence and Offences Against Public Justice",
        punishment_minimum=None, punishment_maximum="2 Years",
        fine=True, cognizable=False, bailable=True, requires_trigger_gate=True,
    ),

    # IPC 119 — "Public servant concealing design to commit offence"
    # Retrieved from "officer" + "disclose"; but requires the concealing person to be
    # a PUBLIC SERVANT. Private hospital doctors/administrators are NOT public servants.
    SectionRule(
        section="119", statute="IPC", bns_equivalent="48",
        title="Public Servant Concealing Design to Commit Offence Which It Is His Duty to Prevent",
        mandatory_ingredients=["public_servant_status", "concealing_design", "it_is_their_legal_duty_to_prevent_the_offence"],
        factual_triggers=["public servant concealing", "government officer concealing", "public servant instructed",
                          "duty as public servant", "public servant facilitating", "government official"],
        chapter_number="V-A", chapter_title="Of Abetment",
        punishment_minimum=None, punishment_maximum="As for abetment of the offence",
        fine=True, cognizable=True, bailable=False, requires_trigger_gate=True,
    ),

    # IPC 218 — "Public servant framing incorrect record with intent to save person from punishment"
    # Requires both (a) a public servant and (b) framing a record. Gate on public servant.
    SectionRule(
        section="218", statute="IPC", bns_equivalent="255",
        title="Public Servant Framing Incorrect Record or Writing with Intent to Save Person from Punishment",
        mandatory_ingredients=["public_servant_status", "frames_incorrect_record_or_writing", "intent_to_save_person_from_punishment_or_property_from_forfeiture"],
        factual_triggers=["public servant framing", "government doctor", "government hospital", "government officer falsifying",
                          "public servant altered record", "government servant framed record"],
        chapter_number="XI", chapter_title="Of False Evidence and Offences Against Public Justice",
        punishment_minimum=None, punishment_maximum="3 Years",
        fine=True, cognizable=False, bailable=True, requires_trigger_gate=True,
    ),

    # IPC 203 — "Giving false information respecting an offence committed"
    # May be relevant when junior staff give a false account of events to investigators.
    SectionRule(
        section="203", statute="IPC", bns_equivalent="240",
        title="Giving False Information Respecting an Offence Committed",
        mandatory_ingredients=["false_information", "respecting_an_offence_actually_committed", "intent_to_screen_offender"],
        factual_triggers=[
            "false information", "gave false information", "false account",
            "misinformed police", "misinformed investigating officer",
            "giving false statement", "fabricated version of events",
            "instructed to give false account",
        ],
        chapter_number="XI", chapter_title="Of False Evidence and Offences Against Public Justice",
        punishment_minimum=None, punishment_maximum="2 Years",
        fine=True, cognizable=False, bailable=True, requires_trigger_gate=False,
    ),

    # IPC 34 — "Acts done by several persons in furtherance of common intention"
    # An enabling/vicarious liability provision — gate is very light (needs multiple actors).
    SectionRule(
        section="34", statute="IPC", bns_equivalent="3(5)",
        title="Acts Done by Several Persons in Furtherance of Common Intention",
        mandatory_ingredients=["criminal_act_by_multiple_persons", "common_intention", "participation_by_each_accused"],
        factual_triggers=[
            "common intention", "in furtherance of", "acted together",
            "jointly", "joint act", "both accused", "two accused",
            "administrator and officer", "hospital administrator", "multiple accused",
        ],
        chapter_number="II", chapter_title="General Explanations",
        punishment_minimum=None, punishment_maximum="As for the offence committed",
        fine=False, cognizable=True, bailable=False, requires_trigger_gate=False,
    ),

]


# ---------------------------------------------------------------------------
# Dynamic Knowledge Base — auto-promotes CSV-sourced sections into KB rules
# ---------------------------------------------------------------------------

# Candidate paths for the persistent dynamic KB JSON file.
# The first writable path that exists (or can be created) is used.
_DYNAMIC_KB_CANDIDATE_PATHS: List[Path] = [
    # Resolve relative to this file's location — works regardless of working directory
    Path(__file__).parent.parent / "data" / "dynamic_kb.json",
    Path(__file__).parent.parent.parent / "data" / "dynamic_kb.json",
    # Explicit project paths
    Path("C:/Users/Ajinkya/Desktop/MootCourt/data/dynamic_kb.json"),
    Path("C:/Users/Ajinkya/Desktop/MootCourt/backend/data/dynamic_kb.json"),
    # Generic fallbacks
    Path("data/dynamic_kb.json"),
    Path("../data/dynamic_kb.json"),
    Path("c:/proj/MootCourt/data/dynamic_kb.json"),
    Path("c:/MootCourt/data/dynamic_kb.json"),
]

_dynamic_kb_lock = threading.Lock()  # Guards in-process concurrent writes


def _resolve_dynamic_kb_path() -> Optional[Path]:
    """
    Returns the first candidate path whose parent directory exists or can be created.
    Tries to create the directory if it doesn't exist.
    """
    for p in _DYNAMIC_KB_CANDIDATE_PATHS:
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            return p
        except Exception:
            if p.parent.exists():
                return p
    return None


def _load_dynamic_kb() -> List[SectionRule]:
    """
    Loads previously auto-promoted SectionRules from the persistent JSON store.
    Returns an empty list if the file does not exist or is unreadable.
    """
    kb_path = _resolve_dynamic_kb_path()
    if not kb_path or not kb_path.exists():
        return []
    try:
        with open(kb_path, "r", encoding="utf-8") as f:
            raw: List[Dict[str, Any]] = json.load(f)
        rules = []
        for entry in raw:
            try:
                rules.append(SectionRule(**entry))
            except Exception as exc:
                logger.warning("DynamicKB: skipping malformed entry %s — %s", entry.get("section"), exc)
        logger.info("DynamicKB: loaded %d auto-promoted rules from %s", len(rules), kb_path)
        return rules
    except Exception as exc:
        logger.warning("DynamicKB: could not load %s — %s", kb_path, exc)
        return []


def _save_dynamic_kb(rules: List[SectionRule]) -> None:
    """
    Persists the current dynamic KB rules list to JSON.
    Called inside _dynamic_kb_lock — safe for concurrent processes only if you
    run a single worker; for multi-worker deployments swap this for a DB upsert.
    """
    kb_path = _resolve_dynamic_kb_path()
    if not kb_path:
        logger.warning("DynamicKB: no writable path found — auto-promoted rule will be in-memory only this session.")
        return
    try:
        kb_path.parent.mkdir(parents=True, exist_ok=True)
        serialisable = [asdict(r) for r in rules]
        with open(kb_path, "w", encoding="utf-8") as f:
            json.dump(serialisable, f, indent=2, ensure_ascii=False)
        logger.info("DynamicKB: persisted %d rules to %s", len(rules), kb_path)
    except Exception as exc:
        logger.warning("DynamicKB: write failed for %s — %s", kb_path, exc)


# In-process dynamic KB — populated from disk at import time, extended at runtime
DYNAMIC_KNOWLEDGE_BASE: List[SectionRule] = _load_dynamic_kb()


def _kb_section_keys() -> Set[str]:
    """
    Returns the set of normalised '{statute}_{section}' keys already present
    across STATUTE_KNOWLEDGE_BASE and DYNAMIC_KNOWLEDGE_BASE combined,
    so promotion skips anything already covered.
    """
    keys: Set[str] = set()
    for rule in STATUTE_KNOWLEDGE_BASE + DYNAMIC_KNOWLEDGE_BASE:
        keys.add(f"{rule.statute.upper()}_{rule.section.upper()}")
        if rule.bns_equivalent and rule.bns_equivalent.upper() not in ("NONE", ""):
            keys.add(f"BNS_{rule.bns_equivalent.upper()}")
    return keys


def promote_from_llm_result(
    section_number: str,
    statute: str,
    title: str,
    chapter: str,
    ingredients: List[str],
    matched_concept: str,
    bns_equivalent: str = "",
    cognizable: bool = True,
    bailable: bool = False,
    punishment_maximum: Optional[str] = None,
) -> Optional[SectionRule]:
    """
    Promotes a section that the LLM verified (Stage 4) but that has NO existing
    SectionRule in the KB. Unlike promote_csv_record_to_kb (which requires a CSV
    record), this builds the SectionRule directly from LLM-verified metadata.

    Also learns the concept → section mapping by storing the concept as a
    factual trigger, so future queries using the same legal concept phrase
    will match this section locally without an LLM call.

    Args:
        section_number:   e.g. "468"
        statute:          "IPC" or "BNS"
        title:            e.g. "Forgery for Purpose of Cheating"
        chapter:          Chapter name/number string
        ingredients:      List of statutory ingredient strings from Stage 4
        matched_concept:  The Stage 1 legal concept that led to this section
                          e.g. "Forgery", "Criminal Breach of Trust"
        bns_equivalent:   Corresponding BNS section if statute is IPC, else ""
        cognizable:       Whether the offence is cognizable
        bailable:         Whether the offence is bailable
        punishment_maximum: Max sentence string e.g. "7 Years"

    Returns:
        The newly created SectionRule, or None if already in KB.
    """
    if not section_number or not statute:
        return None

    existing_keys = _kb_section_keys()
    candidate_key = f"{statute.upper()}_{section_number.upper()}"
    if candidate_key in existing_keys:
        # Already in KB — but enrich triggers if the concept is new
        _enrich_kb_triggers(section_number, statute, matched_concept)
        return None

    # Derive factual triggers from:
    # 1. The matched concept phrase (most important — this is what Stage 1 produced)
    # 2. Meaningful words from the section title
    stop = {"the", "a", "an", "and", "or", "of", "to", "in", "for", "on", "by",
            "with", "is", "was", "are", "were", "any", "such", "not", "be", "as"}

    triggers = set()
    # Concept phrase words (4+ chars) as triggers
    for word in re.findall(r"[a-zA-Z]{4,}", matched_concept.lower()):
        if word not in stop:
            triggers.add(word)
    # Full concept phrase as a trigger
    concept_lower = matched_concept.lower().strip()
    if len(concept_lower) > 4:
        triggers.add(concept_lower)
    # Title words
    for word in re.findall(r"[a-zA-Z]{4,}", title.lower()):
        if word not in stop:
            triggers.add(word)
    # Ingredient words
    for ing in ingredients:
        for word in re.findall(r"[a-zA-Z]{4,}", ing.lower()):
            if word not in stop:
                triggers.add(word)

    # Build mandatory ingredient slugs from ingredient strings
    mandatory = []
    for ing in ingredients:
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", ing.lower()).strip("_")
        if slug:
            mandatory.append(slug)
    if not mandatory:
        mandatory = [re.sub(r"[^a-zA-Z0-9]+", "_", title.lower()).strip("_")]

    new_rule = SectionRule(
        section=section_number,
        statute=statute,
        bns_equivalent=bns_equivalent or section_number,
        title=title,
        mandatory_ingredients=mandatory,
        factual_triggers=sorted(triggers),
        chapter_number=chapter,
        chapter_title=chapter,
        punishment_minimum=None,
        punishment_maximum=punishment_maximum or "As specified under statute",
        fine=True,
        cognizable=cognizable,
        bailable=bailable,
    )

    with _dynamic_kb_lock:
        if candidate_key in _kb_section_keys():
            return None
        DYNAMIC_KNOWLEDGE_BASE.append(new_rule)
        _save_dynamic_kb(DYNAMIC_KNOWLEDGE_BASE)

    logger.info(
        "DynamicKB: LLM-promoted %s %s ('%s') from concept '%s' — triggers: %s",
        statute, section_number, title, matched_concept, list(triggers)[:5],
    )
    return new_rule


def _enrich_kb_triggers(section_number: str, statute: str, new_concept: str) -> None:
    """
    If a section is already in the KB but the matched_concept introduces a new
    trigger phrase, add it to the existing rule's factual_triggers so future
    queries using this concept match locally.
    """
    if not new_concept:
        return
    sec_upper = section_number.upper()
    stat_upper = statute.upper()
    concept_lower = new_concept.lower().strip()

    with _dynamic_kb_lock:
        for rule in DYNAMIC_KNOWLEDGE_BASE:
            if rule.section.upper() == sec_upper and rule.statute.upper() == stat_upper:
                if concept_lower not in rule.factual_triggers:
                    rule.factual_triggers.append(concept_lower)
                    _save_dynamic_kb(DYNAMIC_KNOWLEDGE_BASE)
                    logger.info(
                        "DynamicKB: enriched triggers for %s %s with concept '%s'",
                        statute, section_number, new_concept,
                    )
                return


def promote_csv_record_to_kb(
    csv_record: Dict[str, Any],
    matched_query_terms: List[str],
    first_schedule_meta: Optional[Dict[str, Any]] = None,
) -> Optional[SectionRule]:
    """
    Attempts to auto-promote a CSV-sourced section record into the Dynamic KB
    as a new SectionRule.  Returns the created rule (and appends it to
    DYNAMIC_KNOWLEDGE_BASE) or None if the section is already in the KB.

    Args:
        csv_record:          The raw dict from sections_db (keys: identifier,
                             statute, section_number, title, chapter, full_text, tokens).
        matched_query_terms: The keywords that caused this record to be selected
                             — used as seed factual_triggers.
        first_schedule_meta: Optional metadata dict from StatuteRepository
                             (keys: chapter_number, chapter_title,
                             punishment_minimum, punishment_maximum,
                             fine, cognizable, bailable).
    Returns:
        The newly created SectionRule or None.
    """
    sec_num = csv_record.get("section_number", "").strip()
    statute = csv_record.get("statute", "IPC").strip()
    title = csv_record.get("title", f"{statute} Section {sec_num}").strip()
    chapter = csv_record.get("chapter", "General Offences").strip()

    if not sec_num:
        return None

    existing_keys = _kb_section_keys()
    candidate_key = f"{statute.upper()}_{sec_num.upper()}"
    if candidate_key in existing_keys:
        return None  # Already covered — no-op

    # Derive factual triggers from matched query terms (min length 4 to avoid noise)
    factual_triggers = sorted({t.lower() for t in matched_query_terms if len(t) >= 4})

    # Also mine meaningful words from the CSV title itself as additional triggers
    stop = {"the", "a", "an", "and", "or", "of", "to", "in", "for", "on", "by",
            "with", "is", "was", "are", "were", "any", "such", "not", "be", "as"}
    title_words = [w.lower() for w in re.findall(r"[a-zA-Z]{4,}", title) if w.lower() not in stop]
    for tw in title_words:
        if tw not in factual_triggers:
            factual_triggers.append(tw)

    # Derive a snake_case mandatory ingredient from the title
    ingredient = re.sub(r"[^a-zA-Z0-9]+", "_", title.lower()).strip("_")
    mandatory_ingredients = [ingredient] if ingredient else ["offence_elements_present"]

    # Resolve metadata from First Schedule if available
    fs = first_schedule_meta or {}
    new_rule = SectionRule(
        section=sec_num,
        statute=statute,
        bns_equivalent=fs.get("bns_equivalent", sec_num),  # Best-effort; mapper can refine later
        title=title,
        mandatory_ingredients=mandatory_ingredients,
        factual_triggers=factual_triggers,
        chapter_number=fs.get("chapter_number", chapter or "General Offence Chapter"),
        chapter_title=fs.get("chapter_title", chapter or "General Offences"),
        punishment_minimum=fs.get("punishment_minimum", None),
        punishment_maximum=fs.get("punishment_maximum", "As specified under statute"),
        fine=fs.get("fine", True),
        cognizable=fs.get("cognizable", True),
        bailable=fs.get("bailable", False),
    )

    with _dynamic_kb_lock:
        # Double-check inside lock (another thread may have added it already)
        if candidate_key in _kb_section_keys():
            return None
        DYNAMIC_KNOWLEDGE_BASE.append(new_rule)
        _save_dynamic_kb(DYNAMIC_KNOWLEDGE_BASE)

    logger.info(
        "DynamicKB: auto-promoted %s %s ('%s') — triggers: %s",
        statute, sec_num, title, factual_triggers[:5],
    )
    return new_rule


def get_effective_knowledge_base() -> List[SectionRule]:
    """
    Returns the combined KB (static STATUTE_KNOWLEDGE_BASE + runtime DYNAMIC_KNOWLEDGE_BASE).
    Always use this instead of referencing STATUTE_KNOWLEDGE_BASE directly when you
    need full coverage including auto-promoted rules.
    """
    return STATUTE_KNOWLEDGE_BASE + DYNAMIC_KNOWLEDGE_BASE


# ---------------------------------------------------------------------------
# Chapter-domain coherence system
# ---------------------------------------------------------------------------
# Each IPC chapter is tagged with one or more domain strings.
# A query's domains are derived from its concept labels at retrieval time.
# Sections whose chapter domains share NO overlap with the query domains are
# eliminated — structurally, without any per-section hardcoding.
#
# Domain tags (stable strings — add new ones freely as new case types arise):
#   HOMICIDE              death caused by any means
#   BODILY_HARM           non-fatal injury, hurt, grievous hurt
#   MEDICAL_NEGLIGENCE    rash/negligent medical act causing death or harm
#   TRAFFIC               rash driving, vehicular offences
#   SEXUAL_OFFENCE        rape, sexual assault, outraging modesty
#   DOMESTIC_VIOLENCE     dowry, matrimonial cruelty, harassment
#   PROPERTY_OFFENCE      theft, robbery, cheating, criminal breach of trust
#   DOCUMENT_OFFENCE      forgery, falsification, destruction of records
#   PUBLIC_SERVANT        offences by / relating to public servants
#   PUBLIC_ORDER          unlawful assembly, rioting, affray
#   FALSE_EVIDENCE        perjury, fabricating/destroying evidence, screening
#   DEFAMATION            defamation, insult
#   GENERAL               ancillary / enabling provisions (abetment, conspiracy)
#                         — always compatible with every query domain

# Chapter-title substring → frozenset of domain tags.
# Keys are lowercased substrings; first match wins (most-specific first).
_CHAPTER_DOMAIN_MAP: List[Tuple[str, frozenset]] = [
    # Life / homicide
    ("offences affecting life",              frozenset({"HOMICIDE", "BODILY_HARM", "MEDICAL_NEGLIGENCE", "TRAFFIC"})),
    # Hurt / bodily injury (non-fatal)
    ("hurt",                                  frozenset({"BODILY_HARM"})),
    ("wrongful restraint",                    frozenset({"BODILY_HARM"})),
    ("wrongful confinement",                  frozenset({"BODILY_HARM"})),
    ("criminal force",                        frozenset({"BODILY_HARM"})),
    ("assault",                               frozenset({"BODILY_HARM"})),
    # Sexual offences
    ("sexual offence",                        frozenset({"SEXUAL_OFFENCE"})),
    ("rape",                                  frozenset({"SEXUAL_OFFENCE"})),
    ("outraging",                             frozenset({"SEXUAL_OFFENCE"})),
    # Domestic / matrimonial
    ("dowry",                                 frozenset({"DOMESTIC_VIOLENCE"})),
    ("cruelty by husband",                    frozenset({"DOMESTIC_VIOLENCE"})),
    ("matrimonial",                           frozenset({"DOMESTIC_VIOLENCE"})),
    # Property offences
    ("offences against property",             frozenset({"PROPERTY_OFFENCE"})),
    ("theft",                                 frozenset({"PROPERTY_OFFENCE"})),
    ("robbery",                               frozenset({"PROPERTY_OFFENCE"})),
    ("extortion",                             frozenset({"PROPERTY_OFFENCE"})),
    ("cheating",                              frozenset({"PROPERTY_OFFENCE", "DOCUMENT_OFFENCE"})),
    ("criminal breach of trust",              frozenset({"PROPERTY_OFFENCE"})),
    ("mischief",                              frozenset({"PROPERTY_OFFENCE"})),
    ("criminal trespass",                     frozenset({"PROPERTY_OFFENCE"})),
    # Documents / forgery / records
    ("offences relating to documents",        frozenset({"DOCUMENT_OFFENCE"})),
    ("property marks",                        frozenset({"DOCUMENT_OFFENCE", "PROPERTY_OFFENCE"})),
    # False evidence / screening / perjury
    ("false evidence",                        frozenset({"FALSE_EVIDENCE", "DOCUMENT_OFFENCE"})),
    ("offences against public justice",       frozenset({"FALSE_EVIDENCE", "DOCUMENT_OFFENCE"})),
    # Public servants
    ("offences by or relating to public servants", frozenset({"PUBLIC_SERVANT"})),
    ("contempt of lawful authority",          frozenset({"PUBLIC_SERVANT", "PUBLIC_ORDER"})),
    # Public order / assembly / state security
    ("unlawful assembly",                     frozenset({"PUBLIC_ORDER"})),
    ("offences against the state",            frozenset({"PUBLIC_ORDER"})),
    ("against the state",                     frozenset({"PUBLIC_ORDER"})),  # shorter variant
    ("waging war",                            frozenset({"PUBLIC_ORDER"})),
    ("seditious",                             frozenset({"PUBLIC_ORDER"})),
    ("offences relating to the army",         frozenset({"PUBLIC_ORDER"})),
    ("offences relating to navy",             frozenset({"PUBLIC_ORDER"})),
    ("relating to the army",                  frozenset({"PUBLIC_ORDER"})),
    ("deserter",                              frozenset({"PUBLIC_ORDER"})),
    ("merchant vessel",                       frozenset({"PUBLIC_ORDER"})),
    ("offences relating to elections",        frozenset({"PUBLIC_ORDER"})),
    ("coin",                                  frozenset({"PUBLIC_ORDER"})),      # IPC 230-263A (coinage)
    ("currency",                              frozenset({"PUBLIC_ORDER"})),
    ("weights and measures",                  frozenset({"PUBLIC_ORDER"})),
    # Public health / safety (catch-all for environmental/nuisance offences)
    ("public health",                         frozenset({"PUBLIC_ORDER"})),
    ("public safety",                         frozenset({"PUBLIC_ORDER"})),
    ("public nuisance",                       frozenset({"PUBLIC_ORDER"})),
    ("nuisance",                              frozenset({"PUBLIC_ORDER"})),
    # Defamation / reputation
    ("criminal intimidation",                 frozenset({"DEFAMATION", "BODILY_HARM"})),
    ("defamation",                            frozenset({"DEFAMATION"})),
    # Abetment / conspiracy — domain-agnostic: covered by _ENABLING_SECTION_ALLOWLIST
    ("of abetment",                           frozenset({"GENERAL"})),
    ("criminal conspiracy",                   frozenset({"GENERAL"})),
    # General exceptions / explanations — always domain-agnostic
    ("general exceptions",                    frozenset({"GENERAL"})),
    ("general explanations",                  frozenset({"GENERAL"})),
]


def _chapter_domains(chapter_title: str) -> frozenset:
    """
    Returns the domain set for a chapter title by substring matching.
    Falls back to frozenset({"GENERAL"}) if no chapter matches — ensures
    unknown chapters are never silently eliminated.
    """
    ct = (chapter_title or "").strip().lower()
    for substring, domains in _CHAPTER_DOMAIN_MAP:
        if substring in ct:
            return domains
    return frozenset({"GENERAL"})


# Concept-label keyword → query domain.
# Applied to EACH concept label word-by-word; all matched domains are unioned.
# Keys are lowercase stemmed tokens (Porter stem applied at match time).
# Add new rows as new concept vocabularies emerge — no per-section rules needed.
_CONCEPT_DOMAIN_SIGNALS: Dict[str, str] = {
    # Homicide / death
    "death":          "HOMICIDE",
    "kill":           "HOMICIDE",
    "murder":         "HOMICIDE",
    "homicid":        "HOMICIDE",
    "die":            "HOMICIDE",
    "dead":           "HOMICIDE",
    "deceas":         "HOMICIDE",
    # Medical negligence — death caused by rash/negligent medical act
    "negligen":       "MEDICAL_NEGLIGENCE",
    "negligent":      "MEDICAL_NEGLIGENCE",
    "rash":           "MEDICAL_NEGLIGENCE",
    "medic":          "MEDICAL_NEGLIGENCE",
    "patient":        "MEDICAL_NEGLIGENCE",
    "hospital":       "MEDICAL_NEGLIGENCE",
    "treatment":      "MEDICAL_NEGLIGENCE",   # stopped in BM25 but used for domain only
    "specialist":     "MEDICAL_NEGLIGENCE",
    "surgeri":        "MEDICAL_NEGLIGENCE",
    "surgeon":        "MEDICAL_NEGLIGENCE",
    "physican":       "MEDICAL_NEGLIGENCE",
    "doctor":         "MEDICAL_NEGLIGENCE",
    "clinic":         "MEDICAL_NEGLIGENCE",
    # Traffic
    "drive":          "TRAFFIC",
    "driven":         "TRAFFIC",
    "driving":        "TRAFFIC",
    "vehicl":         "TRAFFIC",
    "road":           "TRAFFIC",
    # Bodily harm (non-fatal)
    "hurt":           "BODILY_HARM",
    "injuri":         "BODILY_HARM",
    "wound":          "BODILY_HARM",
    "grievous":       "BODILY_HARM",
    "assault":        "BODILY_HARM",
    "beat":           "BODILY_HARM",
    "stab":           "BODILY_HARM",
    "fractur":        "BODILY_HARM",
    # Sexual offences
    "rape":           "SEXUAL_OFFENCE",
    "sexual":         "SEXUAL_OFFENCE",
    "molestat":       "SEXUAL_OFFENCE",
    "penetrat":       "SEXUAL_OFFENCE",
    "outraging":      "SEXUAL_OFFENCE",
    # Domestic / matrimonial
    "dowri":          "DOMESTIC_VIOLENCE",
    "cruelti":        "DOMESTIC_VIOLENCE",
    "matrimoni":      "DOMESTIC_VIOLENCE",
    "husband":        "DOMESTIC_VIOLENCE",
    "wife":           "DOMESTIC_VIOLENCE",
    "in-law":         "DOMESTIC_VIOLENCE",
    # Property
    "theft":          "PROPERTY_OFFENCE",
    "steal":          "PROPERTY_OFFENCE",
    "stolen":         "PROPERTY_OFFENCE",
    "robbery":        "PROPERTY_OFFENCE",
    "extort":         "PROPERTY_OFFENCE",
    "cheat":          "PROPERTY_OFFENCE",
    "fraud":          "PROPERTY_OFFENCE",
    "misappropri":    "PROPERTY_OFFENCE",
    "breach of trust": "PROPERTY_OFFENCE",
    "embezzl":        "PROPERTY_OFFENCE",
    "land":           "PROPERTY_OFFENCE",
    "propert":        "PROPERTY_OFFENCE",
    # Document / record offences
    "falsif":         "DOCUMENT_OFFENCE",
    "forgeri":        "DOCUMENT_OFFENCE",
    "forged":         "DOCUMENT_OFFENCE",
    "document":       "DOCUMENT_OFFENCE",
    "record":         "DOCUMENT_OFFENCE",
    "destruct":       "DOCUMENT_OFFENCE",
    "destroy":        "DOCUMENT_OFFENCE",
    "tamper":         "DOCUMENT_OFFENCE",
    "account":        "DOCUMENT_OFFENCE",
    # False evidence / screening
    "evidenc":        "FALSE_EVIDENCE",
    "disappear":      "FALSE_EVIDENCE",
    "screen":         "FALSE_EVIDENCE",
    "conceal":        "FALSE_EVIDENCE",
    "abscond":        "FALSE_EVIDENCE",
    # Defamation
    "defam":          "DEFAMATION",
    "reputat":        "DEFAMATION",
    "slander":        "DEFAMATION",
    # Public servant
    "public servant": "PUBLIC_SERVANT",
    "government":     "PUBLIC_SERVANT",
    # Public order
    "assembl":        "PUBLIC_ORDER",
    "riot":           "PUBLIC_ORDER",
    "sedition":       "PUBLIC_ORDER",
}


def _derive_query_domains(concept_labels: List[str], sub_query_texts: List[str]) -> frozenset:
    """
    Derives a set of query domain strings from Stage 1 concept labels and sub-query text.
    Uses the _CONCEPT_DOMAIN_SIGNALS lookup (stemmed keywords → domain).
    Always includes GENERAL so enabling/ancillary provisions always pass the gate.

    The derived domain set is intentionally BROAD — it includes every domain hinted at
    by any concept label. For a medical negligence + document destruction case it returns:
      {HOMICIDE, MEDICAL_NEGLIGENCE, DOCUMENT_OFFENCE, FALSE_EVIDENCE, GENERAL}
    This means sections from those chapters are eligible; all others are eliminated.
    """
    domains: Set[str] = {"GENERAL"}  # always permit ancillary provisions
    combined = " ".join(concept_labels + sub_query_texts).lower()
    # Multi-word signals first (checked as substrings before stemming)
    for signal, domain in _CONCEPT_DOMAIN_SIGNALS.items():
        if " " in signal:  # multi-word: substring match
            if signal in combined:
                domains.add(domain)
    # Single-word signals: stem each token and match
    for tok in re.findall(r"[a-z]+", combined):
        if len(tok) < 3:
            continue
        stemmed = _PorterStemmer.stem(tok)
        # Try stemmed form first, then raw token
        domain = _CONCEPT_DOMAIN_SIGNALS.get(stemmed) or _CONCEPT_DOMAIN_SIGNALS.get(tok)
        if domain:
            domains.add(domain)
    return frozenset(domains)


# ---------------------------------------------------------------------------
# Retrieval helpers (word-boundary matching, tokenisation, BM25)
# ---------------------------------------------------------------------------

class _WordText(str):
    """
    str subclass whose `term in text` check matches on a LEADING word boundary
    instead of raw substring. 'hit' no longer matches 'white'/'exhibit', while
    stems such as 'intimidat' or 'harass' still match 'intimidation'/'harassed'.
    Lets every existing `any(t in lower_facts for t in [...])` trigger check
    become boundary-aware without rewriting each one.
    """

    def __contains__(self, term: object) -> bool:  # type: ignore[override]
        t = str(term).strip().lower()
        if not t:
            return False
        return re.search(r"(?<![a-z0-9])" + re.escape(t), str(self).lower()) is not None


# Fix 5/6: expanded stop list. Question boilerplate and generic case-narrative
# words carry no statutory signal but matched almost every long section.
_RETRIEVAL_STOP_WORDS: Set[str] = {
    "the", "a", "an", "and", "or", "of", "to", "in", "for", "on", "by", "with", "is", "was",
    "are", "were", "be", "been", "being", "as", "at", "from", "that", "this", "these", "those",
    "it", "its", "his", "her", "their", "them", "he", "she", "they", "who", "whom", "which",
    "what", "when", "where", "how", "why", "any", "such", "not", "no", "nor", "if", "than",
    "then", "also", "may", "shall", "will", "would", "could", "should", "has", "have", "had",
    "do", "does", "did", "into", "out", "up", "about", "against", "between", "after", "before",
    "during", "other", "another", "same", "own", "per", "via",
    # question / legal-framing boilerplate produced by Stage 1 sub-queries
    "legal", "law", "implications", "implication", "consequences", "consequence",
    "ramifications", "ramification", "potential", "possible", "regarding", "relating",
    "related", "concerning", "respect", "alleged", "allegedly", "allegation", "allegations",
    "accused", "applicant", "complainant", "person", "persons", "case", "matter",
    "actual", "certain", "timely", "sequence", "events", "event", "instruction", "instructed",
    "staff", "members", "member", "junior", "senior", "section", "offence", "offences",
    "liability", "liable", "punishment", "punishable", "whoever", "act", "acts", "done",
    # Medical / case-narrative context words that are not statutory crime keywords.
    # "treatment" / "treat" dominates sections like IPC 36, 88, 92 which are about consent
    # to medical procedures — they should not rank above 304A for a negligence query.
    "treat", "treatment",
    # FIX 1 – "fact" was leaking through from "FACT:F1" label tokens and matching
    # every IPC section that contains the word "fact" in its statutory text.
    "fact", "facts",
    # FIX 2 – IPC boilerplate that appears in virtually every section and carries
    # zero discriminative signal for charge identification.
    "court", "judge", "proceeding", "proceedings", "justice",
    "regard", "hold", "holds", "held", "consider", "shows", "herein",
    "aforesaid", "thereby", "thereof", "therein", "thereto", "whereas",
    "nothing", "extent", "purpose", "means", "manner", "nature", "kind",
    "reason", "ground", "general", "special", "lawful", "unlawful",
    "right", "power", "authority", "order", "place", "time", "day",
    "year", "state", "office", "public",
}

# -------------------------------------------------------------------------
# FIX 8 — Query-side domain-generic filter.
#
# These stemmed tokens appear in the plain_language / full_text of *hundreds*
# of IPC sections for completely unrelated reasons:
#   - "medic" → doctor examines rape victim, treats grievous hurt patient
#   - "hospit" → victim taken to hospital after acid attack / miscarriage
#   - "patient" → consent-to-surgery provisions (IPC 88, 92)
#   - "offic" → "officer" as actor in virtually every public-servant section
#   - "report" → FIR, medical report, post-mortem report — all procedural
#   - "victim" → any section involving harm to a person
#   - "complaint" → any cognizable offence
#   - "polic" → any section mentioning police investigation
#
# When these tokens arrive FROM THE QUERY (e.g. "senior medical officer
# instructed junior staff") they carry zero discriminative power for
# identifying *which* IPC section applies. Removing them only from the
# query side means they remain in document indices (IPC 201/204 still
# has "record", "evidence" in its BM25 doc) while they no longer cause
# false-positive matches against unrelated sections.
#
# Do NOT add these to _RETRIEVAL_STOP_WORDS (which applies to both sides).
# Instead strip them from query term_weights before calling _rank().
_QUERY_ONLY_STOP_STEMS: Set[str] = {
    # Role / institution labels (not statutory ingredients)
    "medic",    # "medical" → doctor as context word, not as crime element
    "hospit",   # "hospital"
    "patient",
    "offic",    # "officer", "official"
    "polic",    # "police" — standalone; "custody" pair handled by procedural gate
    # Procedural / narrative nouns (not statutory ingredients)
    "report",   # FIR / medical report / post-mortem report
    "victim",
    "complaint",
    "witness",
    "conduct",
    # Extremely common verbs / nouns with zero IPC discriminative value
    "person",
    "inform",   # "information to police" → FIR boilerplate
    "allege",   # allegations are the framing, not the ingredient
}

# Boilerplate lead-ins removed before tokenising a sub-query sentence.
_QUERY_BOILERPLATE_RE = re.compile(
    r"^\s*(what|which)\s+(are|is|would be|could be)\s+(the\s+)?"
    r"((potential|possible|likely)\s+)?"
    r"(legal\s+)?(implications?|consequences?|ramifications?|issues?|offences?|provisions?)\s+"
    r"(of|for|arising from|relating to|regarding)\s+(the\s+)?",
    re.IGNORECASE,
)

# General Explanations / General Exceptions are never charge candidates on their own.
_NON_OFFENCE_CHAPTER_MARKERS = ("general explanations", "general exceptions")
# Enabling / ancillary-liability provisions that must stay retrievable.
# IPC 34 is in "General Explanations" chapter which is normally filtered as non-offence;
# allowlist it so it can be retrieved when multiple accused are alleged.
_ENABLING_SECTION_ALLOWLIST: Set[str] = {"34", "107", "108", "109", "114", "120A", "120B", "149"}

# ---------------------------------------------------------------------------
# Procedural concept detection
# ---------------------------------------------------------------------------
# Legal concepts that belong to CrPC/BNSS (procedural law), not IPC/BNS (substantive).
# These must NOT be fed to the IPC BM25 index — they produce false positives there.
# Instead they are passed through as-is so the caller can route them to a
# CrPC retrieval track or bail-argument generator.
#
# Detection is via stemmed keyword matching on the concept label.
# Add new procedural keywords here as new concept vocabularies emerge.
_PROCEDURAL_CONCEPT_STEMS: Set[str] = {
    # Bail provisions
    "bail",          # anticipatory bail, regular bail
    "antici",        # anticipatory
    "remand",
    "custody",
    # Trial procedure
    "charg",         # framing of charges (not the offence itself)
    "cogniz",        # cognizance
    "summon",
    "warrant",
    "commit",        # committal proceedings
    # Appellate / revision
    "appeal",
    "revis",
    "stay",
}

_PROCEDURAL_CONCEPT_PHRASES: Set[str] = {
    # Full phrases that unambiguously signal procedural relief
    "anticipatory bail",
    "regular bail",
    "bail application",
    "default bail",
    "statutory bail",
    "remand extension",
    "police custody",
    "judicial custody",
    "framing of charges",
    "discharge application",
    "quashing of fir",
    "section 438",
    "section 439",
    "section 167",
}


def is_procedural_concept(concept_label: str) -> bool:
    """
    Returns True if the concept label describes procedural CrPC/BNSS relief
    rather than an IPC/BNS substantive offence.

    Uses phrase matching first (faster, more precise), then stemmed-token matching.
    """
    label_lower = (concept_label or "").strip().lower()
    # Phrase check — exact substring
    for phrase in _PROCEDURAL_CONCEPT_PHRASES:
        if phrase in label_lower:
            return True
    # Token stem check
    for tok in re.findall(r"[a-z]+", label_lower):
        if len(tok) < 3:
            continue
        if tok in _PROCEDURAL_CONCEPT_STEMS:
            return True
        stemmed = _PorterStemmer.stem(tok)
        if stemmed in _PROCEDURAL_CONCEPT_STEMS:
            return True
    return False

# Relative-score floor (score is normalised to the best hit for the query).
# FIX 5 – raised from 0.30 → 0.45 to cut low-signal noise sections.
_MIN_RELATIVE_SCORE = 0.45
_BM25_K1 = 1.5
_BM25_B = 0.75
# FIX 3 – new field weights: title x5, key_principle x4, ingredients/plain_language/chapter x3,
# illustrations x2, full_text x1.  Heavier signal on the descriptive fields reduces the
# dominance of raw statutory text which is full of common IPC boilerplate.
_TITLE_WEIGHT = 5           # section heading – most discriminative
_KEY_PRINCIPLE_WEIGHT = 4   # plain-language summary (ipc.json "key_principle")
_INGREDIENT_WEIGHT = 3      # ingredients, plain_language, chapter_title, kb triggers
# Absolute floor: a section must cover at least this share of the query's total IDF mass
# (rare-word weight). Unlike the relative floor, a query with nothing relevant returns nothing.
# FIX 6 – was 0.25, raised to 0.30. Note: we also enforce _MIN_MATCHED_TERMS (see below)
# which independently prevents single-common-word matches from passing even at 0.30.
_MIN_COVERAGE = 0.30
# A section must match at least this many DISTINCT query token types.
# This replaces the blunt 0.40 coverage floor: 304A matches 'neglig' (one strong token,
# coverage 0.175) which is genuine signal; IPC 36/88/92 also matched only one token
# ('treat' / 'omiss') which are now stopped. After stopping 'treat', legitimate
# single-token matches like 304A must still pass — hence min_terms=1 but coverage>=0.30.
_MIN_MATCHED_TERMS = 1
_RRF_K = 60


class _PorterStemmer:
    """
    Pure-Python Porter stemmer (no external dependencies).
    Correctly conflates morphological variants:
      negligence / negligent → neglig
      falsification / falsify / falsified → falsif
      destruction / destroy / destroyed → destruct / destroi
      concealment / conceal / concealing → conceal / conc
      omission / omit / omitted → omiss / omit
    The old hand-rolled suffix stripper left negligence ≠ negligent as different
    tokens, preventing 304A from ranking for a negligence-concept query.
    """
    @staticmethod
    def _cons(w: str, i: int) -> bool:
        c = w[i]
        if c in "aeiou":
            return False
        if c == "y":
            return i == 0 or not _PorterStemmer._cons(w, i - 1)
        return True

    @classmethod
    def _m(cls, w: str) -> int:
        n = 0; i = 0; l = len(w)
        while i < l and cls._cons(w, i): i += 1
        while i < l:
            while i < l and not cls._cons(w, i): i += 1
            n += 1
            while i < l and cls._cons(w, i): i += 1
        return n

    @classmethod
    def _vowel_in(cls, w: str) -> bool:
        return any(not cls._cons(w, i) for i in range(len(w)))

    @classmethod
    def _double_c(cls, w: str) -> bool:
        return len(w) >= 2 and w[-1] == w[-2] and cls._cons(w, len(w) - 1)

    @classmethod
    def _cvc(cls, w: str) -> bool:
        l = len(w)
        return (l >= 3 and cls._cons(w, l - 1) and not cls._cons(w, l - 2)
                and cls._cons(w, l - 3) and w[-1] not in "wxy")

    @classmethod
    def stem(cls, word: str) -> str:
        w = word.lower()
        if len(w) <= 2:
            return w
        # Step 1a
        if w.endswith("sses"):
            w = w[:-2]
        elif w.endswith("ies"):
            w = w[:-2]
        elif not w.endswith("ss") and w.endswith("s"):
            w = w[:-1]
        # Step 1b
        if w.endswith("eed"):
            s = w[:-3]
            if cls._m(s) > 0:
                w = w[:-1]
        elif w.endswith("ed"):
            s = w[:-2]
            if cls._vowel_in(s):
                w = s
                if w.endswith(("at", "bl", "iz")):
                    w += "e"
                elif cls._double_c(w) and w[-1] not in "lsz":
                    w = w[:-1]
                elif cls._m(w) == 1 and cls._cvc(w):
                    w += "e"
        elif w.endswith("ing"):
            s = w[:-3]
            if cls._vowel_in(s):
                w = s
                if w.endswith(("at", "bl", "iz")):
                    w += "e"
                elif cls._double_c(w) and w[-1] not in "lsz":
                    w = w[:-1]
                elif cls._m(w) == 1 and cls._cvc(w):
                    w += "e"
        # Step 1c
        if w.endswith("y") and cls._vowel_in(w[:-1]):
            w = w[:-1] + "i"
        # Step 2
        for suf, rep in [
            ("ational","ate"),("tional","tion"),("enci","ence"),("anci","ance"),
            ("izer","ize"),("abli","able"),("alli","al"),("entli","ent"),("eli","e"),
            ("ousli","ous"),("ization","ize"),("ation","ate"),("ator","ate"),
            ("alism","al"),("iveness","ive"),("fulness","ful"),("ousness","ous"),
            ("aliti","al"),("iviti","ive"),("biliti","ble"),
        ]:
            if w.endswith(suf):
                s = w[:-len(suf)]
                if cls._m(s) > 0:
                    w = s + rep
                break
        # Step 3
        for suf, rep in [
            ("icate","ic"),("ative",""),("alize","al"),("iciti","ic"),
            ("ical","ic"),("ful",""),("ness",""),
        ]:
            if w.endswith(suf):
                s = w[:-len(suf)]
                if cls._m(s) > 0:
                    w = s + rep
                break
        # Step 4
        for suf in ["al","ance","ence","er","ic","able","ible","ant","ement",
                    "ment","ent","ion","ou","ism","ate","iti","ous","ive","ize"]:
            if w.endswith(suf):
                s = w[:-len(suf)]
                if suf == "ion":
                    if cls._m(s) > 1 and s.endswith(("s", "t")):
                        w = s
                elif cls._m(s) > 1:
                    w = s
                break
        # Step 5a
        if w.endswith("e"):
            s = w[:-1]
            if cls._m(s) > 1:
                w = s
            elif cls._m(s) == 1 and not cls._cvc(s):
                w = s
        # Step 5b
        if cls._m(w) > 1 and cls._double_c(w) and w.endswith("l"):
            w = w[:-1]
        return w


def _stem(tok: str) -> str:
    """Porter stemmer: negligence/negligent → neglig, falsify/falsification → falsif, etc."""
    return _PorterStemmer.stem(tok)


def _tokenize(text: str) -> List[str]:
    """Lowercase word tokens (word-boundary based), stop words removed, Porter-stemmed."""
    return [
        _stem(t)
        for t in re.findall(r"[a-z]+", (text or "").lower())
        if len(t) > 2 and t not in _RETRIEVAL_STOP_WORDS
    ]


def strip_query_boilerplate(query_text: str) -> str:
    """Turns 'What are the legal consequences of the alleged destruction of X ...?' into a short conduct phrase."""
    q = (query_text or "").strip().rstrip("?")
    return _QUERY_BOILERPLATE_RE.sub("", q).strip()


class _BM25Index:
    """Tiny in-memory BM25 over pre-tokenised documents. No external dependency."""

    def __init__(self, docs_tokens: List[List[str]]):
        self.doc_tf: List[Dict[str, int]] = []
        self.doc_len: List[int] = []
        df: Dict[str, int] = {}
        for toks in docs_tokens:
            tf: Dict[str, int] = {}
            for t in toks:
                tf[t] = tf.get(t, 0) + 1
            self.doc_tf.append(tf)
            self.doc_len.append(len(toks))
            for t in tf:
                df[t] = df.get(t, 0) + 1
        self.n = max(len(docs_tokens), 1)
        self.avgdl = (sum(self.doc_len) / self.n) or 1.0
        self.idf = {
            t: math.log(1.0 + (self.n - d + 0.5) / (d + 0.5)) for t, d in df.items()
        }

    def total_mass(self, term_weights: Dict[str, float]) -> float:
        return sum(w * self.idf[t] for t, w in term_weights.items() if t in self.idf)

    def score(self, idx: int, term_weights: Dict[str, float]) -> Tuple[float, List[str], float]:
        """Returns (bm25 score, matched terms, matched IDF mass)."""
        tf = self.doc_tf[idx]
        dl = self.doc_len[idx]
        total = 0.0
        mass = 0.0
        matched: List[str] = []
        for t, w in term_weights.items():
            f = tf.get(t)
            if not f:
                continue
            idf = self.idf.get(t, 0.0)
            denom = f + _BM25_K1 * (1.0 - _BM25_B + _BM25_B * dl / self.avgdl)
            total += w * idf * f * (_BM25_K1 + 1.0) / denom
            mass += w * idf
            matched.append(t)
        return total, matched, mass


class CandidateSectionMatch(BaseModel):
    section_identifier: str = Field(description="Normalized section identifier e.g. IPC 498A, BNS 85")
    statute: str = Field(description="Statute name: 'IPC' or 'BNS'")
    section_number: str = Field(description="Section number string e.g. '498A', '85'")
    title: str = Field(description="Section title or offense description")
    chapter: Optional[str] = Field(default=None, description="Chapter title if available")
    score: float = Field(description="Local pre-filter relevance score (0.0 to 1.0)")
    matched_terms: List[str] = Field(default_factory=list, description="Keywords/terms matched locally")
    matched_concepts: List[str] = Field(default_factory=list, description="Stage 1 legal concepts that retrieved this section")

    @property
    def statute_type(self) -> str:
        return self.statute

    @property
    def section_title(self) -> str:
        return self.title

    @property
    def chapter_name(self) -> Optional[str]:
        return self.chapter


from .statute_repository import StatuteRepository
class StatuteClassifierPrefilter:
    """
    Fast pre-filter for Statute Identification Stage.
    Uses StatuteRepository cached in-memory database to match query strings against candidate sections.
    """

    def __init__(self):
        repo = StatuteRepository.get_instance()
        self.sections_db: List[Dict[str, Any]] = repo.get_sections_db()
        self._bm25: Optional[_BM25Index] = None

    def _load_datasets(self):
        """Loads dataset records exclusively from ipc.json via StatuteRepository."""
        repo = StatuteRepository.get_instance()
        self.sections_db = repo.get_sections_db()
        self._bm25 = None

    def _get_bm25(self) -> _BM25Index:
        """
        FIX 3 – fully rewritten field-weighted index using all rich ipc.json fields.

        Weight scheme (descending discriminative power):
          title          × 5  – section heading; most specific signal
          key_principle  × 4  – concise plain-language summary of the offence
          plain_language × 3  – layman wording, close to fact vocabulary
          chapter_title  × 3  – chapter context strongly disambiguates
          ingredients    × 3  – legal elements / key_elements list
          kb_triggers    × 3  – domain knowledge-base factual triggers
          illustrations  × 2  – scenario descriptions in the statute itself
          full_text      × 1  – raw statutory text; very noisy, used as catch-all

        All fields sourced from ipc.json via StatuteRepository.get_statute_db().
        """
        if self._bm25 is None:
            try:
                statute_db = StatuteRepository.get_instance().get_statute_db() or {}
            except Exception:
                statute_db = {}
            docs: List[List[str]] = []
            kb_by_key = {
                (rule.statute.upper(), rule.section.upper()): rule
                for rule in get_effective_knowledge_base()
            }
            for rec in self.sections_db:
                statute = str(rec.get("statute", "IPC")).upper()
                section_number = str(rec.get("section_number", "")).upper()
                ext = statute_db.get(
                    f"{rec.get('statute', 'IPC')}_{rec.get('section_number', '')}"
                ) or {}

                # 1. Title / heading — most discriminative signal (weight ×5)
                title_tokens = _tokenize(
                    rec.get("title", "") or str(ext.get("section_title") or "")
                )

                # 2. key_principle — plain-language summary (weight ×4)
                kp_tokens = _tokenize(str(ext.get("key_principle") or ""))

                # 3. plain_language — layman wording (weight ×3)
                pl_tokens = _tokenize(str(ext.get("plain_language") or ""))

                # 4. chapter_title — chapter context is strong disambiguating signal (weight ×3)
                # sections_db stores chapter_title under "chapter"; statute_db also has it.
                chapter_tokens = _tokenize(
                    rec.get("chapter", "") or str(ext.get("chapter_title") or "")
                )

                # 5. ingredients + key_elements — legal elements list (weight ×3)
                ings = ext.get("ingredients") or []
                key_elems = ext.get("key_elements") or []
                all_ings = list(ings) + list(key_elems)
                ing_text = " ".join(str(i) for i in all_ings) if all_ings else ""
                ing_tokens = _tokenize(ing_text)

                # 6. Knowledge-base factual triggers — domain-specific (weight ×3)
                kb_rule = kb_by_key.get((statute, section_number))
                kb_tokens = (
                    _tokenize(
                        " ".join(kb_rule.factual_triggers + kb_rule.mandatory_ingredients)
                    )
                    if kb_rule
                    else []
                )

                # 7. Illustration key_principles — concrete case-scenario vocabulary (weight ×2)
                illustrations = ext.get("illustrations") or []
                illus_parts: List[str] = []
                if isinstance(illustrations, list):
                    for il in illustrations:
                        if isinstance(il, dict):
                            kp = il.get("key_principle") or il.get("text") or ""
                            if kp:
                                illus_parts.append(str(kp))
                        elif isinstance(il, str) and il.strip():
                            illus_parts.append(il)
                illus_tokens = _tokenize(" ".join(illus_parts))

                # 8. Full statutory text — last resort, very noisy (weight ×1)
                # statute_db "full_text" is the raw statute text only (not lowercased concat);
                # fall back to sections_db "full_text" which is the lowercased concatenation of
                # all fields built by StatuteRepository._load_ipc_json().
                full_tokens = _tokenize(
                    str(ext.get("full_text") or rec.get("full_text", ""))
                )

                docs.append(
                    title_tokens * _TITLE_WEIGHT              # ×5
                    + kp_tokens * _KEY_PRINCIPLE_WEIGHT       # ×4
                    + pl_tokens * _INGREDIENT_WEIGHT          # ×3
                    + chapter_tokens * _INGREDIENT_WEIGHT     # ×3
                    + ing_tokens * _INGREDIENT_WEIGHT         # ×3
                    + kb_tokens * _INGREDIENT_WEIGHT          # ×3
                    + illus_tokens * 2                        # ×2
                    + full_tokens                             # ×1
                )
            self._bm25 = _BM25Index(docs)
        return self._bm25

    def _rank(
        self,
        term_weights: Dict[str, float],
        regime_filter: Optional[str],
        gate_text: str,
        query_domains: Optional[frozenset] = None,
    ) -> List[Tuple[Dict[str, Any], float, List[str], float]]:
        """
        Core retrieval for one conduct query. Returns [(record, relative_score, matched_terms,
        coverage)] sorted best-first. Applies: regime filter, non-offence chapter filter,
        chapter-domain coherence gate, fatal-disqualification gate, IDF-mass coverage floor,
        and a relative-score floor.

        query_domains: frozenset of domain strings derived from concept labels (see
        _derive_query_domains). When provided, any section whose chapter domains share no
        overlap with query_domains is eliminated — structurally, without per-section rules.
        Enabling/ancillary provisions (GENERAL domain) always pass regardless of query domain.
        """
        bm25 = self._get_bm25()
        total_mass = bm25.total_mass(term_weights)
        if total_mass <= 0.0:
            return []
        scored: List[Tuple[Dict[str, Any], float, List[str], float]] = []
        for idx, record in enumerate(self.sections_db):
            if regime_filter and record["statute"] != regime_filter:
                continue
            if self._is_non_offence_section(record):
                continue

            # ----------------------------------------------------------------
            # Chapter-domain coherence gate (structural, not per-section)
            # A section passes if ANY of its chapter's domains appears in the
            # query domains. GENERAL always passes (enabling provisions).
            # Skipped when query_domains is None (e.g. legacy callers).
            # ----------------------------------------------------------------
            if query_domains:
                sec_num_upper = str(record.get("section_number", "")).strip().upper()
                if sec_num_upper not in _ENABLING_SECTION_ALLOWLIST:
                    chapter = str(record.get("chapter") or "")
                    sec_chapter_domains = _chapter_domains(chapter)
                    if not sec_chapter_domains.intersection(query_domains):
                        continue  # chapter domain incompatible — eliminate

            disqualified, _, _ = self.evaluate_fatal_disqualification(
                record["section_number"].upper(), record["statute"].upper(), gate_text
            )
            if disqualified:
                continue
            raw, matched, mass = bm25.score(idx, term_weights)
            if raw <= 0.0:
                continue
            coverage = mass / total_mass
            # Dual gate: must cover ≥ MIN_COVERAGE of query IDF mass AND match
            # ≥ MIN_MATCHED_TERMS distinct token types.  Coverage alone was too
            # blunt (cut 304A which has coverage 0.175 on a valid single-token match
            # after stopping "treat").  The term-count gate blocks true zero-signal
            # sections that somehow pass coverage via one ultra-rare query token.
            if coverage < _MIN_COVERAGE or len(matched) < _MIN_MATCHED_TERMS:
                continue
            scored.append((record, raw, matched, coverage))
        if not scored:
            return []
        max_raw = max(x[1] for x in scored) or 1.0
        n_query_tokens = len(term_weights)  # distinct token types in this group's query

        results = []
        for rec, raw, matched, cov in scored:
            rel = raw / max_raw
            if rel < _MIN_RELATIVE_SCORE:
                continue

            # ----------------------------------------------------------------
            # Term-breadth penalty: a single matched token should never produce
            # a high score regardless of its IDF. Scale the score by the fraction
            # of query tokens matched, with a floor so a strong single-match
            # (like 304A on "negligen") still passes at a reasonable score.
            #
            # breadth_factor = matched_tokens / query_tokens, floored at 0.35.
            # A 1-of-1 token query gets factor=1.0 (no penalty — single-token
            # groups arise from narrow concept labels like "Abetment").
            # A 1-of-4 token query gets factor=max(0.35, 0.25)=0.35 — strong penalty.
            # A 3-of-4 token query gets factor=0.75 — modest penalty.
            # ----------------------------------------------------------------
            if n_query_tokens > 1:
                breadth_factor = max(0.35, len(matched) / n_query_tokens)
            else:
                breadth_factor = 1.0  # single-token query: no penalty

            score = round(rel * min(1.0, 0.4 + cov) * breadth_factor, 3)

            # After applying breadth penalty, re-apply the relative floor so
            # penalized sections don't sneak through at a reduced score.
            if score < _MIN_RELATIVE_SCORE * 0.5:
                continue

            results.append((rec, score, matched, round(cov, 3)))

        results.sort(key=lambda x: x[1], reverse=True)
        return results

    @staticmethod
    def _to_match(rec: Dict[str, Any], score: float, matched: List[str], concepts: Optional[List[str]] = None) -> "CandidateSectionMatch":
        return CandidateSectionMatch(
            section_identifier=rec["identifier"],
            statute=rec["statute"],
            section_number=rec["section_number"],
            title=rec["title"],
            chapter=rec["chapter"],
            score=score,
            matched_terms=matched[:5],
            matched_concepts=concepts or [],
        )

    @staticmethod
    def _is_non_offence_section(record: Dict[str, Any]) -> bool:
        """General Explanations / General Exceptions are excluded unless explicitly enabling."""
        sec = str(record.get("section_number", "")).strip().upper()
        if sec in _ENABLING_SECTION_ALLOWLIST:
            return False
        chapter = str(record.get("chapter") or "").lower()
        return any(marker in chapter for marker in _NON_OFFENCE_CHAPTER_MARKERS)

    def shortlist_candidates_for_query(
        self,
        legal_query_obj: LegalQueryObject,
        top_k: int = 10,
        target_regime: Optional[str] = None,
    ) -> List[CandidateSectionMatch]:
        """
        Pre-filters and shortlists top candidate sections for LegalQueryObject.
        Executes 100% locally in Python code with ZERO LLM calls.

        Args:
            legal_query_obj: Validated Stage 1 LegalQueryObject.
            top_k: Maximum number of candidate sections to return (default 10).
            target_regime: Optional 'IPC + CrPC' or 'BNS + BNSS' filter.

        Returns:
            List of CandidateSectionMatch objects sorted by relevance score descending.
        """
        # Collect concept terms and sub-query terms
        # Fix 6: strip question boilerplate ("What are the legal consequences of ...") so only
        # the conduct phrase is matched. Concept labels are already short phrases.
        concept_phrases = [c.concept.lower() for c in legal_query_obj.legal_concepts if c.concept]
        query_terms: List[str] = []
        for phrase in concept_phrases:
            query_terms.extend(re.findall(r"[a-z]+", phrase))

        for sq in legal_query_obj.sub_queries:
            query_terms.extend(re.findall(r"[a-z]+", strip_query_boilerplate(sq.query).lower()))
            if sq.concept:
                concept_phrases.append(sq.concept.lower())
                query_terms.extend(re.findall(r"[a-z]+", sq.concept.lower()))

        # Fix 2/6: expanded stop list + word-level tokens (kept as raw words here so that the
        # KB trigger / bridge logic below still sees readable text; BM25 stems them later).
        filtered_terms = [t for t in query_terms if t not in _RETRIEVAL_STOP_WORDS and len(t) > 2]
        unique_query_terms = set(filtered_terms)


        if not unique_query_terms or not self.sections_db:
            return []

        # Filter database by legal regime if requested
        regime_filter = None
        regime_str = target_regime or legal_query_obj.legal_regime or ""
        if "BNS" in regime_str.upper():
            regime_filter = "BNS"
        elif "IPC" in regime_str.upper():
            regime_filter = "IPC"

        query_full_text = " ".join(concept_phrases) + " " + " ".join(unique_query_terms)

        # Derive query domains for chapter-domain coherence gate.
        sq_texts = [strip_query_boilerplate(sq.query) for sq in legal_query_obj.sub_queries if sq.query]
        query_domains = _derive_query_domains(concept_phrases, sq_texts)

        # BM25 over word tokens with coverage floor (see _rank). Single flat query: all terms weight 1.
        # Apply query-only stop stems to suppress domain-generic context words that appear across
        # hundreds of sections (medic, hospit, offic, etc.) and cause false-positive matches.
        term_weights = {t: 1.0 for t in set(_tokenize(" ".join(unique_query_terms))) - _QUERY_ONLY_STOP_STEMS}
        if not term_weights:
            return []
        ranked = self._rank(term_weights, regime_filter, query_full_text, query_domains)
        results: List[CandidateSectionMatch] = []
        seen: Set[str] = set()
        for rec, score, matched, _cov in ranked:
            if rec["identifier"] in seen:
                continue
            seen.add(rec["identifier"])
            results.append(self._to_match(rec, score, matched))
            if len(results) >= top_k:
                break
        return results

    @staticmethod
    def evaluate_fatal_disqualification(section_number: str, statute: str, facts_text: str) -> Tuple[bool, Optional[str], List[str]]:
        """
        Evaluates mandatory ingredient rules from STATUTE_KNOWLEDGE_BASE to screen sections.
        Returns Tuple of (is_not_triggered, not_triggered_reason, missing_mandatory_ingredients).
        """
        lower_facts = _WordText((facts_text or "").lower())
        sec_num_clean = (section_number or "").strip().upper().replace("SECTION ", "").replace("IPC_", "")

        for rule in get_effective_knowledge_base():
            target_sec = rule.bns_equivalent if "BNS" in (statute or "").upper() else rule.section
            if sec_num_clean == target_sec.upper() or sec_num_clean == rule.section.upper():
                # 1. Subject-Matter Scope Disqualification Check (e.g. MOVABLE_PROPERTY_ONLY vs land)
                if rule.subject_matter_scope == "MOVABLE_PROPERTY_ONLY" and rule.disqualifying_subject_matters:
                    has_disqualifying = any(disq in lower_facts for disq in rule.disqualifying_subject_matters)
                    has_movable_mention = any(m in lower_facts for m in ["cash", "money", "gold", "jewelry", "jewellery", "ornaments", "vehicle", "car", "goods", "stridhan", "movable"])
                    if has_disqualifying and not has_movable_mention:
                        missing = rule.mandatory_ingredients + ["movable_property"]
                        reason = f"Screening non-trigger: Section {rule.section} requires movable property; facts involve immovable property/land."
                        return True, reason, missing

                # 2. Mandatory Factual Trigger Check
                # Only applied when requires_trigger_gate=True — sections where a specific
                # life/body event (death, rape, suicide) MUST appear in the facts verbatim.
                # General property/fraud/document sections are NOT gated here because
                # their facts may be described with different vocabulary than the trigger list;
                # the concept-keyword bridge in shortlist_candidates_for_query handles those.
                if rule.requires_trigger_gate and rule.factual_triggers:
                    has_trigger = any(trig in lower_facts for trig in rule.factual_triggers)
                    if not has_trigger:
                        missing = rule.mandatory_ingredients
                        reason = (
                            f"Screening non-trigger: Section {rule.section} requires a specific "
                            f"factual event ({rule.mandatory_ingredients[0] if rule.mandatory_ingredients else 'mandatory element'}) "
                            f"which is not indicated in the case facts."
                        )
                        return True, reason, missing

        return False, None, []

    @staticmethod
    def compute_hybrid_score(
        ingredient_score: float,
        classifier_score: float,
        keyword_score: float,
        semantic_score: float
    ) -> float:
        """
        Calculates 4-part hybrid score weighted as:
        0.40 Ingredient Match + 0.25 Classifier Score + 0.20 Keyword Match + 0.15 Semantic Similarity
        """
        raw = (
            (0.40 * max(0.0, min(1.0, ingredient_score))) +
            (0.25 * max(0.0, min(1.0, classifier_score))) +
            (0.20 * max(0.0, min(1.0, keyword_score))) +
            (0.15 * max(0.0, min(1.0, semantic_score)))
        )
        return round(raw, 4)

    @staticmethod
    def detect_factual_triggers(facts_text: str, statute_type: str = "IPC") -> List[Dict[str, Any]]:
        """
        Hardcoded keyword->section triggers were REMOVED: they injected sections (stalking,
        intimidation, ...) from substring coincidences, bypassing retrieval. Kept as a no-op
        so existing callers (Stage 2, Stage 3 fallback) keep working. Candidate sections now
        come only from BM25 retrieval over ipc.json.
        """
        return []

    def prefilter_candidates(
        self,
        query_text: str,
        statute_type: str = "IPC",
        top_k: int = 10,
    ) -> List[CandidateSectionMatch]:
        """
        Pre-filters candidates for a raw text query string and statute_type ('IPC' or 'BNS').
        """
        dummy_query = LegalQueryObject(
            legal_regime="BNS + BNSS" if statute_type == "BNS" else "IPC + CrPC",
            legal_concepts=[LegalConceptItem(concept=query_text, confidence=0.95)]
        )
        return self.shortlist_candidates_for_query(dummy_query, top_k=top_k, target_regime=statute_type)

    # ------------------------------------------------------------------
    # Fused retrieval over a whole LegalQueryObject (preferred entry point)
    # ------------------------------------------------------------------

    @staticmethod
    def _collect_strings(obj: Any) -> List[str]:
        """Recursively collects string values from str / list / dict / pydantic objects."""
        if obj is None:
            return []
        if isinstance(obj, str):
            return [obj]
        if hasattr(obj, "model_dump"):
            obj = obj.model_dump()
        if isinstance(obj, dict):
            out: List[str] = []
            for v in obj.values():
                out.extend(StatuteClassifierPrefilter._collect_strings(v))
            return out
        if isinstance(obj, (list, tuple, set)):
            out = []
            for v in obj:
                out.extend(StatuteClassifierPrefilter._collect_strings(v))
            return out
        return []

    @staticmethod
    def _obj_value(obj: Any, name: str, default: Any = None) -> Any:
        """Read a field from a Pydantic object or mapping without assuming one representation."""
        if isinstance(obj, dict):
            return obj.get(name, default)
        return getattr(obj, name, default)

    @staticmethod
    def _is_charge_bearing_fact(fact: Any) -> bool:
        """
        Include alleged/admitted conduct and material results/conditions.
        Exclude defence/prosecution submissions (STATEMENT) from offence-term generation:
        those belong in bail/procedural analysis, not IPC charge retrieval.
        """
        conduct = str(StatuteClassifierPrefilter._obj_value(fact, "conduct_type", "")).upper()
        status = str(StatuteClassifierPrefilter._obj_value(fact, "factual_status", "ALLEGED")).upper()
        return conduct in {"ACT", "OMISSION", "RESULT", "CONDITION"} and status in {
            "ALLEGED", "ADMITTED", "DISPUTED", "UNKNOWN"
        }

    def retrieve_for_legal_query(
        self,
        legal_query_obj: LegalQueryObject,
        statute_type: str = "IPC",
        top_k: int = 20,
        per_concept: int = 4,
        return_procedural: bool = False,
    ):
        """
        Factual-first fused retrieval:
        - one group per legal concept with only its linked sub-query text;
        - one group per charge-bearing factual allegation;
        - statement-only facts (denials, submissions, bail arguments) are not treated as offence conduct;
        - actor/party names are removed from query terms;
        - BM25/coverage gates and fatal factual-event gates remain in force.
        - procedural concepts (bail, remand, CrPC provisions) are skipped from IPC BM25 and
          collected separately; the caller can route them to a CrPC/bail-argument pipeline.

        Returns:
            List[CandidateSectionMatch]  when return_procedural=False (default, backward-compatible)
            Tuple[List[CandidateSectionMatch], List[Dict[str,str]]]  when return_procedural=True
                where the second element is a list of dicts:
                  {"concept": <label>, "sub_query": <linked sub-query text>}
                one entry per procedural concept group that was skipped from IPC retrieval.
        This is a candidate pre-filter, not a statutory-ingredient finding.
        """
        regime_filter = "BNS" if "BNS" in (statute_type or "").upper() else "IPC"

        # Derive query domains from all concept labels and sub-query texts once.
        # These drive the chapter-domain coherence gate in every _rank() call below.
        all_concept_labels: List[str] = [
            str(self._obj_value(c, "concept", "") or "")
            for c in (getattr(legal_query_obj, "legal_concepts", []) or [])
        ]
        all_sq_texts: List[str] = [
            strip_query_boilerplate(str(self._obj_value(sq, "query", "") or ""))
            for sq in (getattr(legal_query_obj, "sub_queries", []) or [])
        ]
        case_summary_text = str(getattr(legal_query_obj, "case_summary", "") or "")
        if case_summary_text:
            all_sq_texts.append(case_summary_text)
        query_domains: frozenset = _derive_query_domains(all_concept_labels, all_sq_texts)
        logger.debug("ChapterDomainGate: query_domains=%s", sorted(query_domains))

        actor_text: List[str] = []
        for attr in ("entities", "relationship"):
            actor_text.extend(self._collect_strings(getattr(legal_query_obj, attr, None)))
        factual_items = list(getattr(legal_query_obj, "factual_allegations", []) or [])
        for fact in factual_items:
            actor_text.extend(self._collect_strings(self._obj_value(fact, "actor")))
        for sq in getattr(legal_query_obj, "sub_queries", []) or []:
            actor_text.extend(self._collect_strings(self._obj_value(sq, "target_parties")))
            actor_text.extend(self._collect_strings(self._obj_value(sq, "role_alleged")))
        actor_tokens = set(_tokenize(" ".join(actor_text)))

        groups: List[Tuple[str, str]] = []
        procedural_groups: List[Dict[str, str]] = []  # procedural concepts skipped from IPC BM25
        used_sq: Set[int] = set()
        for concept in getattr(legal_query_obj, "legal_concepts", []) or []:
            label = str(self._obj_value(concept, "concept", "") or "").strip()
            if not label:
                continue
            concept_id = self._obj_value(concept, "concept_id")
            linked_queries = []
            for index, sq in enumerate(getattr(legal_query_obj, "sub_queries", []) or []):
                sq_concept_id = self._obj_value(sq, "concept_id")
                sq_concept = str(self._obj_value(sq, "concept", "") or "")
                if (concept_id and sq_concept_id == concept_id) or (sq_concept and sq_concept.lower() == label.lower()):
                    linked_queries.append(strip_query_boilerplate(str(self._obj_value(sq, "query", ""))))
                    used_sq.add(index)
            sq_text = " ".join(linked_queries)
            # Route procedural concepts (bail, remand, CrPC) to a separate track instead of
            # feeding them into the IPC BM25 index, where they cause false positives.
            if is_procedural_concept(label):
                logger.debug("ProceduralGate: skipping IPC BM25 for concept %r", label)
                procedural_groups.append({"concept": label, "sub_query": sq_text})
                continue
            groups.append((label, sq_text))

        for index, sq in enumerate(getattr(legal_query_obj, "sub_queries", []) or []):
            if index not in used_sq:
                label = str(self._obj_value(sq, "concept", "") or "")
                query = strip_query_boilerplate(str(self._obj_value(sq, "query", "") or ""))
                # Orphan sub-queries that are procedural also go to the procedural track.
                if is_procedural_concept(label) or is_procedural_concept(query):
                    logger.debug("ProceduralGate: skipping orphan sub-query concept %r", label or query[:40])
                    procedural_groups.append({"concept": label, "sub_query": query})
                    continue
                if label or query:
                    groups.append((label, query))

        # Critical addition: retrieve from individual source facts as well as concept summaries.
        # This prevents a broad concept label from diluting distinctive conduct such as
        # destruction of monitoring records or failure to arrange specialist intervention.
        for fact in factual_items:
            if not self._is_charge_bearing_fact(fact):
                continue
            description = str(self._obj_value(fact, "description", "") or "")
            if description.strip():
                # FIX 4 – was `(f"FACT:{fact_id}", description)`.
                # "FACT:F1" tokenises to ["fact"] → weight-2.0 label token → matched every
                # section whose statutory text contained the word "fact" (e.g. IPC 495, 142,
                # 171G …).  Using the first 60 chars of the description as the label means the
                # label tokens are the same conduct words as the body, which is correct.
                groups.append((description[:60], description))

        # FIX 7 – Also add the raw case_summary as a retrieval group so outcome words
        # such as "death", "negligence" (which appear in the case narrative but are often
        # absent from Stage-1 sub-queries) can still surface sections like IPC 304A.
        # The summary is split at the mid-sentence boundary to avoid diluting a long text
        # into a vector where every token has near-zero IDF mass.
        case_summary = str(getattr(legal_query_obj, "case_summary", "") or "").strip()
        if case_summary:
            # Split roughly in half on a sentence boundary so each chunk is focused.
            mid = len(case_summary) // 2
            split_at = case_summary.rfind(".", 0, mid + 100)
            if split_at < mid // 2:
                split_at = mid
            chunk1 = case_summary[: split_at + 1].strip()
            chunk2 = case_summary[split_at + 1 :].strip()
            for chunk in [chunk1, chunk2]:
                if len(chunk) > 20:
                    groups.append((chunk[:60], chunk))

        # Pre-build title lookup: {normalised_title: identifier} for every section in sections_db.
        # Used below to guarantee KB-title-matched sections are always included even if BM25
        # score falls below the relative floor due to competition in a broad retrieval group.
        title_to_identifier: Dict[str, str] = {}
        for rec in self.sections_db:
            t = (rec.get("title") or "").strip().lower()
            if t:
                title_to_identifier[t] = rec["identifier"]

        group_ranked: List[Tuple[str, List[Tuple[Dict[str, Any], float, List[str], float]]]] = []
        # Track which section identifiers are directly pinned by title-match so we can
        # guarantee their inclusion in fused results even if _rank drops them.
        title_pinned_identifiers: Set[str] = set()
        title_pinned_records: Dict[str, Dict[str, Any]] = {}  # identifier -> record

        for label, text in groups:
            label_tokens = set(_tokenize(label)) - _QUERY_ONLY_STOP_STEMS
            text_tokens = set(_tokenize(text)) - actor_tokens - label_tokens - _QUERY_ONLY_STOP_STEMS
            weights: Dict[str, float] = {token: 2.0 for token in label_tokens}
            weights.update({token: 1.0 for token in text_tokens})
            if not weights:
                continue
            # Do not use actor names or neutral party labels as retrieval evidence.
            gate_text = f"{label} {text}"
            ranked = self._rank(weights, regime_filter, gate_text, query_domains)

            # Title-pin: if the concept label is (or starts with) a section title verbatim,
            # force that section into results at a high synthetic score, bypassing the
            # _MIN_RELATIVE_SCORE floor that can drop it when competing with a stronger signal.
            label_norm = label.strip().lower()
            for title_norm, ident in title_to_identifier.items():
                # Accept if label starts with the section title (handles "Title — extra context").
                if label_norm == title_norm or label_norm.startswith(title_norm):
                    title_pinned_identifiers.add(ident)
                    # Find the full record so we can inject it into best/fused later.
                    for r in self.sections_db:
                        if r["identifier"] == ident:
                            title_pinned_records[ident] = r
                            break

            if ranked:
                group_ranked.append((label or text[:40], ranked[:10]))

        fused: Dict[str, float] = {}
        best: Dict[str, Tuple[Dict[str, Any], float, List[str]]] = {}
        concepts_for: Dict[str, List[str]] = {}
        for label, ranked in group_ranked:
            for rank, (record, relative_score, matched, _coverage) in enumerate(ranked):
                key = record["identifier"]
                fused[key] = fused.get(key, 0.0) + 1.0 / (_RRF_K + rank + 1)
                if key not in best or relative_score > best[key][1]:
                    best[key] = (record, relative_score, matched)
                concepts_for.setdefault(key, [])
                if label not in concepts_for[key]:
                    concepts_for[key].append(label)

        # Title-pin injection: for any section whose title exactly matched a concept label,
        # ensure it appears in fused results with a synthetic score equivalent to rank-1.
        # This guarantees IPC 201/204 etc. are never silently dropped by the relative-score
        # floor when a noisier section happens to top the retrieval group.
        for pinned_id, pinned_rec in title_pinned_records.items():
            gate_text_for_pin = f"{pinned_rec.get('title', '')} {pinned_rec.get('chapter', '')}"
            disqualified, _, _ = self.evaluate_fatal_disqualification(
                pinned_rec["section_number"].upper(), pinned_rec["statute"].upper(), gate_text_for_pin
            )
            if disqualified:
                continue
            if pinned_id not in fused:
                # Insert as a top-2 synthetic hit (slightly below rank-0 to avoid always topping)
                fused[pinned_id] = 1.0 / (_RRF_K + 1)
                best[pinned_id] = (pinned_rec, 0.85, ["title_pin"])
                concepts_for[pinned_id] = ["title-matched concept"]
            else:
                # Already retrieved — boost its RRF score so it ranks higher
                fused[pinned_id] += 1.0 / (_RRF_K + 1)

        if not fused:
            if return_procedural:
                return [], procedural_groups
            return []

        # Preserve per-issue recall without blindly padding from unrelated global matches.
        selected: List[str] = []
        for rank_index in range(max(1, per_concept)):
            for _label, ranked in group_ranked:
                if rank_index < len(ranked):
                    key = ranked[rank_index][0]["identifier"]
                    if key not in selected:
                        selected.append(key)
                    if len(selected) >= top_k:
                        break
            if len(selected) >= top_k:
                break
        for key in sorted(fused, key=fused.get, reverse=True):
            if len(selected) >= top_k:
                break
            if key not in selected:
                selected.append(key)

        selected.sort(key=lambda key: fused[key], reverse=True)
        ipc_matches = [
            self._to_match(best[key][0], best[key][1], best[key][2], concepts_for[key])
            for key in selected
        ]
        if procedural_groups:
            logger.info(
                "ProceduralGate: %d procedural concept(s) separated from IPC retrieval: %s",
                len(procedural_groups),
                [pg["concept"] for pg in procedural_groups],
            )
        if return_procedural:
            return ipc_matches, procedural_groups
        return ipc_matches