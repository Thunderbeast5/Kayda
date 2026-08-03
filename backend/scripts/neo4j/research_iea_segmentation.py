import pandas as pd
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[3]
iea_csv_path = BASE_DIR / "data" / "cleaned" / "iea.csv"

df_iea = pd.read_csv(iea_csv_path, dtype=str).fillna("")
print("=" * 80)
print(f" IEA CLEAN DATASET INSPECTION ({len(df_iea)} rows)")
print("=" * 80)

embed_expl = []
embed_illus = []
embed_prov = []
embed_exc = []

for idx, r in df_iea.iterrows():
    sec = r["section"].strip()
    desc = r["description"].strip()

    if "Explanation" in desc or "EXPL" in desc.upper():
        embed_expl.append((sec, r["title"]))
    if "Illustration" in desc or "Illustrations" in desc:
        embed_illus.append((sec, r["title"]))
    if "Provided that" in desc:
        embed_prov.append((sec, r["title"]))
    if "Exception" in desc:
        embed_exc.append((sec, r["title"]))

print(f"\nIEA Sections with Explanation  : {len(embed_expl)} -> {embed_expl[:8]}")
print(f"IEA Sections with Illustration : {len(embed_illus)} -> {embed_illus[:8]}")
print(f"IEA Sections with Proviso      : {len(embed_prov)} -> {embed_prov[:8]}")
print(f"IEA Sections with Exception    : {len(embed_exc)} -> {embed_exc[:8]}")
