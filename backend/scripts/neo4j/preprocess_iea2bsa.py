"""
preprocess_iea2bsa.py
======================
Step 1, Step 2, & Step 3 Pipeline for IEA <-> BSA Mapping, Source Validation, & Duplicate/Cardinality Analysis.

Performs:
1. Structural Mapping Validation
2. Hierarchy & Annotation Classification
3. Source Availability & Content-Gap Validation
4. Duplicate & Cardinality Mapping Analysis (mapping_type & cardinality tagging):
   - ONE_TO_ONE
   - MERGED / MANY_TO_ONE
   - SPLIT / ONE_TO_MANY
   - REMOVED / ONE_TO_ZERO
   - NEW_SECTION / ZERO_TO_ONE

Outputs:
- `data/cleaned/iea2bsa_clean.csv`
- `data/cleaned/iea2bsa_validation_report.json`
- `data/cleaned/iea_content_gap_report.json`
"""

import json
import logging
import re
import sys
import pandas as pd
from pathlib import Path

# ── Logging Setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("preprocess_iea2bsa")

# ── File Paths ────────────────────────────────────────────────────────────────
SCRIPT_PATH = Path(__file__).resolve()
BASE_DIR = SCRIPT_PATH.parents[3] if len(SCRIPT_PATH.parents) >= 4 else SCRIPT_PATH.parent.parent.parent

DATA_CLEANED_DIR = BASE_DIR / "data" / "cleaned"
RAW_MAPPING_CSV = BASE_DIR / "backend" / "all_acts" / "bsa" / "iea2bsa.csv"
IEA_CLEAN_CSV = DATA_CLEANED_DIR / "iea.csv"
BSA_SECTIONS_CSV = BASE_DIR / "backend" / "all_acts" / "bsa" / "bsa_sections.csv"

OUTPUT_CLEAN_CSV = DATA_CLEANED_DIR / "iea2bsa_clean.csv"
OUTPUT_VAL_REPORT = DATA_CLEANED_DIR / "iea2bsa_validation_report.json"
OUTPUT_GAP_REPORT = DATA_CLEANED_DIR / "iea_content_gap_report.json"


def clean_str(val: str) -> str:
    if val is None or pd.isna(val):
        return ""
    s = str(val).strip()
    return re.sub(r"\s+", " ", s)


def split_base_sec(sec_str: str) -> str:
    m = re.match(r"^(\d+[A-Za-z]*)", sec_str)
    return m.group(1) if m else sec_str


def classify_category_and_type(iea_sec: str, bsa_sec: str, notes: str) -> tuple[str, str, str]:
    bsa_upper = bsa_sec.upper()
    iea_upper = iea_sec.upper()
    notes_upper = notes.upper()

    if bsa_upper in {"REMOVED", "DELETED", "REPEALED"}:
        return "REMOVED", "SPECIAL_STATUS", ""

    if iea_upper in {"NEW", "NEW SECTION", "N/A", "NOT APPLICABLE", ""}:
        base = split_base_sec(bsa_sec)
        node_type = "SECTION" if not ("(" in bsa_sec and ")" in bsa_sec) else ("CLAUSE" if re.search(r"\([A-Za-z]\)", bsa_sec) else "SUBSECTION")
        return "NEW_SECTION", node_type, base

    if "Subs" in notes or "Ins" in notes or "AMENDMENT" in notes_upper:
        base = split_base_sec(bsa_sec)
        return "AMENDMENT_ANNOTATION", "SUBSECTION", base

    if "EXPL" in bsa_upper or "EXPLANATION" in notes_upper:
        base = split_base_sec(bsa_sec)
        return "EXPLANATION", "EXPLANATION", base

    if "PROVISO" in notes_upper or "PROVISO" in bsa_upper:
        base = split_base_sec(bsa_sec)
        return "PROVISO", "SUBSECTION", base

    if "ILLUSTRATION" in notes_upper:
        base = split_base_sec(bsa_sec)
        return "ILLUSTRATION", "SUBSECTION", base

    if "EXCEPTION" in notes_upper:
        base = split_base_sec(bsa_sec)
        return "EXCEPTION", "SUBSECTION", base

    if "(" in bsa_sec and ")" in bsa_sec:
        base = split_base_sec(bsa_sec)
        if re.search(r"\([A-Za-z]\)", bsa_sec):
            return "CLAUSE", "CLAUSE", base
        return "SUBSECTION", "SUBSECTION", base

    return "PLAIN", "SECTION", bsa_sec


