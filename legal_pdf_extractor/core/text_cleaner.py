"""
text_cleaner.py — Intelligent text cleaning for legal documents
"""
import re
from utils.text_utils import clean_text, remove_page_artifacts


def clean_page(text: str) -> str:
    """Full cleaning pipeline for a single page."""
    text = clean_text(text)
    text = remove_page_artifacts(text)
    text = _fix_ocr_artifacts(text)
    text = _normalize_quotes(text)
    text = _fix_spacing(text)
    return text


def _fix_ocr_artifacts(text: str) -> str:
    """Fix common OCR errors in Indian legal documents."""
    # 'l' misread as '1' in common legal words
    replacements = [
        (r'\b1aw\b', 'law'), (r'\b1egal\b', 'legal'),
        (r'\bArt1cle\b', 'Article'), (r'\bSect1on\b', 'Section'),
        (r'\bJust1ce\b', 'Justice'), (r'\bC0urt\b', 'Court'),
        (r'\bpet1tioner\b', 'petitioner'), (r'\brespond[e3]nt\b', 'respondent'),
        (r'[''`]', "'"), (r'["""]', '"'),
    ]
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    # Remove lone special characters on their own lines
    text = re.sub(r'^\s*[|\\/_~*#@]+\s*$', '', text, flags=re.MULTILINE)
    return text


def _normalize_quotes(text: str) -> str:
    text = re.sub(r'[''`]', "'", text)
    text = re.sub(r'["""]', '"', text)
    return text


def _fix_spacing(text: str) -> str:
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def clean_all_pages(pages: list[dict]) -> list[dict]:
    for p in pages:
        p["text"] = clean_page(p["text"])
    return pages


def merge_pages_to_text(pages: list[dict]) -> str:
    return "\n\n".join(p["text"] for p in pages if p["text"].strip())
