import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[3]
clean_csv_path = BASE_DIR / "data" / "cleaned" / "iea2bsa_clean.csv"

df = pd.read_csv(clean_csv_path, dtype=str).fillna("")

# Inspect Notes for references to ranges like 132(1)-(2), 146(2)-(3), etc.
range_rows = df[df["Notes"].str.contains(r"-\(\d+\)|-\d+", regex=True)]

print("=" * 80)
print(" RANGE / SPLIT TARGETS IN NOTES")
print("=" * 80)
for idx, r in range_rows.iterrows():
    print(f"IEA_{r['IEA_Section']} -> BSA_{r['BSA_Section_Clean']} | Notes: {r['Notes']}")
