"""
Main extraction runner — Phase 1 of the fine-tuning pipeline.

Usage:
    python run_extraction.py                    # process all PDFs in raw_pdfs/
    python run_extraction.py --resume           # skip already-succeeded files
    python run_extraction.py --file foo.pdf     # process a single file
    python run_extraction.py --summary          # print manifest summary only

Outputs:
    extracted_records/<stem>.json   — one JSON record per PDF
    extracted_text/<stem>.txt       — clean plain text (for manual inspection)
    manifest/manifest.jsonl         — processing log (append-only)
"""

import argparse
import gc
import json
import logging
import re
import sys
from pathlib import Path

from extraction.triage import triage_pdf, text_layer_extract, ocr_extract
from extraction.field_extractor import extract_fields
from extraction.manifest import write_entry, already_processed, print_summary

# ── Folder paths ──────────────────────────────────────────────────────────────
RAW_PDFS_DIR = Path("raw_pdfs")
EXTRACTED_TEXT_DIR = Path("extracted_text")
EXTRACTED_RECORDS_DIR = Path("extracted_records")
MANIFEST_DIR = Path("manifest")

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(MANIFEST_DIR / "run.log", mode="a", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


# ── Folder bootstrap ──────────────────────────────────────────────────────────
def ensure_dirs() -> None:
    for d in [RAW_PDFS_DIR, EXTRACTED_TEXT_DIR, EXTRACTED_RECORDS_DIR, MANIFEST_DIR]:
        d.mkdir(parents=True, exist_ok=True)


# ── Single-file processing ────────────────────────────────────────────────────
def process_pdf(pdf_path: Path, resume: bool = False) -> bool:
    """
    Full pipeline for one PDF:
      1. Triage (TEXT_LAYER vs SCANNED)
      2. Extract text via appropriate path
      3. Parse fields
      4. Write outputs
      5. Log to manifest
    Returns True on success, False on failure.
    """
    pdf_name = pdf_path.name
    # Build a unique stem that includes the batch folder name to avoid collisions
    # e.g. "Batch 1/TheLawsSuperOnline-1.pdf" → stem = "Batch1__TheLawsSuperOnline-1"
    # Root-level PDFs keep their stem unchanged.
    try:
        relative = pdf_path.relative_to(RAW_PDFS_DIR)
        parts = relative.parts  # e.g. ("Batch 1", "TheLawsSuperOnline-1.pdf") or ("foo.pdf",)
    except ValueError:
        parts = (pdf_path.name,)

    if len(parts) > 1:
        # Sanitise folder name: remove spaces, special chars
        folder_prefix = re.sub(r"[^A-Za-z0-9_-]", "", parts[0]) + "__"
        stem = folder_prefix + pdf_path.stem
    else:
        stem = pdf_path.stem

    # Manifest key includes the relative path for uniqueness
    manifest_key = str(Path(*parts)) if len(parts) > 1 else pdf_path.name

    if resume and already_processed(manifest_key):
        logger.info(f"[skip] {manifest_key} — already succeeded")
        return True

    logger.info(f"\n{'─'*55}")
    logger.info(f"[start] Processing: {manifest_key}")

    classification = "TEXT_LAYER"
    page_count = 0
    clean_text = ""

    # ── Step 1: Triage ────────────────────────────────────────────────────
    try:
        classification = triage_pdf(pdf_path)
    except Exception as e:
        write_entry(manifest_key, "UNKNOWN", "FAILED", error=f"Triage failed: {e}")
        logger.error(f"[triage] {manifest_key} failed: {e}")
        return False

    # ── Step 2: Extract text ──────────────────────────────────────────────
    try:
        if classification == "TEXT_LAYER":
            clean_text, page_count = text_layer_extract(pdf_path)
        else:
            logger.warning(f"[ocr] {manifest_key} classified as SCANNED — using Tesseract fallback")
            clean_text, page_count = ocr_extract(pdf_path)
    except Exception as e:
        write_entry(manifest_key, classification, "FAILED", page_count=page_count, error=f"Extraction failed: {e}")
        logger.error(f"[extract] {manifest_key} failed: {e}")
        return False

    # Save clean text for manual inspection
    txt_path = EXTRACTED_TEXT_DIR / f"{stem}.txt"
    txt_path.write_text(clean_text, encoding="utf-8")

    # ── Step 3: Parse fields ──────────────────────────────────────────────
    try:
        record = extract_fields(clean_text, manifest_key, classification)
    except Exception as e:
        write_entry(manifest_key, classification, "FAILED", page_count=page_count, error=f"Field parsing failed: {e}")
        logger.error(f"[fields] {manifest_key} failed: {e}")
        return False

    # ── Step 4: Write record to disk immediately (memory discipline) ──────
    out_path = EXTRACTED_RECORDS_DIR / f"{stem}.json"
    out_path.write_text(record.to_json(), encoding="utf-8")

    # ── Step 5: Manifest entry ────────────────────────────────────────────
    missing_critical = record.missing_critical_fields
    status = "PARTIAL" if (record.missing_anchors or missing_critical) else "SUCCESS"

    fields_present = [
        f for f in [
            "case_citation", "court", "coram", "decided_on", "decided_on_year",
            "appeal_type", "appellant", "respondent", "referred_acts",
            "headnote_raw", "headnote_points", "judgment_author",
            "bail_amount_original", "bail_amount_modified", "numbered_paragraphs",
            "ratio_decidendi", "bail_outcome", "bail_conditions",
            "dispute_nature", "final_verdict", "cited_judgments",
        ]
        if getattr(record, f, None)
    ]

    write_entry(
        pdf_name=manifest_key,
        classification=classification,
        status=status,
        page_count=page_count,
        fields_extracted=fields_present,
        missing_anchors=record.missing_anchors,
        warnings=record.warnings,
        output_file=str(out_path),
    )

    para_count = len(record.numbered_paragraphs)
    logger.info(
        f"[done] {manifest_key} → {status} | "
        f"paragraphs={para_count} | "
        f"bail_orig={record.bail_amount_original} | "
        f"bail_mod={record.bail_amount_modified} | "
        f"outcome={record.bail_outcome} | "
        f"s438={'YES' if record.has_section_438 else 'NO'}"
    )
    if record.warnings:
        for w in record.warnings:
            logger.warning(f"  ⚠  {w}")
    if record.missing_anchors:
        logger.warning(f"  ⚠  Missing anchors: {record.missing_anchors}")

    # ── Memory cleanup — don't accumulate records in memory across files ──
    del clean_text, record
    gc.collect()

    return status in ("SUCCESS", "PARTIAL")


# ── Batch runner ──────────────────────────────────────────────────────────────
def run_all(resume: bool = False) -> None:
    """Process every PDF in raw_pdfs/ and all subfolders sequentially."""
    # rglob("*.pdf") finds PDFs at any depth: raw_pdfs/*.pdf, raw_pdfs/Batch 1/*.pdf, etc.
    pdfs = sorted(RAW_PDFS_DIR.rglob("*.pdf"))

    if not pdfs:
        logger.warning(f"No PDFs found in {RAW_PDFS_DIR}/")
        return

    logger.info(f"Found {len(pdfs)} PDFs to process")
    succeeded = 0
    failed = 0
    skipped = 0

    for pdf_path in pdfs:
        if resume and already_processed(pdf_path.name):
            skipped += 1
            continue
        ok = process_pdf(pdf_path, resume=resume)
        if ok:
            succeeded += 1
        else:
            failed += 1

    logger.info(f"\n{'='*55}")
    logger.info(f"BATCH COMPLETE: {succeeded} succeeded | {failed} failed | {skipped} skipped")
    logger.info(f"{'='*55}")
    print_summary()


# ── Entry point ───────────────────────────────────────────────────────────────
def main() -> None:
    ensure_dirs()

    parser = argparse.ArgumentParser(
        description="Extract structured fields from anticipatory bail PDFs"
    )
    parser.add_argument(
        "--file", "-f",
        type=str,
        default=None,
        help="Process a single PDF file (basename or full path)"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip PDFs that already have a SUCCESS entry in the manifest"
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print manifest summary and exit"
    )
    args = parser.parse_args()

    if args.summary:
        print_summary()
        return

    if args.file:
        pdf_path = Path(args.file)
        if not pdf_path.is_absolute():
            pdf_path = RAW_PDFS_DIR / pdf_path
        if not pdf_path.exists():
            logger.error(f"File not found: {pdf_path}")
            sys.exit(1)
        process_pdf(pdf_path, resume=args.resume)
    else:
        run_all(resume=args.resume)


if __name__ == "__main__":
    main()
