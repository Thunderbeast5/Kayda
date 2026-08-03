"""
preprocess_crpc2bnss.py
=======================
Step 1 of BNSS <-> CrPC Pipeline.

Reads backend/all_acts/bnss/crpc2bnss.csv, cleans, classifies, and validates mapping data.
Outputs:
  - data/cleaned/crpc2bnss_clean.csv
  - data/cleaned/crpc2bnss_validation_report.json

Enforces hard assertions:
  - Deleted CrPC sections (BNSS == 'Removed'): 11
  - New BNSS sections (CrPC == 'Not Applicable'): 5
  - Real hierarchy nodes: 3 (BNSS_35(1), BNSS_35(3), BNSS_37(c))
  - Amendment annotations: 2 (BNSS_396(Subs), BNSS_397(Subs))
"""

import json
import re
import sys
import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[3]
INPUT_CSV = BASE_DIR / "backend" / "all_acts" / "bnss" / "crpc2bnss.csv"
OUTPUT_DIR = BASE_DIR / "data" / "cleaned"
OUTPUT_CSV = OUTPUT_DIR / "crpc2bnss_clean.csv"
REPORT_JSON = OUTPUT_DIR / "crpc2bnss_validation_report.json"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Regex for amendment annotations like (Subs), (Ins), (Am), (Rep), (Ren)
AMENDMENT_REGEX = re.compile(r"^(\d+[A-Za-z]*)\((Subs|Ins|Am|Rep|Ren)\)$", re.IGNORECASE)
# Regex for sub-nodes with numeric subsection or letter clause
SUBSECTION_REGEX = re.compile(r"^(\d+[A-Za-z]*)\((\d+[A-Za-z]*)\)$")
CLAUSE_REGEX = re.compile(r"^(\d+[A-Za-z]*)\(([a-zA-Z])\)$")


def clean_str(val) -> str:
    if pd.isna(val) or val is None:
        return ""
    s = str(val).strip()
    return "" if s.lower() in ["nan", "none", "null"] else s


