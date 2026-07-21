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

    # Additional OCR errors found in scanned Indian SC PDFs
    (r"\bf'ower\b",         'power'),
    (r"\bf'owers\b",        'powers'),
    (r'\bnonns\b',          'norms'),
    (r'\bphces\b',          'places'),
    (r'\bphce\b',           'place'),
    (r'\bshcmld\b',         'should'),
    (r'\btJi,ere\b',        'there'),
    (r'\btJiere\b',         'there'),
    (r'\bscheine\b',        'scheme'),
    (r'\bconstitutio\b',    'constitution'),
    (r'\bconstitu\s+tion\b','constitution'),
    (r'\blegisla\s+tion\b', 'legislation'),
    (r'\bprovi\s+sion\b',   'provision'),
    (r'\bfunda\s+mental\b', 'fundamental'),
    (r'\bharas\s+sment\b',  'harassment'),
    (r'\bemploy\s+ment\b',  'employment'),
    (r'\bwork\s+place\b',   'workplace'),
    (r'\bwork\s+places\b',  'workplaces'),
    (r'\binterna\s+tional\b','international'),
    (r'\bconven\s+tion\b',  'convention'),
    (r'\b/ife\b',           'life'),
    (r'\b/iberty\b',        'liberty'),
    (r'\b/aw\b',            'law'),
    (r'\bATticle\b',        'Article'),
    (r'\bAT\s+ticle\b',     'Article'),
    (r'\bbein[g~]\b',       'being'),
    (r'\bsig\s+nificance\b','significance'),
    (r'\bvio\s+lation\b',   'violation'),
    (r'\bimple\s+menting\b','implementing'),
    (r'\bconcomit\s+ant\b', 'concomitant'),
    (r'\b~he\b',            'the'),
    (r'\bTh~\b',            'The'),
    (r'\b[Hh]eld,\b',       'Held,'),

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

    # ── Remove SCC column/margin markers (A B C ... H on their own or inline) ──
    # Pattern: capital letter A-H surrounded by spaces or at line boundaries
    # These are SCC law report marginal line markers, e.g. "...working women A results..."
    text = re.sub(r'(?<=[a-z,\.;])\s+[A-H]\s+(?=[A-Z])', ' ', text)  # mid-sentence markers
    text = re.sub(r'\s+[A-H]\s*$', '', text, flags=re.MULTILINE)       # end-of-line markers
    text = re.sub(r'^\s*[A-H]\s+(?=[A-Z])', '', text, flags=re.MULTILINE)  # start-of-line

    # Fix broken words with stray spaces inside: "Ar ticle" → "Article"
    text = re.sub(r'\bAr\s+ticle\b', 'Article', text, flags=re.IGNORECASE)
    text = re.sub(r'\bSe\s+ction\b', 'Section', text, flags=re.IGNORECASE)
    text = re.sub(r'\bJus\s+tice\b', 'Justice', text, flags=re.IGNORECASE)
    text = re.sub(r'\bim\s+plementing\b', 'implementing', text, flags=re.IGNORECASE)
    text = re.sub(r'\bab\s+sence\b', 'absence', text, flags=re.IGNORECASE)
    text = re.sub(r'\binter\s+national\b', 'international', text, flags=re.IGNORECASE)
    text = re.sub(r'\blin[Hh]\s*guistic\b', 'linguistic', text, flags=re.IGNORECASE)
    text = re.sub(r'\ban\.d\b', 'and', text)
    text = re.sub(r'\bo~\b', 'of', text)
    text = re.sub(r'\bbein~\b', 'beings', text)
    text = re.sub(r'\bprac-\s*\n\s*tices\b', 'practices', text)
    text = re.sub(r'The\s*,e\s+nforcement', 'The enforcement', text)

    # Fix Article number OCR errors
    # "Article 5 lA" / "5 lA" → "Article 51A" (lowercase l misread as 1, space inserted)
    text = re.sub(r'\bArticle\s+5\s+[lI]A\b', 'Article 51A', text)
    text = re.sub(r'\b5\s+[lI]A\b(?!\s*\d)', 'Article 51A', text)
    # "5 I. Promotion" → "51. Promotion"
    text = re.sub(r'\b5\s+I\.\s+Promotion', '51. Promotion', text)
    # "JS. Prohibition" → "15. Prohibition" (J=1, S=5)
    text = re.sub(r'\bJS\.\s+Prohibition', '15. Prohibition', text)
    # CTI → CJI (common OCR error in SC judgments)
    text = re.sub(r'\bCTI\b', 'CJI', text)
    text = re.sub(r'\bCTI\.\b', 'CJI.', text)
    text = re.sub(r'\bC\.T\.I\.\b', 'C.J.I.', text)
    # "/ife" → "life", "/iberty" → "liberty" (l misread as /)
    text = re.sub(r'\b/ife\b', 'life', text)
    text = re.sub(r'\b/iberty\b', 'liberty', text)
    text = re.sub(r'\b/aw\b', 'law', text)
    # "ofsexual" → "of sexual" (missing space)
    text = re.sub(r'\bof(sexual|working|women)\b', r'of \1', text, flags=re.IGNORECASE)
    # "rdief" → "relief"
    text = re.sub(r'\brdief\b', 'relief', text, flags=re.IGNORECASE)
    # "religfon" → "religion"
    text = re.sub(r'\breligfon\b', 'religion', text, flags=re.IGNORECASE)
    # "The filed" → "The field"  (d/d+l confusion)
    text = re.sub(r'\bthe\s+filed\b', 'the field', text, flags=re.IGNORECASE)
    # Bracket normalisation: [4 10-E] → [410-E]
    text = re.sub(r'\[4\s+10-([A-Z])\]', r'[410-\1]', text)
    text = re.sub(r'\[4\s+10-f?C[JI]?\]', '[410-C]', text)
    # Middle dot to hyphen in citations: [407·A] → [407-A]
    text = re.sub(r'\[(\d+)[·•]([A-Z])\]', r'[\1-\2]', text)
    # Curly brace to parenthesis: C 2{d) → 2(d)
    text = re.sub(r'\{([a-z])\)', r'(\1)', text)
    # "A_s" → "As"
    text = re.sub(r'\bA_s\b', 'As', text)
    # "mater nity" → "maternity"
    text = re.sub(r'\bmater\s+nity\b', 'maternity', text, flags=re.IGNORECASE)
    # Remove lone special characters on their own lines
    text = re.sub(r'^\s*[|\\/_~*#@$%^&]{1,3}\s*$', '', text, flags=re.MULTILINE)
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
