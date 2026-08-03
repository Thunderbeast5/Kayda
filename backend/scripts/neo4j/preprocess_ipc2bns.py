"""
preprocess_ipc2bns.py
======================
Step 1 Preprocessing Pipeline for IPC <-> BNS Mapping Data.

Performs data cleaning, normalization, section/subsection classification,
compound target splitting, duplicate detection, and parent section validation
on raw `ipc2bns.csv` against `bns_sections_clean.csv`.

Independent of Neo4j (no DB connections or Cypher execution).
"""

from __future__ import annotations

import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

import pandas as pd

# ── Logging Setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("preprocess_ipc2bns")

# ── File Paths ────────────────────────────────────────────────────────────────
# Project root is c:\proj\MootCourt (4 levels up from this script)
SCRIPT_PATH = Path(__file__).resolve()
BASE_DIR = SCRIPT_PATH.parents[3] if len(SCRIPT_PATH.parents) >= 4 else SCRIPT_PATH.parent.parent.parent

# Candidate locations for data/cleaned
data_clean_candidates = [
    BASE_DIR / "data" / "cleaned",
    BASE_DIR.parent / "data" / "cleaned",
    Path("data/cleaned"),
]
DATA_CLEANED_DIR = next((p for p in data_clean_candidates if p.exists()), BASE_DIR / "data" / "cleaned")

IPC2BNS_RAW_CSV = DATA_CLEANED_DIR / "ipc2bns.csv"
BNS_CLEAN_CSV = DATA_CLEANED_DIR / "bns_sections_clean.csv"

OUTPUT_CLEAN_CSV = DATA_CLEANED_DIR / "ipc2bns_clean.csv"
OUTPUT_REPORT_CSV = DATA_CLEANED_DIR / "ipc2bns_validation_report.csv"

SPECIAL_STATUS_TOKENS = {"REMOVED", "DELETED", "REPEALED", "N/A", "NA", "NAN", "NONE", ""}


