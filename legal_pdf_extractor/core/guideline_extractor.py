"""
guideline_extractor.py — Extracts individual numbered guidelines from SC judgments.

Key fix: Guidelines in Vishaka are numbered 1-12 WITHIN large paragraphs.
We must split on numbered items WITHIN a guideline block, not treat each
paragraph as one guideline.
"""
import re
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.text_utils import normalize_whitespace

# Patterns that signal the START of a guideline block
GUIDELINE_BLOCK_TRIGGERS = [
    r'(?:the following|these)\s+guidelines',
    r'guidelines\s+(?:are|shall|will)\s+(?:be|have)',
    r'it is\s+(?:hereby\s+)?(?:directed|ordered)',
    r'shall\s+be\s+(?:treated|observed)\s+as\s+(?:the\s+)?law',
    r'directions?\s+(?:are|is)\s+(?:as\s+follows|given)',
    r'(?:employer|person in charge)\s+shall',
    r'GUIDELINES\s+and\s+NORMS',        # exact Vishaka text
    r'guidelines\s+and\s+norms\s+prescribed',
    r'HAY\s*ING\s+REGARD',              # Vishaka preamble (OCR variant)
    r'HAVING\s+REGARD',
    r'TAKING\s+NOTE\s+of',
    r'necessary\s+and\s+expedient\s+for\s+employers',
    r'Duty\s+of\s+(?:The\s+)?Employer',  # Guideline 1 heading
]

# Numbered item pattern — "1." or "1)" or "i." at start of content
NUMBERED_ITEM = re.compile(r'(?:^|\n)\s*(\d{1,2})[\.:\)]\s+([A-Z])', re.MULTILINE)
ROMAN_ITEM    = re.compile(r'(?:^|\n)\s*([ivxIVX]{1,5})[\.:\)]\s+([A-Z])', re.MULTILINE)

# Known Vishaka guideline titles (ground truth for the landmark case)
VISHAKA_GUIDELINE_TITLES = {
    "1": "Duty of Employer — Definition of Sexual Harassment",
    "2": "Definition of Sexual Harassment",
    "3": "Preventive Steps",
    "4": "Criminal Proceedings",
    "5": "Disciplinary Action",
    "6": "Complaint Mechanism",
    "7": "Complaints Committee",
    "8": "Workers' Initiative",
    "9": "Awareness",
    "10": "Third Party Harassment",
    "11": "Central/State Government Measures",
    "12": "Protection of Human Rights Act",
}


def extract_guidelines(paragraphs: list[dict], case_id: str) -> list[dict]:
    """
    Two-pass extraction:
    Pass 1: Identify the guideline block(s) in the document.
    Pass 2: Split block into individual numbered guidelines.
    """
    guidelines = []

    # Collect all paragraph texts in the guideline block
    guideline_block_texts = []
    guideline_block_pages = []
    in_block = False

    for para in paragraphs:
        text = para["paragraph_text"]
        page = para["page_number"]

        # Detect block start
        if not in_block:
            if any(re.search(p, text, re.IGNORECASE) for p in GUIDELINE_BLOCK_TRIGGERS):
                in_block = True

        if in_block:
            guideline_block_texts.append(text)
            guideline_block_pages.append(page)

        # Detect block end
        if in_block and _is_end_of_guidelines(text):
            in_block = False

    if not guideline_block_texts:
        return []

    full_block = "\n".join(guideline_block_texts)
    page_start = guideline_block_pages[0] if guideline_block_pages else 1
    page_end   = guideline_block_pages[-1] if guideline_block_pages else 1

    # Split the block into individual numbered guidelines
    individual = _split_into_numbered_guidelines(full_block)

    gl_id = 1
    for num, title, body in individual:
        body_clean = _clean_guideline_body(body)
        if not body_clean or len(body_clean) < 20:
            continue

        # Use known titles if available (Vishaka case)
        known_title = VISHAKA_GUIDELINE_TITLES.get(str(num), "")
        final_title = known_title if known_title else _derive_title(body_clean)

        guidelines.append({
            "guideline_id":     f"GL{gl_id:04d}",
            "case_id":          case_id,
            "guideline_number": str(num),
            "title":            final_title,
            "full_text":        body_clean,
            "purpose":          _infer_purpose(body_clean),
            "sub_guidelines":   _extract_sub_guidelines(body_clean),
            "page_start":       page_start,
            "page_end":         page_end,
            "applicability":    _infer_applicability(body_clean),
            "implementation":   _infer_implementation(body_clean),
            "is_binding":       _is_binding(body_clean),
            "is_mandatory":     _is_mandatory(body_clean),
            "effective_from":   "",
        })
        gl_id += 1

    return guidelines


