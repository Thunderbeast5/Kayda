"""
output_saver.py — Saves all 15 datasets in CSV, JSON, JSONL, Parquet
Each run writes to a timestamped subfolder so open files never block saves.
"""
import os, sys, datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
from utils.file_utils import save_json, save_jsonl, ensure_dirs
from utils.logging_utils import get_logger

logger = get_logger("output_saver")


def save_all(result: dict, output_dir: str, case_id: str, formats: list[str]):
    # Timestamped run folder — never collides with open files
    run_ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir  = os.path.join(output_dir, f"{case_id}_{run_ts}")

    ensure_dirs(
        os.path.join(run_dir, "csv"),
        os.path.join(run_dir, "json"),
        os.path.join(run_dir, "jsonl"),
        os.path.join(run_dir, "parquet"),
    )
    logger.info(f"  Output folder: {run_dir}")

    for dataset_key, rows in result.items():
        safe_name = dataset_key   # e.g. dataset_01_metadata

        flat_rows = [_flatten_row(r) for r in rows] if rows else []

        if "csv" in formats:
            path = os.path.join(run_dir, "csv", f"{safe_name}.csv")
            try:
                pd.DataFrame(flat_rows).to_csv(path, index=False, encoding="utf-8")
            except PermissionError as e:
                logger.error(f"  PermissionError saving {safe_name}.csv — close the file if open: {e}")
                continue

        if "json" in formats:
            path = os.path.join(run_dir, "json", f"{safe_name}.json")
            save_json(rows or [], path)

        if "jsonl" in formats:
            path = os.path.join(run_dir, "jsonl", f"{safe_name}.jsonl")
            save_jsonl(rows or [], path)

        if "parquet" in formats:
            try:
                path = os.path.join(run_dir, "parquet", f"{safe_name}.parquet")
                pd.DataFrame(flat_rows).to_parquet(path, index=False)
            except Exception as e:
                logger.warning(f"  Parquet save failed for {dataset_key}: {e}")

        logger.info(f"  {dataset_key}: {len(rows) if rows else 0} rows")

    logger.info(f"  All datasets saved to: {run_dir}")
    return run_dir


def _flatten_row(row: dict) -> dict:
    """Convert lists/dicts to strings for CSV/Parquet compatibility."""
    flat = {}
    for k, v in row.items():
        if isinstance(v, (list, dict)):
            flat[k] = str(v)
        elif v is None:
            flat[k] = ""
        else:
            flat[k] = v
    return flat


    for dataset_key, rows in result.items():
        safe_name = f"{case_id}_{dataset_key}"

        if not rows:
            # Write empty file with just header so it's visible
            logger.warning(f"  {dataset_key}: 0 rows — writing empty file")
            rows = []  # still save empty

        flat_rows = [_flatten_row(r) for r in rows]

        if "csv" in formats:
            path = os.path.join(output_dir, "csv", f"{safe_name}.csv")
            pd.DataFrame(flat_rows).to_csv(path, index=False, encoding="utf-8")

        if "json" in formats:
            path = os.path.join(output_dir, "json", f"{safe_name}.json")
            save_json(rows, path)

        if "jsonl" in formats:
            path = os.path.join(output_dir, "jsonl", f"{safe_name}.jsonl")
            save_jsonl(rows, path)

        if "parquet" in formats:
            try:
                path = os.path.join(output_dir, "parquet", f"{safe_name}.parquet")
                pd.DataFrame(flat_rows).to_parquet(path, index=False)
            except Exception as e:
                logger.warning(f"  Parquet save failed for {dataset_key}: {e}")

        logger.info(f"  Saved {dataset_key}: {len(rows)} rows")


def _flatten_row(row: dict) -> dict:
    """Convert lists/dicts to strings for CSV compatibility."""
    flat = {}
    for k, v in row.items():
        if isinstance(v, (list, dict)):
            flat[k] = str(v)
        elif v is None:
            flat[k] = ""
        else:
            flat[k] = v
    return flat
