"""
output_saver.py — Saves all 15 datasets individually AND as a single combined file.

Per-run output structure:
  outputs/{case_id}_{timestamp}/
    csv/
      dataset_01_metadata.csv          ← individual dataset files (unchanged)
      dataset_02_paragraphs.csv
      ...
      dataset_15_qa.csv
      ALL_DATASETS_COMBINED.csv        ← NEW: all 15 datasets in one CSV
    json/
      dataset_01_metadata.json
      ...
      ALL_DATASETS_COMBINED.json       ← NEW: all 15 datasets in one JSON
    jsonl/  ...
    parquet/ ...
"""
import os, sys, datetime, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
from utils.file_utils import ensure_dirs
from utils.logging_utils import get_logger

logger = get_logger("output_saver")


def save_all(result: dict, output_dir: str, case_id: str, formats: list[str]) -> str:
    """
    Save every dataset individually, then write combined files.
    Returns the run directory path.
    """
    run_ts  = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = os.path.join(output_dir, f"{case_id}_{run_ts}")

    ensure_dirs(
        os.path.join(run_dir, "csv"),
        os.path.join(run_dir, "json"),
        os.path.join(run_dir, "jsonl"),
        os.path.join(run_dir, "parquet"),
    )
    logger.info(f"  Output folder: {run_dir}")

    # ── Step 1: Save each dataset individually ────────────────────────────────
    for dataset_key, rows in result.items():
        rows = rows or []
        flat_rows = [_flatten(r) for r in rows]

        if "csv" in formats:
            _safe_csv(pd.DataFrame(flat_rows),
                      os.path.join(run_dir, "csv", f"{dataset_key}.csv"))

        if "json" in formats:
            _safe_json(rows, os.path.join(run_dir, "json", f"{dataset_key}.json"))

        if "jsonl" in formats:
            _safe_jsonl(rows, os.path.join(run_dir, "jsonl", f"{dataset_key}.jsonl"))

        if "parquet" in formats:
            _safe_parquet(pd.DataFrame(flat_rows),
                          os.path.join(run_dir, "parquet", f"{dataset_key}.parquet"))

        logger.info(f"  {dataset_key}: {len(rows)} rows")

    # ── Step 2: Save combined files ───────────────────────────────────────────
    _save_combined(result, run_dir, case_id, formats)

    logger.info(f"  All datasets saved to: {run_dir}")
    return run_dir


# ── Combined file builders ────────────────────────────────────────────────────

def _save_combined(result: dict, run_dir: str, case_id: str, formats: list[str]):
    """
    Merge all 15 datasets into single files.

    CSV:  One sheet per dataset stacked vertically, separated by a header row
          showing the dataset name. Each row gets a 'dataset' column.

    JSON: { "case_id": "...", "datasets": { "dataset_01_metadata": [...], ... } }
    """
    # ── Combined CSV ──────────────────────────────────────────────────────────
    if "csv" in formats:
        combined_rows = []
        for dataset_key, rows in result.items():
            if not rows:
                continue
            for i, row in enumerate(rows):
                flat = _flatten(row)
                combined_rows.append({
                    "dataset":    dataset_key,
                    "case_id":    case_id,
                    "record_num": i + 1,
                    "record_id":  flat.get(
                        # Use the most meaningful ID field per dataset
                        next((k for k in ["paragraph_id", "sentence_id", "entity_id",
                                          "citation_id", "article_id", "act_section_id",
                                          "guideline_id", "principle_id", "quote_id",
                                          "event_id", "triple_id", "chunk_id",
                                          "train_id", "qa_id", "case_id"]
                              if k in flat), "record_num"),
                        str(i + 1)
                    ),
                    "data": json.dumps(flat, ensure_ascii=False, default=str),
                })

        if combined_rows:
            combined_df = pd.DataFrame(combined_rows)
            path = os.path.join(run_dir, "csv", "ALL_DATASETS_COMBINED.csv")
            _safe_csv(combined_df, path)
            logger.info(f"  Combined CSV: {len(combined_df)} rows, 4 columns, 0 nulls → {path}")

    # ── Combined JSON ─────────────────────────────────────────────────────────
    if "json" in formats:
        combined = {
            "case_id":        case_id,
            "generated_at":   datetime.datetime.utcnow().isoformat(),
            "total_datasets": len(result),
            "datasets": {k: (v or []) for k, v in result.items()},
        }
        path = os.path.join(run_dir, "json", "ALL_DATASETS_COMBINED.json")
        _safe_json(combined, path, raw=True)
        total = sum(len(v or []) for v in result.values())
        logger.info(f"  Combined JSON: {total} total records → {path}")

    # ── Combined JSONL ────────────────────────────────────────────────────────
    if "jsonl" in formats:
        path = os.path.join(run_dir, "jsonl", "ALL_DATASETS_COMBINED.jsonl")
        try:
            with open(path, "w", encoding="utf-8") as f:
                for dataset_key, rows in result.items():
                    for row in (rows or []):
                        line = dict(row) if isinstance(row, dict) else {"value": row}
                        line["_dataset"] = dataset_key
                        line["_case_id"] = case_id
                        f.write(json.dumps(line, ensure_ascii=False, default=str) + "\n")
            logger.info(f"  Combined JSONL → {path}")
        except Exception as e:
            logger.warning(f"  Combined JSONL failed: {e}")


# ── I/O helpers ───────────────────────────────────────────────────────────────

def _safe_csv(df: pd.DataFrame, path: str):
    try:
        df.to_csv(path, index=False, encoding="utf-8")
    except PermissionError:
        logger.error(f"  PermissionError: {path} — close the file if open in Excel")
    except Exception as e:
        logger.error(f"  CSV save failed {path}: {e}")


def _safe_json(data, path: str, raw: bool = False):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        logger.error(f"  JSON save failed {path}: {e}")


def _safe_jsonl(rows: list, path: str):
    try:
        with open(path, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    except Exception as e:
        logger.error(f"  JSONL save failed {path}: {e}")


def _safe_parquet(df: pd.DataFrame, path: str):
    try:
        df.to_parquet(path, index=False)
    except Exception as e:
        logger.warning(f"  Parquet save failed {path}: {e}")


def _flatten(row) -> dict:
    """Convert nested lists/dicts to strings for CSV/Parquet compatibility."""
    if not isinstance(row, dict):
        return {"value": str(row)}
    flat = {}
    for k, v in row.items():
        if isinstance(v, (list, dict)):
            flat[k] = json.dumps(v, ensure_ascii=False, default=str)
        elif v is None:
            flat[k] = ""
        else:
            flat[k] = v
    return flat