def classify_row(crpc_sec: str, bnss_sec: str):
    crpc_clean = clean_str(crpc_sec)
    bnss_clean = clean_str(bnss_sec)

    # 1. Removed / Deleted CrPC section
    if bnss_clean.lower() in ["removed", "deleted", "n/a", "na", "-"]:
        return {
            "Category": "REMOVED",
            "NodeType": "SPECIAL_STATUS",
            "BNSS_Clean": "REMOVED",
            "ParentSection": "",
            "SubsectionNumber": "",
            "Clause": "",
            "AmendmentType": "",
            "Notes": "Deleted CrPC Section (No BNSS Successor)",
        }

    # 2. Check Amendment Annotations like 396(Subs), 397(Subs)
    am_match = AMENDMENT_REGEX.match(bnss_clean)
    if am_match:
        base_sec = am_match.group(1)
        ann_type = am_match.group(2)
        return {
            "Category": "AMENDMENT_ANNOTATION",
            "NodeType": "SECTION",
            "BNSS_Clean": base_sec,
            "ParentSection": "",
            "SubsectionNumber": "",
            "Clause": "",
            "AmendmentType": ann_type.lower(),
            "Notes": f"Legislative history annotation: {ann_type} mapped to base section {base_sec}",
        }

    # 3. Check New Section (CrPC Not Applicable) - can also be a Clause/Subsection (e.g. 37(c))
    if crpc_clean.lower() in ["not applicable", "n/a", "na", "-"]:
        cl_match = CLAUSE_REGEX.match(bnss_clean)
        sub_match = SUBSECTION_REGEX.match(bnss_clean)
        
        if cl_match:
            base_sec = cl_match.group(1)
            clause_ltr = cl_match.group(2)
            return {
                "Category": "NEW_SECTION",
                "NodeType": "CLAUSE",
                "BNSS_Clean": bnss_clean,
                "ParentSection": base_sec,
                "SubsectionNumber": "",
                "Clause": clause_ltr,
                "AmendmentType": "",
                "Notes": f"New BNSS Clause under {base_sec} (No CrPC Predecessor)",
            }
        elif sub_match:
            base_sec = sub_match.group(1)
            sub_num = sub_match.group(2)
            return {
                "Category": "NEW_SECTION",
                "NodeType": "SUBSECTION",
                "BNSS_Clean": bnss_clean,
                "ParentSection": base_sec,
                "SubsectionNumber": sub_num,
                "Clause": "",
                "AmendmentType": "",
                "Notes": f"New BNSS Subsection under {base_sec} (No CrPC Predecessor)",
            }
        else:
            return {
                "Category": "NEW_SECTION",
                "NodeType": "SECTION",
                "BNSS_Clean": bnss_clean,
                "ParentSection": "",
                "SubsectionNumber": "",
                "Clause": "",
                "AmendmentType": "",
                "Notes": "New BNSS Section (No CrPC Predecessor)",
            }

    # 4. Check Real Subsections like 35(1), 35(3)
    sub_match = SUBSECTION_REGEX.match(bnss_clean)
    if sub_match:
        base_sec = sub_match.group(1)
        sub_num = sub_match.group(2)
        return {
            "Category": "SUBSECTION",
            "NodeType": "SUBSECTION",
            "BNSS_Clean": bnss_clean,
            "ParentSection": base_sec,
            "SubsectionNumber": sub_num,
            "Clause": "",
            "AmendmentType": "",
            "Notes": f"Hierarchy subsection under {base_sec}",
        }

    # 5. Check Real Clauses like 37(c)
    cl_match = CLAUSE_REGEX.match(bnss_clean)
    if cl_match:
        base_sec = cl_match.group(1)
        clause_ltr = cl_match.group(2)
        return {
            "Category": "CLAUSE",
            "NodeType": "CLAUSE",
            "BNSS_Clean": bnss_clean,
            "ParentSection": base_sec,
            "SubsectionNumber": "",
            "Clause": clause_ltr,
            "AmendmentType": "",
            "Notes": f"Hierarchy clause under {base_sec}",
        }

    # 6. Default PLAIN section
    return {
        "Category": "PLAIN",
        "NodeType": "SECTION",
        "BNSS_Clean": bnss_clean,
        "ParentSection": "",
        "SubsectionNumber": "",
        "Clause": "",
        "AmendmentType": "",
        "Notes": "Standard 1:1 section mapping",
    }


