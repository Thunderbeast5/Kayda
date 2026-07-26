"""
text_utils.py — Text cleaning and normalization utilities
"""
import re
import unicodedata


def clean_text(text: str) -> str:
    """Full pipeline: normalize unicode, remove artifacts, fix spacing."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r'\x00', '', text)                        # null bytes
    text = re.sub(r'[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)  # control chars
    text = re.sub(r'(\w)-\n(\w)', r'\1\2', text)            # hyphenated line breaks
    text = re.sub(r'\n{3,}', '\n\n', text)                  # multiple blank lines
    text = re.sub(r'[ \t]{2,}', ' ', text)                  # multiple spaces
    text = re.sub(r' +\n', '\n', text)                      # trailing spaces
    return text.strip()


def remove_page_artifacts(text: str) -> str:
    """Remove page numbers, headers, footers common in Indian SC judgments."""
    lines = text.split('\n')
    cleaned = []
    for line in lines:
        stripped = line.strip()
        # standalone page numbers
        if re.fullmatch(r'\d{1,4}', stripped):
            continue
        # common header/footer patterns
        if re.match(r'^(page|pg\.?)\s*\d+', stripped, re.IGNORECASE):
            continue
        if re.match(r'^\d+\s+/\s+\d+$', stripped):
            continue
        cleaned.append(line)
    return '\n'.join(cleaned)


def normalize_whitespace(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()


def is_meaningful(text: str, min_len: int = 20) -> bool:
    t = normalize_whitespace(text)
    return len(t) >= min_len and not re.fullmatch(r'[\d\s\.\-\_]+', t)


def count_words(text: str) -> int:
    return len(text.split()) if text else 0


def count_tokens_approx(text: str) -> int:
    """Approximate token count (words * 1.3)."""
    return int(count_words(text) * 1.3)


def extract_between(text: str, start_marker: str, end_marker: str) -> str:
    pattern = re.escape(start_marker) + r'(.*?)' + re.escape(end_marker)
    m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else ""


def split_into_sentences(text: str) -> list[str]:
    """Simple sentence splitter for legal text."""
    try:
        import nltk
        sentences = nltk.sent_tokenize(text)
    except Exception:
        sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
    return [s.strip() for s in sentences if s.strip()]
