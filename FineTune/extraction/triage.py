"""
PDF triage: classify each PDF as TEXT_LAYER or SCANNED.
Also provides the two extraction paths:
  - text_layer_extract(): uses pdfplumber
  - ocr_extract(): uses pdf2image + Tesseract (fallback only)
"""

import gc
import re
import logging
from pathlib import Path

import pdfplumber

from .schema import CHARS_PER_PAGE_THRESHOLD
from .cleaner import clean_full_document

logger = logging.getLogger(__name__)


# ── Text-layer extraction ─────────────────────────────────────────────────────

def text_layer_extract(pdf_path: Path) -> tuple[str, int]:
    """
    Extract all text from a PDF using pdfplumber (text-layer path).
    Returns (clean_document_text, page_count).
    Closes the PDF before returning — no handle leaks.
    """
    pages_text: list[str] = []
    page_count = 0

    with pdfplumber.open(str(pdf_path)) as pdf:
        page_count = len(pdf.pages)
        for page in pdf.pages:
            raw = page.extract_text() or ""
            pages_text.append(raw)
        # File handle released here by context manager

    clean_text = clean_full_document(pages_text)
    return clean_text, page_count


# ── Triage ────────────────────────────────────────────────────────────────────

def triage_pdf(pdf_path: Path) -> str:
    """
    Classify PDF as 'TEXT_LAYER' or 'SCANNED'.
    Uses average characters per page as the signal.
    Returns one of: "TEXT_LAYER" | "SCANNED"
    """
    total_chars = 0
    page_count = 0

    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            page_count = len(pdf.pages)
            for page in pdf.pages:
                raw = page.extract_text() or ""
                total_chars += len(raw)
    except Exception as e:
        logger.warning(f"[triage] Could not open {pdf_path.name}: {e}")
        return "SCANNED"  # conservative default — will try OCR

    if page_count == 0:
        return "SCANNED"

    avg_chars = total_chars / page_count
    classification = "TEXT_LAYER" if avg_chars >= CHARS_PER_PAGE_THRESHOLD else "SCANNED"
    logger.info(
        f"[triage] {pdf_path.name}: {avg_chars:.0f} avg chars/page → {classification}"
    )
    return classification


# ── OCR fallback extraction ───────────────────────────────────────────────────

def ocr_extract(pdf_path: Path) -> tuple[str, int]:
    """
    OCR extraction for scanned PDFs.
    Renders one page at a time at 300 DPI, runs Tesseract, then discards
    the image immediately — never holds more than one page image in memory.
    Returns (clean_document_text, page_count).
    """
    try:
        from pdf2image import convert_from_path
        import pytesseract
        from PIL import Image, ImageFilter, ImageOps
    except ImportError as e:
        raise RuntimeError(
            f"OCR dependencies not available: {e}. "
            "Install pdf2image, pytesseract, and Pillow."
        ) from e

    pages_text: list[str] = []

    # Get page count without loading images
    with pdfplumber.open(str(pdf_path)) as pdf:
        page_count = len(pdf.pages)

    logger.info(f"[ocr] Starting OCR on {pdf_path.name} ({page_count} pages)")

    for page_num in range(1, page_count + 1):
        # Render single page — much lower memory than convert_from_path(all pages)
        images = convert_from_path(
            str(pdf_path),
            dpi=300,
            first_page=page_num,
            last_page=page_num,
        )
        if not images:
            pages_text.append("")
            continue

        img = images[0]

        # Binarize: convert to greyscale, then threshold to black/white
        img = img.convert("L")                          # greyscale
        img = img.point(lambda x: 0 if x < 128 else 255, "1")  # binarize

        # OCR with single uniform block (documents are single-column, no tables)
        # psm 6 = "Assume a single uniform block of text"
        raw_text = pytesseract.image_to_string(
            img,
            lang="eng",
            config="--psm 6 --oem 1",
        )
        pages_text.append(raw_text)

        # Explicitly free the image before next iteration
        del img, images
        gc.collect()
        logger.debug(f"[ocr] Page {page_num}/{page_count} done")

    clean_text = clean_full_document(pages_text)
    return clean_text, page_count
