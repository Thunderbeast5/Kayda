"""
main.py — CLI entry point for Legal PDF Extractor

Usage:
    python main.py path/to/judgment.pdf
    python main.py path/to/judgment.pdf --formats csv json jsonl
    python main.py path/to/folder/ --batch
    python main.py path/to/judgment.pdf --output outputs/
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import CONFIG
from core.extractor import extract_pdf
from core.output_saver import save_all
from utils.file_utils import list_pdfs, load_checkpoint, save_checkpoint, ensure_dirs
from utils.logging_utils import get_logger

logger = get_logger("main", CONFIG["LOG_FILE"], CONFIG["LOG_LEVEL"])


def process_single(pdf_path: str, output_dir: str, formats: list[str]):
    logger.info(f"Processing: {pdf_path}")
    start = time.time()
    result = extract_pdf(pdf_path, CONFIG)
    case_id = "UNKNOWN"
    if result["dataset_01_metadata"]:
        case_id = result["dataset_01_metadata"][0].get("case_id", "UNKNOWN")
    run_dir = save_all(result, output_dir, case_id, formats)
    elapsed = round(time.time() - start, 2)
    logger.info(f"Done: {os.path.basename(pdf_path)} in {elapsed}s")
    print(f"\n  Output saved to: {run_dir}")
    return result


def process_batch(directory: str, output_dir: str, formats: list[str]):
    pdfs = list_pdfs(directory)
    logger.info(f"Found {len(pdfs)} PDFs in {directory}")

    # Checkpoint support
    checkpoint = load_checkpoint() or {"done": []}
    done = set(checkpoint["done"])

    for i, pdf in enumerate(pdfs):
        if pdf in done:
            logger.info(f"  Skipping (already processed): {os.path.basename(pdf)}")
            continue
        logger.info(f"  [{i+1}/{len(pdfs)}] {os.path.basename(pdf)}")
        try:
            process_single(pdf, output_dir, formats)
            done.add(pdf)
            checkpoint["done"] = list(done)
            save_checkpoint(checkpoint)
        except Exception as e:
            logger.error(f"  Failed: {pdf} — {e}")


def main():
    parser = argparse.ArgumentParser(description="Legal PDF Extractor — 15 Dataset Generator")
    parser.add_argument("input", help="PDF file path or directory (with --batch)")
    parser.add_argument("--batch", action="store_true", help="Process all PDFs in directory")
    parser.add_argument("--output", default=CONFIG["OUTPUT_DIR"], help="Output directory")
    parser.add_argument("--formats", nargs="+",
                        default=CONFIG["OUTPUT_FORMATS"],
                        choices=["csv", "json", "jsonl", "parquet"],
                        help="Output formats")

    args = parser.parse_args()
    ensure_dirs(args.output, "logs", "checkpoints")

    if args.batch:
        process_batch(args.input, args.output, args.formats)
    else:
        if not os.path.isfile(args.input):
            print(f"ERROR: File not found: {args.input}")
            sys.exit(1)
        process_single(args.input, args.output, args.formats)

    print(f"\n✅ Extraction complete. Outputs saved to: {args.output}")


if __name__ == "__main__":
    main()
