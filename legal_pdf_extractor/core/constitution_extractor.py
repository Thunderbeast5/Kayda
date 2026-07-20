"""
constitution_extractor.py — Extracts constitutional article references
"""
import re
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.text_utils import normalize_whitespace

FUNDAMENTAL_RIGHTS = {str(i) for i in range(12, 36)}  # Articles 12-35
DIRECTIVE_PRINCIPLES = {str(i) for i in range(36, 51)}
FUNDAMENTAL_DUTIES = {"51A"}

ARTICLE_TITLES = {
    "14": "Equality before law",
    "15": "Prohibition of discrimination",
    "16": "Equality of opportunity in public employment",
    "17": "Abolition of untouchability",
    "19": "Protection of freedom of speech etc.",
    "21": "Protection of life and personal liberty",
    "21A": "Right to education",
    "23": "Prohibition of traffic in human beings",
    "24": "Prohibition of child labour",
    "25": "Freedom of conscience and religion",
    "32": "Remedies for enforcement of rights (Dr. Ambedkar's heart of Constitution)",
    "39": "Certain principles to be followed by State",
    "39A": "Equal justice and free legal aid",
    "46": "Promotion of educational and economic interests of SC/ST",
    "51A": "Fundamental Duties",
    "226": "Power of High Courts to issue writs",
    "136": "Special leave to appeal by Supreme Court",
    "141": "Law declared by Supreme Court binding on all courts",
    "142": "Enforcement of decrees and orders of Supreme Court",
}


def extract_articles(paragraphs: list[dict], case_id: str) -> list[dict]:
    articles = []
    art_id = 1
    seen = set()

    for para in paragraphs:
        text = para["paragraph_text"]
        page = para["page_number"]
        para_id = para["paragraph_id"]

        matches = re.finditer(
            r'Article[s]?\s+(\d+[A-Z]?(?:\(\d+\))?(?:\([a-z]\))?)',
            text, re.IGNORECASE
        )
        for m in matches:
            art_num = m.group(1).strip()
            key = f"{art_num}_{para_id}"
            if key in seen:
                continue
            seen.add(key)

            # Extract context (100 chars around the article mention)
            start = max(0, m.start() - 80)
            context = normalize_whitespace(text[start: m.end() + 120])

            articles.append({
                "article_id":          f"ART{art_id:04d}",
                "case_id":             case_id,
                "article_number":      art_num,
                "article_title":       ARTICLE_TITLES.get(art_num, ""),
                "full_text":           "",   # Can be filled from Constitution JSON
                "summary":             _summarize_article(art_num),
                "how_used":            _infer_how_used(context),
                "interpretation":      _extract_interpretation(context),
                "paragraph":           para_id,
                "page":                page,
                "is_fundamental_right":   art_num in FUNDAMENTAL_RIGHTS,
                "is_directive_principle": art_num in DIRECTIVE_PRINCIPLES,
                "is_fundamental_duty":    art_num in FUNDAMENTAL_DUTIES,
            })
            art_id += 1

    return articles


def _summarize_article(art_num: str) -> str:
    return ARTICLE_TITLES.get(art_num, f"Constitutional provision Article {art_num}")


def _infer_how_used(context: str) -> str:
    c = context.lower()
    if "violated" in c:
        return "Invoked as violated right"
    if "interprete" in c or "interpretation" in c:
        return "Interpreted by court"
    if "applied" in c:
        return "Applied to facts"
    if "referred" in c:
        return "Referred"
    return "Invoked"


def _extract_interpretation(context: str) -> str:
    sentences = re.split(r'(?<=[.!?])\s+', context)
    for s in sentences:
        if any(w in s.lower() for w in ["means", "interpreted", "held", "signifies", "includes"]):
            return normalize_whitespace(s)[:250]
    return ""
