"""
Local Statute Classifier & Pre-Filter Module for LexiGraph Backend.
Pre-filters 574+ IPC/BNS sections down to top candidate sections (5-10) using local TF-IDF & keyword matching.
Executes 100% locally in Python code with ZERO LLM API calls.
"""

import csv
import math
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
from pydantic import BaseModel, Field

from .schemas import LegalConceptItem, LegalQueryObject, SubQueryItem


class CandidateSectionMatch(BaseModel):
    section_identifier: str = Field(description="Normalized section identifier e.g. IPC 498A, BNS 85")
    statute: str = Field(description="Statute name: 'IPC' or 'BNS'")
    section_number: str = Field(description="Section number string e.g. '498A', '85'")
    title: str = Field(description="Section title or offense description")
    chapter: Optional[str] = Field(default=None, description="Chapter title if available")
    score: float = Field(description="Local pre-filter relevance score (0.0 to 1.0)")
    matched_terms: List[str] = Field(default_factory=list, description="Keywords/terms matched locally")


class StatuteClassifierPrefilter:
    """
    Local statute pre-filter classifier loading section records from data/new/ CSV datasets.
    Pre-filters candidate section shortlists locally before LLM verification.
    """

    def __init__(self):
        self.sections_db: List[Dict[str, Any]] = []
        self._load_datasets()

    def _load_datasets(self):
        """Loads IPC and BNS dataset records into local in-memory index."""
        candidate_ipc = [
            Path("data/new/ipc_sections.csv"),
            Path("../data/new/ipc_sections.csv"),
            Path("c:/MootCourt/data/new/ipc_sections.csv"),
        ]
        candidate_bns = [
            Path("data/update_combine_Dataset/bns.csv"),
            Path("../data/update_combine_Dataset/bns.csv"),
            Path("c:/MootCourt/data/update_combine_Dataset/bns.csv"),
            Path("data/new/bns_sections_clean.csv"),
            Path("../data/new/bns_sections_clean.csv"),
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

        for record in self.sections_db:
            if regime_filter and record["statute"] != regime_filter:
                continue

            record_text = record["full_text"]
            record_title = record["title"].lower()

            matched = [term for term in unique_query_terms if term in record_text]
            if not matched:
                continue

            # Calculate base term score
            term_score = len(matched) / (len(unique_query_terms) ** 0.5)

            # Boost exact concept phrase matches and title matches
            phrase_boost = 1.0
            for phrase in concept_phrases:
                if len(phrase) > 3:
                    if phrase in record_text:
                        phrase_boost += 1.5
                    if phrase in record_title:
                        phrase_boost += 2.0
                    # Check individual key words matching title
                    words = [w for w in re.findall(r"\w+", phrase) if w not in stop_words]
                    title_matches = [w for w in words if w in record_title]
                    if title_matches:
                        phrase_boost += (len(title_matches) * 0.5)

            final_score = min(1.0, round((term_score * phrase_boost) / 2.0, 2))
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
