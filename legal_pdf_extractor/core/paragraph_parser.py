"""
paragraph_parser.py — Paragraph and section detection for SC judgments
"""
import re
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import SECTION_TYPE_KEYWORDS
from utils.text_utils import count_words, count_tokens_approx, normalize_whitespace


def split_into_paragraphs(pages: list[dict]) -> list[dict]:
    """Extract paragraphs from page list, preserving page info."""
    paragraphs = []
    para_id = 1
    current_heading = ""
    current_subheading = ""

    for page in pages:
        text = page["text"]
        page_num = page["page_number"]
        blocks = re.split(r'\n{2,}', text)

        for block in blocks:
            block = block.strip()
            if not block or len(block) < 15:
                continue

            # Detect headings
            if _is_heading(block):
                current_heading = normalize_whitespace(block)
                current_subheading = ""
                continue
            if _is_subheading(block):
                current_subheading = normalize_whitespace(block)
                continue

            para_num_match = re.match(r'^(\d+)\.\s+', block)
            para_num = para_num_match.group(1) if para_num_match else None

            is_list, list_type, indent = _detect_list(block)

            paragraphs.append({
                "paragraph_id":    f"P{para_id:05d}",
                "page_number":     page_num,
                "paragraph_number": para_num,
                "heading":         current_heading,
                "subheading":      current_subheading,
                "paragraph_text":  normalize_whitespace(block),
                "word_count":      count_words(block),
                "character_count": len(block),
                "is_numbered":     para_num is not None,
                "is_list_item":    is_list,
                "list_type":       list_type,
                "indent_level":    indent,
                "parent_heading":  current_heading,
                "has_citation":    bool(re.search(r'\(\d{4}\)\s+\d+\s+SCC|AIR\s+\d{4}\s+SC', block)),
                "citation_count":  len(re.findall(r'\(\d{4}\)\s+\d+\s+SCC|AIR\s+\d{4}\s+SC', block)),
                "has_article":     bool(re.search(r'Article\s+\d+', block, re.IGNORECASE)),
                "has_section":     bool(re.search(r'[Ss]ection\s+\d+', block)),
                "tokens":          count_tokens_approx(block),
                "section_type":    classify_section(block, current_heading),
            })
            para_id += 1

    return paragraphs


def _is_heading(text: str) -> bool:
    t = text.strip()
    if len(t) > 120:
        return False
    if re.match(r'^[A-Z][A-Z\s\-:]{5,}$', t):
        return True
    if re.match(r'^(JUDGMENT|ORDER|FACTS|ISSUES|HELD|REASONS|GUIDELINES|APPENDIX|BACKGROUND)', t, re.IGNORECASE):
        return True
    return False


def _is_subheading(text: str) -> bool:
    t = text.strip()
    return bool(re.match(r'^[A-Z][A-Za-z\s]{3,60}:$', t) and len(t) < 80)


def _detect_list(text: str) -> tuple[bool, str | None, int]:
    if re.match(r'^\d+[\.\)]\s+', text):
        return True, "numbered", 0
    if re.match(r'^[a-z][\.\)]\s+', text):
        return True, "numbered", 1
    if re.match(r'^[-•*]\s+', text):
        return True, "bullet", 0
    if re.match(r'^\s{4,}', text):
        return True, "bullet", 1
    return False, None, 0


def classify_section(text: str, heading: str = "") -> str:
    combined = (text + " " + heading).lower()
    scores = {}
    for stype, keywords in SECTION_TYPE_KEYWORDS.items():
        scores[stype] = sum(1 for kw in keywords if kw in combined)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "Miscellaneous"
