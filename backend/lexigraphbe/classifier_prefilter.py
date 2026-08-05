"""
Local Statute Classifier & Pre-Filter Module for LexiGraph Backend.
Pre-filters 574+ IPC/BNS sections down to top candidate sections (5-10) using local TF-IDF & keyword matching.
Executes 100% locally in Python code with ZERO LLM API calls.
"""

import csv
import math
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, Any
from pydantic import BaseModel, Field

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
    punishment_maximum: str = "3 Years"
    fine: bool = True
    cognizable: bool = True
    bailable: bool = False


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
]


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

            # 2. Knowledge Base Factual Trigger Matching
            kb_boost = 0.0
            for rule in STATUTE_KNOWLEDGE_BASE:
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
        for rec, score, matched_list in matches[:top_k]:
            if rec["identifier"] not in seen_identifiers:
                seen_identifiers.add(rec["identifier"])
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

        for rule in STATUTE_KNOWLEDGE_BASE:
            target_sec = rule.bns_equivalent if "BNS" in (statute or "").upper() else rule.section
            if sec_num_clean == target_sec.upper() or sec_num_clean == rule.section.upper():
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
        Detects factual triggers in facts_text and automatically suggests candidate sections
        (Primary and Secondary) across all plausible offences.
        """
        lower_facts = (facts_text or "").lower()
        is_bns = "BNS" in (statute_type or "").upper()
        suggestions = []

        # Trigger 1: Dowry harassment / cruelty -> 498A IPC / 85 BNS (Primary) + Sec 4 DP Act (Primary)
        if any(term in lower_facts for term in ["dowry", "cruelty", "harass", "demand", "torture", "in-laws"]):
            suggestions.append({
                "section_number": "85" if is_bns else "498A",
                "section_title": "Cruelty by Husband or Relatives",
                "statute": "BNS" if is_bns else "IPC",
                "candidate_type": "PRIMARY",
                "trigger": "Dowry harassment / cruelty alleged",
            })
            suggestions.append({
                "section_number": "Section 4",
                "section_title": "Penalty for demanding dowry",
                "statute": "Dowry Prohibition Act",
                "candidate_type": "PRIMARY",
                "trigger": "Unlawful dowry demand alleged",
            })

        # Trigger 2: Giving or taking dowry -> Sec 3 DP Act
        if any(term in lower_facts for term in ["give dowry", "given dowry", "take dowry", "took dowry", "received dowry", "paid cash", "cash demanded"]):
            suggestions.append({
                "section_number": "Section 3",
                "section_title": "Penalty for giving or taking dowry",
                "statute": "Dowry Prohibition Act",
                "candidate_type": "SECONDARY",
                "trigger": "Giving or taking of dowry indicated",
            })

        # Trigger 3: Stridhan / ornaments / property retained -> 406 IPC / 316 BNS (Secondary)
        if any(term in lower_facts for term in ["stridhan", "ornaments", "jewelry", "jewellery", "gold", "articles retained", "property not returned"]):
            suggestions.append({
                "section_number": "316" if is_bns else "406",
                "section_title": "Criminal Breach of Trust",
                "statute": "BNS" if is_bns else "IPC",
                "candidate_type": "SECONDARY",
                "trigger": "Entrustment and non-return of stridhan / property alleged",
            })

        # Trigger 4: Threats / intimidation -> 506 IPC / 351 BNS (Secondary)
        if any(term in lower_facts for term in ["threat", "threatened", "intimidat", "warning", "abuse", "scared"]):
            suggestions.append({
                "section_number": "351" if is_bns else "506",
                "section_title": "Criminal Intimidation",
                "statute": "BNS" if is_bns else "IPC",
                "candidate_type": "SECONDARY",
                "trigger": "Threats / criminal intimidation alleged",
            })

        # Trigger 5: Physical assault / hurt -> 323 IPC / 115 BNS (Secondary)
        if any(term in lower_facts for term in ["assault", "beaten", "slapped", "physical violence", "hurt", "injured", "hit"]):
            suggestions.append({
                "section_number": "115" if is_bns else "323",
                "section_title": "Voluntarily Causing Hurt",
                "statute": "BNS" if is_bns else "IPC",
                "candidate_type": "SECONDARY",
                "trigger": "Physical assault / bodily hurt alleged",
            })

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
