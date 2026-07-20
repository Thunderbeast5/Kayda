"""
citation_extractor.py — Extracts and parses Indian legal citations
"""
import re
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import CITATION_PATTERNS
from utils.date_utils import extract_year
from utils.text_utils import normalize_whitespace


CASE_NAME_PATTERN = re.compile(
    r'([A-Z][a-zA-Z\s\.]+(?:vs?\.?|v/s|versus)\s+[A-Z][a-zA-Z\s\.]+)',
    re.IGNORECASE
)


def extract_citations(paragraphs: list[dict], case_id: str) -> list[dict]:
    citations = []
    cit_id = 1
    seen = set()

    for para in paragraphs:
        text = para["paragraph_text"]
        page = para["page_number"]
        para_id = para["paragraph_id"]

        # Extract citation strings
        for pattern in CITATION_PATTERNS:
            for m in re.finditer(pattern, text, re.IGNORECASE):
                citation_str = normalize_whitespace(m.group())
                if citation_str in seen:
                    continue
                seen.add(citation_str)

                # Try to find case name near citation
                start = max(0, m.start() - 150)
                context_text = text[start:m.end() + 50]
                case_match = CASE_NAME_PATTERN.search(context_text)
                cited_case = normalize_whitespace(case_match.group()) if case_match else "Unknown"

                year = extract_year(citation_str)
                citations.append({
                    "citation_id":               f"CIT{cit_id:04d}",
                    "case_id":                   case_id,
                    "cited_case":                cited_case,
                    "short_name":                _make_short_name(cited_case),
                    "citation":                  citation_str,
                    "court":                     _detect_court(citation_str),
                    "year":                      year,
                    "why_cited":                 _infer_why_cited(context_text),
                    "paragraph":                 para_id,
                    "page":                      page,
                    "is_precedent":              True,
                    "is_referred":               True,
                    "is_distinguished":          _contains(context_text, ["distinguished", "distinguish"]),
                    "is_overruled":              _contains(context_text, ["overruled", "overrule"]),
                    "legal_principle_extracted": _extract_principle_near(context_text),
                    "relevance_score":           0.8,
                })
                cit_id += 1

    return citations


def _make_short_name(case_name: str) -> str:
    if not case_name or case_name == "Unknown":
        return ""
    parts = re.split(r'\s+vs?\.?\s+|\s+versus\s+', case_name, flags=re.IGNORECASE)
    return parts[0].strip()[:40] if parts else case_name[:40]


def _detect_court(citation: str) -> str:
    if re.search(r'\bSC\b|Supreme Court|SCR|SCC', citation, re.IGNORECASE):
        return "Supreme Court of India"
    if re.search(r'\bHC\b|High Court', citation, re.IGNORECASE):
        return "High Court"
    return "Unknown"


def _infer_why_cited(context: str) -> str:
    c = context.lower()
    if any(w in c for w in ["followed", "relied upon", "applied"]):
        return "Followed as precedent"
    if any(w in c for w in ["distinguished"]):
        return "Distinguished"
    if any(w in c for w in ["overruled"]):
        return "Overruled"
    if any(w in c for w in ["referred", "cited"]):
        return "Referred"
    return "Cited"


def _contains(text: str, keywords: list[str]) -> bool:
    t = text.lower()
    return any(kw in t for kw in keywords)


def _extract_principle_near(context: str) -> str:
    sentences = re.split(r'(?<=[.!?])\s+', context)
    for s in sentences:
        if any(w in s.lower() for w in ["held", "principle", "laid down", "established", "rule"]):
            return normalize_whitespace(s)[:200]
    return ""
