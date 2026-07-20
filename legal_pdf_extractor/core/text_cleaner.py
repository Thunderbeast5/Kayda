"""
text_cleaner.py — Intelligent text cleaning for legal documents
Fixes: OCR artifacts, spacing, encoding, page artifacts
"""
import re
from utils.text_utils import clean_text, remove_page_artifacts

# ── Comprehensive OCR correction map for Indian SC judgments ──────────────────
OCR_CORRECTIONS = [
    # Garbled "Article" variants — most common OCR failure
    (r'\bArlie/es\b',       'Articles'),
    (r'\bArtiele[s]?\b',    'Articles'),
    (r'\bArt1cle[s]?\b',    'Articles'),
    (r'\bArtlcle[s]?\b',    'Articles'),
    (r'\bArtiele\b',        'Article'),
    (r'\bArt\.?\s*1\b',     'Art. I'),

    # Garbled "Section"
    (r'\bSect1on[s]?\b',    'Sections'),
    (r'\bSect\.?\s*1on\b',  'Section'),

    # Court / Justice
    (r'\bJust1ce\b',        'Justice'),
    (r'\bC0urt\b',          'Court'),
    (r'\bCourt\b',          'Court'),           # normalise already correct
    (r'\bSupreme\s+Coult\b','Supreme Court'),
    (r'\bCh1ef\b',          'Chief'),

    # Common legal words
    (r'\b1aw\b',            'law'),
    (r'\b1egal\b',          'legal'),
    (r'\brem[e3]dy\b',      'remedy'),
    (r'\brem[e3]d[yi]\b',   'remedy'),
    (r'\bremecty\b',        'remedy'),
    (r'\bsafegu[a@]rds?\b', 'safeguards'),
    (r'\bsafegnards?\b',    'safeguards'),
    (r'\bvacum\b',          'vacuum'),
    (r'\bworkero\b',        'workers'),
    (r'\bw0rkers\b',        'workers'),
    (r'\bfodependence\b',   'independence'),
    (r'\bindep[e3]nd[e3]nce\b', 'independence'),
    (r'\bdet[e3][!i]?\s*rm[i1]ned\b', 'determined'),
    (r'\bdete[!]\s*mined\b','determined'),
    (r'\bdet[e3]!\s*mined\b','determined'),
    (r'\bse[xX][:\s]*ually\b', 'sexually'),
    (r'\bseX:ually\b',      'sexually'),
    (r'\bh[a@]r[a@]ssment\b','harassment'),
    (r'\bpet1tioner\b',     'petitioner'),
    (r'\brespond[e3]nt[s]?\b','respondents'),
    (r'\bpetit10ner\b',     'petitioner'),
    (r'\bjudgm[e3]nt\b',    'judgment'),
    (r'\bconst1tut1on\b',   'constitution'),
    (r'\bfundament[a@]l\b', 'fundamental'),
    (r'\bequ[a@]l1ty\b',    'equality'),
    (r'\bl1berty\b',        'liberty'),
    (r'\bengagem[e3]nt\b',  'engagement'),
    (r'\bemploym[e3]nt\b',  'employment'),
    (r'\bw0rkplace\b',      'workplace'),
    (r'\bguid[e3]l1ne[s]?\b','guidelines'),
    (r'\bv10lat[e3]s?\b',   'violates'),
    (r'\bv10lat10n\b',      'violation'),
    (r'\bpr0tect10n\b',     'protection'),
    (r'\bpr0v1s10n[s]?\b',  'provisions'),
    (r'\bconv[e3]nt10n\b',  'convention'),
    (r'\bint[e3]rnat10nal\b','international'),
    (r'\bconst1tut10nal\b', 'constitutional'),

    # Digit/letter confusion
    (r'\b0f\b',             'of'),
    (r'\b[Ii]n[Ii]t1al\b',  'initial'),
    (r'\bTh[e3]\b',         'The'),
    (r'\b[Ii]t [Ii][s5]\b', 'It is'),

    # Quote normalisation
    (r'[''`]',              "'"),
    (r'["""]',              '"'),
    (r'\u2018|\u2019',      "'"),
    (r'\u201c|\u201d',      '"'),
]


def clean_page(text: str) -> str:
    """Full cleaning pipeline for a single page."""
    text = clean_text(text)
    text = remove_page_artifacts(text)
    text = _fix_ocr_artifacts(text)
    text = _fix_spacing(text)
    return text


def _fix_ocr_artifacts(text: str) -> str:
    for pattern, replacement in OCR_CORRECTIONS:
        try:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        except re.error:
            pass
    # Remove lone junk lines (single chars, only symbols)
    text = re.sub(r'^\s*[|\\/_~*#@$%^&]{1,3}\s*$', '', text, flags=re.MULTILINE)
    # Fix broken words with stray spaces inside: "Ar ticle" → "Article"
    text = re.sub(r'\bAr\s+ticle\b', 'Article', text, flags=re.IGNORECASE)
    text = re.sub(r'\bSe\s+ction\b', 'Section', text, flags=re.IGNORECASE)
    text = re.sub(r'\bJus\s+tice\b', 'Justice', text, flags=re.IGNORECASE)
    return text


def _fix_spacing(text: str) -> str:
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def clean_all_pages(pages: list[dict]) -> list[dict]:
    for p in pages:
        p["text"] = clean_page(p["text"])
    return pages


def merge_pages_to_text(pages: list[dict]) -> str:
    return "\n\n".join(p["text"] for p in pages if p["text"].strip())
