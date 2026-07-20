"""
keyword_extractor.py — Legal keyword extraction using RAKE + KeyBERT fallback
"""
import re
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.text_utils import normalize_whitespace


def extract_keywords(text: str, top_n: int = 15) -> list[str]:
    """Try RAKE first, fall back to frequency-based."""
    try:
        from rake_nltk import Rake
        import nltk
        try:
            nltk.data.find('corpora/stopwords')
        except LookupError:
            nltk.download('stopwords', quiet=True)
        r = Rake()
        r.extract_keywords_from_text(text)
        phrases = r.get_ranked_phrases()[:top_n]
        return [normalize_whitespace(p) for p in phrases if len(p.split()) <= 5]
    except Exception:
        return _frequency_keywords(text, top_n)


def _frequency_keywords(text: str, top_n: int) -> list[str]:
    """Simple frequency-based keyword extraction."""
    stop_words = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to",
        "for", "of", "with", "by", "from", "that", "this", "which",
        "is", "are", "was", "were", "be", "been", "being", "have", "has",
        "had", "do", "does", "did", "will", "would", "could", "should",
        "may", "might", "shall", "such", "as", "its", "it", "not"
    }
    words = re.findall(r'\b[a-zA-Z]{4,}\b', text.lower())
    freq = {}
    for w in words:
        if w not in stop_words:
            freq[w] = freq.get(w, 0) + 1
    sorted_words = sorted(freq.items(), key=lambda x: -x[1])
    return [w for w, _ in sorted_words[:top_n]]
