"""
entity_extractor.py — Legal NER with correct entity classification
Fixes: VISHAKA→Case_Name, RAJASTHAN→Location, ORS→skip, JJ→skip
"""
import re
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.text_utils import normalize_whitespace

# ── Known Indian states and UTs (for Location classification) ─────────────────
INDIAN_STATES = {
    "rajasthan", "maharashtra", "gujarat", "punjab", "haryana", "kerala",
    "karnataka", "tamilnadu", "tamil nadu", "andhra pradesh", "telangana",
    "uttar pradesh", "madhya pradesh", "bihar", "jharkhand", "odisha",
    "west bengal", "assam", "delhi", "goa", "himachal pradesh",
    "uttarakhand", "chhattisgarh", "manipur", "meghalaya", "mizoram",
    "nagaland", "sikkim", "tripura", "arunachal pradesh", "jammu",
    "kashmir", "ladakh", "chandigarh", "puducherry",
}

# ── Words that spaCy misclassifies — block list ────────────────────────────────
SKIP_ENTITIES = {
    "ors", "anr", "jj", "cji", "j.", "j.j.", "viz", "etc",
    "supra", "infra", "ibid", "id", "pp", "pg", "no",
    "sc", "hc", "air", "scc", "scr",
}

# ── Case-name indicators ───────────────────────────────────────────────────────
CASE_NAME_PATTERN = re.compile(
    r'([A-Z][A-Za-z\s\.&]+(?:\s+(?:vs?\.?|versus|v/s)\s+)[A-Z][A-Za-z\s\.&]+)',
    re.IGNORECASE
)

ACT_PATTERNS = [
    r'([\w\s]+Act,?\s*\d{4})',
    r'([\w\s]+Code,?\s*\d{4})',
    r'([\w\s]+Rules?,?\s*\d{4})',
    r'(Constitution of India)',
]

COURT_PATTERNS = [
    r'(Supreme Court of India)',
    r'(High Court of [\w\s]+)',
    r'(District Court)',
    r'(Sessions Court)',
    r'(Family Court)',
    r'(Magistrate(?:\'s)? Court)',
]

CONVENTION_PATTERNS = [
    r'(CEDAW)',
    r'(UDHR)',
    r'(ICCPR)',
    r'(Convention on[\w\s,]+)',
    r'(International[\w\s]+Convention)',
    r'(United Nations[\w\s]+Convention)',
    r'(Beijing\s+Statement)',
    r'(Universal\s+Declaration)',
]

COMMITTEE_PATTERNS = [
    r'(Complaints?\s+Committee)',
    r'(Internal\s+Complaints?\s+Committee)',
    r'(National\s+Commission[\w\s]*)',
    r'(State\s+Commission[\w\s]*)',
    r'(Human\s+Rights\s+Commission)',
]

# spaCy label → our type, with post-processing corrections
SPACY_LABEL_MAP = {
    "PERSON": "Person",
    "ORG":    "Organization",
    "GPE":    "Location",       # will be verified against state list
    "DATE":   "Date",
    "LAW":    "Act",
    "FAC":    "Organization",
    "EVENT":  "Concept",
    "NORP":   "Concept",        # nationalities/religions
}


def extract_entities(paragraphs: list[dict], case_id: str,
                     use_spacy: bool = True) -> list[dict]:
    entities = []

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

        # 1. Rule-based (high confidence, always run)
        entities.extend(_extract_rule_based(text, page, para_id, case_id))

        # 2. spaCy with post-correction
        if spacy_nlp:
            entities.extend(_extract_spacy(text, page, para_id, case_id, spacy_nlp))

    # Deduplicate by (entity text, entity_type, paragraph)
    seen = set()
    unique = []
    for e in entities:
        key = (e["entity"].lower(), e["entity_type"], e["paragraph"])
        if key not in seen:
            seen.add(key)
            unique.append(e)

    # Assign sequential IDs
    for i, e in enumerate(unique):
        e["entity_id"] = f"ENT{i+1:05d}"

    return unique


def _ctx(text: str, start: int, end: int, window: int = 60) -> str:
    return normalize_whitespace(text[max(0, start - window): end + window])


