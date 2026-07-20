"""
section_classifier.py — Act and section reference extractor
"""
import re
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.text_utils import normalize_whitespace


def extract_acts_sections(paragraphs: list[dict], case_id: str) -> list[dict]:
    records = []
    rec_id = 1

    for para in paragraphs:
        text = para["paragraph_text"]
        page = para["page_number"]
        para_id = para["paragraph_id"]

        # Pattern: Section X of Act Y
        for m in re.finditer(
            r'[Ss]ections?\s+(\d+[A-Z]?)(?:\((\d+)\))?(?:\(([a-z])\))?\s+of\s+([\w\s]+?Act[\w\s,]*?\d{4})',
            text
        ):
            start = max(0, m.start() - 80)
            context = normalize_whitespace(text[start: m.end() + 120])

            records.append({
                "act_section_id":       f"AS{rec_id:04d}",
                "case_id":              case_id,
                "act_name":             normalize_whitespace(m.group(4)),
                "act_short_name":       _make_short_act_name(m.group(4)),
                "section":              m.group(1),
                "subsection":           m.group(2) or "",
                "clause":               m.group(3) or "",
                "purpose":              _infer_purpose(context),
                "context":              context,
                "page":                 page,
                "paragraph":            para_id,
                "is_cited":             True,
                "is_interpreted":       _is_interpreted(context),
                "interpretation_given": _extract_interpretation(context),
            })
            rec_id += 1

    return records


def _make_short_act_name(act_name: str) -> str:
    words = act_name.strip().split()
    initials = [w[0].upper() for w in words if w[0].isupper()]
    return "".join(initials) if initials else act_name[:10]


def _infer_purpose(context: str) -> str:
    c = context.lower()
    if "defines" in c or "definition" in c:
        return "Definition"
    if "punish" in c or "penalty" in c:
        return "Penal provision"
    if "procedur" in c:
        return "Procedural"
    if "interprete" in c:
        return "Interpretation"
    return "Reference"


def _is_interpreted(context: str) -> bool:
    return bool(re.search(r'\bmeans\b|\binterpreted?\b|\bconstrued?\b|\bheld\b',
                          context, re.IGNORECASE))


def _extract_interpretation(context: str) -> str:
    sentences = re.split(r'(?<=[.!?])\s+', context)
    for s in sentences:
        if any(w in s.lower() for w in ["means", "interpreted", "construed", "held", "signifies"]):
            return normalize_whitespace(s)[:250]
    return ""
