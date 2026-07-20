"""
output_saver.py — Saves all 15 datasets in CSV, JSON, JSONL, Parquet
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
from utils.file_utils import save_json, save_jsonl, ensure_dirs
from utils.logging_utils import get_logger

logger = get_logger("output_saver")


def save_all(result: dict, output_dir: str, case_id: str, formats: list[str]):
    ensure_dirs(
        os.path.join(output_dir, "csv"),
        os.path.join(output_dir, "json"),
        os.path.join(output_dir, "jsonl"),
        os.path.join(output_dir, "parquet"),
    )

    for dataset_key, rows in result.items():
        if not rows:
            logger.warning(f"  {dataset_key}: empty, skipping")
            continue

        safe_name = f"{case_id}_{dataset_key}"

        # Flatten nested dicts/lists for CSV/Parquet
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
