import pandas as pd
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[3]
bsa_csv = BASE_DIR / "backend" / "all_acts" / "bsa" / "bsa_sections.csv"

df = pd.read_csv(bsa_csv, dtype=str).fillna("")

print("=" * 80)
print(f" BSA SECTIONS CSV INSPECTION ({len(df)} rows)")
print("=" * 80)
print("Columns:", df.columns.tolist())

# Inspect section column values
sections = df["Section"].tolist()
print("\nSample Section values:")
print(sections[:20])

# Find rows containing (1), (a), Explanation, Illustration, Exception, Proviso
embed_sub = [s for s in sections if "(" in s and ")" in s]
embed_expl = [s for s in sections if "EXPL" in s.upper() or "EXPLANATION" in s.upper()]
embed_prov = [s for s in sections if "PROVISO" in s.upper()]
embed_illus = [s for s in sections if "ILLUSTRATION" in s.upper()]

print(f"\nSections with parentheses: {len(embed_sub)} -> {embed_sub[:10]}")
print(f"Sections with Explanation: {len(embed_expl)} -> {embed_expl}")
print(f"Sections with Proviso: {len(embed_prov)} -> {embed_prov}")
print(f"Sections with Illustration: {len(embed_illus)} -> {embed_illus}")

# Inspect Description text for embedded markers in sections
print("\nChecking Description field for embedded (1), (2), (a), (b), Explanation, Illustration, Exception, Proviso...")

sample_descs = df[df["Description"].str.contains(r"\(\d+\)|\(a\)|Explanation|Illustration|Proviso|Exception", regex=True)]
print(f"Rows with embedded markers in Description: {len(sample_descs)}")
