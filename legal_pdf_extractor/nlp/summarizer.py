"""
summarizer.py — Extractive summarization for legal text
"""
import re
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.text_utils import normalize_whitespace, count_words


def extractive_summary(text: str, max_sentences: int = 8) -> str:
    """Score and pick top sentences for summary."""
    from utils.text_utils import split_into_sentences
    sentences = split_into_sentences(text)
    if not sentences:
        return ""

    scored = []
    for s in sentences:
        score = _score_sentence(s)
        scored.append((score, s))

    scored.sort(key=lambda x: -x[0])
    top = [s for _, s in scored[:max_sentences]]

    # Restore original order
    order = {s: i for i, s in enumerate(sentences)}
    top.sort(key=lambda s: order.get(s, 999))

    return " ".join(top)


def _score_sentence(sent: str) -> float:
    score = 0.0
    t = sent.lower()
    # Legal importance signals
    for kw in ["held", "ratio", "principle", "established", "guideline",
               "fundamental right", "article", "the court", "we hold",
               "directed", "order", "judgment"]:
        if kw in t:
            score += 1.0
    # Penalize very short or very long
    wc = count_words(sent)
    if wc < 5 or wc > 80:
        score -= 1.0
    return score


def summarize_150words(text: str) -> str:
    summary = extractive_summary(text, max_sentences=6)
    words = summary.split()
    if len(words) > 150:
        summary = " ".join(words[:150]) + "..."
    return normalize_whitespace(summary)


def extract_ratio_decidendi(text: str) -> str:
    """Extract the binding ratio from judgment text."""
    sentences = _split_sent(text)
    for s in sentences:
        t = s.lower()
        if any(w in t for w in ["we hold", "it is held", "ratio", "binding",
                                  "the law laid down", "principle established"]):
            return normalize_whitespace(s)[:500]
    return extractive_summary(text, max_sentences=2)


def extract_obiter_dicta(text: str) -> str:
    sentences = _split_sent(text)
    obiter = []
    for s in sentences:
        t = s.lower()
        if any(w in t for w in ["we observe", "in passing", "though not necessary",
                                  "we may add", "obiter", "it may be noted"]):
            obiter.append(s)
    return " ".join(obiter[:3])


def extract_final_order(text: str) -> str:
    sentences = _split_sent(text)
    for s in reversed(sentences):
        t = s.lower()
        if any(w in t for w in ["appeal is dismissed", "petition is dismissed",
                                  "petition is allowed", "appeal is allowed",
                                  "disposed of", "accordingly ordered"]):
            return normalize_whitespace(s)
    return ""


def _split_sent(text: str) -> list[str]:
    try:
        import nltk
        return nltk.sent_tokenize(text)
    except Exception:
        return re.split(r'(?<=[.!?])\s+', text)