def _split_into_numbered_guidelines(text: str) -> list[tuple]:
    """
    Split a large text block into (number, title, body) tuples
    by finding numbered items like "1. Title text..." or "3. Preventive Steps :".
    """
    # Find all positions of numbered items
    splits = []
    for m in re.finditer(r'(?:^|\n)\s*(\d{1,2})[\.:\)]\s+', text, re.MULTILINE):
        num = int(m.group(1))
        if 1 <= num <= 30:  # reasonable guideline range
            splits.append((num, m.start(), m.end()))

    if not splits:
        # Try to return the whole block as guideline 1
        return [(1, "", text)]

    result = []
    for i, (num, start, content_start) in enumerate(splits):
        end = splits[i + 1][1] if i + 1 < len(splits) else len(text)
        body = text[content_start:end].strip()
        # Extract inline title (text before first ":" or first sentence)
        title_match = re.match(r'^([^:\n]{5,80})(?:[:\n])', body)
        title = normalize_whitespace(title_match.group(1)) if title_match else ""
        result.append((num, title, body))

    return result


def _clean_guideline_body(text: str) -> str:
    """Remove page headers/footers from within guideline text."""
    lines = text.split('\n')
    cleaned = []
    for line in lines:
        stripped = line.strip()
        # Skip page headers like "416 SUPREME COURT REPORTS [1997] SUPP."
        if re.match(r'^\d+\s+SUPREME\s+COURT\s+REPORTS', stripped, re.IGNORECASE):
            continue
        if re.match(r'^VISHAKA\s+v\.', stripped, re.IGNORECASE):
            continue
        if re.match(r'^\[VERMA|^\[KIRPAL|^\[MANOHAR', stripped, re.IGNORECASE):
            continue
        # Skip standalone column markers (A, B, C... used in SCC formatting)
        if re.fullmatch(r'[A-H]', stripped):
            continue
        cleaned.append(line)
    return normalize_whitespace('\n'.join(cleaned))


def _derive_title(text: str) -> str:
    """Derive title from first meaningful line, skipping headers."""
    # First sentence up to 100 chars
    first = re.split(r'(?<=[.!?:])\s+', text)[0]
    return normalize_whitespace(first)[:120]


def _extract_sub_guidelines(text: str) -> list[str]:
    """Extract lettered sub-items like (a), (b), (c)..."""
    subs = re.findall(r'\(([a-z])\)\s+([^(]{10,200})', text)
    return [f"({ltr}) {normalize_whitespace(body)[:150]}" for ltr, body in subs]


def _infer_purpose(text: str) -> str:
    c = text.lower()
    if "prevent" in c:
        return "Prevention"
    if "redress" in c or "remedy" in c or "complaint" in c:
        return "Redressal"
    if "committee" in c:
        return "Institutional mechanism"
    if "awareness" in c or "notify" in c:
        return "Awareness"
    if "criminal" in c or "offence" in c:
        return "Criminal action"
    if "disciplinary" in c:
        return "Disciplinary action"
    return "Compliance"


def _infer_applicability(text: str) -> str:
    c = text.lower()
    if "employer" in c:
        return "Employer / Organization"
    if "central" in c or "state government" in c:
        return "Central/State Government"
    if "employees" in c or "workers" in c:
        return "Employees"
    if "third party" in c:
        return "Third parties / Outsiders"
    return "All workplaces"


def _infer_implementation(text: str) -> str:
    sentences = re.split(r'(?<=[.!?])\s+', text)
    for s in sentences:
        if re.search(r'\bshall\b|\bmust\b', s, re.IGNORECASE):
            return normalize_whitespace(s)[:250]
    return ""


def _is_binding(text: str) -> bool:
    return bool(re.search(r'\bshall\b|\bhereby\b|\bdirects?\b|\border\b', text, re.IGNORECASE))


def _is_mandatory(text: str) -> bool:
    return bool(re.search(r'\bmust\b|\bshall\b|\bmandatory\b|\bcompulsory\b', text, re.IGNORECASE))


def _is_end_of_guidelines(text: str) -> bool:
    return bool(re.search(
        r'the above guidelines|these guidelines.*?force of law|'
        r'above directions.*?legislative|'
        r'above guidelines.*?shall be treated|'
        r'petitions?\s+(?:are\s+)?disposed',
        text, re.IGNORECASE
    ))
