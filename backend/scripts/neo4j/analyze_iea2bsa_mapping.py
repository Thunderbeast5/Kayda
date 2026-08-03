import pandas as pd
import json
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[3]

iea2bsa_path = BASE_DIR / "backend" / "all_acts" / "bsa" / "iea2bsa.csv"
iea_json_path = BASE_DIR / "backend" / "all_acts" / "bsa" / "iea.json"
bsa_sections_path = BASE_DIR / "backend" / "all_acts" / "bsa" / "bsa_sections.csv"

df_map = pd.read_csv(iea2bsa_path, dtype=str).fillna("")
with open(iea_json_path, "r", encoding="utf-8") as f:
    iea_json = json.load(f)
df_bsa = pd.read_csv(bsa_sections_path, dtype=str).fillna("")

iea_json_secs = {str(item["section"]).strip(): item for item in iea_json if "section" in item}

print("=" * 80)
print(" IEA <-> BSA MAPPING CATEGORY & STRUCTURAL ANALYSIS")
print("=" * 80)

categories = {
    "PLAIN": [],
    "SUBSECTION": [],
    "CLAUSE": [],
    "EXPLANATION": [],
    "PROVISO": [],
    "ILLUSTRATION": [],
    "EXCEPTION": [],
    "NEW_SECTION": [],
    "REMOVED": [],
    "AMENDMENT_ANNOTATION": [],
}

missing_iea_in_json = []

for idx, r in df_map.iterrows():
    iea_sec = r["IEA Section"].strip()
    bsa_sec = r["BSA Section"].strip()
    notes = r["Key Changes / Notes"].strip()

    # Check missing IEA text in iea.json
    if iea_sec.upper() not in {"NEW", "NOT APPLICABLE", "N/A", ""} and bsa_sec.upper() != "REMOVED":
        if iea_sec not in iea_json_secs:
            missing_iea_in_json.append(iea_sec)

    # Classify category
    if bsa_sec.upper() in {"REMOVED", "DELETED", "REPEALED"}:
        categories["REMOVED"].append((iea_sec, bsa_sec, notes))
    elif iea_sec.upper() in {"NEW", "NEW SECTION", "N/A", "NOT APPLICABLE", ""}:
        categories["NEW_SECTION"].append((iea_sec, bsa_sec, notes))
    elif "Subs" in notes or "Ins" in notes or "Amendment" in notes:
        categories["AMENDMENT_ANNOTATION"].append((iea_sec, bsa_sec, notes))
    elif "EXPL" in bsa_sec.upper() or "EXPLANATION" in notes.upper():
        categories["EXPLANATION"].append((iea_sec, bsa_sec, notes))
    elif "PROVISO" in notes.upper():
        categories["PROVISO"].append((iea_sec, bsa_sec, notes))
    elif "ILLUSTRATION" in notes.upper():
        categories["ILLUSTRATION"].append((iea_sec, bsa_sec, notes))
    elif "EXCEPTION" in notes.upper():
        categories["EXCEPTION"].append((iea_sec, bsa_sec, notes))
    elif "(" in bsa_sec and ")" in bsa_sec:
        # Check sub or clause
        if re.search(r"\([A-Za-z]\)", bsa_sec):
            categories["CLAUSE"].append((iea_sec, bsa_sec, notes))
        else:
            categories["SUBSECTION"].append((iea_sec, bsa_sec, notes))
    else:
        categories["PLAIN"].append((iea_sec, bsa_sec, notes))

print("\n--- CATEGORY BREAKDOWN ---")
total_cat = 0
for cat, items in categories.items():
    print(f"{cat:20s}: {len(items)}")
    total_cat += len(items)

print(f"\nTotal Categorized Rows: {total_cat} (File Total: {len(df_map)})")
print(f"\nMissing IEA Sections in iea.json: {len(missing_iea_in_json)} -> {missing_iea_in_json}")