def main():
    print("=" * 80)
    print(" STEP 1: PREPROCESSING & VALIDATION OF CRPC <-> BNSS MAPPING")
    print("=" * 80 + "\n")

    if not INPUT_CSV.exists():
        print(f"ERROR: Input mapping file not found at {INPUT_CSV}")
        sys.exit(1)

    df_raw = pd.read_csv(INPUT_CSV, dtype=str).fillna("")
    print(f"Loaded raw crpc2bnss.csv: {len(df_raw)} rows")

    # Load CrPC source dataset for content gap detection (prefers data/cleaned/crpc.csv)
    crpc_csv_path = BASE_DIR / "data" / "cleaned" / "crpc.csv"
    crpc_json_path = BASE_DIR / "backend" / "all_acts" / "bnss" / "crpc.json"

    crpc_source_sections = set()
    if crpc_csv_path.exists():
        df_crpc_src = pd.read_csv(crpc_csv_path, dtype=str).fillna("")
        crpc_source_sections = set(df_crpc_src["Section"].str.strip().str.upper())
        print(f"Loaded source dataset from {crpc_csv_path.name}: {len(crpc_source_sections)} unique sections")
    elif crpc_json_path.exists():
        with open(crpc_json_path, "r", encoding="utf-8") as f:
            crpc_json_data = json.load(f)
        crpc_source_sections = set(str(item.get("section", "")).strip().upper() for item in crpc_json_data)
        print(f"Loaded source crpc.json from {crpc_json_path.name}: {len(crpc_source_sections)} unique sections")
    else:
        print(f"WARNING: No CrPC source dataset found at {crpc_csv_path} or {crpc_json_path}")

    cleaned_rows = []
    missing_sections_details = []

    for idx, row in df_raw.iterrows():
        crpc_sec = clean_str(row.get("CrPC Section"))
        crpc_subj = clean_str(row.get("CrPC Subject"))
        bnss_sec_raw = clean_str(row.get("BNSS Section"))
        bnss_subj = clean_str(row.get("BNSS Subject"))
        notes_raw = clean_str(row.get("Key Changes / Notes") or row.get("Key Changes"))

        class_res = classify_row(crpc_sec, bnss_sec_raw)
        category = class_res["Category"]
        crpc_sec_upper = crpc_sec.strip().upper()

        # Determine content availability & source metadata
        if category in ["NEW_SECTION", "REMOVED"] or crpc_sec_upper in ["NOT APPLICABLE", "REMOVED", "N/A", "NA", ""]:
            content_available = False
            content_source = "not_applicable"
            requires_backfill = "NO"
        elif crpc_sec_upper in crpc_source_sections:
            content_available = True
            content_source = "source_dataset"
            requires_backfill = "NO"
        else:
            content_available = False
            content_source = "mapping_title_only"
            requires_backfill = "YES"
            missing_sections_details.append({
                "crpc_section": crpc_sec,
                "crpc_subject": crpc_subj,
                "bnss_section": class_res["BNSS_Clean"],
                "bnss_subject": bnss_subj,
                "content_source": content_source,
                "requires_backfill": requires_backfill
            })

        cleaned_row = {
            "RowIndex": idx + 1,
            "CrPC_Section": crpc_sec,
            "CrPC_Subject": crpc_subj,
            "BNSS_Section_Raw": bnss_sec_raw,
            "BNSS_Section_Clean": class_res["BNSS_Clean"],
            "BNSS_Subject": bnss_subj,
            "Category": category,
            "NodeType": class_res["NodeType"],
            "ParentSection": class_res["ParentSection"],
            "SubsectionNumber": class_res["SubsectionNumber"],
            "Clause": class_res["Clause"],
            "AmendmentType": class_res["AmendmentType"],
            "content_available": content_available,
            "content_source": content_source,
            "requires_backfill": requires_backfill,
            "ValidationStatus": "VALID",
            "Notes": f"{notes_raw} | {class_res['Notes']}".strip(" |"),
        }
        cleaned_rows.append(cleaned_row)

    df_clean = pd.DataFrame(cleaned_rows)

    # ── CONTENT GAP REPORT GENERATION ──────────────────────────────────────────
    missing_list = [item["crpc_section"] for item in missing_sections_details]
    gap_report = {
        "total_mapping_rows": len(df_clean),
        "sections_in_crpc_source": len(crpc_source_sections),
        "missing_sections_count": len(missing_list),
        "missing_list": missing_list,
        "missing_details": missing_sections_details
    }
    
    gap_report_path = OUTPUT_DIR / "crpc_content_gap_report.json"
    with open(gap_report_path, "w", encoding="utf-8") as f:
        json.dump(gap_report, f, indent=2)
    print(f"Generated CrPC Content Gap Report: {gap_report_path}")
    print(f"  * Detected {len(missing_list)} CrPC sections missing full content: {missing_list}")

    # ── VALIDATION ASSERTIONS ──────────────────────────────────────────────────
    category_counts = df_clean["Category"].value_counts().to_dict()

    removed_count = category_counts.get("REMOVED", 0)
    new_sec_count = category_counts.get("NEW_SECTION", 0)
    sub_count = len(df_clean[df_clean["NodeType"] == "SUBSECTION"])
    clause_count = len(df_clean[df_clean["NodeType"] == "CLAUSE"])
    real_hierarchy_count = sub_count + clause_count
    amendment_count = category_counts.get("AMENDMENT_ANNOTATION", 0)
    plain_count = category_counts.get("PLAIN", 0)

    print("\n--- CLASSIFICATION BREAKDOWN ---")
    print(f"  * PLAIN Sections        : {plain_count:4d}")
    print(f"  * REMOVED (Deleted CrPC): {removed_count:4d} (Expected: 11)")
    print(f"  * NEW_SECTION (New BNSS): {new_sec_count:4d} (Expected: 5)")
    print(f"  * SUBSECTION            : {sub_count:4d} (BNSS_35(1), BNSS_35(3))")
    print(f"  * CLAUSE                : {clause_count:4d} (BNSS_37(c))")
    print(f"  * REAL HIERARCHY TOTAL  : {real_hierarchy_count:4d} (Expected: 3)")
    print(f"  * AMENDMENT ANNOTATION  : {amendment_count:4d} (Expected: 2 -> BNSS_396(Subs), BNSS_397(Subs))")
    print(f"  * TOTAL ROWS            : {len(df_clean):4d}")

    # Check Hard Assertions
    assertion_errors = []
    if removed_count != 11:
        assertion_errors.append(f"Expected 11 REMOVED sections, got {removed_count}")
    if new_sec_count != 5:
        assertion_errors.append(f"Expected 5 NEW_SECTION entries, got {new_sec_count}")
    if real_hierarchy_count != 3:
        assertion_errors.append(f"Expected 3 REAL HIERARCHY nodes, got {real_hierarchy_count}")
    if amendment_count != 2:
        assertion_errors.append(f"Expected 2 AMENDMENT ANNOTATION entries, got {amendment_count}")

    # Save cleaned dataset
    try:
        df_clean.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")
        print(f"\nSaved cleaned dataset: {OUTPUT_CSV}")
    except PermissionError:
        import time
        time.sleep(0.5)
        try:
            df_clean.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")
            print(f"\nSaved cleaned dataset: {OUTPUT_CSV}")
        except PermissionError:
            fallback_csv = OUTPUT_DIR / "crpc2bnss_clean.csv"
            df_clean.to_csv(OUTPUT_DIR / "crpc2bnss_clean_temp.csv", index=False, encoding="utf-8")
            print(f"\nSaved cleaned dataset to fallback file: {OUTPUT_DIR / 'crpc2bnss_clean_temp.csv'}")

    # Generate JSON Validation Report
    report = {
        "status": "PASSED" if not assertion_errors else "FAILED",
        "total_rows": len(df_clean),
        "counts": {
            "plain": plain_count,
            "removed_deleted_crpc": removed_count,
            "new_bnss_sections": new_sec_count,
            "real_hierarchy_nodes": real_hierarchy_count,
            "subsections": sub_count,
            "clauses": clause_count,
            "amendment_annotations": amendment_count,
        },
        "real_hierarchy_details": df_clean[df_clean["Category"].isin(["SUBSECTION", "CLAUSE"])][
            ["CrPC_Section", "BNSS_Section_Clean", "Category", "ParentSection", "SubsectionNumber", "Clause"]
        ].to_dict(orient="records"),
        "amendment_annotation_details": df_clean[df_clean["Category"] == "AMENDMENT_ANNOTATION"][
            ["CrPC_Section", "BNSS_Section_Raw", "BNSS_Section_Clean", "AmendmentType"]
        ].to_dict(orient="records"),
        "removed_sections_details": df_clean[df_clean["Category"] == "REMOVED"][
            ["CrPC_Section", "CrPC_Subject"]
        ].to_dict(orient="records"),
        "new_bnss_sections_details": df_clean[df_clean["Category"] == "NEW_SECTION"][
            ["BNSS_Section_Clean", "BNSS_Subject"]
        ].to_dict(orient="records"),
        "assertion_errors": assertion_errors,
    }

    with open(REPORT_JSON, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"Saved validation report: {REPORT_JSON}")

    if assertion_errors:
        print("\n" + "!" * 80)
        print(" VALIDATION FAILED WITH ASSERTION ERRORS:")
        for err in assertion_errors:
            print(f"   - {err}")
        print("!" * 80)
        sys.exit(1)
    else:
        print("\n" + "=" * 80)
        print(" STEP 1 PREPROCESSING & VALIDATION PASSED PERFECTLY!")
        print("=" * 80)


if __name__ == "__main__":
    main()
