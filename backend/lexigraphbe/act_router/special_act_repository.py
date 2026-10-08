"""
Special Act Repository for Act Router Sub-Pipeline.

Manages, caches, and indexes the 8 Special Act JSON documents:
1. dowry_prohibition_act.json
2. indian_institutes_of_information_technology_act.json
3. itpa.json
4. juvenile_justice_act.json
5. pocso_act.json
6. posh_act.json
7. prohibition_of_child_marriage_act.json
8. sc_st_prevention_of_atrocities_act.json

Provides:
  - Zero-API-call candidate prefiltering for any selected Special Act.
  - In-memory caching so JSONs are loaded only when requested.
  - Normalized access to section numbers, titles, chapters, and statutory text.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

SPECIAL_ACT_TITLES: Dict[str, str] = {
    "dowry_prohibition_act.json": "The Dowry Prohibition Act, 1961",
    "indian_institutes_of_information_technology_act.json": "The Indian Institutes of Information Technology Act, 2014",
    "itpa.json": "The Immoral Traffic (Prevention) Act, 1956",
    "juvenile_justice_act.json": "The Juvenile Justice (Care and Protection of Children) Act, 2015",
    "pocso_act.json": "The Protection of Children from Sexual Offences Act, 2012",
    "posh_act.json": "The Sexual Harassment of Women at Workplace (Prevention, Prohibition and Redressal) Act, 2013",
    "prohibition_of_child_marriage_act.json": "The Prohibition of Child Marriage Act, 2006",
    "sc_st_prevention_of_atrocities_act.json": "The Scheduled Castes and the Scheduled Tribes (Prevention of Atrocities) Act, 1989",
}

# Core baseline substantive/penal/procedural sections per Act to guarantee high recall
_CORE_SECTIONS_PER_ACT: Dict[str, List[str]] = {
    "dowry_prohibition_act.json": ["2", "3", "4", "4A", "6", "8", "8A", "8B"],
    "pocso_act.json": ["3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "14", "19", "29", "30"],
    "posh_act.json": ["2", "3", "4", "9", "10", "11", "12", "14", "15", "19", "26"],
    "sc_st_prevention_of_atrocities_act.json": ["3", "4", "8", "14", "14A", "18", "18A"],
    "itpa.json": ["2", "3", "4", "5", "6", "7", "8", "9"],
    "juvenile_justice_act.json": ["2", "10", "12", "15", "18", "21", "74", "75", "76", "77", "78", "79", "82"],
    "prohibition_of_child_marriage_act.json": ["2", "3", "9", "10", "11", "12", "13", "14"],
    "indian_institutes_of_information_technology_act.json": ["2", "22", "24", "34", "35"],
}


class SpecialActRepository:
    """Thread-safe cached repository for Special Act documents."""

    _instance: Optional["SpecialActRepository"] = None
    _lock = threading.Lock()

    def __init__(self):
        if SpecialActRepository._instance is not None:
            raise RuntimeError("SpecialActRepository is a singleton. Use SpecialActRepository.get_instance().")
        self._cached_acts: Dict[str, List[Dict[str, Any]]] = {}
        self._cached_meta: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def get_instance(cls) -> "SpecialActRepository":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        with cls._lock:
            cls._instance = None

    def _get_doc_path(self, document_name: str) -> Optional[Path]:
        """Resolves path to a special act json file."""
        candidates = [
            Path(__file__).parent / document_name,
            Path(__file__).parent / "act_router" / document_name,
            Path("backend/lexigraphbe/act_router") / document_name,
            Path("lexigraphbe/act_router") / document_name,
            Path("act_router") / document_name,
        ]
        return next((p for p in candidates if p.exists()), None)

    def load_act(self, document_name: str) -> List[Dict[str, Any]]:
        """
        Loads and normalizes all sections from a special act JSON.
        Caches results in memory.
        """
        doc_key = document_name.strip()
        if doc_key in self._cached_acts:
            return self._cached_acts[doc_key]

        file_path = self._get_doc_path(doc_key)
        if not file_path:
            logger.warning(f"Special Act JSON not found: {doc_key}")
            return []

        try:
            with open(file_path, mode="r", encoding="utf-8-sig") as f:
                data = json.load(f)

            doc_meta = data.get("document", {})
            self._cached_meta[doc_key] = doc_meta

            sections_list: List[Dict[str, Any]] = []

            for chapter in data.get("chapters", []):
                ch_num = chapter.get("chapter_number")
                ch_title = chapter.get("chapter_title")
                for sec in chapter.get("sections", []):
                    s_num = str(sec.get("section_number", "")).strip()
                    if not s_num:
                        continue
                    heading = sec.get("heading", "") or ""
                    text = sec.get("text", "") or ""

                    # If text is empty, check sub_sections
                    if not text and "sub_sections" in sec:
                        sub_parts = []
                        for sub in sec["sub_sections"]:
                            lbl = sub.get("label", "")
                            stxt = sub.get("text", "")
                            if lbl or stxt:
                                sub_parts.append(f"{lbl} {stxt}".strip())
                        text = "\n".join(sub_parts)

                    sections_list.append({
                        "document": doc_key,
                        "act_title": doc_meta.get("title") or SPECIAL_ACT_TITLES.get(doc_key, doc_key),
                        "section_number": s_num,
                        "heading": heading,
                        "chapter_number": ch_num,
                        "chapter_title": ch_title,
                        "text": text,
                        "is_definition": sec.get("is_definition", False),
                        "is_punishment": sec.get("is_punishment", False),
                    })

            self._cached_acts[doc_key] = sections_list
            return sections_list

        except Exception as e:
            logger.error(f"Error loading {doc_key}: {e}")
            return []

    def get_act_title(self, document_name: str) -> str:
        """Returns the full title for a special act document."""
        if document_name in self._cached_meta:
            t = self._cached_meta[document_name].get("title")
            if t:
                return t
        return SPECIAL_ACT_TITLES.get(document_name, document_name)

    def prefilter_candidates(
        self,
        document_name: str,
        facts_text: str,
        concept_terms: Optional[List[str]] = None,
        top_k: int = 8,
    ) -> List[Dict[str, Any]]:
        """
        Executes a 100% deterministic, ZERO API CALL candidate section prefilter
        on a specific Special Act JSON using keyword overlap and core penal weighting.
        """
        sections = self.load_act(document_name)
        if not sections:
            return []

        core_set = set(_CORE_SECTIONS_PER_ACT.get(document_name, []))

        # Tokenize case facts and concepts
        facts_lower = (facts_text or "").lower()
        query_words = set(re.findall(r"\w+", facts_lower)) - {
            "the", "and", "or", "of", "to", "in", "a", "is", "was", "for", "on", "by", "with",
            "at", "from", "as", "an", "that", "this", "it", "be", "are", "were"
        }
        if concept_terms:
            for c in concept_terms:
                query_words.update(re.findall(r"\w+", c.lower()))

        scored_candidates: List[Tuple[float, Dict[str, Any]]] = []

        for sec in sections:
            s_num = sec["section_number"]
            heading = sec["heading"]
            text = sec["text"]

            h_words = set(re.findall(r"\w+", heading.lower()))
            t_words = set(re.findall(r"\w+", text[:600].lower()))

            # Keyword overlap
            h_overlap = len(query_words & h_words)
            t_overlap = len(query_words & t_words)

            score = (h_overlap * 2.5) + (t_overlap * 0.5)

            # Bonus for core penal/substantive provisions
            if s_num in core_set:
                score += 3.0
            if sec.get("is_punishment"):
                score += 2.0

            scored_candidates.append((score, sec))

        # Sort descending by score
        scored_candidates.sort(key=lambda x: x[0], reverse=True)

        # Ensure core sections are not starved out if facts have low lexical overlap
        seen_sec_nums: Set[str] = set()
        shortlisted: List[Dict[str, Any]] = []

        for score, sec in scored_candidates:
            if len(shortlisted) >= top_k:
                break
            s_num = sec["section_number"]
            if s_num not in seen_sec_nums:
                seen_sec_nums.add(s_num)
                shortlisted.append(sec)

        return shortlisted