def load_and_validate_inputs(
    ipc2bns_path: Path, bns_clean_path: Path
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Loads raw IPC-BNS mapping and cleaned BNS sections CSVs, validating column presence.

    Args:
        ipc2bns_path: Path to raw ipc2bns.csv file.
        bns_clean_path: Path to cleaned bns_sections_clean.csv file.

    Returns:
        Tuple of (ipc2bns_df, bns_clean_df).

    Raises:
        FileNotFoundError: If any required file does not exist.
        ValueError: If mandatory columns are missing.
    """
    logger.info("Task 1: Loading input CSV files...")
    if not ipc2bns_path.exists():
        raise FileNotFoundError(f"Missing required input file: {ipc2bns_path}")
    if not bns_clean_path.exists():
        raise FileNotFoundError(f"Missing required input file: {bns_clean_path}")

    ipc2bns_df = pd.read_csv(ipc2bns_path, dtype=str).fillna("")
    bns_clean_df = pd.read_csv(bns_clean_path, dtype=str).fillna("")

    # Validate columns
    required_ipc2bns_cols = ["IPC_Section", "IPC_Title", "BNS_Section", "BNS_Title"]
    missing_ipc_cols = [col for col in required_ipc2bns_cols if col not in ipc2bns_df.columns]
    if missing_ipc_cols:
        raise ValueError(f"ipc2bns.csv missing required columns: {missing_ipc_cols}")

    if "Section" not in bns_clean_df.columns:
        raise ValueError("bns_sections_clean.csv missing required column 'Section'")

    logger.info(
        f"Input files loaded successfully. Raw mappings: {len(ipc2bns_df)} rows, "
        f"BNS reference sections: {len(bns_clean_df)} rows."
    )
    return ipc2bns_df, bns_clean_df


def normalize_text(text: Any) -> str:
    """Normalizes string value by trimming whitespace, collapsing multiple spaces, and upper-casing keywords."""
    if text is None or pd.isna(text):
        return ""
    s = str(text).strip()
    s = re.sub(r"\s+", " ", s)
    return s


def normalize_dataset(df: pd.DataFrame) -> pd.DataFrame:
    """Normalizes all columns in the dataframe."""
    logger.info("Task 2: Normalizing string values, whitespaces, and casing...")
    norm_df = df.copy()
    for col in norm_df.columns:
        norm_df[col] = norm_df[col].apply(normalize_text)

    # Standardize casing for BNS_Section keywords
    def standardize_bns_section(val: str) -> str:
        u = val.upper()
        if u in {"REMOVED", "DELETED", "REPEALED", "N/A", "NA", "NONE"}:
            return u
        # Replace EXPL variants with EXPL.
        val_clean = re.sub(r"\(\s*(?:EXPL|EXPLANATION)\.?\s*\)", "(EXPL.)", val, flags=re.IGNORECASE)
        return val_clean

    norm_df["BNS_Section"] = norm_df["BNS_Section"].apply(standardize_bns_section)
    return norm_df


def split_compound_targets(df: pd.DataFrame) -> pd.DataFrame:
    """Splits compound target entries (e.g. '2(19) & 2(35)') into individual rows with duplicated IPC metadata."""
    logger.info("Task 4: Handling compound BNS section targets...")
    split_rows: List[Dict[str, str]] = []
    compound_count = 0

    for idx, row in df.iterrows():
        bns_target_raw = row["BNS_Section"]
        u = bns_target_raw.upper()

        if u in SPECIAL_STATUS_TOKENS:
            row_dict = row.to_dict()
            row_dict["BNS_Section_Raw"] = bns_target_raw
            row_dict["BNS_Section_Clean"] = bns_target_raw
            split_rows.append(row_dict)
            continue

        # Split on & , ; or word 'and'
        parts = [
            p.strip()
            for p in re.split(r"\s*(?:&|,|;|\band\b)\s*", bns_target_raw, flags=re.IGNORECASE)
            if p.strip()
        ]

        if len(parts) > 1:
            compound_count += 1
            for part in parts:
                row_dict = row.to_dict()
                row_dict["BNS_Section_Raw"] = bns_target_raw
                row_dict["BNS_Section_Clean"] = part
                split_rows.append(row_dict)
        else:
            row_dict = row.to_dict()
            row_dict["BNS_Section_Raw"] = bns_target_raw
            row_dict["BNS_Section_Clean"] = bns_target_raw
            split_rows.append(row_dict)

    result_df = pd.DataFrame(split_rows)
    logger.info(f"Split {compound_count} compound target rows into {len(result_df)} single-target mapping rows.")
    return result_df


def parse_and_classify_target(target: str) -> Dict[str, str]:
    """Classifies BNS target identifier and extracts structural properties.

    Node Types:
      - SPECIAL_STATUS: REMOVED, DELETED, REPEALED, N/A, empty
      - EXPLANATION: e.g. 5(EXPL.)
      - CLAUSE: e.g. 137(1)(A) or 125(A)
      - SUBSECTION: e.g. 8(1), 103(2), 2(19)
      - SECTION: e.g. 302, 103, 4
      - UNKNOWN: Unmatched target format
    """
    t = normalize_text(target)
    u = t.upper()

    if u in SPECIAL_STATUS_TOKENS:
        return {
            "NodeType": "SPECIAL_STATUS",
            "ParentSection": "",
            "ParentSubsection": "",
            "SubsectionNumber": "",
            "Clause": "",
        }

    # 1. EXPLANATION: e.g. 5(EXPL.) or 5 (EXPL.)
    m_exp = re.match(r"^(\d+[A-Z]*)\s*\((?:EXPL|EXPLANATION)\.?\)$", u)
    if m_exp:
        sec = m_exp.group(1)
        return {
            "NodeType": "EXPLANATION",
            "ParentSection": sec,
            "ParentSubsection": sec,
            "SubsectionNumber": "",
            "Clause": "",
        }

    # 2. CLAUSE: e.g. 137(1)(A)
    m_clause1 = re.match(r"^(\d+[A-Z]*)\(([0-9]+)\)\(([A-Z]+)\)$", u)
    if m_clause1:
        sec, sub, cl = m_clause1.group(1), m_clause1.group(2), m_clause1.group(3)
        return {
            "NodeType": "CLAUSE",
            "ParentSection": sec,
            "ParentSubsection": f"{sec}({sub})",
            "SubsectionNumber": sub,
            "Clause": cl,
        }

    # CLAUSE without sub: e.g. 125(A)
    m_clause2 = re.match(r"^(\d+[A-Z]*)\(([A-Z]+)\)$", u)
    if m_clause2:
        sec, cl = m_clause2.group(1), m_clause2.group(2)
        return {
            "NodeType": "CLAUSE",
            "ParentSection": sec,
            "ParentSubsection": sec,
            "SubsectionNumber": "",
            "Clause": cl,
        }

    # 3. SUBSECTION: e.g. 8(1), 103(2)
    m_sub = re.match(r"^(\d+[A-Z]*)\(([0-9]+)\)$", u)
    if m_sub:
        sec, sub = m_sub.group(1), m_sub.group(2)
        return {
            "NodeType": "SUBSECTION",
            "ParentSection": sec,
            "ParentSubsection": f"{sec}({sub})",
            "SubsectionNumber": sub,
            "Clause": "",
        }

    # 4. SECTION: e.g. 302, 103, 4
    m_sec = re.match(r"^(\d+[A-Z]*)$", u)
    if m_sec:
        sec = m_sec.group(1)
        return {
            "NodeType": "SECTION",
            "ParentSection": sec,
            "ParentSubsection": sec,
            "SubsectionNumber": "",
            "Clause": "",
        }

    return {
        "NodeType": "UNKNOWN",
        "ParentSection": "",
        "ParentSubsection": "",
        "SubsectionNumber": "",
        "Clause": "",
    }


def classify_mappings(df: pd.DataFrame) -> pd.DataFrame:
    """Applies node classification and structural property extraction to every row."""
    logger.info("Task 3: Classifying mapping node types and extracting parent/subsection/clause attributes...")
    classified_df = df.copy()

    node_types: List[str] = []
    parent_secs: List[str] = []
    parent_subsecs: List[str] = []
    subsec_nums: List[str] = []
    clauses: List[str] = []

    for _, row in classified_df.iterrows():
        target = row["BNS_Section_Clean"]
        info = parse_and_classify_target(target)
        node_types.append(info["NodeType"])
        parent_secs.append(info["ParentSection"])
        parent_subsecs.append(info["ParentSubsection"])
        subsec_nums.append(info["SubsectionNumber"])
        clauses.append(info["Clause"])

    classified_df["NodeType"] = node_types
    classified_df["ParentSection"] = parent_secs
    classified_df["ParentSubsection"] = parent_subsecs
    classified_df["SubsectionNumber"] = subsec_nums
    classified_df["Clause"] = clauses

    return classified_df


def validate_parent_sections(df: pd.DataFrame, bns_clean_df: pd.DataFrame) -> pd.DataFrame:
    """Validates that extracted ParentSection exists inside bns_sections_clean.csv."""
    logger.info("Task 6: Validating parent section existence against bns_sections_clean.csv...")
    valid_bns_sections: Set[str] = set(bns_clean_df["Section"].astype(str).str.strip().unique())

    val_df = df.copy()
    val_statuses: List[str] = []

    for _, row in val_df.iterrows():
        node_type = row["NodeType"]
        parent = row["ParentSection"]

        if node_type == "SPECIAL_STATUS":
            val_statuses.append("SPECIAL_STATUS")
        elif node_type == "UNKNOWN":
            val_statuses.append("INVALID_FORMAT")
        elif parent in valid_bns_sections:
            val_statuses.append("VALID")
        else:
            val_statuses.append("MISSING_PARENT")

    val_df["ValidationStatus"] = val_statuses
    return val_df


def detect_duplicates_and_manual_reviews(df: pd.DataFrame) -> pd.DataFrame:
    """Detects duplicate BNS subsection IDs, records tie-breakers, and flags manual review requirements."""
    logger.info("Task 5 & 7: Detecting duplicate subsection mappings and assigning metadata flags...")
    proc_df = df.copy()

    # Filter out special status / empty targets for duplicate grouping
    valid_mask = ~proc_df["NodeType"].isin(["SPECIAL_STATUS", "UNKNOWN"])
    target_counts = proc_df[valid_mask]["BNS_Section_Clean"].value_counts()
    duplicate_targets = set(target_counts[target_counts > 1].index)

    dup_groups: List[str] = []
    manual_reviews: List[str] = []

    for _, row in proc_df.iterrows():
        target = row["BNS_Section_Clean"]
        if target in duplicate_targets:
            dup_groups.append(f"DUP_{target}")
            manual_reviews.append("YES")
        else:
            dup_groups.append("NONE")
            manual_reviews.append("NO")

    proc_df["DuplicateGroup"] = dup_groups
    proc_df["RequiresManualReview"] = manual_reviews

    return proc_df


def generate_validation_report(
    raw_df: pd.DataFrame, clean_df: pd.DataFrame, report_path: Path
) -> pd.DataFrame:
    """Generates detailed validation report and console summary."""
    logger.info("Task 9: Generating validation report CSV and summary statistics...")

    total_raw_rows = len(raw_df)
    total_clean_rows = len(clean_df)

    node_type_counts = clean_df["NodeType"].value_counts().to_dict()
    val_status_counts = clean_df["ValidationStatus"].value_counts().to_dict()

    dup_mask = clean_df["DuplicateGroup"] != "NONE"
    duplicate_rows = clean_df[dup_mask]
    unique_dup_targets = duplicate_rows["BNS_Section_Clean"].nunique()

    missing_parent_rows = clean_df[clean_df["ValidationStatus"] == "MISSING_PARENT"]
    unknown_type_rows = clean_df[clean_df["NodeType"] == "UNKNOWN"]

    report_records = [
        {"Metric": "Total Raw Rows Processed", "Value": total_raw_rows},
        {"Metric": "Total Expanded Clean Rows", "Value": total_clean_rows},
        {"Metric": "Valid Mappings Count", "Value": val_status_counts.get("VALID", 0)},
        {"Metric": "Special Status Mappings Count", "Value": val_status_counts.get("SPECIAL_STATUS", 0)},
        {"Metric": "Missing Parent Mappings Count", "Value": val_status_counts.get("MISSING_PARENT", 0)},
        {"Metric": "Invalid Format / Unknown Mappings", "Value": val_status_counts.get("INVALID_FORMAT", 0)},
        {"Metric": "SECTION Node Type Count", "Value": node_type_counts.get("SECTION", 0)},
        {"Metric": "SUBSECTION Node Type Count", "Value": node_type_counts.get("SUBSECTION", 0)},
        {"Metric": "CLAUSE Node Type Count", "Value": node_type_counts.get("CLAUSE", 0)},
        {"Metric": "EXPLANATION Node Type Count", "Value": node_type_counts.get("EXPLANATION", 0)},
        {"Metric": "SPECIAL_STATUS Node Type Count", "Value": node_type_counts.get("SPECIAL_STATUS", 0)},
        {"Metric": "UNKNOWN Node Type Count", "Value": node_type_counts.get("UNKNOWN", 0)},
        {"Metric": "Unique Duplicate BNS Target IDs", "Value": unique_dup_targets},
        {"Metric": "Total Rows Flagged for Manual Review", "Value": len(duplicate_rows)},
    ]

    report_df = pd.DataFrame(report_records)
    report_df.to_csv(report_path, index=False)
    logger.info(f"Validation report saved to: {report_path}")

    # Print summary table to console
    print("\n" + "=" * 80)
    print(" IPC <-> BNS PREPROCESSING & VALIDATION SUMMARY REPORT")
    print("=" * 80)
    for rec in report_records:
        print(f"  {rec['Metric']:<42} : {rec['Value']}")
    print("-" * 80)

    if not duplicate_rows.empty:
        print(f"\n[!] Duplicate BNS Targets requiring manual review ({unique_dup_targets} unique targets):")
        grouped = duplicate_rows.groupby("BNS_Section_Clean")["IPC_Section"].apply(list).to_dict()
        for bns_id, ipc_list in list(grouped.items())[:15]:  # Display first 15
            print(f"  - BNS '{bns_id}' mapped from IPC sections: {ipc_list}")
        if len(grouped) > 15:
            print(f"  ... and {len(grouped) - 15} more duplicate targets.")

    if not missing_parent_rows.empty:
        print(f"\n[!] Missing Parent BNS Sections ({len(missing_parent_rows)} rows):")
        for _, r in missing_parent_rows.iterrows():
            print(f"  - IPC {r['IPC_Section']} -> BNS {r['BNS_Section_Clean']} (Parent '{r['ParentSection']}' not found)")

    print("=" * 80 + "\n")
    return report_df


def run_pipeline() -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Executes the end-to-end preprocessing pipeline for IPC <-> BNS mapping dataset."""
    logger.info("=== Starting Step 1 Preprocessing Pipeline for IPC <-> BNS Mappings ===")

    # Task 1: Load and Validate Inputs
    raw_ipc2bns_df, bns_clean_df = load_and_validate_inputs(IPC2BNS_RAW_CSV, BNS_CLEAN_CSV)

    # Task 2: Normalize All Data
    norm_df = normalize_dataset(raw_ipc2bns_df)

    # Task 4: Split Compound Targets
    split_df = split_compound_targets(norm_df)

    # Task 3: Classify Mapping Node Types & Extract Attributes
    classified_df = classify_mappings(split_df)

    # Task 6: Validate Parent Sections
    validated_df = validate_parent_sections(classified_df, bns_clean_df)

    # Task 5 & 7: Detect Duplicates & Flag Manual Reviews
    final_df = detect_duplicates_and_manual_reviews(validated_df)

    # Reorder columns cleanly for final output
    output_cols = [
        "IPC_Section",
        "IPC_Title",
        "BNS_Section_Raw",
        "BNS_Section_Clean",
        "BNS_Title",
        "Notes",
        "NodeType",
        "ParentSection",
        "ParentSubsection",
        "SubsectionNumber",
        "Clause",
        "ValidationStatus",
        "DuplicateGroup",
        "RequiresManualReview",
    ]

    # Include any extra columns if present
    for col in final_df.columns:
        if col not in output_cols and col != "BNS_Section":
            output_cols.append(col)

    final_output_df = final_df[output_cols].copy()

    # Task 8: Generate Clean Output File
    logger.info(f"Task 8: Writing cleaned dataset to {OUTPUT_CLEAN_CSV}...")
    OUTPUT_CLEAN_CSV.parent.mkdir(parents=True, exist_ok=True)
    final_output_df.to_csv(OUTPUT_CLEAN_CSV, index=False)
    logger.info(f"Saved {len(final_output_df)} cleaned mapping rows to {OUTPUT_CLEAN_CSV}.")

    # Task 9: Generate Validation Report
    report_df = generate_validation_report(raw_ipc2bns_df, final_output_df, OUTPUT_REPORT_CSV)

    logger.info("=== Step 1 Preprocessing Pipeline Complete ===")
    return final_output_df, report_df


if __name__ == "__main__":
    run_pipeline()
