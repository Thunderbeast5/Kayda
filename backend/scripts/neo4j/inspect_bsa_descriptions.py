import pandas as pd
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[3]
bsa_csv = BASE_DIR / "backend" / "all_acts" / "bsa" / "bsa_sections.csv"

df = pd.read_csv(bsa_csv, dtype=str).fillna("")

# Inspect specific sections like Section 2 (Definitions), Section 63 (Electronic Evidence), Section 23 (Confessions), Section 39 (Expert Opinion), etc.
sample_secs = ["2", "23", "39", "61", "63", "74", "132", "146"]

print("=" * 80)
print(" SAMPLE BSA DESCRIPTION TEXT ANALYSIS")
print("=" * 80)

for sec_num in sample_secs:
    match = df[df["Section"].str.strip() == sec_num]
    if not match.empty:
        r = match.iloc[0]
        desc = r["Description"]
        print(f"\n--- BSA SECTION {sec_num}: '{r.get('Section _name')}' ---")
        print(desc[:500] + ("..." if len(desc) > 500 else ""))
