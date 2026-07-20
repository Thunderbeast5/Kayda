"""
sentence_segmenter.py — Sentence extraction with legal-aware splitting
"""
import re
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.text_utils import normalize_whitespace, count_tokens_approx


SPEAKER_PATTERNS = {
    "Court":      [
        r'\bthe court\b', r'\bwe hold\b', r'\bwe are of the view\b',
        r'\bit is held\b', r'\bthis court\b', r'\bin our opinion\b',
        r'\bwe observe\b', r'\bwe direct\b', r'\bwe find\b',
        r'\bthe bench\b', r'\bper curiam\b', r'\bthe judges\b',
    ],
    "Petitioner": [
        r'\bpetitioner submits\b', r'\bpetitioner contends\b',
        r'\blearned counsel.*?petitioner\b', r'\bappellant submits\b',
        r'\bappellant contends\b', r'\bon behalf of.*?petitioner\b',
        r'\bfor the petitioner\b', r'\bfor the appellant\b',
    ],
    "Respondent": [
        r'\brespondent submits\b', r'\bstate submits\b',
        r'\blearned counsel.*?respondent\b', r'\bfor the respondent\b',
        r'\bopposing counsel\b', r'\bgovernment pleader\b',
        r'\badditional solicitor general\b', r'\bsolicitor general\b',
    ],
    "Quote":      [
        r'^["\u201c]', r'["\u201c].{10,}["\u201d]',
    ],
}


def extract_sentences(paragraphs: list[dict], case_id: str) -> list[dict]:
    sentences = []
    sent_id = 1

    for para in paragraphs:
        text = para["paragraph_text"]
        page = para["page_number"]
        para_id = para["paragraph_id"]

        raw_sentences = _split_sentences(text)
        for sent in raw_sentences:
            sent = sent.strip()
            if len(sent) < 10:
                continue
            sentences.append({
                "sentence_id":         f"S{sent_id:06d}",
                "case_id":             case_id,
                "page":                page,
                "paragraph":           para_id,
                "sentence":            normalize_whitespace(sent),
                "speaker":             _detect_speaker(sent),
                "importance_score":    _importance_score(sent),
                "contains_article":    bool(re.search(r'Article\s+\d+', sent, re.IGNORECASE)),
                "contains_section":    bool(re.search(r'[Ss]ection\s+\d+', sent)),
                "contains_case_name":  bool(re.search(r'\bvs?\.\b|\bversus\b', sent, re.IGNORECASE)),
                "contains_act":        bool(re.search(r'\w+\s+Act,?\s*\d{4}', sent)),
                "contains_person":     bool(re.search(r'\bJustice\b|\bMr\.\b|\bMs\.\b|\bDr\.\b', sent)),
                "contains_date":       bool(re.search(r'\d{1,2}[/-]\d{1,2}[/-]\d{4}|\b\d{4}\b', sent)),
                "contains_organization": bool(re.search(r'\bCommittee\b|\bCommission\b|\bBoard\b|\bCourt\b', sent)),
                "contains_location":   bool(re.search(r'\bIndia\b|\bDelhi\b|\bRajasthan\b|\bState\b', sent)),
                "contains_quote":      bool(re.search(r'["\u201c\u201d]', sent)),
                "is_definition":       _is_definition(sent),
                "is_legal_principle":  _is_legal_principle(sent),
                "sentiment":           "neutral",
                "sentence_type":       _sentence_type(sent),
                "token_count":         count_tokens_approx(sent),
                "dependency_parse":    None,
            })
            sent_id += 1

    return sentences


def _split_sentences(text: str) -> list[str]:
    try:
        import nltk
        try:
            nltk.data.find('tokenizers/punkt')
        except LookupError:
            nltk.download('punkt', quiet=True)
        return nltk.sent_tokenize(text)
    except Exception:
        return re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)


def _detect_speaker(text: str) -> str:
    t = text.lower()
    for speaker, patterns in SPEAKER_PATTERNS.items():
        for p in patterns:
            if re.search(p, t):
                return speaker
    return "Unknown"


def _importance_score(text: str) -> float:
    score = 0.3
    t = text.lower()
    if any(w in t for w in ["held", "ratio", "principle", "established", "landmark"]):
        score += 0.3
    if any(w in t for w in ["article", "section", "act", "constitution"]):
        score += 0.2
    if any(w in t for w in ["fundamental right", "right to life", "equality"]):
        score += 0.2
    return min(round(score, 2), 1.0)


def _is_definition(text: str) -> bool:
    return bool(re.search(r'\bmeans\b|\bshall mean\b|\bis defined as\b|\bdenotes\b', text, re.IGNORECASE))


def _is_legal_principle(text: str) -> bool:
    return bool(re.search(r'\bit is (well )?settled\b|\bthe law is\b|\bprinciple of\b|\brule of\b',
                          text, re.IGNORECASE))


def _sentence_type(text: str) -> str:
    t = text.strip()
    if t.endswith("?"):
        return "interrogative"
    if t.endswith("!"):
        return "exclamatory"
    if re.match(r'^(do|does|shall|must|should|let)\b', t, re.IGNORECASE):
        return "imperative"
    return "declarative"
