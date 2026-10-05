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
        """Loads dataset records exclusively from ipc.json via StatuteRepository."""
        repo = StatuteRepository.get_instance()
        self.sections_db = repo.get_sections_db()

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
            # ── Existing entries (violence / property offences) ─────────────────────────
            "dishonest inducement to deliver property": ["extortion", "extorted", "blackmail", "threatened", "induced delivery"],
            "dishonestly inducing delivery": ["extortion", "blackmail", "threatened", "induced delivery"],
            "criminal intimidation": ["threat", "threatened", "intimidat", "warning"],
            "physical assault": ["assault", "beaten", "hurt", "pushed", "shoved", "slapped",
                               "physical violence", "physical abuse", "physical incident",
                               "kicked", "punched", "struck", "bodily harm", "manhandled"],
            "voluntarily causing hurt": ["assault", "hurt", "beaten", "physical violence",
                                        "pushed", "shoved", "slapped", "manhandled"],
            "theft": ["theft", "stolen", "stole", "took away"],
            "criminal breach of trust": ["stridhan", "ornaments", "property not returned", "entrustment"],
            "extortion": ["extortion", "extorted", "blackmail", "threatened", "demanded money"],
            "cheating": ["cheated", "defrauded", "deceived", "fraud"],
            "robbery": ["robbery", "robbed", "looted", "snatched by force"],
            "house trespass": ["trespass", "entered illegally", "barged in", "godown", "building", "dwelling", "theft", "receptacle"],
            "criminal trespass": ["trespass", "entered illegally", "encroached", "godown", "storage", "building", "theft", "stole", "removed", "receptacle"],
            "breaking open": ["theft", "property", "receptacle", "godown", "padlock", "lock", "trespass", "stole", "removed"],
            "removing property": ["theft", "stolen", "property", "movable", "misappropriation", "dishonest misappropriation"],
            "taking raw materials": ["theft", "stolen", "property", "movable", "raw materials", "inventory"],
            "mischief": ["damaged", "destroyed property", "mischief"],
            "abetment of suicide": ["abetment of suicide", "instigated suicide", "harassment led to suicide"],

            # ── Homicide / death offences ───────────────────────────────────────────────
            # Map death-related concept phrases to ensure proper section matching.
            # Critical: "sudden quarrel" + "death" should trigger Section 300 (Murder with Exception 4)
            # and Section 304 (Culpable homicide not amounting to murder), NOT Section 301 (transferred malice).
            "causing death": ["death", "killed", "murder", "culpable homicide", "homicide"],
            "causing death during quarrel": ["death", "killed", "murder", "culpable homicide", "sudden quarrel", "sudden fight", "heat of passion"],
            "causing death during sudden quarrel": ["death", "killed", "murder", "culpable homicide", "sudden quarrel", "sudden fight", "heat of passion", "provocation"],
            "death in sudden fight": ["death", "killed", "murder", "culpable homicide", "sudden quarrel", "sudden fight", "heat of passion"],
            "culpable homicide": ["death", "killed", "murder", "culpable homicide"],

            # ── Forgery / document fraud ────────────────────────────────────────────────
            # Maps Stage 1 concept labels for document-fraud cases to trigger keywords that
            # match 463/465/467/468/471/423 entries in the KB and CSV.
            "forgery": ["forgery", "forged document", "fake signature", "fabricated", "false document"],
            "forgery of document": ["forgery", "forged document", "fabricated document", "false document"],
            "forgery of valuable security": [
                "forged document", "forgery", "sale deed", "title deed", "ownership document",
                "forged deed", "fake deed", "valuable security",
            ],
            "fraudulent document": ["forged document", "forgery", "false document", "fabricated", "fake deed"],
            "forged ownership documents": [
                "forged document", "forgery", "ownership document", "title deed", "sale deed",
                "fake ownership", "fabricated deed", "forged deed",
            ],
            "fraudulent deed": [
                "fraudulent deed", "false deed", "forged deed", "sale deed",
                "false consideration", "fake sale deed", "fraudulent sale deed",
            ],
            "fraudulent sale deed": [
                "fraudulent deed", "false deed", "forged deed", "sale deed",
                "false consideration", "fraudulent transfer",
            ],
            "making false document": ["forgery", "forged document", "false document", "fabricated"],
            "using forged document": ["forged document", "used forged document", "submitted fake document"],

            # ── Dishonest property transfer (Stage 1 concept labels for land-fraud) ─────
            # Stage 1 uses "Dishonest Transfer", "Fraudulent Sale", "Property Fraud" as
            # concept labels.  Map these to vocabulary that triggers 420 and 423.
            "dishonest transfer": [
                "dishonest transfer", "fraudulent transfer", "cheated", "defrauded",
                "fraudulent sale", "dishonestly transferred", "fraudulently transferred",
            ],
            "dishonest transfer of property": [
                "dishonest transfer", "fraudulent transfer", "cheated", "defrauded",
                "fraudulent sale", "property fraud", "false representation",
            ],
            "dishonest transfer of immovable property": [
                "dishonest transfer", "fraudulent transfer", "cheated", "defrauded",
                "fraudulent sale", "false representation", "dishonestly transferred",
            ],
            "fraudulent transfer": [
                "fraudulent transfer", "fraudulent sale", "cheated", "defrauded",
                "dishonest transfer", "fraudulently transferred",
            ],
            "fraudulent property transfer": [
                "fraudulent transfer", "cheated", "defrauded", "fraudulent sale",
                "false representation", "property fraud",
            ],
            "property fraud": [
                "cheated", "defrauded", "deceived", "fraud", "fraudulent transfer",
                "dishonest transfer", "property fraud",
            ],
            "fraudulent sale": [
                "fraudulent sale", "cheated", "defrauded", "fraudulent transfer",
                "sale deed", "fraudulent deed",
            ],

            # ── Anticipatory bail / bail procedural context ─────────────────────────────
            # Ensure the procedural enabling section is matched when Stage 1 identifies
            # the legal proceeding context as "Anticipatory Bail Application".
            "anticipatory bail": ["anticipatory bail", "pre-arrest bail", "apprehension of arrest"],
            "anticipatory bail application": ["anticipatory bail", "pre-arrest bail", "seeking anticipatory"],
            "bail application": ["anticipatory bail", "bail", "pre-arrest bail"],
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

        # 3. Detect factual triggers and append any missing suggestions
        raw_facts = getattr(legal_query_obj, "case_facts", "") or ""
        trigger_text = raw_facts + " " + query_full_text
        detected = self.detect_factual_triggers(trigger_text, statute_type=regime_filter or "IPC")
        for trig in detected:
            trig_sec = trig["section_number"]
            trig_stat = trig["statute"]
            candidate_key = f"{trig_stat}_{trig_sec}"
            if candidate_key not in seen_identifiers:
                seen_identifiers.add(candidate_key)
                results.append(
                    CandidateSectionMatch(
                        section_identifier=f"{trig_stat} {trig_sec}",
                        statute=trig_stat,
                        section_number=trig_sec,
                        title=trig["section_title"],
                        chapter="Statutory Chapter",
                        score=0.92,
                        matched_terms=["factual_trigger"],
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
        Detects factual triggers in facts_text and automatically suggests candidate sections.
        Combines hardcoded triggers with live KB rules (static + dynamic) so auto-promoted
        sections are matched on future queries without any code changes.
        """
        lower_facts = (facts_text or "").lower()
        is_bns = "BNS" in (statute_type or "").upper()
        suggestions = []
        seen_keys: set = set()
        repo = StatuteRepository.get_instance()

        def _add(sec_num: str, title: str, statute: str, ctype: str, trigger_note: str) -> None:
            # Strictly filter against ipc.json if statute is IPC
            if statute.upper() == "IPC" and not repo.is_in_ipc_json(sec_num):
                return
            _PENAL_STATUTES = {"BNS", "BNSS"}
            if not is_bns and statute in _PENAL_STATUTES:
                return
            if is_bns and statute in {"IPC", "CrPC"}:
                return
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

        # --- Trigger 0: Procedural context triggers (run before KB and factual triggers) ---
        # These fire on the legal proceeding type, not on offence facts.  They must always
        # appear in the output when the corresponding procedural stage is present.

        # Trigger 0A: Anticipatory bail -> CrPC 438 / BNSS 482
        # The enabling provision for anticipatory bail must always be in the candidate list.
        # Fires on procedural vocabulary — not on any specific offence or party name.
        if any(term in lower_facts for term in [
            "anticipatory bail", "pre-arrest bail", "section 438", "crpc 438",
            "bnss 482", "apprehension of arrest", "seeking anticipatory",
            "application for anticipatory", "anticipatory bail application",
        ]):
            if is_bns:
                _add(
                    sec_num="482",
                    title="Direction for Grant of Bail to Person Apprehending Arrest",
                    statute="BNSS",
                    ctype="PRIMARY",
                    trigger_note="Anticipatory bail application — BNSS 482 is the enabling provision",
                )
            else:
                _add(
                    sec_num="438",
                    title="Direction for Grant of Bail to Person Apprehending Arrest",
                    statute="CrPC",
                    ctype="PRIMARY",
                    trigger_note="Anticipatory bail application — CrPC 438 is the enabling provision",
                )

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

        # Trigger 1: Dowry harassment / cruelty -> 498A IPC (Primary) + Sec 4 DP Act (Primary)
        if any(term in lower_facts for term in ["dowry", "cruelty", "harass", "demand", "torture", "in-laws"]):
            _add(
                sec_num="498A",
                title="Cruelty by Husband or Relatives",
                statute="IPC",
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

        # Trigger 3: Stridhan / ornaments / property retained -> 406 IPC (Secondary)
        if any(term in lower_facts for term in ["stridhan", "ornaments", "jewelry", "jewellery", "gold", "articles retained", "property not returned"]):
            _add(
                sec_num="406",
                title="Criminal Breach of Trust",
                statute="IPC",
                ctype="SECONDARY",
                trigger_note="Entrustment and non-return of stridhan / property alleged",
            )

        # Trigger 4: Threats / intimidation -> 506 IPC (Secondary)
        if any(term in lower_facts for term in ["threat", "threatened", "intimidat", "warning", "abuse", "scared"]):
            _add(
                sec_num="506",
                title="Criminal Intimidation",
                statute="IPC",
                ctype="SECONDARY",
                trigger_note="Threats / criminal intimidation alleged",
            )

        # Trigger 5: Physical assault / hurt -> 323 IPC (Secondary)
        if any(term in lower_facts for term in [
            "assault", "beaten", "slapped", "physical violence", "hurt", "injured", "hit",
            "pushed", "shoved", "kicked", "punched", "struck", "physical abuse",
            "physical harm", "bodily harm", "physically abused", "physical incident",
            "physical force", "forced her", "forced him", "manhandled",
        ]):
            _add(
                sec_num="323",
                title="Voluntarily Causing Hurt",
                statute="IPC",
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

        # Trigger 11: Theft -> 379 IPC (Primary)
        if any(term in lower_facts for term in [
            "theft", "stolen", "stole", "snatched", "pickpocket",
            "property stolen", "cash stolen", "vehicle stolen",
            "took away", "took the", "took her", "took his",
            "took laptop", "took mobile", "took phone", "took bag",
            "took from", "removed from", "carried away", "loaded", "raw materials",
            "broke open", "padlock", "godown", "inventory", "bags of",
        ]):
            _add(
                sec_num="379",
                title="Punishment for Theft",
                statute="IPC",
                ctype="PRIMARY",
                trigger_note="Theft / taking of movable property alleged",
            )
            _add(
                sec_num="378",
                title="Theft",
                statute="IPC",
                ctype="PRIMARY",
                trigger_note="Theft — dishonest taking of movable property without consent",
            )
            _add(
                sec_num="380",
                title="Theft in Dwelling House, Godown, or Building",
                statute="IPC",
                ctype="PRIMARY",
                trigger_note="Theft from building / storage godown alleged",
            )
            if any(t in lower_facts for t in ["house theft", "broke into house", "burglary", "entered house and stole"]):
                _add(
                    sec_num="380",
                    title="Theft in Dwelling House",
                    statute="IPC",
                    ctype="PRIMARY",
                    trigger_note="Theft from dwelling house alleged",
                )

        # Trigger 12: Robbery / dacoity -> 392 IPC (Primary)
        if any(term in lower_facts for term in ["robbery", "robbed", "looted", "snatched by force",
                                                 "mugged", "chain snatching", "armed robbery"]):
            _add(
                sec_num="392",
                title="Punishment for Robbery",
                statute="IPC",
                ctype="PRIMARY",
                trigger_note="Robbery alleged",
            )
            if any(t in lower_facts for t in ["dacoity", "dacoits", "group robbery", "five persons robbed"]):
                _add(
                    sec_num="395",
                    title="Dacoity",
                    statute="IPC",
                    ctype="PRIMARY",
                    trigger_note="Dacoity by group of five or more alleged",
                )

        # Trigger 13: Cheating / fraud / dishonest inducement to deliver property -> 420 IPC (Conditional)
        if any(term in lower_facts for term in [
            "cheated", "defrauded", "deceived", "fraud", "fake promise",
            "scam", "misrepresentation", "duped", "swindled",
            # Property-fraud vocabulary from Stage 1 concept labels and case narratives
            "dishonest transfer", "dishonestly transferred", "fraudulent transfer",
            "fraudulent sale", "fraudulent sale deed", "false representation of title",
            "induced to sell", "induced to transfer", "dishonestly induced",
            "pretended to be owner", "false title claim", "fraudulently obtained property",
            "property fraud", "fraudulently induced",
        ]):
            _add(
                sec_num="420",
                title="Cheating and Dishonestly Inducing Delivery of Property",
                statute="IPC",
                ctype="CONDITIONAL",
                trigger_note="Cheating / dishonest inducement to deliver property alleged — conditional upon proof of deceptive inducement causing delivery",
            )

        # Trigger 14: Extortion / blackmail -> 384 IPC (Primary)
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
                sec_num="384",
                title="Punishment for Extortion",
                statute="IPC",
                ctype="PRIMARY",
                trigger_note="Extortion / blackmail / threat to accuse alleged",
            )
            _add(
                sec_num="383",
                title="Extortion",
                statute="IPC",
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

        # Trigger 20: Forgery / forged documents -> 463/465/467/468/471 IPC
        # Base offence 465 is PRIMARY (creation of false document).
        # Compound/aggravated offences 468, 471, 467, 423 are CONDITIONAL because they require
        # unproven gating prerequisites (purpose of cheating, use as genuine, valuable security status, false statement).
        _forgery_base_terms = [
            "forged document", "fake signature", "fabricated paper",
            "forgery", "falsified record", "counterfeit", "forged will",
            "fake will", "forged cheque", "fabricated document",
            # Vocabulary that appears in land-fraud FIRs
            "forged ownership", "forged deed", "fake deed", "fraudulent deed",
            "ownership document", "title deed", "sale deed", "ownership papers",
            "forged documents", "fabricated ownership",
        ]
        if any(term in lower_facts for term in _forgery_base_terms):
            # 465: Base forgery — PRIMARY when false document creation is alleged
            _add(
                sec_num="465",
                title="Forgery",
                statute="IPC",
                ctype="PRIMARY",
                trigger_note="Forgery alleged — making a false document",
            )
            # 468: Forgery with cheating intent — CONDITIONAL (requires specific cheating purpose)
            _add(
                sec_num="468",
                title="Forgery for Purpose of Cheating",
                statute="IPC",
                ctype="CONDITIONAL",
                trigger_note="Forgery for cheating alleged — conditional upon purpose of forgery being cheating under Section 415",
            )
            # 471: Using forged document as genuine — CONDITIONAL (requires proof of use/presentation)
            _add(
                sec_num="471",
                title="Using Forged Document as Genuine",
                statute="IPC",
                ctype="CONDITIONAL",
                trigger_note="Use of forged document as genuine alleged — conditional upon proof of presentation or use in transaction",
            )

            # Sub-check for 467: The forged instrument is a "valuable security" or "will"
            _valuable_security_terms = [
                "sale deed", "title deed", "ownership document", "registered document",
                "conveyance deed", "gift deed", "transfer deed", "lease deed",
                "power of attorney", "ownership papers", "land document", "property document",
                "land title", "forged deed", "fake deed", "fraudulent deed",
                "forged will", "fake will", "forged cheque", "promissory note",
                "bond", "stamp paper", "registered deed", "forged ownership",
                "ownership papers", "title document",
            ]
            if any(term in lower_facts for term in _valuable_security_terms):
                _add(
                    sec_num="467",
                    title="Forgery of Valuable Security / Will",
                    statute="IPC",
                    ctype="CONDITIONAL",
                    trigger_note="Forgery of valuable security / title deed alleged — conditional upon document qualifying under Section 467",
                )

            # Sub-check for 423: Executing a deed containing a false statement of consideration/beneficiary
            _deed_execution_terms = [
                "executed deed", "executed sale deed", "sale deed", "executed a deed",
                "registered deed", "fraudulent deed", "dishonest deed", "false deed",
                "fraudulent execution", "fraudulent sale deed", "dishonest transfer",
                "dishonestly transferred", "fraudulently transferred",
            ]
            if any(term in lower_facts for term in _deed_execution_terms):
                _add(
                    sec_num="423",
                    title="Dishonest or Fraudulent Execution of Deed Containing a False Statement",
                    statute="IPC",
                    ctype="CONDITIONAL",
                    trigger_note="Fraudulent deed execution alleged — conditional upon deed containing false statement of consideration or beneficiary",
                )

            # Sub-check for 423: Executing a deed that contains a false statement
            # (the characteristic act in sale-deed fraud — registering a deed with false
            # consideration, false seller identity, or false title representation).
            _deed_execution_terms = [
                "executed deed", "executed sale deed", "sale deed", "executed a deed",
                "registered deed", "fraudulent deed", "dishonest deed", "false deed",
                "fraudulent execution", "fraudulent sale deed", "dishonest transfer",
                "dishonestly transferred", "fraudulently transferred",
            ]
            if any(term in lower_facts for term in _deed_execution_terms):
                _add(
                    sec_num="423",
                    title="Dishonest or Fraudulent Execution of Deed Containing a False Statement",
                    statute="IPC",
                    ctype="PRIMARY",
                    trigger_note="Fraudulent execution of deed with false statement alleged",
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