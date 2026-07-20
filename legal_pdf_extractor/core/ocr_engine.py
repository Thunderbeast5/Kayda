"""
ocr_engine.py — PDF text extraction with OCR fallback
Handles: digital PDFs, scanned PDFs, mixed PDFs
"""
import io
import os
from pathlib import Path
from typing import Optional
from utils.logging_utils import get_logger

logger = get_logger("ocr_engine")


def extract_text_pdfplumber(pdf_path: str, max_pages: Optional[int] = None) -> list[dict]:
    """Primary: extract text from digital PDF using pdfplumber."""
    import pdfplumber
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        limit = min(total, max_pages) if max_pages else total
        for i, page in enumerate(pdf.pages[:limit]):
            text = page.extract_text() or ""
            pages.append({
                "page_number": i + 1,
                "text": text,
                "width": page.width,
                "height": page.height,
                "method": "pdfplumber",
            })
    return pages


def extract_text_ocr(pdf_path: str, max_pages: Optional[int] = None,
                      lang: str = "eng", dpi: int = 300) -> list[dict]:
    """Fallback: OCR using pytesseract for scanned pages."""
    import pytesseract
    from pdf2image import convert_from_path
    import cv2
    import numpy as np

    pages = []
    images = convert_from_path(pdf_path, dpi=dpi)
    limit = min(len(images), max_pages) if max_pages else len(images)

    for i, img in enumerate(images[:limit]):
        # Preprocess: grayscale + threshold
        img_np = np.array(img)
        gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
        _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        text = pytesseract.image_to_string(thresh, lang=lang)
        pages.append({
            "page_number": i + 1,
            "text": text,
            "width": img.width,
            "height": img.height,
            "method": "ocr_tesseract",
        })
        logger.debug(f"OCR page {i+1}/{limit}")
    return pages


def is_scanned_page(text: str, threshold: int = 50) -> bool:
    """Detect if a page is scanned (very little extractable text)."""
    return len(text.strip()) < threshold


def extract_pages(pdf_path: str, max_pages: Optional[int] = None,
                   lang: str = "eng", dpi: int = 300) -> list[dict]:
    """
    Smart extraction:
    - Try pdfplumber first
    - Fall back to OCR for pages with insufficient text
    """
    logger.info(f"Extracting: {Path(pdf_path).name}")
    try:
        pages = extract_text_pdfplumber(pdf_path, max_pages)
    except Exception as e:
        logger.warning(f"pdfplumber failed ({e}), using OCR")
        pages = extract_text_ocr(pdf_path, max_pages, lang, dpi)
        return pages

    # Hybrid: OCR scanned pages
    scanned_indices = [i for i, p in enumerate(pages) if is_scanned_page(p["text"])]
    if scanned_indices:
        logger.info(f"  {len(scanned_indices)} pages appear scanned, running OCR on them")
        try:
            ocr_pages = extract_text_ocr(pdf_path, max_pages, lang, dpi)
            for idx in scanned_indices:
                if idx < len(ocr_pages):
                    pages[idx]["text"] = ocr_pages[idx]["text"]
                    pages[idx]["method"] = "hybrid_ocr"
        except Exception as e:
            logger.warning(f"OCR fallback failed: {e}")

    total_text = sum(len(p["text"]) for p in pages)
    logger.info(f"  {len(pages)} pages, {total_text} chars extracted")
    return pages
