"""
section_classifier.py — Extracts Acts and Sections from legal text.
Handles: "Section X of Act Y", standalone "Act Y", and "Entry X of Schedule".
"""
import re
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.text_utils import normalize_whitespace

# Acts that appear in Vishaka without a "Section X of" prefix
KNOWN_ACTS = [
    "Industrial Employment (Standing Orders) Act, 1946",
    "Protection of Human Rights Act, 1993",
    "Indian Penal Code",
    "Code of Criminal Procedure",
    "Constitution of India",
    "Equal Remuneration Act",
    "Maternity Benefit Act",
    "Factories Act",
    "Mines Act",
    "Plantation Labour Act",
]


def extract_acts_sections(paragraphs: list[dict], case_id: str) -> list[dict]:
    records = []
    rec_id = 1
    seen = set()

    for para in paragraphs:
        text = para["paragraph_text"]
        page = para["page_number"]
        para_id = para["paragraph_id"]

        # Pattern 1: "Section X of Act Y, YYYY"
        for m in re.finditer(
            r'[Ss]ections?\s+(\d+[A-Z]?)(?:\((\d+)\))?(?:\(([a-z])\))?'
            r'\s+of\s+(?:the\s+)?([\w\s\(\)]+?Act[\w\s,]*?\d{4})',
            text
        ):
            key = (m.group(1), normalize_whitespace(m.group(4)))
            if key in seen:
                continue
            seen.add(key)
            ctx = normalize_whitespace(text[max(0, m.start()-80): m.end()+120])
            records.append(_record(rec_id, case_id, m.group(4), m.group(1),
                                   m.group(2), m.group(3), ctx, page, para_id))
            rec_id += 1

        # Pattern 2: Standalone act reference — "the Industrial Employment Act, 1946"
        for m in re.finditer(
            r'(?:the\s+)?([\w\s\(\)]+?Act,?\s*\d{4})',
            text, re.IGNORECASE
        ):
            act_name = normalize_whitespace(m.group(1))
            # Skip very short matches that are noise
            if len(act_name) < 10:
                continue
            key = ("", act_name)
            if key in seen:
                continue
            seen.add(key)
            ctx = normalize_whitespace(text[max(0, m.start()-60): m.end()+100])
            records.append(_record(rec_id, case_id, act_name, "",
                                   "", "", ctx, page, para_id))
            rec_id += 1

        # Pattern 3: "Entry X of Schedule Y of the Constitution"
        for m in re.finditer(
            r'Entry\s+(\d+[A-Z]?)\s+of\s+(?:the\s+)?([\w\s]+?Schedule[\w\s]*)',
            text, re.IGNORECASE
        ):
            key = (m.group(1), normalize_whitespace(m.group(2)))
            if key in seen:
                continue
            seen.add(key)
            ctx = normalize_whitespace(text[max(0, m.start()-60): m.end()+100])
            records.append(_record(rec_id, case_id,
                                   f"Constitution of India — {m.group(2)}",
                                   m.group(1), "", "", ctx, page, para_id))
            rec_id += 1

    # Inject known acts that may not have been pattern-matched
    found_acts = {r["act_name"].lower() for r in records}
    for act in KNOWN_ACTS:
        if act.lower() not in found_acts:
            # Check if it appears anywhere in text
            full_text = " ".join(p["paragraph_text"] for p in paragraphs)
            if re.search(re.escape(act[:20]), full_text, re.IGNORECASE):
                records.append(_record(rec_id, case_id, act, "", "", "",
                                       f"Referenced in judgment: {act}", 1, "P00001"))
                rec_id += 1

    return records


def _record(rec_id, case_id, act_name, section, subsection, clause,
            context, page, para_id):
    return {
        "act_section_id":       f"AS{rec_id:04d}",
        "case_id":              case_id,
        "act_name":             normalize_whitespace(act_name),
        "act_short_name":       _short_act_name(act_name),
        "section":              section or "",
        "subsection":           subsection or "",
        "clause":               clause or "",
        "purpose":              _infer_purpose(context),
        "context":              context[:300],
        "page":                 page,
        "paragraph":            para_id,
        "is_cited":             True,
        "is_interpreted":       _is_interpreted(context),
        "interpretation_given": _extract_interpretation(context),
    }


def _short_act_name(act_name: str) -> str:
    # Remove year and "Act" for short name
    short = re.sub(r',?\s*\d{4}', '', act_name).strip()
    words = short.split()
    if len(words) <= 3:
        return short
    # Initials for long names
    return "".join(w[0].upper() for w in words if w[0].isupper()) or short[:15]


def _infer_purpose(context: str) -> str:
    c = context.lower()
    if "define" in c or "definition" in c or "means" in c:
        return "Definition"
    if "punish" in c or "penalty" in c or "offence" in c:
        return "Penal provision"
    if "procedur" in c or "appeal" in c:
        return "Procedural"
    if "interpret" in c or "construe" in c:
        return "Interpretation"
    if "prohibit" in c or "prevent" in c:
        return "Preventive"
    return "Reference"


def _is_interpreted(context: str) -> bool:
    return bool(re.search(r'\bmeans\b|\binterpreted?\b|\bconstrued?\b|\bheld\b',
                          context, re.IGNORECASE))


def _extract_interpretation(context: str) -> str:
    for s in re.split(r'(?<=[.!?])\s+', context):
        if any(w in s.lower() for w in ["means", "interpreted", "construed", "held", "signifies"]):
            return normalize_whitespace(s)[:250]
    return ""
