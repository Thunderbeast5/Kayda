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
    ),
    SectionRule(
        section="307",
        statute="IPC",
        bns_equivalent="109",
        title="Attempt to Murder",
        mandatory_ingredients=["attempt_to_murder", "intent_to_cause_death"],
        factual_triggers=["attempt to murder", "intent to kill", "stabbed in chest", "shot", "strangled", "life-threatening", "attempted to kill"],
        chapter_number="XVI",
        chapter_title="Offences Affecting Life",
        punishment_minimum=None,
        punishment_maximum="10 Years",
        fine=True,
        cognizable=True,
        bailable=False,
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
    ),
    SectionRule(
        section="498A",
        statute="IPC",
        bns_equivalent="85",
        title="Cruelty by Husband or Relatives",
        mandatory_ingredients=["marriage_relationship", "cruelty_or_dowry_harassment"],
        factual_triggers=["dowry", "cruelty", "harass", "demand", "torture", "in-laws", "matrimonial"],
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
        factual_triggers=["cheated", "defrauded", "deceived", "fake promise", "money induced", "false representation", "scam"],
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
        factual_triggers=["false deed", "fraudulent deed", "fabricated transfer", "false consideration", "bogus document", "fictitious transfer"],
        chapter_number="XVII",
        chapter_title="Offences Relating to Property / Fraudulent Documents",
        punishment_minimum=None,
        punishment_maximum="2 Years",  # First Schedule IPC: 2 years or fine or both
        fine=True,
        cognizable=False,   # First Schedule: Non-cognizable
        bailable=True,      # First Schedule: Bailable
    ),
    SectionRule(
        section="506",
        statute="IPC",
        bns_equivalent="351",
        title="Criminal Intimidation",
        mandatory_ingredients=["threat_of_injury_to_person_or_property"],
        factual_triggers=["threat", "threatened", "intimidat", "warning", "abuse", "scared", "terrorised"],
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

    # ------------------------------------------------------------------ #
    #  OFFENCES AGAINST LIFE & BODY                                        #
    # ------------------------------------------------------------------ #
    SectionRule(
        section="302",
        statute="IPC",
        bns_equivalent="101",
        title="Murder",
        mandatory_ingredients=["death_of_human_being", "act_done_with_intention_to_cause_death_or_knowledge"],
        factual_triggers=["murdered", "killed", "homicide", "death caused", "shot dead", "stabbed to death",
                          "strangulated", "poisoned", "set on fire", "burnt alive", "beaten to death", "lynched"],
        chapter_number="XVI",
        chapter_title="Offences Affecting the Human Body",
        punishment_minimum="Life Imprisonment",
        punishment_maximum="Death",
        fine=False,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="304",
        statute="IPC",
        bns_equivalent="105",
        title="Culpable Homicide Not Amounting to Murder",
        mandatory_ingredients=["death_caused", "culpable_homicide_not_amounting_to_murder"],
        factual_triggers=["culpable homicide", "not murder", "sudden provocation", "death without premeditation",
                          "unintended killing", "accidental killing", "heat of passion"],
        chapter_number="XVI",
        chapter_title="Offences Affecting the Human Body",
        punishment_minimum=None,
        punishment_maximum="Life Imprisonment",
        fine=True,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="304A",
        statute="IPC",
        bns_equivalent="106",
        title="Causing Death by Negligence",
        mandatory_ingredients=["death_caused", "negligent_or_rash_act", "not_amounting_to_culpable_homicide"],
        factual_triggers=["negligence", "rash driving", "accident", "road accident", "vehicle hit", "knocked down",
                          "ran over", "medical negligence", "negligent act caused death", "careless"],
        chapter_number="XVI",
        chapter_title="Offences Affecting the Human Body",
        punishment_minimum=None,
        punishment_maximum="2 Years",
        fine=True,
        cognizable=False,
        bailable=True,
    ),
    SectionRule(
        section="306",
        statute="IPC",
        bns_equivalent="108",
        title="Abetment of Suicide",
        mandatory_ingredients=["suicide_committed", "abetment_by_accused"],
        factual_triggers=["abetment of suicide", "instigated suicide", "drove to suicide", "harassment led to suicide",
                          "suicide note", "forced to commit suicide", "compelled suicide", "victim ended life"],
        chapter_number="XVI",
        chapter_title="Offences Affecting the Human Body",
        punishment_minimum=None,
        punishment_maximum="10 Years",
        fine=True,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="308",
        statute="IPC",
        bns_equivalent="110",
        title="Attempt to Commit Culpable Homicide",
        mandatory_ingredients=["act_done_with_intention_or_knowledge", "likely_to_cause_death"],
        factual_triggers=["attempt to commit culpable homicide", "attempt to kill without premeditation",
                          "attacked with intent", "grievous injury with intent to kill"],
        chapter_number="XVI",
        chapter_title="Offences Affecting the Human Body",
        punishment_minimum=None,
        punishment_maximum="7 Years",
        fine=True,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="309",
        statute="IPC",
        bns_equivalent="226",
        title="Attempt to Commit Suicide",
        mandatory_ingredients=["attempt_to_commit_suicide"],
        factual_triggers=["attempted suicide", "tried to kill himself", "tried to kill herself",
                          "consumed poison", "self-harm attempt", "slit wrist", "jumped from building"],
        chapter_number="XVI",
        chapter_title="Offences Affecting the Human Body",
        punishment_minimum=None,
        punishment_maximum="1 Year",
        fine=True,
        cognizable=False,
        bailable=True,
    ),
    SectionRule(
        section="319",
        statute="IPC",
        bns_equivalent="114",
        title="Hurt",
        mandatory_ingredients=["bodily_pain_disease_or_infirmity_caused"],
        factual_triggers=["hurt", "bodily pain", "caused pain", "physical injury", "bruises", "injury caused"],
        chapter_number="XVI",
        chapter_title="Offences Affecting the Human Body",
        punishment_minimum=None,
        punishment_maximum="1 Year",
        fine=True,
        cognizable=False,
        bailable=True,
    ),
    SectionRule(
        section="324",
        statute="IPC",
        bns_equivalent="117",
        title="Voluntarily Causing Hurt by Dangerous Weapons",
        mandatory_ingredients=["voluntarily_causing_hurt", "dangerous_weapon_or_means"],
        factual_triggers=["knife", "weapon", "sharp object", "acid", "fire", "rod", "iron rod", "stick",
                          "dangerous weapon", "sharp instrument", "sword", "dagger", "blade"],
        chapter_number="XVI",
        chapter_title="Offences Affecting the Human Body",
        punishment_minimum=None,
        punishment_maximum="3 Years",
        fine=True,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="325",
        statute="IPC",
        bns_equivalent="117",
        title="Voluntarily Causing Grievous Hurt",
        mandatory_ingredients=["voluntarily_causing_grievous_hurt"],
        factual_triggers=["grievous hurt", "grievous injury", "bone fracture", "fracture", "permanent disability",
                          "loss of limb", "disfigured", "eye injured", "ear damaged", "serious bodily injury"],
        chapter_number="XVI",
        chapter_title="Offences Affecting the Human Body",
        punishment_minimum=None,
        punishment_maximum="7 Years",
        fine=True,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="326",
        statute="IPC",
        bns_equivalent="117",
        title="Voluntarily Causing Grievous Hurt by Dangerous Weapons",
        mandatory_ingredients=["voluntarily_causing_grievous_hurt", "dangerous_weapon_or_means"],
        factual_triggers=["grievous hurt by weapon", "acid attack", "shot with gun", "stabbed grievously",
                          "chopped", "maimed by weapon", "grievous wound by knife"],
        chapter_number="XVI",
        chapter_title="Offences Affecting the Human Body",
        punishment_minimum=None,
        punishment_maximum="Life Imprisonment",
        fine=True,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="326A",
        statute="IPC",
        bns_equivalent="124",
        title="Voluntarily Causing Grievous Hurt by Use of Acid",
        mandatory_ingredients=["acid_attack", "grievous_hurt_caused"],
        factual_triggers=["acid attack", "acid thrown", "acid poured", "chemical attack", "burnt with acid",
                          "face disfigured by acid", "corrosive substance"],
        chapter_number="XVI",
        chapter_title="Offences Affecting the Human Body",
        punishment_minimum="10 Years",
        punishment_maximum="Life Imprisonment",
        fine=True,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="354",
        statute="IPC",
        bns_equivalent="74",
        title="Assault or Criminal Force on Woman with Intent to Outrage Her Modesty",
        mandatory_ingredients=["assault_or_criminal_force", "woman_victim", "intent_to_outrage_modesty"],
        factual_triggers=["outrage modesty", "molestation", "groped", "touched inappropriately", "eve teasing",
                          "sexual harassment", "touched without consent", "forcibly touched", "indecent assault"],
        chapter_number="XVI",
        chapter_title="Offences Against Women",
        punishment_minimum="1 Year",
        punishment_maximum="5 Years",
        fine=True,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="354A",
        statute="IPC",
        bns_equivalent="75",
        title="Sexual Harassment",
        mandatory_ingredients=["sexual_harassment_of_woman"],
        factual_triggers=["sexual harassment", "unwelcome sexual advances", "demand sexual favour",
                          "sexually coloured remarks", "showing pornography", "workplace harassment"],
        chapter_number="XVI",
        chapter_title="Offences Against Women",
        punishment_minimum=None,
        punishment_maximum="3 Years",
        fine=True,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="354D",
        statute="IPC",
        bns_equivalent="78",
        title="Stalking",
        mandatory_ingredients=["stalking_of_woman", "repeated_unwanted_contact_or_following"],
        factual_triggers=["stalking", "following", "monitoring", "watching repeatedly", "contacted repeatedly",
                          "cyberstalking", "online stalking", "tracking location", "surveillance of woman"],
        chapter_number="XVI",
        chapter_title="Offences Against Women",
        punishment_minimum=None,
        punishment_maximum="5 Years",
        fine=True,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="363",
        statute="IPC",
        bns_equivalent="137",
        title="Kidnapping",
        mandatory_ingredients=["kidnapping_from_lawful_guardianship_or_from_india"],
        factual_triggers=["kidnapped", "kidnapping", "abducted", "taken away", "missing child", "child missing",
                          "minor taken", "lured away", "enticed away", "taken without consent of guardian"],
        chapter_number="XVI",
        chapter_title="Kidnapping, Abduction, Slavery",
        punishment_minimum=None,
        punishment_maximum="7 Years",
        fine=True,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="364",
        statute="IPC",
        bns_equivalent="139",
        title="Kidnapping or Abduction in Order to Murder",
        mandatory_ingredients=["kidnapping_or_abduction", "intent_to_murder_or_endanger_life"],
        factual_triggers=["kidnapped to kill", "abducted to murder", "taken away to harm",
                          "kidnapping for ransom and threat to kill", "abducted and murdered"],
        chapter_number="XVI",
        chapter_title="Kidnapping, Abduction, Slavery",
        punishment_minimum="Life Imprisonment",
        punishment_maximum="Death",
        fine=False,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="364A",
        statute="IPC",
        bns_equivalent="140",
        title="Kidnapping for Ransom",
        mandatory_ingredients=["kidnapping_or_abduction", "ransom_demand_or_threat_to_cause_death"],
        factual_triggers=["ransom", "kidnapped for ransom", "demand ransom", "paid ransom",
                          "hostage", "release in exchange for money", "abducted for money"],
        chapter_number="XVI",
        chapter_title="Kidnapping, Abduction, Slavery",
        punishment_minimum="Life Imprisonment",
        punishment_maximum="Death",
        fine=False,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="366",
        statute="IPC",
        bns_equivalent="142",
        title="Kidnapping / Abduction of Woman to Compel Her Marriage",
        mandatory_ingredients=["kidnapping_or_abduction_of_woman", "compulsion_to_marry_or_illicit_intercourse"],
        factual_triggers=["kidnapped for marriage", "forced marriage", "abducted woman", "compelled to marry",
                          "taken away to marry", "lured into marriage", "tricked into marriage"],
        chapter_number="XVI",
        chapter_title="Kidnapping, Abduction, Slavery",
        punishment_minimum=None,
        punishment_maximum="10 Years",
        fine=True,
        cognizable=True,
        bailable=False,
    ),

    # ------------------------------------------------------------------ #
    #  SEXUAL OFFENCES                                                     #
    # ------------------------------------------------------------------ #
    SectionRule(
        section="375",
        statute="IPC",
        bns_equivalent="63",
        title="Rape (Definition)",
        mandatory_ingredients=["sexual_intercourse", "without_consent_or_against_will"],
        factual_triggers=["rape", "sexual assault", "forced intercourse", "non-consensual sex",
                          "sexually assaulted", "ravished", "violated"],
        chapter_number="XVI",
        chapter_title="Sexual Offences",
        punishment_minimum="7 Years",
        punishment_maximum="Life Imprisonment",
        fine=True,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="376A",
        statute="IPC",
        bns_equivalent="66",
        title="Rape Causing Death or Persistent Vegetative State",
        mandatory_ingredients=["rape_committed", "death_or_persistent_vegetative_state_caused"],
        factual_triggers=["rape and murder", "raped and killed", "died after rape", "rape victim died",
                          "vegetative state after rape", "gang rape and death"],
        chapter_number="XVI",
        chapter_title="Sexual Offences",
        punishment_minimum="20 Years",
        punishment_maximum="Death",
        fine=False,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="376D",
        statute="IPC",
        bns_equivalent="70",
        title="Gang Rape",
        mandatory_ingredients=["rape_committed_by_group_of_persons"],
        factual_triggers=["gang rape", "group rape", "multiple accused rape", "raped by several persons",
                          "raped by more than one", "collective rape"],
        chapter_number="XVI",
        chapter_title="Sexual Offences",
        punishment_minimum="20 Years",
        punishment_maximum="Life Imprisonment",
        fine=True,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="377",
        statute="IPC",
        bns_equivalent="None",  # Decriminalized for consensual acts; retained for non-consensual
        title="Unnatural Offences",
        mandatory_ingredients=["carnal_intercourse_against_order_of_nature", "non_consensual"],
        factual_triggers=["unnatural offence", "sodomy", "carnal intercourse against nature",
                          "sexual abuse of minor boy", "sexual assault on male"],
        chapter_number="XVI",
        chapter_title="Sexual Offences",
        punishment_minimum=None,
        punishment_maximum="Life Imprisonment",
        fine=True,
        cognizable=True,
        bailable=False,
    ),

    # ------------------------------------------------------------------ #
    #  PROPERTY OFFENCES                                                   #
    # ------------------------------------------------------------------ #
    SectionRule(
        section="378",
        statute="IPC",
        bns_equivalent="303",
        title="Theft",
        mandatory_ingredients=["movable_property", "dishonest_intention", "taken_without_consent"],
        factual_triggers=["theft", "stolen", "stole", "took away", "missing property", "property stolen",
                          "cash stolen", "jewellery stolen", "mobile stolen", "vehicle stolen", "pickpocket"],
        chapter_number="XVII",
        chapter_title="Offences Against Property",
        punishment_minimum=None,
        punishment_maximum="3 Years",
        fine=True,
        cognizable=True,
        bailable=False,
        subject_matter_scope="MOVABLE_PROPERTY_ONLY",
        disqualifying_subject_matters=["land", "plot", "real estate", "immovable property", "building", "flat", "field", "site"],
    ),
    SectionRule(
        section="379",
        statute="IPC",
        bns_equivalent="304",
        title="Punishment for Theft",
        mandatory_ingredients=["movable_property", "dishonest_taking_without_consent"],
        factual_triggers=["theft", "stolen", "stole", "robbed of", "snatched", "pick-pocketed",
                          "burglarized", "house theft", "property taken"],
        chapter_number="XVII",
        chapter_title="Offences Against Property",
        punishment_minimum=None,
        punishment_maximum="3 Years",
        fine=True,
        cognizable=True,
        bailable=False,
        subject_matter_scope="MOVABLE_PROPERTY_ONLY",
        disqualifying_subject_matters=["land", "plot", "real estate", "immovable property", "building", "flat", "field", "site"],
    ),
    SectionRule(
        section="380",
        statute="IPC",
        bns_equivalent="305",
        title="Theft in Dwelling House",
        mandatory_ingredients=["theft", "committed_in_dwelling_house_or_building"],
        factual_triggers=["house theft", "burglary", "theft in house", "theft in building", "broke into house",
                          "entered house and stole", "domestic theft", "theft from residence"],
        chapter_number="XVII",
        chapter_title="Offences Against Property",
        punishment_minimum=None,
        punishment_maximum="7 Years",
        fine=True,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="383",
        statute="IPC",
        bns_equivalent="308",
        title="Extortion",
        mandatory_ingredients=["putting_in_fear_of_injury", "dishonestly_inducing_delivery_of_property"],
        factual_triggers=["extortion", "extorted", "blackmail", "blackmailed", "demanded money under threat",
                          "threatened to harm unless paid", "coerced to pay", "forced to give money"],
        chapter_number="XVII",
        chapter_title="Offences Against Property",
        punishment_minimum=None,
        punishment_maximum="3 Years",
        fine=True,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="384",
        statute="IPC",
        bns_equivalent="309",
        title="Punishment for Extortion",
        mandatory_ingredients=["extortion_committed"],
        factual_triggers=["extortion", "extorted money", "blackmail", "coercion for money",
                          "demanded money with threat", "paid under duress"],
        chapter_number="XVII",
        chapter_title="Offences Against Property",
        punishment_minimum=None,
        punishment_maximum="3 Years",
        fine=True,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="385",
        statute="IPC",
        bns_equivalent="310",
        title="Putting Person in Fear of Injury in Order to Commit Extortion",
        mandatory_ingredients=["putting_in_fear_of_injury", "attempt_to_extort"],
        factual_triggers=["threatened to extort", "put in fear to extort", "intimidated for money",
                          "threatened family for extortion"],
        chapter_number="XVII",
        chapter_title="Offences Against Property",
        punishment_minimum=None,
        punishment_maximum="2 Years",
        fine=True,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="390",
        statute="IPC",
        bns_equivalent="309",
        title="Robbery",
        mandatory_ingredients=["theft_or_extortion", "with_use_or_threat_of_force"],
        factual_triggers=["robbery", "robbed", "snatched by force", "mugged", "looted", "chain snatching",
                          "bag snatched", "robbed at gunpoint", "robbery at knifepoint"],
        chapter_number="XVII",
        chapter_title="Offences Against Property",
        punishment_minimum=None,
        punishment_maximum="10 Years",
        fine=True,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="392",
        statute="IPC",
        bns_equivalent="309",
        title="Punishment for Robbery",
        mandatory_ingredients=["robbery_committed"],
        factual_triggers=["robbery", "robbed", "looted by force", "snatching", "mugging",
                          "dacoity", "plunder", "violent theft"],
        chapter_number="XVII",
        chapter_title="Offences Against Property",
        punishment_minimum=None,
        punishment_maximum="10 Years",
        fine=True,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="394",
        statute="IPC",
        bns_equivalent="311",
        title="Voluntarily Causing Hurt in Committing Robbery",
        mandatory_ingredients=["robbery", "hurt_caused_during_robbery"],
        factual_triggers=["injured during robbery", "beaten during robbery", "hurt while robbing",
                          "assault during robbery", "robbed and beaten"],
        chapter_number="XVII",
        chapter_title="Offences Against Property",
        punishment_minimum="Life Imprisonment",
        punishment_maximum="Life Imprisonment",
        fine=True,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="395",
        statute="IPC",
        bns_equivalent="310",
        title="Dacoity",
        mandatory_ingredients=["robbery_by_five_or_more_persons"],
        factual_triggers=["dacoity", "dacoits", "group robbery", "gang robbery", "looted by group",
                          "five persons robbed", "armed gang", "gang looted"],
        chapter_number="XVII",
        chapter_title="Offences Against Property",
        punishment_minimum="Life Imprisonment",
        punishment_maximum="Life Imprisonment",
        fine=True,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="396",
        statute="IPC",
        bns_equivalent="310",
        title="Dacoity with Murder",
        mandatory_ingredients=["dacoity", "murder_committed_during_dacoity"],
        factual_triggers=["dacoity and murder", "killed during dacoity", "shot during dacoity",
                          "murdered during robbery", "gang robbery with killing"],
        chapter_number="XVII",
        chapter_title="Offences Against Property",
        punishment_minimum="Life Imprisonment",
        punishment_maximum="Death",
        fine=False,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="397",
        statute="IPC",
        bns_equivalent="311",
        title="Robbery or Dacoity with Attempt to Cause Death or Grievous Hurt",
        mandatory_ingredients=["robbery_or_dacoity", "attempt_to_cause_death_or_grievous_hurt"],
        factual_triggers=["attempted to kill during robbery", "shot during robbery", "stabbed during dacoity",
                          "grievous hurt during robbery", "deadly weapon in robbery"],
        chapter_number="XVII",
        chapter_title="Offences Against Property",
        punishment_minimum="7 Years",
        punishment_maximum="Life Imprisonment",
        fine=False,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="411",
        statute="IPC",
        bns_equivalent="317",
        title="Dishonestly Receiving Stolen Property",
        mandatory_ingredients=["receiving_stolen_property", "knowledge_or_reason_to_believe_it_is_stolen"],
        factual_triggers=["received stolen property", "bought stolen goods", "purchasing stolen items",
                          "handling stolen goods", "in possession of stolen property", "knowingly received stolen"],
        chapter_number="XVII",
        chapter_title="Offences Against Property",
        punishment_minimum=None,
        punishment_maximum="3 Years",
        fine=True,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="447",
        statute="IPC",
        bns_equivalent="329",
        title="Punishment for Criminal Trespass",
        mandatory_ingredients=["entry_into_property", "without_permission_and_with_intent_to_commit_offence"],
        factual_triggers=["trespass", "trespassed", "entered property illegally", "encroached",
                          "entered without permission", "illegal entry", "forcibly entered premises"],
        chapter_number="XVII",
        chapter_title="Offences Against Property",
        punishment_minimum=None,
        punishment_maximum="3 Months",
        fine=True,
        cognizable=False,
        bailable=True,
    ),
    SectionRule(
        section="448",
        statute="IPC",
        bns_equivalent="329",
        title="Punishment for House-Trespass",
        mandatory_ingredients=["criminal_trespass_into_dwelling_house"],
        factual_triggers=["house trespass", "illegally entered house", "broke into home", "entered dwelling illegally",
                          "uninvited entry into house", "trespassed into residence", "barged into house"],
        chapter_number="XVII",
        chapter_title="Offences Against Property",
        punishment_minimum=None,
        punishment_maximum="1 Year",
        fine=True,
        cognizable=False,
        bailable=True,
    ),
    SectionRule(
        section="451",
        statute="IPC",
        bns_equivalent="329",
        title="House-Trespass in Order to Commit Offence Punishable with Imprisonment",
        mandatory_ingredients=["house_trespass", "intent_to_commit_offence"],
        factual_triggers=["broke into house to commit offence", "trespassed to steal", "entered to harm",
                          "broke in with criminal intent", "home invasion"],
        chapter_number="XVII",
        chapter_title="Offences Against Property",
        punishment_minimum=None,
        punishment_maximum="2 Years",
        fine=True,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="454",
        statute="IPC",
        bns_equivalent="332",
        title="Lurking House-Trespass or House-Breaking in Order to Commit Offence",
        mandatory_ingredients=["house_breaking_or_lurking_trespass", "intent_to_commit_offence"],
        factual_triggers=["house breaking", "broke into house", "lurking trespass", "broke lock", "broke door",
                          "entered through window", "broke into to steal", "burglary"],
        chapter_number="XVII",
        chapter_title="Offences Against Property",
        punishment_minimum=None,
        punishment_maximum="3 Years",
        fine=True,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="457",
        statute="IPC",
        bns_equivalent="332",
        title="Lurking House-Trespass or House-Breaking by Night",
        mandatory_ingredients=["house_breaking_or_lurking_trespass_by_night", "intent_to_commit_offence"],
        factual_triggers=["broke into house at night", "night burglary", "nighttime break-in",
                          "house broken at night", "nocturnal housebreaking", "night trespass"],
        chapter_number="XVII",
        chapter_title="Offences Against Property",
        punishment_minimum=None,
        punishment_maximum="5 Years",
        fine=True,
        cognizable=True,
        bailable=False,
    ),

    # ------------------------------------------------------------------ #
    #  DOCUMENT / FINANCIAL FRAUD OFFENCES                                 #
    # ------------------------------------------------------------------ #
    SectionRule(
        section="409",
        statute="IPC",
        bns_equivalent="316",
        title="Criminal Breach of Trust by Public Servant / Banker / Merchant",
        mandatory_ingredients=["entrustment_in_capacity_of_public_servant_or_banker",
                               "dishonest_misappropriation_or_conversion"],
        factual_triggers=["banker", "public servant", "agent misappropriated", "entrusted funds misused",
                          "government funds embezzled", "bank fraud", "merchant fraud", "carrier fraud"],
        chapter_number="XVII",
        chapter_title="Criminal Breach of Trust",
        punishment_minimum="Life Imprisonment",
        punishment_maximum="Life Imprisonment",
        fine=True,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="415",
        statute="IPC",
        bns_equivalent="318",
        title="Cheating",
        mandatory_ingredients=["deception", "fraudulently_inducing_to_deliver_property_or_alter_signed_document"],
        factual_triggers=["cheated", "defrauded", "deceived", "false promise", "fraud", "misrepresentation",
                          "induced by false pretence", "tricked into paying", "false representation"],
        chapter_number="XVII",
        chapter_title="Offences Against Property",
        punishment_minimum=None,
        punishment_maximum="1 Year",
        fine=True,
        cognizable=False,
        bailable=True,
    ),
    SectionRule(
        section="417",
        statute="IPC",
        bns_equivalent="318",
        title="Punishment for Cheating",
        mandatory_ingredients=["cheating_committed"],
        factual_triggers=["cheated", "fraud", "deceived", "false promise made", "duped", "swindled",
                          "misled", "misrepresented facts"],
        chapter_number="XVII",
        chapter_title="Offences Against Property",
        punishment_minimum=None,
        punishment_maximum="1 Year",
        fine=True,
        cognizable=False,
        bailable=True,
    ),
    SectionRule(
        section="467",
        statute="IPC",
        bns_equivalent="337",
        title="Forgery of Valuable Security / Will",
        mandatory_ingredients=["forgery_of_valuable_security_or_will_or_authority_to_adopt"],
        factual_triggers=["forged will", "fake will", "forged cheque", "forged valuable security",
                          "forged promissory note", "false authority to adopt", "counterfeit bond",
                          "forged stamp paper", "forged power of attorney"],
        chapter_number="XVIII",
        chapter_title="Offences Relating to Documents",
        punishment_minimum=None,
        punishment_maximum="Life Imprisonment",
        fine=True,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="471",
        statute="IPC",
        bns_equivalent="341",
        title="Using as Genuine a Forged Document",
        mandatory_ingredients=["using_forged_document_as_genuine", "knowledge_that_it_is_forged"],
        factual_triggers=["used forged document", "submitted fake document", "passed off forged",
                          "presented false document", "used counterfeit document", "submitted fabricated document"],
        chapter_number="XVIII",
        chapter_title="Offences Relating to Documents",
        punishment_minimum=None,
        punishment_maximum="Life Imprisonment",
        fine=True,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="477A",
        statute="IPC",
        bns_equivalent="344",
        title="Falsification of Accounts",
        mandatory_ingredients=["clerk_or_servant_or_officer", "wilful_destruction_or_falsification_of_accounts"],
        factual_triggers=["falsified accounts", "manipulated accounts", "tampered books", "forged books of account",
                          "altered financial records", "destroyed accounts", "cooked books", "falsified entries"],
        chapter_number="XVIII",
        chapter_title="Offences Relating to Documents",
        punishment_minimum=None,
        punishment_maximum="7 Years",
        fine=True,
        cognizable=True,
        bailable=False,
    ),

    # ------------------------------------------------------------------ #
    #  PUBLIC ORDER, RIOTING & UNLAWFUL ASSEMBLY                          #
    # ------------------------------------------------------------------ #
    SectionRule(
        section="141",
        statute="IPC",
        bns_equivalent="189",
        title="Unlawful Assembly",
        mandatory_ingredients=["assembly_of_five_or_more_persons", "common_object_to_commit_offence"],
        factual_triggers=["unlawful assembly", "mob", "gathering", "group assembled", "five or more persons",
                          "rioting", "crowd gathered illegally", "mob violence", "assembly with common object"],
        chapter_number="VIII",
        chapter_title="Offences Against Public Tranquillity",
        punishment_minimum=None,
        punishment_maximum="6 Months",
        fine=True,
        cognizable=False,
        bailable=True,
    ),
    SectionRule(
        section="143",
        statute="IPC",
        bns_equivalent="191",
        title="Punishment for Member of Unlawful Assembly",
        mandatory_ingredients=["membership_of_unlawful_assembly"],
        factual_triggers=["member of unlawful assembly", "part of mob", "part of riotous assembly",
                          "participated in mob", "joined unlawful assembly"],
        chapter_number="VIII",
        chapter_title="Offences Against Public Tranquillity",
        punishment_minimum=None,
        punishment_maximum="6 Months",
        fine=True,
        cognizable=False,
        bailable=True,
    ),
    SectionRule(
        section="144",
        statute="IPC",
        bns_equivalent="190",
        title="Joining Unlawful Assembly Armed with Deadly Weapon",
        mandatory_ingredients=["member_of_unlawful_assembly", "armed_with_deadly_weapon"],
        factual_triggers=["armed mob", "mob with weapons", "rioters with weapons", "armed with gun in assembly",
                          "assembly with lethal weapons", "armed crowd"],
        chapter_number="VIII",
        chapter_title="Offences Against Public Tranquillity",
        punishment_minimum=None,
        punishment_maximum="2 Years",
        fine=True,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="147",
        statute="IPC",
        bns_equivalent="191",
        title="Punishment for Rioting",
        mandatory_ingredients=["rioting", "member_of_unlawful_assembly"],
        factual_triggers=["rioting", "riot", "rioters", "mob violence", "violent mob", "public disturbance",
                          "communal riot", "riotous assembly", "loot and riot"],
        chapter_number="VIII",
        chapter_title="Offences Against Public Tranquillity",
        punishment_minimum=None,
        punishment_maximum="2 Years",
        fine=True,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="148",
        statute="IPC",
        bns_equivalent="191",
        title="Rioting Armed with Deadly Weapon",
        mandatory_ingredients=["rioting", "armed_with_deadly_weapon"],
        factual_triggers=["rioting with weapons", "armed riot", "armed rioters", "guns in riot",
                          "weapons during riot", "firing during riot", "arson during riot"],
        chapter_number="VIII",
        chapter_title="Offences Against Public Tranquillity",
        punishment_minimum=None,
        punishment_maximum="3 Years",
        fine=True,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="149",
        statute="IPC",
        bns_equivalent="190",
        title="Every Member of Unlawful Assembly Guilty of Offence Committed in Prosecution of Common Object",
        mandatory_ingredients=["membership_of_unlawful_assembly", "offence_committed_in_prosecution_of_common_object"],
        factual_triggers=["common object", "in furtherance of common object", "all members guilty",
                          "group offence", "constructive liability", "joint liability in assembly"],
        chapter_number="VIII",
        chapter_title="Offences Against Public Tranquillity",
        punishment_minimum=None,
        punishment_maximum="As per main offence",
        fine=True,
        cognizable=True,
        bailable=False,
    ),

    # ------------------------------------------------------------------ #
    #  ABETMENT & CRIMINAL CONSPIRACY                                      #
    # ------------------------------------------------------------------ #
    SectionRule(
        section="107",
        statute="IPC",
        bns_equivalent="45",
        title="Abetment of a Thing",
        mandatory_ingredients=["instigation_or_conspiracy_or_intentional_aid"],
        factual_triggers=["abetment", "instigated", "aided", "assisted", "conspiracy", "provoked to commit",
                          "helped commit crime", "facilitated", "gave shelter to accused", "aided and abetted"],
        chapter_number="V",
        chapter_title="Abetment",
        punishment_minimum=None,
        punishment_maximum="As per main offence",
        fine=True,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="109",
        statute="IPC",
        bns_equivalent="48",
        title="Punishment of Abetment if the Act Abetted is Committed in Consequence",
        mandatory_ingredients=["abetment", "offence_committed_in_consequence_of_abetment"],
        factual_triggers=["abetted offence", "crime committed due to instigation", "abettor",
                          "conspiracy resulted in crime", "aided in offence", "offence committed due to abetment"],
        chapter_number="V",
        chapter_title="Abetment",
        punishment_minimum=None,
        punishment_maximum="As per main offence",
        fine=True,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="120A",
        statute="IPC",
        bns_equivalent="61",
        title="Definition of Criminal Conspiracy",
        mandatory_ingredients=["agreement_between_two_or_more", "to_commit_illegal_act_or_by_illegal_means"],
        factual_triggers=["criminal conspiracy", "conspired", "hatched conspiracy", "planned together",
                          "agreed to commit crime", "co-conspirators", "in conspiracy with", "joint plan"],
        chapter_number="VA",
        chapter_title="Criminal Conspiracy",
        punishment_minimum=None,
        punishment_maximum="As per main offence",
        fine=True,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="120B",
        statute="IPC",
        bns_equivalent="61",
        title="Punishment of Criminal Conspiracy",
        mandatory_ingredients=["criminal_conspiracy_committed"],
        factual_triggers=["criminal conspiracy", "conspired to commit", "hatched plan", "planned crime",
                          "conspiracy to murder", "conspiracy to cheat", "conspired together"],
        chapter_number="VA",
        chapter_title="Criminal Conspiracy",
        punishment_minimum=None,
        punishment_maximum="As per main offence",
        fine=True,
        cognizable=True,
        bailable=False,
    ),

    # ------------------------------------------------------------------ #
    #  OFFENCES AGAINST THE STATE & PUBLIC SERVANTS                       #
    # ------------------------------------------------------------------ #
    SectionRule(
        section="153A",
        statute="IPC",
        bns_equivalent="196",
        title="Promoting Enmity Between Different Groups",
        mandatory_ingredients=["promoting_disharmony_or_enmity", "on_grounds_of_religion_race_community_etc"],
        factual_triggers=["hate speech", "communal disharmony", "promoting enmity", "religious hatred",
                          "inciting riot", "promoting religious hatred", "communal speech", "divisive speech"],
        chapter_number="VIII",
        chapter_title="Offences Against Public Tranquillity",
        punishment_minimum=None,
        punishment_maximum="3 Years",
        fine=True,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="166",
        statute="IPC",
        bns_equivalent="215",
        title="Public Servant Disobeying Law with Intent to Cause Injury",
        mandatory_ingredients=["public_servant", "disobeying_direction_of_law", "intent_to_cause_injury"],
        factual_triggers=["public servant illegal act", "police officer abuse of power", "government official misconduct",
                          "officer acted illegally", "violated law deliberately", "illegal detention by police"],
        chapter_number="IX",
        chapter_title="Offences by or Relating to Public Servants",
        punishment_minimum=None,
        punishment_maximum="1 Year",
        fine=True,
        cognizable=False,
        bailable=True,
    ),
    SectionRule(
        section="182",
        statute="IPC",
        bns_equivalent="229",
        title="False Information to Public Servant",
        mandatory_ingredients=["false_information_given", "to_public_servant", "intent_to_cause_harm"],
        factual_triggers=["false complaint", "false FIR", "lodged fake complaint", "false information to police",
                          "filed false case", "false report", "false statement to police"],
        chapter_number="X",
        chapter_title="Contempt of Lawful Authority of Public Servants",
        punishment_minimum=None,
        punishment_maximum="6 Months",
        fine=True,
        cognizable=False,
        bailable=True,
    ),
    SectionRule(
        section="186",
        statute="IPC",
        bns_equivalent="221",
        title="Obstructing Public Servant in Discharge of Public Functions",
        mandatory_ingredients=["obstruction_of_public_servant", "in_discharge_of_public_functions"],
        factual_triggers=["obstruction of police", "obstructed government official", "prevented officer",
                          "resisted arrest", "obstructed duty", "interfered with public servant"],
        chapter_number="X",
        chapter_title="Contempt of Lawful Authority of Public Servants",
        punishment_minimum=None,
        punishment_maximum="3 Months",
        fine=True,
        cognizable=False,
        bailable=True,
    ),
    SectionRule(
        section="193",
        statute="IPC",
        bns_equivalent="229",
        title="Punishment for False Evidence",
        mandatory_ingredients=["giving_false_evidence", "in_judicial_proceeding_or_before_public_servant"],
        factual_triggers=["false evidence", "perjury", "false affidavit", "false deposition",
                          "gave false statement under oath", "lied in court", "fabricated evidence"],
        chapter_number="XI",
        chapter_title="False Evidence and Offences Against Public Justice",
        punishment_minimum=None,
        punishment_maximum="7 Years",
        fine=True,
        cognizable=False,
        bailable=False,
    ),
    SectionRule(
        section="201",
        statute="IPC",
        bns_equivalent="238",
        title="Causing Disappearance of Evidence of Offence",
        mandatory_ingredients=["knowledge_that_offence_committed", "causing_disappearance_of_evidence_or_giving_false_information"],
        factual_triggers=["destroyed evidence", "concealed evidence", "tampered evidence", "hidden body",
                          "disposed of body", "removed body", "burnt body", "washed crime scene",
                          "gave false information to screen offender"],
        chapter_number="XI",
        chapter_title="False Evidence and Offences Against Public Justice",
        punishment_minimum=None,
        punishment_maximum="7 Years",
        fine=True,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="211",
        statute="IPC",
        bns_equivalent="247",
        title="False Charge of Offence Made with Intent to Injure",
        mandatory_ingredients=["false_criminal_charge_instituted", "intent_to_injure"],
        factual_triggers=["false complaint filed", "false FIR filed", "malicious prosecution",
                          "false case filed", "fabricated criminal charge", "baseless criminal complaint"],
        chapter_number="XI",
        chapter_title="False Evidence and Offences Against Public Justice",
        punishment_minimum=None,
        punishment_maximum="7 Years",
        fine=True,
        cognizable=False,
        bailable=False,
    ),
    SectionRule(
        section="294",
        statute="IPC",
        bns_equivalent="296",
        title="Obscene Acts and Songs",
        mandatory_ingredients=["obscene_act_in_public_place", "causing_annoyance_to_others"],
        factual_triggers=["obscene act", "obscene song", "obscenity in public", "indecent act",
                          "vulgar act in public", "lewd act", "public indecency"],
        chapter_number="XIV",
        chapter_title="Offences Affecting Public Health and Decency",
        punishment_minimum=None,
        punishment_maximum="3 Months",
        fine=True,
        cognizable=False,
        bailable=True,
    ),

    # ------------------------------------------------------------------ #
    #  MATRIMONIAL & DOMESTIC OFFENCES                                     #
    # ------------------------------------------------------------------ #
    SectionRule(
        section="494",
        statute="IPC",
        bns_equivalent="82",
        title="Marrying Again During Lifetime of Husband or Wife (Bigamy)",
        mandatory_ingredients=["previous_valid_marriage_subsisting", "second_marriage_contracted"],
        factual_triggers=["bigamy", "second marriage", "married again", "second wife", "second husband",
                          "married while first spouse alive", "concealed first marriage", "double marriage"],
        chapter_number="XX",
        chapter_title="Offences Relating to Marriage",
        punishment_minimum=None,
        punishment_maximum="7 Years",
        fine=True,
        cognizable=False,
        bailable=True,
    ),
    SectionRule(
        section="495",
        statute="IPC",
        bns_equivalent="83",
        title="Same Offence with Concealment of Former Marriage from Person with Whom Subsequent Marriage is Contracted",
        mandatory_ingredients=["bigamy", "concealment_of_previous_marriage"],
        factual_triggers=["concealed first marriage", "hid prior marriage", "married by hiding first marriage",
                          "did not disclose previous marriage", "bigamy by concealment"],
        chapter_number="XX",
        chapter_title="Offences Relating to Marriage",
        punishment_minimum=None,
        punishment_maximum="10 Years",
        fine=True,
        cognizable=False,
        bailable=True,
    ),
    SectionRule(
        section="496",
        statute="IPC",
        bns_equivalent="84",
        title="Marriage Ceremony Fraudulently Gone Through Without Lawful Marriage",
        mandatory_ingredients=["fraudulent_marriage_ceremony", "not_a_lawful_marriage"],
        factual_triggers=["fraudulent marriage", "fake marriage ceremony", "sham marriage",
                          "pretended to marry", "fake nikah", "false marriage ritual"],
        chapter_number="XX",
        chapter_title="Offences Relating to Marriage",
        punishment_minimum=None,
        punishment_maximum="7 Years",
        fine=True,
        cognizable=False,
        bailable=True,
    ),
    SectionRule(
        section="509",
        statute="IPC",
        bns_equivalent="79",
        title="Word, Gesture or Act Intended to Insult the Modesty of a Woman",
        mandatory_ingredients=["word_gesture_or_act", "intended_to_insult_modesty_of_woman"],
        factual_triggers=["insulted modesty", "passed lewd remarks", "sexual comment", "wolf-whistling",
                          "obscene gesture towards woman", "eve teasing", "indecent remark", "comment on body"],
        chapter_number="XXII",
        chapter_title="Criminal Intimidation, Insult and Annoyance",
        punishment_minimum=None,
        punishment_maximum="3 Years",
        fine=True,
        cognizable=True,
        bailable=True,
    ),

    # ------------------------------------------------------------------ #
    #  ARMS & EXPLOSIVES                                                   #
    # ------------------------------------------------------------------ #
    SectionRule(
        section="25",
        statute="Arms Act 1959",
        bns_equivalent="25",
        title="Punishment for Certain Offences (Arms Act)",
        mandatory_ingredients=["possession_or_use_of_arms_without_licence"],
        factual_triggers=["illegal weapon", "unlicensed gun", "country made pistol", "country made revolver",
                          "illegal firearm", "unlicensed firearm", "arms without licence", "katta", "desi katta",
                          "country made gun", "illegal arms", "found with weapon"],
        chapter_number="Arms Act",
        chapter_title="Arms Act Offences",
        punishment_minimum="1 Year",
        punishment_maximum="3 Years",
        fine=True,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="27",
        statute="Arms Act 1959",
        bns_equivalent="27",
        title="Punishment for Use of Arms (Arms Act)",
        mandatory_ingredients=["use_of_arms", "in_commission_of_offence"],
        factual_triggers=["used weapon in offence", "fired gun", "shot at", "armed assault", "used firearm",
                          "pistol fired", "gun used", "weapon used in crime"],
        chapter_number="Arms Act",
        chapter_title="Arms Act Offences",
        punishment_minimum="3 Years",
        punishment_maximum="7 Years",
        fine=True,
        cognizable=True,
        bailable=False,
    ),

    # ------------------------------------------------------------------ #
    #  SC/ST (PREVENTION OF ATROCITIES) ACT                               #
    # ------------------------------------------------------------------ #
    SectionRule(
        section="3(1)(r)",
        statute="SC/ST (POA) Act",
        bns_equivalent="3(1)(r)",
        title="Intentional Insult or Intimidation of SC/ST Member in Public View",
        mandatory_ingredients=["victim_belongs_to_SC_or_ST", "intentional_insult_or_intimidation_in_public_view"],
        factual_triggers=["sc st atrocity", "caste abuse", "caste slur", "abused with caste name",
                          "humiliated dalit", "caste discrimination", "atrocity on scheduled caste",
                          "atrocity on scheduled tribe", "casteist abuse"],
        chapter_number="SC/ST Act",
        chapter_title="Prevention of Atrocities",
        punishment_minimum="6 Months",
        punishment_maximum="5 Years",
        fine=True,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="3(2)(v)",
        statute="SC/ST (POA) Act",
        bns_equivalent="3(2)(v)",
        title="Committing Offence Punishable with Death or Life Imprisonment Against SC/ST Member",
        mandatory_ingredients=["offence_punishable_with_death_or_life", "victim_belongs_to_SC_or_ST",
                               "committed_on_ground_of_caste"],
        factual_triggers=["killed dalit", "murdered scheduled caste", "raped scheduled caste woman",
                          "rape of sc woman", "murder of st person", "atrocity leading to death"],
        chapter_number="SC/ST Act",
        chapter_title="Prevention of Atrocities",
        punishment_minimum="Life Imprisonment",
        punishment_maximum="Death",
        fine=True,
        cognizable=True,
        bailable=False,
    ),

    # ------------------------------------------------------------------ #
    #  INFORMATION TECHNOLOGY ACT (CYBER OFFENCES)                        #
    # ------------------------------------------------------------------ #
    SectionRule(
        section="66",
        statute="IT Act 2000",
        bns_equivalent="66",
        title="Computer Related Offences",
        mandatory_ingredients=["computer_related_offence", "dishonest_or_fraudulent_act"],
        factual_triggers=["hacking", "computer hack", "unauthorised access", "data breach", "cyber fraud",
                          "computer virus", "ransomware", "phishing", "online fraud", "cyber crime",
                          "email hack", "account hacked"],
        chapter_number="IT Act",
        chapter_title="Cyber Offences",
        punishment_minimum=None,
        punishment_maximum="3 Years",
        fine=True,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="66C",
        statute="IT Act 2000",
        bns_equivalent="66C",
        title="Identity Theft",
        mandatory_ingredients=["fraudulent_use_of_electronic_signature_password_or_unique_identification_feature"],
        factual_triggers=["identity theft", "stole identity", "used someone's password", "impersonated online",
                          "used another's credentials", "fake identity online", "OTP fraud", "stolen credentials"],
        chapter_number="IT Act",
        chapter_title="Cyber Offences",
        punishment_minimum=None,
        punishment_maximum="3 Years",
        fine=True,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="66D",
        statute="IT Act 2000",
        bns_equivalent="66D",
        title="Cheating by Personation Using Computer Resource",
        mandatory_ingredients=["cheating_by_personation", "using_computer_resource_or_communication_device"],
        factual_triggers=["online impersonation", "cheated by fake identity", "fake profile fraud",
                          "WhatsApp fraud", "fake email fraud", "cyber personation", "UPI fraud",
                          "social media impersonation"],
        chapter_number="IT Act",
        chapter_title="Cyber Offences",
        punishment_minimum=None,
        punishment_maximum="3 Years",
        fine=True,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="67",
        statute="IT Act 2000",
        bns_equivalent="67",
        title="Publishing Obscene Material in Electronic Form",
        mandatory_ingredients=["publishing_or_transmitting_obscene_material", "in_electronic_form"],
        factual_triggers=["obscene content online", "pornographic content shared", "viral obscene video",
                          "obscene photo circulated", "indecent video shared", "pornography published online"],
        chapter_number="IT Act",
        chapter_title="Cyber Offences",
        punishment_minimum=None,
        punishment_maximum="5 Years",
        fine=True,
        cognizable=True,
        bailable=False,
    ),

    # ------------------------------------------------------------------ #
    #  NDPS (NARCOTICS) ACT                                               #
    # ------------------------------------------------------------------ #
    SectionRule(
        section="20",
        statute="NDPS Act 1985",
        bns_equivalent="20",
        title="Punishment for Contravention in Relation to Cannabis",
        mandatory_ingredients=["possession_production_sale_or_use_of_cannabis"],
        factual_triggers=["cannabis", "marijuana", "ganja", "charas", "hashish", "weed", "drugs found",
                          "narcotic drug", "possession of drugs", "drug peddling", "selling ganja"],
        chapter_number="NDPS Act",
        chapter_title="Narcotic Drugs Offences",
        punishment_minimum="6 Months",
        punishment_maximum="10 Years",
        fine=True,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="21",
        statute="NDPS Act 1985",
        bns_equivalent="21",
        title="Punishment for Contravention in Relation to Manufactured Drugs",
        mandatory_ingredients=["possession_sale_or_use_of_manufactured_drugs"],
        factual_triggers=["heroin", "cocaine", "opium", "morphine", "manufactured drug", "smack",
                          "brown sugar", "hard drug", "contraband drug", "drug trafficking", "mephedrone", "md"],
        chapter_number="NDPS Act",
        chapter_title="Narcotic Drugs Offences",
        punishment_minimum="6 Months",
        punishment_maximum="20 Years",
        fine=True,
        cognizable=True,
        bailable=False,
    ),
    SectionRule(
        section="29",
        statute="NDPS Act 1985",
        bns_equivalent="29",
        title="Abetment and Criminal Conspiracy (NDPS Act)",
        mandatory_ingredients=["abetment_or_conspiracy_related_to_drug_offence"],
        factual_triggers=["drug conspiracy", "helped in drug trafficking", "abetted drug offence",
                          "facilitated drug peddling", "drug network", "drug syndicate"],
        chapter_number="NDPS Act",
        chapter_title="Narcotic Drugs Offences",
        punishment_minimum=None,
        punishment_maximum="As per main drug offence",
        fine=True,
        cognizable=True,
        bailable=False,
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


class CandidateSectionMatch(BaseModel):
    section_identifier: str = Field(description="Normalized section identifier e.g. IPC 498A, BNS 85")
    statute: str = Field(description="Statute name: 'IPC' or 'BNS'")
    section_number: str = Field(description="Section number string e.g. '498A', '85'")
    title: str = Field(description="Section title or offense description")
    chapter: Optional[str] = Field(default=None, description="Chapter title if available")
    score: float = Field(description="Local pre-filter relevance score (0.0 to 1.0)")
    matched_terms: List[str] = Field(default_factory=list, description="Keywords/terms matched locally")

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

    def _load_datasets(self):
        """Loads IPC and BNS dataset records into local in-memory index."""
        candidate_ipc = [
            Path("data/new/ipc_sections.csv"),
            Path("../data/new/ipc_sections.csv"),
            Path("c:/proj/MootCourt/data/new/ipc_sections.csv"),
            Path("c:/MootCourt/data/new/ipc_sections.csv"),
        ]
        candidate_bns = [
            Path("data/new/bns_sections1.csv"),
            Path("c:/proj/MootCourt/data/new/bns_sections1.csv"),
            Path("data/new/bns_sections_clean.csv"),
            Path("../data/new/bns_sections_clean.csv"),
            Path("c:/proj/MootCourt/data/new/bns_sections_clean.csv"),
            Path("c:/MootCourt/data/new/bns_sections_clean.csv"),
        ]

        # 1. Load IPC dataset
        for p in candidate_ipc:
            if p.exists():
                try:
                    with open(p, mode="r", encoding="utf-8", errors="ignore") as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            sec_id = (row.get("Section") or "").strip()
                            offense = (row.get("Offense") or "").strip()
                            desc = (row.get("Description") or "").strip()
                            if sec_id:
                                clean_num = sec_id.replace("IPC_", "").strip()
                                full_text = f"{offense} {desc} {clean_num}".lower()
                                self.sections_db.append({
                                    "identifier": f"IPC {clean_num}",
                                    "statute": "IPC",
                                    "section_number": clean_num,
                                    "title": offense or f"IPC Section {clean_num}",
                                    "chapter": "IPC Offence Chapter",
                                    "full_text": full_text,
                                    "tokens": set(re.findall(r"\w+", full_text)),
                                })
                    break
                except Exception:
                    pass

        # 2. Load BNS dataset
        for p in candidate_bns:
            if p.exists():
                try:
                    with open(p, mode="r", encoding="utf-8", errors="ignore") as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            sec_num = (row.get("Section") or "").strip()
                            title = (row.get("Title") or "").strip()
                            desc = (row.get("Description") or "").strip()
                            chap = (row.get("Chapter") or "").strip()
                            keywords = (row.get("Keywords") or "").strip()
                            if sec_num:
                                full_text = f"{title} {desc} {chap} {keywords} {sec_num}".lower()
                                self.sections_db.append({
                                    "identifier": f"BNS {sec_num}",
                                    "statute": "BNS",
                                    "section_number": sec_num,
                                    "title": title or f"BNS Section {sec_num}",
                                    "chapter": chap,
                                    "full_text": full_text,
                                    "tokens": set(re.findall(r"\w+", full_text)),
                                })
                    break
                except Exception:
                    pass

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
        concept_phrases = [c.concept.lower() for c in legal_query_obj.legal_concepts if c.concept]
        query_terms = []
        for phrase in concept_phrases:
            query_terms.extend(re.findall(r"\w+", phrase))

        for sq in legal_query_obj.sub_queries:
            query_terms.extend(re.findall(r"\w+", sq.query.lower()))
            if sq.concept:
                concept_phrases.append(sq.concept.lower())
                query_terms.extend(re.findall(r"\w+", sq.concept.lower()))

        # Filter out common stop words
        stop_words = {"the", "a", "an", "and", "or", "of", "to", "in", "for", "on", "by", "with", "is", "was", "are", "were"}
        filtered_terms = [t for t in query_terms if t not in stop_words and len(t) > 2]
        unique_query_terms = set(filtered_terms)

        # Concept-to-keyword vocabulary bridge:
        # Legal concept phrases from Stage 1 use formal language that doesn't match
        # section titles directly. Expand known concept phrases into trigger keywords.
        _CONCEPT_KEYWORD_BRIDGE = {
            "dishonest inducement to deliver property": ["extortion", "extorted", "blackmail", "threatened", "induced delivery"],
            "dishonestly inducing delivery": ["extortion", "blackmail", "threatened", "induced delivery"],
            "criminal intimidation": ["threat", "threatened", "intimidat", "warning"],
            "physical assault": ["assault", "beaten", "hurt", "pushed", "slapped"],
            "voluntarily causing hurt": ["assault", "hurt", "beaten", "physical violence"],
            "theft": ["theft", "stolen", "stole", "took away"],
            "criminal breach of trust": ["stridhan", "ornaments", "property not returned", "entrustment"],
            "extortion": ["extortion", "extorted", "blackmail", "threatened", "demanded money"],
            "cheating": ["cheated", "defrauded", "deceived", "fraud"],
            "robbery": ["robbery", "robbed", "looted", "snatched by force"],
            "wrongful restraint": ["restrained", "blocked", "stopped forcibly"],
            "wrongful confinement": ["confined", "locked", "detained"],
            "house trespass": ["trespass", "entered illegally", "barged in"],
            "criminal trespass": ["trespass", "entered illegally", "encroached"],
            "mischief": ["damaged", "destroyed property", "mischief"],
            "abetment of suicide": ["abetment of suicide", "instigated suicide", "harassment led to suicide"],
        }
        full_concepts_lower = " ".join(concept_phrases).lower()
        for concept_key, extra_keywords in _CONCEPT_KEYWORD_BRIDGE.items():
            if concept_key in full_concepts_lower:
                unique_query_terms.update(extra_keywords)

        if not unique_query_terms or not self.sections_db:
            return []

        # Filter database by legal regime if requested
        regime_filter = None
        regime_str = target_regime or legal_query_obj.legal_regime or ""
        if "BNS" in regime_str.upper():
            regime_filter = "BNS"
        elif "IPC" in regime_str.upper():
            regime_filter = "IPC"

        matches: List[Tuple[Dict[str, Any], float, List[str]]] = []

        query_full_text = " ".join(concept_phrases) + " " + " ".join(unique_query_terms)

        for record in self.sections_db:
            if regime_filter and record["statute"] != regime_filter:
                continue

            sec_num = record["section_number"].upper()
            sec_statute = record["statute"].upper()

            # 1. Fatal Disqualification Check (reject 304B/307/376 if mandatory triggers missing)
            disqualified, _, _ = self.evaluate_fatal_disqualification(sec_num, sec_statute, query_full_text)
            if disqualified:
                continue

            record_text = record["full_text"]
            record_title = record["title"].lower()

            matched = [term for term in unique_query_terms if term in record_text]

            # 2. Knowledge Base Factual Trigger Matching (static + dynamic KB)
            kb_boost = 0.0
            for rule in get_effective_knowledge_base():
                rule_sec = rule.bns_equivalent if sec_statute == "BNS" else rule.section
                if sec_num == rule_sec.upper() or sec_num == rule.section.upper():
                    if rule.factual_triggers:
                        if any(trig in query_full_text.lower() for trig in rule.factual_triggers):
                            kb_boost += 2.5
                    break

            if not matched and kb_boost == 0.0:
                continue

            # Calculate base term score
            term_score = len(matched) / (len(unique_query_terms) ** 0.5) if matched else 0.5

            # Boost exact concept phrase matches, title matches, and KB triggers
            phrase_boost = 1.0 + kb_boost
            for phrase in concept_phrases:
                if len(phrase) > 3:
                    if phrase in record_text:
                        phrase_boost += 1.5
                    if phrase in record_title:
                        phrase_boost += 2.0
                    words = [w for w in re.findall(r"\w+", phrase) if w not in stop_words]
                    title_matches = [w for w in words if w in record_title]
                    if title_matches:
                        phrase_boost += (len(title_matches) * 0.5)

            final_score = min(1.0, round((term_score * phrase_boost) / 4.0, 2))
            matches.append((record, final_score, matched))

        # Sort matches by score descending
        matches.sort(key=lambda x: x[1], reverse=True)

        results = []
        seen_identifiers = set()
        existing_kb_keys = _kb_section_keys()

        for rec, score, matched_list in matches[:top_k]:
            if rec["identifier"] not in seen_identifiers:
                seen_identifiers.add(rec["identifier"])

                # --- Dynamic KB promotion ------------------------------------------
                # If this CSV record has no SectionRule yet, auto-promote it so that
                # future queries get full KB-quality verification for this section.
                candidate_key = f"{rec['statute'].upper()}_{rec['section_number'].upper()}"
                if candidate_key not in existing_kb_keys:
                    try:
                        from .statute_repository import StatuteRepository
                        fs_meta = StatuteRepository.get_instance().get_first_schedule_metadata(
                            rec["section_number"], rec["statute"]
                        )
                    except Exception:
                        fs_meta = None
                    promoted = promote_csv_record_to_kb(
                        csv_record=rec,
                        matched_query_terms=matched_list,
                        first_schedule_meta=fs_meta,
                    )
                    if promoted:
                        # Refresh key set so subsequent hits in the same loop see it
                        existing_kb_keys.add(candidate_key)
                # -------------------------------------------------------------------

                results.append(
                    CandidateSectionMatch(
                        section_identifier=rec["identifier"],
                        statute=rec["statute"],
                        section_number=rec["section_number"],
                        title=rec["title"],
                        chapter=rec["chapter"],
                        score=score,
                        matched_terms=matched_list[:5],
                    )
                )

        return results

    @staticmethod
    def evaluate_fatal_disqualification(section_number: str, statute: str, facts_text: str) -> Tuple[bool, Optional[str], List[str]]:
        """
        Evaluates mandatory ingredient rules from STATUTE_KNOWLEDGE_BASE to screen sections.
        Returns Tuple of (is_not_triggered, not_triggered_reason, missing_mandatory_ingredients).
        """
        lower_facts = (facts_text or "").lower()
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
                if rule.factual_triggers:
                    has_trigger = any(trig in lower_facts for trig in rule.factual_triggers)
                    if not has_trigger:
                        missing = rule.mandatory_ingredients
                        reason = f"Screening non-trigger: Mandatory statutory ingredients ({', '.join(rule.mandatory_ingredients)}) not indicated in case facts."
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
        Detects factual triggers in facts_text and automatically suggests candidate sections.
        Combines hardcoded triggers with live KB rules (static + dynamic) so auto-promoted
        sections are matched on future queries without any code changes.
        """
        lower_facts = (facts_text or "").lower()
        is_bns = "BNS" in (statute_type or "").upper()
        suggestions = []
        seen_keys: set = set()

        def _add(sec_num, title, statute, ctype, trigger_note):
            k = f"{statute}_{sec_num}"
            if k not in seen_keys:
                seen_keys.add(k)
                suggestions.append({
                    "section_number": sec_num,
                    "section_title": title,
                    "statute": statute,
                    "candidate_type": ctype,
                    "trigger": trigger_note,
                })

        # --- KB-driven triggers (static + dynamic) ---
        # This runs first so promoted rules are matched before the hardcoded list.
        for rule in get_effective_knowledge_base():
            if not rule.factual_triggers:
                continue
            target_statute = "BNS" if is_bns else "IPC"
            rule_statute = "BNS" if (rule.bns_equivalent and rule.bns_equivalent not in ("", "NONE")) else rule.statute
            if rule_statute.upper() != target_statute:
                continue
            sec = rule.bns_equivalent if (is_bns and rule.bns_equivalent not in ("", "NONE")) else rule.section
            matched_triggers = [t for t in rule.factual_triggers if t in lower_facts]
            if matched_triggers:
                _add(
                    sec_num=sec,
                    title=rule.title,
                    statute=target_statute,
                    ctype="PRIMARY" if not rule.bailable else "SECONDARY",
                    trigger_note=f"KB trigger matched: {matched_triggers[0]}",
                )

        # --- Hardcoded triggers (supplement KB-driven triggers above) ---
        # Use _add() so these don't duplicate what the KB already matched.

        # Trigger 1: Dowry harassment / cruelty -> 498A IPC / 85 BNS (Primary) + Sec 4 DP Act (Primary)
        if any(term in lower_facts for term in ["dowry", "cruelty", "harass", "demand", "torture", "in-laws"]):
            _add(
                sec_num="85",
                title="Cruelty by Husband or Relatives",
                statute="BNS",
                ctype="PRIMARY",
                trigger_note="Dowry harassment / cruelty alleged",
            )
            _add(
                sec_num="Section 4",
                title="Penalty for demanding dowry",
                statute="Dowry Prohibition Act",
                ctype="PRIMARY",
                trigger_note="Unlawful dowry demand alleged",
            )

        # Trigger 2: Giving or taking dowry -> Sec 3 DP Act
        if any(term in lower_facts for term in ["give dowry", "given dowry", "take dowry", "took dowry", "received dowry", "paid cash", "cash demanded"]):
            _add(
                sec_num="Section 3",
                title="Penalty for giving or taking dowry",
                statute="Dowry Prohibition Act",
                ctype="SECONDARY",
                trigger_note="Giving or taking of dowry indicated",
            )

        # Trigger 3: Stridhan / ornaments / property retained -> 406 IPC / 316 BNS (Secondary)
        if any(term in lower_facts for term in ["stridhan", "ornaments", "jewelry", "jewellery", "gold", "articles retained", "property not returned"]):
            _add(
                sec_num="316",
                title="Criminal Breach of Trust",
                statute="BNS",
                ctype="SECONDARY",
                trigger_note="Entrustment and non-return of stridhan / property alleged",
            )

        # Trigger 4: Threats / intimidation -> 506 IPC / 351 BNS (Secondary)
        if any(term in lower_facts for term in ["threat", "threatened", "intimidat", "warning", "abuse", "scared"]):
            _add(
                sec_num="351",
                title="Criminal Intimidation",
                statute="BNS",
                ctype="SECONDARY",
                trigger_note="Threats / criminal intimidation alleged",
            )

        # Trigger 5: Physical assault / hurt -> 323 IPC / 115 BNS (Secondary)
        if any(term in lower_facts for term in ["assault", "beaten", "slapped", "physical violence", "hurt", "injured", "hit"]):
            _add(
                sec_num="115",
                title="Voluntarily Causing Hurt",
                statute="BNS",
                ctype="SECONDARY",
                trigger_note="Physical assault / bodily hurt alleged",
            )

        # Trigger 6: Murder / killing -> 302 IPC (Primary)
        if any(term in lower_facts for term in ["murdered", "killed", "homicide", "shot dead", "stabbed to death",
                                                 "beaten to death", "strangulated", "poisoned", "burnt alive", "lynched"]):
            _add(
                sec_num="302",
                title="Murder",
                statute="IPC",
                ctype="PRIMARY",
                trigger_note="Murder / killing of a person alleged",
            )

        # Trigger 7: Attempt to murder -> 307 IPC (Primary)
        if any(term in lower_facts for term in ["attempt to murder", "attempted to kill", "tried to kill",
                                                 "stabbed in chest", "shot at", "life-threatening attack"]):
            _add(
                sec_num="307",
                title="Attempt to Murder",
                statute="IPC",
                ctype="PRIMARY",
                trigger_note="Attempt to murder indicated",
            )
            # Also suggest 120B (conspiracy) if multiple accused
            if any(t in lower_facts for t in ["conspiracy", "conspired", "hatched plan", "planned"]):
                _add(
                sec_num="120B",
                title="Criminal Conspiracy",
                statute="IPC",
                ctype="SECONDARY",
                trigger_note="Criminal conspiracy to commit murder alleged",
            )

        # Trigger 8: Abetment of suicide -> 306 IPC (Primary)
        if any(term in lower_facts for term in ["abetment of suicide", "instigated suicide", "drove to suicide",
                                                 "suicide note", "harassment led to suicide", "forced to commit suicide"]):
            _add(
                sec_num="306",
                title="Abetment of Suicide",
                statute="IPC",
                ctype="PRIMARY",
                trigger_note="Abetment of suicide alleged",
            )

        # Trigger 9: Rape / sexual assault -> 376 IPC (Primary)
        if any(term in lower_facts for term in ["rape", "sexual assault", "sexually assaulted", "intercourse",
                                                 "penetration", "gang rape", "ravished", "violated"]):
            _add(
                sec_num="376",
                title="Rape / Sexual Assault",
                statute="IPC",
                ctype="PRIMARY",
                trigger_note="Rape / sexual assault alleged",
            )
            if any(t in lower_facts for t in ["gang rape", "multiple accused rape", "raped by several"]):
                _add(
                sec_num="376D",
                title="Gang Rape",
                statute="IPC",
                ctype="PRIMARY",
                trigger_note="Gang rape alleged",
            )

        # Trigger 10: Kidnapping / abduction -> 363 IPC (Primary)
        if any(term in lower_facts for term in ["kidnapped", "kidnapping", "abducted", "abduction", "missing child",
                                                 "taken away", "minor taken", "enticed away"]):
            _add(
                sec_num="363",
                title="Kidnapping",
                statute="IPC",
                ctype="PRIMARY",
                trigger_note="Kidnapping / abduction alleged",
            )
            if any(t in lower_facts for t in ["ransom", "paid ransom", "demand ransom", "hostage"]):
                _add(
                sec_num="364A",
                title="Kidnapping for Ransom",
                statute="IPC",
                ctype="PRIMARY",
                trigger_note="Kidnapping for ransom alleged",
            )

        # Trigger 11: Theft -> 379 IPC / 304 BNS (Primary)
        # Also catches: "took", "took away", "took the laptop", "took property" (physical taking without consent)
        if any(term in lower_facts for term in [
            "theft", "stolen", "stole", "snatched", "pickpocket",
            "property stolen", "cash stolen", "vehicle stolen",
            "took away", "took the", "took her", "took his",
            "took laptop", "took mobile", "took phone", "took bag",
            "took from", "removed from", "carried away",
        ]):
            _add(
                sec_num="304",
                title="Punishment for Theft",
                statute="BNS",
                ctype="PRIMARY",
                trigger_note="Theft / taking of movable property alleged",
            )
            _add(
                sec_num="303",
                title="Theft",
                statute="BNS",
                ctype="PRIMARY",
                trigger_note="Theft — dishonest taking of movable property without consent",
            )
            if any(t in lower_facts for t in ["house theft", "broke into house", "burglary", "entered house and stole"]):
                _add(
                sec_num="305",
                title="Theft in Dwelling House",
                statute="BNS",
                ctype="PRIMARY",
                trigger_note="Theft from dwelling house alleged",
            )

        # Trigger 12: Robbery / dacoity -> 392 IPC / 309 BNS (Primary)
        if any(term in lower_facts for term in ["robbery", "robbed", "looted", "snatched by force",
                                                 "mugged", "chain snatching", "armed robbery"]):
            _add(
                sec_num="309",
                title="Punishment for Robbery",
                statute="BNS",
                ctype="PRIMARY",
                trigger_note="Robbery alleged",
            )
            if any(t in lower_facts for t in ["dacoity", "dacoits", "group robbery", "five persons robbed"]):
                _add(
                sec_num="310",
                title="Dacoity",
                statute="BNS",
                ctype="PRIMARY",
                trigger_note="Dacoity by group of five or more alleged",
            )

        # Trigger 13: Cheating / fraud -> 420 IPC / 318 BNS (Primary)
        if any(term in lower_facts for term in ["cheated", "defrauded", "deceived", "fraud", "fake promise",
                                                 "scam", "misrepresentation", "duped", "swindled"]):
            _add(
                sec_num="318",
                title="Cheating and Dishonestly Inducing Delivery of Property",
                statute="BNS",
                ctype="PRIMARY",
                trigger_note="Cheating / fraud alleged",
            )

        # Trigger 14: Extortion / blackmail -> 384 IPC / 309 BNS (Primary)
        # Also covers: threat to accuse of crime to extract money (classic extortion pattern)
        if any(term in lower_facts for term in [
            "extortion", "extorted", "blackmail", "blackmailed",
            "demanded money under threat", "coerced to pay",
            "threatened to accuse", "threatened to file", "threatened to expose",
            "accuse of fraud", "accuse her of fraud", "accuse him of fraud",
            "threatened to publicly", "threatened publicly",
            "transfer money", "transfer the money",
            "dishonest inducement", "dishonestly induced",
            "inducement to deliver", "inducing delivery",
            "pay or else", "pay otherwise", "money or else",
            "demanded transfer", "demanded payment under",
        ]):
            _add(
                sec_num="309",
                title="Punishment for Extortion",
                statute="BNS",
                ctype="PRIMARY",
                trigger_note="Extortion / blackmail / threat to accuse alleged",
            )
            _add(
                sec_num="308",
                title="Extortion",
                statute="BNS",
                ctype="PRIMARY",
                trigger_note="Extortion — putting in fear to dishonestly induce delivery of property",
            )

        # Trigger 15: Rioting / mob violence -> 147, 148 IPC (Primary)
        if any(term in lower_facts for term in ["rioting", "riot", "mob violence", "communal riot",
                                                 "rioters", "violent mob", "public disturbance"]):
            _add(
                sec_num="147",
                title="Rioting",
                statute="IPC",
                ctype="PRIMARY",
                trigger_note="Rioting / mob violence alleged",
            )
            _add(
                sec_num="149",
                title="Common Object Liability (Unlawful Assembly)",
                statute="IPC",
                ctype="SECONDARY",
                trigger_note="Common object of unlawful assembly alleged",
            )
            if any(t in lower_facts for t in ["weapon", "armed", "guns", "firing", "arson"]):
                _add(
                sec_num="148",
                title="Rioting Armed with Deadly Weapon",
                statute="IPC",
                ctype="PRIMARY",
                trigger_note="Armed rioting alleged",
            )

        # Trigger 16: Criminal conspiracy -> 120B IPC (Secondary)
        if any(term in lower_facts for term in ["criminal conspiracy", "conspired", "hatched conspiracy",
                                                 "planned together", "co-conspirators", "joint plan"]):
            _add(
                sec_num="120B",
                title="Criminal Conspiracy",
                statute="IPC",
                ctype="SECONDARY",
                trigger_note="Criminal conspiracy alleged",
            )

        # Trigger 17: Abetment -> 109 IPC (Secondary)
        if any(term in lower_facts for term in ["abetment", "instigated", "aided", "abetted", "facilitated crime",
                                                 "helped commit", "gave shelter to accused"]):
            _add(
                sec_num="109",
                title="Abetment",
                statute="IPC",
                ctype="SECONDARY",
                trigger_note="Abetment of offence alleged",
            )

        # Trigger 18: Grievous hurt -> 325 IPC (Secondary)
        if any(term in lower_facts for term in ["grievous hurt", "grievous injury", "fracture", "bone broken",
                                                 "permanent disability", "disfigured", "loss of limb"]):
            _add(
                sec_num="325",
                title="Voluntarily Causing Grievous Hurt",
                statute="IPC",
                ctype="PRIMARY",
                trigger_note="Grievous bodily hurt alleged",
            )

        # Trigger 19: Acid attack -> 326A IPC (Primary)
        if any(term in lower_facts for term in ["acid attack", "acid thrown", "acid poured", "burnt with acid",
                                                 "face disfigured by acid", "chemical attack"]):
            _add(
                sec_num="326A",
                title="Voluntarily Causing Grievous Hurt by Use of Acid",
                statute="IPC",
                ctype="PRIMARY",
                trigger_note="Acid attack alleged",
            )

        # Trigger 20: Forgery / forged documents -> 468 IPC (Primary)
        if any(term in lower_facts for term in ["forged document", "fake signature", "fabricated paper",
                                                 "forgery", "falsified record", "counterfeit", "forged will",
                                                 "fake will", "forged cheque"]):
            _add(
                sec_num="468",
                title="Forgery for Purpose of Cheating",
                statute="IPC",
                ctype="PRIMARY",
                trigger_note="Forgery for cheating alleged",
            )
            _add(
                sec_num="471",
                title="Using Forged Document as Genuine",
                statute="IPC",
                ctype="SECONDARY",
                trigger_note="Use of forged document alleged",
            )

        # Trigger 21: Cyber crime / IT Act -> Section 66 IT Act (Primary)
        if any(term in lower_facts for term in ["hacking", "cyber fraud", "phishing", "online fraud",
                                                 "account hacked", "OTP fraud", "UPI fraud", "cyber crime"]):
            _add(
                sec_num="66",
                title="Computer Related Offences (IT Act)",
                statute="IT Act 2000",
                ctype="PRIMARY",
                trigger_note="Cyber / computer offence alleged",
            )
            if any(t in lower_facts for t in ["identity theft", "stole identity", "used someone's password",
                                               "fake identity", "stolen credentials"]):
                _add(
                sec_num="66C",
                title="Identity Theft (IT Act)",
                statute="IT Act 2000",
                ctype="SECONDARY",
                trigger_note="Identity theft alleged",
            )

        # Trigger 22: Drugs / NDPS -> Section 20 / 21 NDPS Act
        if any(term in lower_facts for term in ["drugs", "narcotics", "ganja", "cannabis", "heroin", "cocaine",
                                                 "opium", "brown sugar", "drug peddling", "smack", "mephedrone"]):
            if any(t in lower_facts for t in ["ganja", "cannabis", "marijuana", "charas", "weed"]):
                _add(
                sec_num="20",
                title="Contravention re Cannabis (NDPS Act)",
                statute="NDPS Act 1985",
                ctype="PRIMARY",
                trigger_note="Cannabis drug offence alleged",
            )
            else:
                _add(
                sec_num="21",
                title="Contravention re Manufactured Drugs (NDPS Act)",
                statute="NDPS Act 1985",
                ctype="PRIMARY",
                trigger_note="Manufactured narcotic drug offence alleged",
            )

        # Trigger 23: Illegal arms / weapons -> Section 25 Arms Act
        if any(term in lower_facts for term in ["illegal weapon", "unlicensed gun", "country made pistol",
                                                 "katta", "desi katta", "illegal firearm", "arms without licence"]):
            _add(
                sec_num="25",
                title="Illegal Possession of Arms (Arms Act)",
                statute="Arms Act 1959",
                ctype="SECONDARY",
                trigger_note="Illegal arms / weapon possession alleged",
            )

        # Trigger 24: SC/ST atrocity -> Section 3(1)(r) SC/ST POA Act
        if any(term in lower_facts for term in ["sc st atrocity", "caste abuse", "caste slur", "dalit",
                                                 "scheduled caste", "scheduled tribe", "casteist"]):
            _add(
                sec_num="3(1)(r)",
                title="Intentional Insult to SC/ST Member (SC/ST POA Act)",
                statute="SC/ST (POA) Act",
                ctype="PRIMARY",
                trigger_note="SC/ST atrocity / caste abuse alleged",
            )

        # Trigger 25: Negligent death (road accident) -> 304A IPC (Primary)
        if any(term in lower_facts for term in ["rash driving", "road accident", "vehicle hit", "knocked down",
                                                 "ran over", "medical negligence", "negligent act caused death"]):
            _add(
                sec_num="304A",
                title="Causing Death by Negligence",
                statute="IPC",
                ctype="PRIMARY",
                trigger_note="Death caused by rash / negligent act alleged",
            )

        # Trigger 26: Bigamy -> 494 IPC (Primary)
        if any(term in lower_facts for term in ["bigamy", "second marriage", "married again", "married while first spouse alive",
                                                 "second wife", "second husband", "double marriage"]):
            _add(
                sec_num="494",
                title="Bigamy",
                statute="IPC",
                ctype="PRIMARY",
                trigger_note="Bigamy / second marriage alleged",
            )

        # Trigger 27: Molestation / outraging modesty -> 354 IPC (Primary)
        if any(term in lower_facts for term in ["molestation", "groped", "touched inappropriately", "outrage modesty",
                                                 "indecent assault", "sexual harassment"]):
            _add(
                sec_num="354",
                title="Assault or Criminal Force to Outrage Modesty of Woman",
                statute="IPC",
                ctype="PRIMARY",
                trigger_note="Molestation / outraging modesty of woman alleged",
            )

        # Trigger 28: Stalking -> 354D IPC (Primary)
        if any(term in lower_facts for term in ["stalking", "following", "monitoring", "watching repeatedly",
                                                 "cyberstalking", "online stalking", "tracking location"]):
            _add(
                sec_num="354D",
                title="Stalking",
                statute="IPC",
                ctype="PRIMARY",
                trigger_note="Stalking of woman alleged",
            )

        # Trigger 29: Destroying / tampering evidence -> 201 IPC (Secondary)
        if any(term in lower_facts for term in ["destroyed evidence", "tampered evidence", "concealed evidence",
                                                 "hidden body", "disposed of body", "burnt body", "washed crime scene"]):
            _add(
                sec_num="201",
                title="Causing Disappearance of Evidence",
                statute="IPC",
                ctype="SECONDARY",
                trigger_note="Destruction / concealment of evidence alleged",
            )

        # Trigger 30: False complaint / perjury -> 182 / 211 IPC (Secondary)
        if any(term in lower_facts for term in ["false complaint", "false FIR", "fake FIR", "malicious prosecution",
                                                 "false case filed", "fabricated complaint"]):
            _add(
                sec_num="211",
                title="False Charge of Offence Made with Intent to Injure",
                statute="IPC",
                ctype="SECONDARY",
                trigger_note="False / malicious criminal complaint alleged",
            )
            _add(
                sec_num="182",
                title="False Information to Public Servant",
                statute="IPC",
                ctype="SECONDARY",
                trigger_note="False information to police / public servant alleged",
            )

        return suggestions

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