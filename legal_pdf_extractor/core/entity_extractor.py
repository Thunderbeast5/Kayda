"""
entity_extractor.py — Legal NER: persons, organizations, acts, articles, dates
"""
import re
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.text_utils import normalize_whitespace

ENTITY_TYPES = [
    "Person", "Organization", "Location", "Date", "Act", "Article",
    "Section", "Citation", "Court", "Case_Name", "Legal_Principle",
    "Concept", "Convention", "Committee", "Commission", "Rule",
    "Notification", "Policy", "Guideline", "Term"
]

ACT_PATTERNS = [
    r'([\w\s]+Act,?\s*\d{4})',
    r'([\w\s]+Code,?\s*\d{4})',
    r'([\w\s]+Rules?,?\s*\d{4})',
    r'(Constitution of India)',
    r'(CEDAW|UDHR|ICCPR|International[\w\s]+Convention)',
]

COURT_PATTERNS = [
    r'(Supreme Court of India)',
    r'(High Court of [\w\s]+)',
    r'(District Court)',
    r'(Sessions Court)',
    r'(Magistrate Court)',
]


def extract_entities(paragraphs: list[dict], case_id: str,
                     use_spacy: bool = True) -> list[dict]:
    entities = []
    ent_id = 1

    spacy_nlp = None
    if use_spacy:
        try:
            import spacy
            spacy_nlp = spacy.load("en_core_web_sm")
        except Exception:
            spacy_nlp = None

    for para in paragraphs:
        text = para["paragraph_text"]
        page = para["page_number"]
        para_id = para["paragraph_id"]

        # Rule-based extraction
        rule_ents = _extract_rule_based(text, page, para_id, case_id)
        entities.extend(rule_ents)
        ent_id += len(rule_ents)

        # spaCy NER
        if spacy_nlp:
            spacy_ents = _extract_spacy(text, page, para_id, case_id, spacy_nlp, ent_id)
            entities.extend(spacy_ents)
            ent_id += len(spacy_ents)

    # Re-assign IDs
    for i, e in enumerate(entities):
        e["entity_id"] = f"ENT{i+1:05d}"

    return entities


def _get_context(text: str, start: int, end: int, window: int = 50) -> str:
    words = text.split()
    # approximate word positions
    s = max(0, start - window)
    e = min(len(text), end + window)
    return normalize_whitespace(text[s:e])


def _extract_rule_based(text: str, page: int, para_id: str, case_id: str) -> list[dict]:
    ents = []

    # Acts and statutes
    for pattern in ACT_PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            ents.append(_make_entity(
                m.group(1), "Act", page, para_id, case_id,
                _get_context(text, m.start(), m.end()),
                m.start(), m.end(), 0.9
            ))

    # Constitutional articles
    for m in re.finditer(r'Article[s]?\s+(\d+[A-Z]?(?:\(\d+\))?)', text, re.IGNORECASE):
        ents.append(_make_entity(
            m.group(), "Article", page, para_id, case_id,
            _get_context(text, m.start(), m.end()),
            m.start(), m.end(), 0.95
        ))

    # Sections
    for m in re.finditer(r'[Ss]ection\s+\d+[A-Z]?(?:\(\d+\))?(?:\([a-z]\))?', text):
        ents.append(_make_entity(
            m.group(), "Section", page, para_id, case_id,
            _get_context(text, m.start(), m.end()),
            m.start(), m.end(), 0.9
        ))

    # Courts
    for pattern in COURT_PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            ents.append(_make_entity(
                m.group(1), "Court", page, para_id, case_id,
                _get_context(text, m.start(), m.end()),
                m.start(), m.end(), 0.9
            ))

    # International conventions
    for m in re.finditer(r'(CEDAW|UDHR|ICCPR|UN\s+Convention[\w\s]+)', text, re.IGNORECASE):
        ents.append(_make_entity(
            m.group(), "Convention", page, para_id, case_id,
            _get_context(text, m.start(), m.end()),
            m.start(), m.end(), 0.85
        ))

    return ents


def _extract_spacy(text: str, page: int, para_id: str, case_id: str,
                   nlp, start_id: int) -> list[dict]:
    ents = []
    doc = nlp(text[:1000000])  # spaCy limit guard
    label_map = {
        "PERSON": "Person", "ORG": "Organization",
        "GPE": "Location", "DATE": "Date", "LAW": "Act",
        "FAC": "Organization", "EVENT": "Concept"
    }
    for ent in doc.ents:
        mapped = label_map.get(ent.label_)
        if mapped:
            ents.append(_make_entity(
                ent.text, mapped, page, para_id, case_id,
                text[max(0, ent.start_char-50): ent.end_char+50],
                ent.start_char, ent.end_char, 0.75
            ))
    return ents


def _make_entity(entity: str, etype: str, page: int, para_id: str,
                 case_id: str, context: str, start: int, end: int,
                 confidence: float) -> dict:
    return {
        "entity_id":       "",  # assigned later
        "entity":          normalize_whitespace(entity),
        "entity_type":     etype,
        "page":            page,
        "paragraph":       para_id,
        "context":         normalize_whitespace(context)[:300],
        "confidence":      confidence,
        "position_start":  start,
        "position_end":    end,
        "normalized_form": normalize_whitespace(entity).title(),
    }
