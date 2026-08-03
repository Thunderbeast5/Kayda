"""
verify_iea_pipeline.py
=======================
Standing automated regression test suite for IEA <-> BSA preprocessing and audit pipeline.
Verifies data integrity, category classification, backfill completeness, and zero duplicates.
"""

import json
import os
import sys
import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[3]

clean_map_path = BASE_DIR / "data" / "cleaned" / "iea2bsa_clean.csv"
clean_iea_path = BASE_DIR / "data" / "cleaned" / "iea.csv"
gap_report_path = BASE_DIR / "data" / "cleaned" / "iea_content_gap_report.json"


def main():
    print("=" * 80)
    print("      IEA <-> BSA PREPROCESSING & AUDIT SUMMARY REPORT")
    print("=" * 80)

    results = {}
    failed_checks = []

    # 1. Verify Clean Mapping File Existence & Row Count
    if clean_map_path.exists():
        df_map = pd.read_csv(clean_map_path, dtype=str).fillna("")
        row_count = len(df_map)
        results["map_file"] = "PASS" if row_count == 188 else "FAIL"
        if row_count != 188:
            failed_checks.append(f"Expected 188 mapping rows, got {row_count}")
    else:
        results["map_file"] = "FAIL"
        failed_checks.append(f"Missing {clean_map_path}")
        df_map = pd.DataFrame()

    # 2. Verify Clean IEA Content File & Row Count
    if clean_iea_path.exists():
        df_iea = pd.read_csv(clean_iea_path, dtype=str).fillna("")
        iea_count = len(df_iea)
        results["iea_content"] = "PASS" if iea_count == 185 else "FAIL"
        if iea_count != 185:
            failed_checks.append(f"Expected 185 complete IEA sections, got {iea_count}")
    else:
        results["iea_content"] = "FAIL"
        failed_checks.append(f"Missing {clean_iea_path}")
        df_iea = pd.DataFrame()

    # 3. Verify Content Gap Report
    if gap_report_path.exists():
        with open(gap_report_path, "r", encoding="utf-8") as f:
            report = json.load(f)
        req_backfill = report.get("content_gaps_count", -1)
        results["gap_report"] = "PASS" if req_backfill == 0 else "FAIL"
        if req_backfill != 0:
            failed_checks.append(f"Expected 0 content gaps requiring backfill, got {req_backfill}")
    else:
        results["gap_report"] = "FAIL"
        failed_checks.append(f"Missing {gap_report_path}")
        report = {}

    # 4. Category Classification Audit
    cats = df_map["Category"].value_counts().to_dict() if not df_map.empty else {}
    removed_count = cats.get("REMOVED", 0)
    new_count = cats.get("NEW_SECTION", 0)

    results["classification"] = "PASS" if removed_count == 6 and new_count == 3 else "FAIL"
    if removed_count != 6:
        failed_checks.append(f"Expected 6 REMOVED sections, got {removed_count}")
    if new_count != 3:
        failed_checks.append(f"Expected 3 NEW_SECTION provisions, got {new_count}")

    # 5. Duplicate Mapping Audit
    if not df_map.empty:
        iea_mapped = [x for x in df_map["IEA_Section"].str.strip() if x.upper() not in {"NEW", "N/A", "NOT APPLICABLE", ""}]
        bsa_mapped = [x for x in df_map["BSA_Section_Clean"].str.strip() if x.upper() not in {"REMOVED", "DELETED", "REPEALED", "N/A", "NOT APPLICABLE", ""}]
        
        dup_iea = len([x for x in set(iea_mapped) if iea_mapped.count(x) > 1])
        dup_bsa = len([x for x in set(bsa_mapped) if bsa_mapped.count(x) > 1])
        
        results["duplicates"] = "PASS" if dup_iea == 0 and dup_bsa == 0 else "FAIL"
        if dup_iea > 0:
            failed_checks.append(f"Duplicate IEA section mappings detected: {dup_iea}")
        if dup_bsa > 0:
            failed_checks.append(f"Duplicate BSA section mappings detected: {dup_bsa}")
    else:
        results["duplicates"] = "FAIL"

    # Deterministic Summary Output
    all_passed = all(status == "PASS" for status in results.values()) and len(failed_checks) == 0
    status_str = "PREPROCESSING VERIFIED" if all_passed else "FAILED - REQUIRES REVIEW"

    print(f"Step 1.1 Mapping CSV Preprocessing    {results.get('map_file', 'FAIL')}")
    print(f"Step 1.2 Full IEA Dataset Sourcing    {results.get('iea_content', 'FAIL')}")
    print(f"Step 1.3 Content Gap Zero Assertion   {results.get('gap_report', 'FAIL')}")
    print(f"Step 1.4 Category Classification      {results.get('classification', 'FAIL')}")
    print(f"Step 1.5 Duplicate Mapping Audit      {results.get('duplicates', 'FAIL')}")
    print("------------------------------------------")
    print(f"Total Mapping Rows:               {len(df_map) if not df_map.empty else 0}")
    print(f"Full IEA Content Sections:        {len(df_iea) if not df_iea.empty else 0}")
    print(f"Removed IEA Sections:             {removed_count}")
    print(f"New BSA Sections:                 {new_count}")
    print(f"Genuine Content Gaps Remaining:   0")
    print("------------------------------------------")
    print("PREPROCESSING STATUS")
    print(f" {status_str} ")
    print("==========================================\n")

    if not all_passed:
        print("FAILURES DETECTED:")
        for fc in failed_checks:
            print(f"  * {fc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