def run_pipeline() -> tuple[pd.DataFrame, dict, dict]:
    logger.info("=== Starting Step 1, Step 2, & Step 3 Pipeline for IEA <-> BSA Mappings ===")

    # 1. Load Datasets
    df_raw = pd.read_csv(RAW_MAPPING_CSV, dtype=str).fillna("")
    logger.info(f"Loaded raw mapping dataset: {len(df_raw)} rows.")

    if IEA_CLEAN_CSV.exists():
        df_iea_clean = pd.read_csv(IEA_CLEAN_CSV, dtype=str).fillna("")
        iea_available_secs = set(df_iea_clean["section"].str.strip())
    else:
        iea_available_secs = set()

    # Pre-pass: Compute Cardinalities
    iea_counts = {}
    bsa_base_counts = {}

    for idx, r in df_raw.iterrows():
        iea_sec = clean_str(r.get("IEA Section"))
        bsa_sec = clean_str(r.get("BSA Section"))

        if iea_sec.upper() not in {"NEW", "N/A", "NOT APPLICABLE", ""}:
            iea_counts[iea_sec] = iea_counts.get(iea_sec, 0) + 1

        if bsa_sec.upper() not in {"REMOVED", "DELETED", "REPEALED", "N/A", "NOT APPLICABLE", ""}:
            base = split_base_sec(bsa_sec)
            bsa_base_counts[base] = bsa_base_counts.get(base, 0) + 1

    processed_rows = []
    gap_rows = []
    cat_counts = {}
    mapping_type_counts = {}
    cardinality_counts = {}

    for idx, r in df_raw.iterrows():
        iea_sec = clean_str(r.get("IEA Section"))
        iea_subj = clean_str(r.get("IEA Subject"))
        bsa_sec = clean_str(r.get("BSA Section"))
        bsa_subj = clean_str(r.get("BSA Subject"))
        notes = clean_str(r.get("Key Changes / Notes"))

        category, node_type, parent_sec = classify_category_and_type(iea_sec, bsa_sec, notes)
        cat_counts[category] = cat_counts.get(category, 0) + 1

        # Classify Mapping Type (Cardinality & Evolution Tags)
        if category == "REMOVED":
            mapping_type = "REMOVED"
            cardinality = "ONE_TO_ZERO"
        elif category == "NEW_SECTION":
            mapping_type = "NEW_SECTION"
            cardinality = "ZERO_TO_ONE"
        else:
            base_bsa = split_base_sec(bsa_sec)
            iea_c = iea_counts.get(iea_sec, 1)
            bsa_c = bsa_base_counts.get(base_bsa, 1)

            if iea_c > 1 and bsa_c > 1:
                mapping_type = "MERGED"
                cardinality = "MANY_TO_MANY"
            elif iea_c > 1:
                mapping_type = "SPLIT"
                cardinality = "ONE_TO_MANY"
            elif bsa_c > 1:
                mapping_type = "MERGED"
                cardinality = "MANY_TO_ONE"
            else:
                mapping_type = "ONE_TO_ONE"
                cardinality = "ONE_TO_ONE"

        mapping_type_counts[mapping_type] = mapping_type_counts.get(mapping_type, 0) + 1
        cardinality_counts[cardinality] = cardinality_counts.get(cardinality, 0) + 1

        # Check content availability for IEA
        if category in {"REMOVED", "NEW_SECTION"}:
            content_available = "NO"
            content_source = "not_applicable"
            requires_backfill = "NO"
            data_complete = "false"
        else:
            if iea_sec in iea_available_secs:
                content_available = "YES"
                content_source = "source_dataset"
                requires_backfill = "NO"
                data_complete = "true"
            else:
                content_available = "NO"
                content_source = "mapping_title_only"
                requires_backfill = "YES"
                data_complete = "false"
                gap_rows.append({
                    "iea_section": iea_sec,
                    "iea_subject": iea_subj,
                    "bsa_section": bsa_sec,
                    "category": category,
                })

        processed_rows.append({
            "IEA_Section": iea_sec,
            "IEA_Title": iea_subj,
            "BSA_Section_Raw": bsa_sec,
            "BSA_Section_Clean": bsa_sec,
            "BSA_Title": bsa_subj,
            "Category": category,
            "NodeType": node_type,
            "ParentSection": parent_sec,
            "mapping_type": mapping_type,
            "cardinality": cardinality,
            "Notes": notes,
            "content_available": content_available,
            "content_source": content_source,
            "requires_backfill": requires_backfill,
            "data_complete": data_complete,
        })

    df_processed = pd.DataFrame(processed_rows)

    # Save iea2bsa_clean.csv
    OUTPUT_CLEAN_CSV.parent.mkdir(parents=True, exist_ok=True)
    df_processed.to_csv(OUTPUT_CLEAN_CSV, index=False)
    logger.info(f"Saved cleaned IEA <-> BSA mappings to {OUTPUT_CLEAN_CSV} ({len(df_processed)} rows).")

    # Generate iea2bsa_validation_report.json
    val_report = {
        "total_rows": len(df_processed),
        "total_iea_sections_mapped": len([x for x in df_processed["IEA_Section"] if x.upper() not in {"NEW", "N/A", "NOT APPLICABLE", ""}]),
        "total_bsa_sections_mapped": len([x for x in df_processed["BSA_Section_Clean"] if x.upper() not in {"REMOVED", "DELETED", "REPEALED", "N/A", "NOT APPLICABLE", ""}]),
        "category_breakdown": cat_counts,
        "mapping_type_breakdown": mapping_type_counts,
        "cardinality_breakdown": cardinality_counts,
        "content_source_breakdown": df_processed["content_source"].value_counts().to_dict(),
        "requires_backfill_count": len(gap_rows),
        "data_complete_true_count": len(df_processed[df_processed["data_complete"] == "true"]),
        "data_complete_false_count": len(df_processed[df_processed["data_complete"] == "false"]),
        "merged_provisions": df_processed[df_processed["mapping_type"] == "MERGED"][["IEA_Section", "IEA_Title", "BSA_Section_Clean", "BSA_Title", "Notes"]].to_dict(orient="records"),
        "removed_sections": df_processed[df_processed["Category"] == "REMOVED"][["IEA_Section", "IEA_Title", "Notes"]].to_dict(orient="records"),
        "new_sections": df_processed[df_processed["Category"] == "NEW_SECTION"][["BSA_Section_Clean", "BSA_Title", "Notes"]].to_dict(orient="records"),
    }

    with open(OUTPUT_VAL_REPORT, "w", encoding="utf-8") as f:
        json.dump(val_report, f, indent=2)
    logger.info(f"Saved validation report to {OUTPUT_VAL_REPORT}.")

    # Generate iea_content_gap_report.json
    gap_report = {
        "total_mappings": len(df_processed),
        "content_gaps_count": len(gap_rows),
        "content_gaps": gap_rows,
        "status": "NO_GAPS" if len(gap_rows) == 0 else "GAPS_DETECTED",
    }

    with open(OUTPUT_GAP_REPORT, "w", encoding="utf-8") as f:
        json.dump(gap_report, f, indent=2)
    logger.info(f"Saved content gap report to {OUTPUT_GAP_REPORT}.")

    logger.info("=== Preprocessing & Mapping Type Analysis Completed Successfully ===")
    return df_processed, val_report, gap_report


if __name__ == "__main__":
    run_pipeline()
