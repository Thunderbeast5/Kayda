import pandas as pd
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[3]

iea2bsa_path = BASE_DIR / "backend" / "all_acts" / "bsa" / "iea2bsa.csv"
iea_json_path = BASE_DIR / "backend" / "all_acts" / "bsa" / "iea.json"
bsa_sections_path = BASE_DIR / "backend" / "all_acts" / "bsa" / "bsa_sections.csv"

df_map = pd.read_csv(iea2bsa_path, dtype=str).fillna("")
print("=" * 80)
print(f" IEA2BSA.CSV INSPECTION ({len(df_map)} rows)")
print("=" * 80)
print("Columns:", df_map.columns.tolist())
print("\nFirst 10 rows preview:")
for idx, row in df_map.head(10).iterrows():
    print(dict(row))

with open(iea_json_path, "r", encoding="utf-8") as f:
    iea_data = json.load(f)
print("\n" + "=" * 80)
print(f" IEA.JSON INSPECTION (Total Sections: {len(iea_data)})")
print("=" * 80)
if isinstance(iea_data, list):
    print("Sample record keys:", list(iea_data[0].keys()) if len(iea_data) > 0 else "Empty")
    print("Sample record section:", iea_data[0].get("section"))

df_bsa = pd.read_csv(bsa_sections_path, dtype=str).fillna("")
print("\n" + "=" * 80)
print(f" BSA_SECTIONS.CSV INSPECTION ({len(df_bsa)} rows)")
print("=" * 80)
print("Columns:", df_bsa.columns.tolist())
print("Total rows:", len(df_bsa))