def _extract_rule_based(text: str, page: int, para_id: str, case_id: str) -> list[dict]:
    ents = []

    # Case names (highest priority — before person/org)
    for m in CASE_NAME_PATTERN.finditer(text):
        name = normalize_whitespace(m.group())
        if len(name) > 10 and len(name.split()) >= 3:
            ents.append(_ent(name, "Case_Name", page, para_id,
                             _ctx(text, m.start(), m.end()), m.start(), m.end(), 0.92))

    # Acts / statutes
    for pat in ACT_PATTERNS:
        for m in re.finditer(pat, text, re.IGNORECASE):
            val = normalize_whitespace(m.group(1))
            if len(val) > 5:
                ents.append(_ent(val, "Act", page, para_id,
                                 _ctx(text, m.start(), m.end()), m.start(), m.end(), 0.93))

    # Constitutional Articles
    for m in re.finditer(r'Articles?\s+(\d+[A-Z]?(?:\(\d+\))?(?:\([a-z]\))?)', text, re.IGNORECASE):
        ents.append(_ent(m.group(), "Article", page, para_id,
                         _ctx(text, m.start(), m.end()), m.start(), m.end(), 0.97))

    # Sections
    for m in re.finditer(r'[Ss]ections?\s+\d+[A-Z]?(?:\(\d+\))?(?:\([a-z]\))?', text):
        ents.append(_ent(m.group(), "Section", page, para_id,
                         _ctx(text, m.start(), m.end()), m.start(), m.end(), 0.92))

    # Courts
    for pat in COURT_PATTERNS:
        for m in re.finditer(pat, text, re.IGNORECASE):
            ents.append(_ent(m.group(1), "Court", page, para_id,
                             _ctx(text, m.start(), m.end()), m.start(), m.end(), 0.95))

    # Conventions
    for pat in CONVENTION_PATTERNS:
        for m in re.finditer(pat, text, re.IGNORECASE):
            val = normalize_whitespace(m.group(1))
            if len(val) > 3:
                ents.append(_ent(val, "Convention", page, para_id,
                                 _ctx(text, m.start(), m.end()), m.start(), m.end(), 0.90))

    # Committees / Commissions
    for pat in COMMITTEE_PATTERNS:
        for m in re.finditer(pat, text, re.IGNORECASE):
            ents.append(_ent(m.group(1), "Committee", page, para_id,
                             _ctx(text, m.start(), m.end()), m.start(), m.end(), 0.88))

    # Judges (Justice X. Y.)
    for m in re.finditer(r'(?:Justice|Hon\'?ble)\s+([A-Z][a-z]+(?:\s+[A-Z]\.?\s*[A-Z]?[a-z]*)+)', text):
        ents.append(_ent(m.group(), "Person", page, para_id,
                         _ctx(text, m.start(), m.end()), m.start(), m.end(), 0.90))

    # Indian states → Location
    for state in INDIAN_STATES:
        for m in re.finditer(r'\b' + re.escape(state) + r'\b', text, re.IGNORECASE):
            ents.append(_ent(m.group().title(), "Location", page, para_id,
                             _ctx(text, m.start(), m.end()), m.start(), m.end(), 0.88))

    # Citations
    for m in re.finditer(r'\(\d{4}\)\s+\d+\s+SCC\s+\d+|AIR\s+\d{4}\s+SC\s+\d+', text):
        ents.append(_ent(m.group(), "Citation", page, para_id,
                         _ctx(text, m.start(), m.end()), m.start(), m.end(), 0.95))

    return ents


def _extract_spacy(text: str, page: int, para_id: str, case_id: str, nlp) -> list[dict]:
    ents = []
    try:
        doc = nlp(text[:500000])
    except Exception:
        return ents

    for ent in doc.ents:
        raw = ent.text.strip()
        raw_lower = raw.lower().replace(".", "").replace(" ", "")

        # Skip junk tokens
        if raw_lower in SKIP_ENTITIES:
            continue
        if len(raw) < 2:
            continue
        if re.fullmatch(r'[\d\s\.\-,]+', raw):
            continue

        mapped = SPACY_LABEL_MAP.get(ent.label_)
        if not mapped:
            continue

        # Post-correction: GPE → check if it's an Indian state
        if ent.label_ == "GPE":
            mapped = "Location"

        # Post-correction: ORG → check if it's actually a case name
        if ent.label_ == "ORG":
            if re.search(r'\bvs?\.\b|\bversus\b', raw, re.IGNORECASE):
                mapped = "Case_Name"
            elif raw.upper() == raw and len(raw.split()) == 1:
                # All-caps single word — check known conventions first
                known_conventions = {"CEDAW", "UDHR", "ICCPR", "ILO", "WHO", "UN", "UNESCO"}
                if raw.upper() in known_conventions:
                    mapped = "Convention"
                else:
                    mapped = "Case_Name"

        # Post-correction: PERSON → check it's not a location
        if ent.label_ == "PERSON":
            if raw.lower() in INDIAN_STATES:
                mapped = "Location"

        ents.append(_ent(
            normalize_whitespace(raw), mapped, page, para_id,
            text[max(0, ent.start_char - 50): ent.end_char + 50],
            ent.start_char, ent.end_char,
            0.72  # lower confidence for spaCy — rule-based takes priority
        ))

    return ents


def _ent(entity: str, etype: str, page: int, para_id: str,
         context: str, start: int, end: int, confidence: float) -> dict:
    return {
        "entity_id":       "",
        "entity":          normalize_whitespace(entity),
        "entity_type":     etype,
        "page":            page,
        "paragraph":       para_id,
        "context":         normalize_whitespace(context)[:300],
        "confidence":      round(confidence, 2),
        "position_start":  start,
        "position_end":    end,
        "normalized_form": normalize_whitespace(entity).title(),
    }
