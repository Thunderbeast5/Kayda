"""
Text cleaning utilities.

Key problem this solves: the source PDFs embed page footers and licence stamps
INSIDE the middle of multi-page fields (headnote, cited judgments). Because
pdfplumber reads page by page and joins the text, these footer lines appear
mid-sentence. This cleaner removes them *before* anchor-splitting so field
content is continuous and not broken by boilerplate fragments.
"""

import re
import hashlib
from .schema import BOILERPLATE_PATTERNS, PAGE_FOOTER_PATTERN


def strip_boilerplate(text: str) -> str:
    """
    Remove vendor licence/copyright lines and page footers line-by-line.
    Must be applied BEFORE anchor splitting so mid-field page breaks are healed.
    """
    lines = text.splitlines()
    cleaned = []
    for line in lines:
        stripped = line.strip()
        # Skip any line containing a known boilerplate substring
        if any(pattern in line for pattern in BOILERPLATE_PATTERNS):
            continue
        # Skip page-footer lines  e.g. "Page 1 of 3 Copyright ..."
        # Matched at start of stripped line to avoid false positives mid-sentence
        if re.match(PAGE_FOOTER_PATTERN, stripped):
            continue
        cleaned.append(line)
    return "\n".join(cleaned)


def heal_mid_field_breaks(text: str) -> str:
    """
    After stripping boilerplate, adjacent text that was split across a page
    boundary now has an empty line between the two halves. If the line before
    the gap ends without sentence-ending punctuation (no . ? ! :), it was
    likely a mid-sentence break — join the two halves.

    Example:
        "...the condition imposed by"     <- no period, page break was here
        ""
        "the High Court while..."
    becomes:
        "...the condition imposed by the High Court while..."
    """
    lines = text.splitlines()
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        # If this line is empty and we have a previous non-empty line that
        # doesn't end with sentence-closing punctuation, peek at next non-empty line
        if line.strip() == "" and result:
            prev = result[-1].rstrip()
            if prev and prev[-1] not in ".?!:,;)\"'":
                # Find next non-empty line
                j = i + 1
                while j < len(lines) and lines[j].strip() == "":
                    j += 1
                if j < len(lines):
                    next_line = lines[j].strip()
                    # Looks like a continuation (starts lowercase or with article)
                    if next_line and (next_line[0].islower() or next_line[:4].lower() in ("the ", "a hi", "an a", "this", "that", "wher", "the ", "of t")):
                        result[-1] = result[-1].rstrip() + " " + next_line
                        i = j + 1
                        continue
        result.append(line)
        i += 1
    return "\n".join(result)


def normalise_whitespace(text: str) -> str:
    """
    Collapse PDF column-wrap whitespace artefacts:
    pdfplumber sometimes inserts multiple spaces mid-word when lines in the PDF
    are wide and text overflows the column boundary.
    """
    lines = text.splitlines()
    normalised = []
    for line in lines:
        # Collapse 3+ consecutive spaces to one (2 spaces may be intentional indent)
        line = re.sub(r" {3,}", " ", line)
        normalised.append(line.strip())
    result = "\n".join(normalised)
    # Collapse 3+ consecutive blank lines to 2
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def _para_hash(text: str) -> str:
    key = re.sub(r"\s+", " ", text).strip().lower()
    return hashlib.md5(key.encode()).hexdigest()


def deduplicate_blocks(blocks: list[str]) -> list[str]:
    """
    Remove exact-duplicate text blocks (normalised comparison).
    Keeps first occurrence. Guards against PDFs that embed both a styled
    and a plain-text copy of each page.
    """
    seen: set[str] = set()
    result = []
    for block in blocks:
        h = _para_hash(block)
        if h not in seen:
            seen.add(h)
            result.append(block)
    return result


def clean_page_text(raw_text: str) -> str:
    """Full per-page cleaning pipeline."""
    text = strip_boilerplate(raw_text)
    text = normalise_whitespace(text)
    return text


def clean_full_document(pages: list[str]) -> str:
    """
    Clean all pages and join into one document string.
    Page boundaries are marked with two newlines — enough separation for
    anchor splitting without introducing visible tokens.

    IMPORTANT: boilerplate must be stripped per-page BEFORE joining, so that
    mid-field page footers don't appear inside field content after join.
    """
    cleaned_pages = [clean_page_text(p) for p in pages if p and p.strip()]
    joined = "\n\n".join(cleaned_pages)
    # After joining, heal any remaining mid-sentence page breaks
    joined = heal_mid_field_breaks(joined)
    return joined
