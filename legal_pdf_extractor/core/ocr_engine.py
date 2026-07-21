"""
ocr_engine.py — PDF text extraction with Google Vision AI OCR
=============================================================
Priority order:
  1. pdfplumber  — digital/selectable text (fast, free, perfect quality)
  2. Google Vision AI — scanned/image pages (superior OCR accuracy)
  3. Tesseract  — local fallback if Vision AI fails

Credentials loaded from backend/.env:
  GOOGLE_VISION_CREDENTIALS_PATH = path to service account JSON
  OCR_PROVIDER = "vision" | "tesseract"
"""

import io
import os
import base64
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load credentials from backend/.env
_BASE = Path(__file__).resolve().parent.parent.parent  # mootcourt/
_ENV  = _BASE / "backend" / ".env"
load_dotenv(_ENV)

VISION_CREDS_PATH = os.getenv("GOOGLE_VISION_CREDENTIALS_PATH", "")
OCR_PROVIDER      = os.getenv("OCR_PROVIDER", "vision").lower()

# Resolve relative credential path relative to backend/
if VISION_CREDS_PATH and not Path(VISION_CREDS_PATH).is_absolute():
    VISION_CREDS_PATH = str(_BASE / "backend" / VISION_CREDS_PATH)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.logging_utils import get_logger

logger = get_logger("ocr_engine")
logger.info(f"OCR provider: {OCR_PROVIDER}")
logger.info(f"Vision credentials: {VISION_CREDS_PATH}")


# ── 1. pdfplumber (digital PDFs) ─────────────────────────────────────────────
def extract_text_pdfplumber(pdf_path: str,
                             max_pages: Optional[int] = None) -> list[dict]:
    """Extract text from selectable/digital PDF pages."""
    import pdfplumber
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        limit = min(len(pdf.pages), max_pages) if max_pages else len(pdf.pages)
        for i, page in enumerate(pdf.pages[:limit]):
            text = page.extract_text() or ""
            pages.append({
                "page_number": i + 1,
                "text":        text,
                "width":       page.width,
                "height":      page.height,
                "method":      "pdfplumber",
            })
    return pages


