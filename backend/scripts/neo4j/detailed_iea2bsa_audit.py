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

print("=" * 80)
print(" DETAILED AUDIT OF IEA2BSA.CSV MAPPINGS")
print("=" * 80)

# Check duplicates
iea_secs = [r["IEA Section"].strip() for _, r in df_map.iterrows() if r["IEA Section"].strip().upper() not in {"NEW", "N/A", "NOT APPLICABLE", ""}]
dup_iea = set([x for x in iea_secs if iea_secs.count(x) > 1])
print(f"\n1. Duplicate IEA Sections mapped ({len(dup_iea)}): {sorted(list(dup_iea))}")

bsa_secs = [r["BSA Section"].strip() for _, r in df_map.iterrows() if r["BSA Section"].strip().upper() not in {"REMOVED", "DELETED", "REPEALED", "N/A", "NOT APPLICABLE", ""}]
dup_bsa = set([x for x in bsa_secs if bsa_secs.count(x) > 1])
print(f"2. Duplicate BSA Sections mapped ({len(dup_bsa)}): {sorted(list(dup_bsa))}")

# Check Removed IEA Sections
removed_iea = df_map[df_map["BSA Section"].str.strip().str.upper().isin(["REMOVED", "DELETED", "REPEALED"])]
print(f"\n3. Removed IEA Sections ({len(removed_iea)}):")
for idx, r in removed_iea.iterrows():
    print(f"   * IEA_{r['IEA Section']}: '{r['IEA Subject']}' | Notes: {r['Key Changes / Notes']}")

# Check New BSA Sections
new_bsa = df_map[df_map["IEA Section"].str.strip().str.upper().isin(["NEW", "NEW SECTION", "N/A", "NOT APPLICABLE", ""])]
print(f"\n4. New BSA Sections ({len(new_bsa)}):")
for idx, r in new_bsa.iterrows():
    print(f"   * BSA_{r['BSA Section']}: '{r['BSA Subject']}' | Notes: {r['Key Changes / Notes']}")

# Check Hierarchy & Subsections
sub_rows = df_map[df_map["BSA Section"].str.contains(r"\(", na=False)]
print(f"\n5. Hierarchy & Subsection Mappings ({len(sub_rows)}):")
for idx, r in sub_rows.iterrows():
    print(f"   * IEA_{r['IEA Section']} -> BSA_{r['BSA Section']} ('{r['BSA Subject']}') | Notes: {r['Key Changes / Notes']}")
