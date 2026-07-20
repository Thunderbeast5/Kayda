"""
guideline_extractor.py — Extracts structured guidelines/directions from judgments
"""
import re
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.text_utils import normalize_whitespace


GUIDELINE_TRIGGERS = [
    r'(?:the following|these) guidelines',
    r'shall be followed',
    r'hereby directs?',
    r'it is directed',
    r'mandatory.*?requirement',
    r'employer shall',
    r'complaints? committee',
    r'guidelines? (?:are|is|shall)',
]


def extract_guidelines(paragraphs: list[dict], case_id: str) -> list[dict]:
    guidelines = []
    gl_id = 1
    in_guideline_block = False
    current_gl = None

    for para in paragraphs:
        text = para["paragraph_text"]
        page = para["page_number"]
        para_id = para["paragraph_id"]

        # Detect start of guideline block
        if any(re.search(p, text, re.IGNORECASE) for p in GUIDELINE_TRIGGERS):
            in_guideline_block = True

        if in_guideline_block and _is_guideline_item(text):
            num = _extract_guideline_number(text)
            title = _extract_guideline_title(text)
            sub_gl = _extract_sub_guidelines(text)

            guidelines.append({
                "guideline_id":    f"GL{gl_id:04d}",
                "case_id":         case_id,
                "guideline_number": num or gl_id,
                "title":           title,
                "full_text":       normalize_whitespace(text),
                "purpose":         _infer_purpose(text),
                "sub_guidelines":  sub_gl,
                "page_start":      page,
                "page_end":        page,
                "applicability":   _infer_applicability(text),
                "implementation":  _infer_implementation(text),
                "is_binding":      _is_binding(text),
                "is_mandatory":    _is_mandatory(text),
                "effective_from":  "",
            })
            gl_id += 1

        # End of guideline block detection
        if in_guideline_block and _is_end_of_guidelines(text):
            in_guideline_block = False

    return guidelines


def _is_guideline_item(text: str) -> bool:
    t = text.strip()
    return bool(
        re.match(r'^\d+[\.\)]\s+', t) or
        re.match(r'^[ivxIVX]+[\.\)]\s+', t) or
        any(w in t.lower() for w in ["shall", "must", "required", "mandatory", "directive"])
    )


def _extract_guideline_number(text: str) -> str | None:
    m = re.match(r'^(\d+)[\.\)]\s+', text.strip())
    return m.group(1) if m else None


def _extract_guideline_title(text: str) -> str:
    first_sentence = re.split(r'(?<=[.!?])\s+', text)[0]
    return normalize_whitespace(first_sentence)[:150]


def _extract_sub_guidelines(text: str) -> list[str]:
    sub = re.findall(r'[a-z][\.\)]\s+[A-Z][^.]+\.', text)
    return [normalize_whitespace(s) for s in sub]


def _infer_purpose(text: str) -> str:
    if "prevent" in text.lower():
        return "Prevention"
    if "redress" in text.lower() or "remedy" in text.lower():
        return "Redressal"
    if "committee" in text.lower():
        return "Institutional mechanism"
    return "Compliance"


def _infer_applicability(text: str) -> str:
    c = text.lower()
    if "employer" in c:
        return "Employer / Organization"
    if "state" in c or "government" in c:
        return "State Government"
    if "all" in c:
        return "All workplaces"
    return "All parties"


def _infer_implementation(text: str) -> str:
    sentences = re.split(r'(?<=[.!?])\s+', text)
    for s in sentences:
        if "shall" in s.lower() or "must" in s.lower():
            return normalize_whitespace(s)[:200]
    return ""


def _is_binding(text: str) -> bool:
    return bool(re.search(r'\bshall\b|\bhereby\b|\bdirects?\b', text, re.IGNORECASE))


def _is_mandatory(text: str) -> bool:
    return bool(re.search(r'\bmust\b|\bshall\b|\bmandatory\b|\bcompulsory\b', text, re.IGNORECASE))


def _is_end_of_guidelines(text: str) -> bool:
    return bool(re.search(r'the above guidelines|these guidelines.*?force of law|'
                          r'above directions.*?legislative provisions', text, re.IGNORECASE))