# ── 2. Google Vision AI (scanned PDFs) ───────────────────────────────────────
def extract_text_google_vision(pdf_path: str,
                                max_pages: Optional[int] = None,
                                dpi: int = 300) -> list[dict]:
    """
    OCR using Google Cloud Vision AI document_text_detection.
    Converts each page to PNG then sends to Vision API.
    Returns higher quality text than Tesseract for legal documents.
    """
    from google.cloud import vision
    from google.oauth2 import service_account
    from pdf2image import convert_from_path

    if not VISION_CREDS_PATH or not Path(VISION_CREDS_PATH).exists():
        raise FileNotFoundError(
            f"Google Vision credentials not found at: {VISION_CREDS_PATH}\n"
            f"Set GOOGLE_VISION_CREDENTIALS_PATH in backend/.env"
        )

    # Authenticate with service account
    credentials = service_account.Credentials.from_service_account_file(
        VISION_CREDS_PATH,
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    client = vision.ImageAnnotatorClient(credentials=credentials)

    logger.info(f"  Converting PDF to images (dpi={dpi})...")
    images = convert_from_path(pdf_path, dpi=dpi, fmt="png")
    limit  = min(len(images), max_pages) if max_pages else len(images)

    pages = []
    for i, img in enumerate(images[:limit]):
        logger.info(f"  Vision AI OCR: page {i+1}/{limit}")

        # Convert PIL image to bytes
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        content = buf.getvalue()

        # Call Vision API — document_text_detection is optimised for dense text
        vision_image = vision.Image(content=content)
        response = client.document_text_detection(image=vision_image)

        if response.error.message:
            logger.warning(f"  Vision API error on page {i+1}: {response.error.message}")
            text = ""
        else:
            text = response.full_text_annotation.text if response.full_text_annotation else ""

        pages.append({
            "page_number": i + 1,
            "text":        text,
            "width":       img.width,
            "height":      img.height,
            "method":      "google_vision",
        })

    return pages


# ── 3. Tesseract (local fallback) ─────────────────────────────────────────────
def extract_text_tesseract(pdf_path: str,
                            max_pages: Optional[int] = None,
                            lang: str = "eng",
                            dpi: int = 300) -> list[dict]:
    """Local Tesseract OCR fallback."""
    import pytesseract
    from pdf2image import convert_from_path
    import cv2
    import numpy as np

    images = convert_from_path(pdf_path, dpi=dpi)
    limit  = min(len(images), max_pages) if max_pages else len(images)

    pages = []
    for i, img in enumerate(images[:limit]):
        img_np = np.array(img)
        gray   = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
        _, thresh = cv2.threshold(gray, 150, 255,
                                  cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        text = pytesseract.image_to_string(thresh, lang=lang)
        pages.append({
            "page_number": i + 1,
            "text":        text,
            "width":       img.width,
            "height":      img.height,
            "method":      "tesseract",
        })
        logger.debug(f"  Tesseract page {i+1}/{limit}")

    return pages


# ── Helpers ───────────────────────────────────────────────────────────────────
def is_scanned_page(text: str, threshold: int = 80) -> bool:
    """True if a page has very little extractable text (likely scanned)."""
    return len(text.strip()) < threshold


def _ocr_scanned_pages(pdf_path: str, pages: list[dict],
                        scanned_indices: list[int],
                        max_pages: Optional[int],
                        lang: str, dpi: int) -> list[dict]:
    """
    Run OCR only on the scanned pages and merge results back.
    Uses Google Vision AI if configured, else Tesseract.
    """
    logger.info(f"  {len(scanned_indices)} scanned pages detected — running OCR")

    try:
        if OCR_PROVIDER == "vision":
            ocr_pages = extract_text_google_vision(pdf_path, max_pages, dpi)
            method    = "hybrid_google_vision"
        else:
            raise ValueError("tesseract requested")
    except Exception as e:
        logger.warning(f"  Google Vision failed ({e}), falling back to Tesseract")
        try:
            ocr_pages = extract_text_tesseract(pdf_path, max_pages, lang, dpi)
            method    = "hybrid_tesseract"
        except Exception as e2:
            logger.error(f"  Tesseract also failed: {e2}")
            return pages

    for idx in scanned_indices:
        if idx < len(ocr_pages):
            pages[idx]["text"]   = ocr_pages[idx]["text"]
            pages[idx]["method"] = method

    return pages


# ── Main entry point ──────────────────────────────────────────────────────────
def extract_pages(pdf_path: str,
                  max_pages: Optional[int] = None,
                  lang: str = "eng",
                  dpi: int = 300) -> list[dict]:
    """
    Smart 3-tier extraction:
      Tier 1: pdfplumber for all pages
      Tier 2: Google Vision AI for scanned pages (OCR_PROVIDER=vision)
      Tier 3: Tesseract fallback if Vision AI unavailable

    If pdfplumber completely fails (encrypted/corrupt),
    goes straight to full Vision AI OCR.
    """
    logger.info(f"Extracting: {Path(pdf_path).name}")

    # Tier 1: pdfplumber
    try:
        pages = extract_text_pdfplumber(pdf_path, max_pages)
        logger.info(f"  pdfplumber: {len(pages)} pages extracted")
    except Exception as e:
        logger.warning(f"  pdfplumber failed ({e}) — going full OCR")
        if OCR_PROVIDER == "vision":
            pages = extract_text_google_vision(pdf_path, max_pages, dpi)
        else:
            pages = extract_text_tesseract(pdf_path, max_pages, lang, dpi)
        total = sum(len(p["text"]) for p in pages)
        logger.info(f"  Full OCR: {len(pages)} pages, {total} chars")
        return pages

    # Tier 2: identify and OCR scanned pages
    scanned = [i for i, p in enumerate(pages) if is_scanned_page(p["text"])]
    if scanned:
        pages = _ocr_scanned_pages(pdf_path, pages, scanned, max_pages, lang, dpi)

    total = sum(len(p["text"]) for p in pages)
    scanned_count = sum(1 for p in pages if "vision" in p["method"] or "tesseract" in p["method"])
    logger.info(f"  Done: {len(pages)} pages | {total} chars | "
                f"{scanned_count} pages OCR'd via {OCR_PROVIDER}")
    return pages
