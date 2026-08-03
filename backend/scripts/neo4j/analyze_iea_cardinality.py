import pandas as pd
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[3]
clean_map_path = BASE_DIR / "data" / "cleaned" / "iea2bsa_clean.csv"

df = pd.read_csv(clean_map_path, dtype=str).fillna("")

# Count IEA section frequencies (excluding NEW and REMOVED)
iea_counts = {}
bsa_counts = {}
bsa_base_counts = {}

for idx, r in df.iterrows():
    iea_sec = r["IEA_Section"].strip()
    bsa_sec = r["BSA_Section_Clean"].strip()
    cat = r["Category"].strip()

    if cat != "NEW_SECTION" and iea_sec.upper() not in {"NEW", "N/A", "NOT APPLICABLE", ""}:
        iea_counts[iea_sec] = iea_counts.get(iea_sec, 0) + 1

    if cat != "REMOVED" and bsa_sec.upper() not in {"REMOVED", "DELETED", "REPEALED", "N/A", "NOT APPLICABLE", ""}:
        bsa_counts[bsa_sec] = bsa_counts.get(bsa_sec, 0) + 1
        m = re.match(r"^(\d+[A-Za-z]*)", bsa_sec)
        base = m.group(1) if m else bsa_sec
        bsa_base_counts[base] = bsa_base_counts.get(base, 0) + 1

print("=" * 80)
print(" CARDINALITY & MERGE/SPLIT ANALYSIS FOR IEA <-> BSA")
print("=" * 80)

print("\n--- 1. IEA Sections mapping to multiple BSA targets (ONE_TO_MANY / SPLIT) ---")
one_to_many_iea = {k: v for k, v in iea_counts.items() if v > 1}
if one_to_many_iea:
    for k, v in one_to_many_iea.items():
        targets = df[df["IEA_Section"].str.strip() == k]["BSA_Section_Clean"].tolist()
        print(f"   * IEA_{k} -> {v} BSA targets: {targets}")
else:
    print("   None (All active IEA sections map to 1 BSA section/sub-node in this CSV)")

print("\n--- 2. BSA Sections containing multiple IEA source sections (MANY_TO_ONE / MERGED) ---")
many_to_one_bsa = {k: v for k, v in bsa_base_counts.items() if v > 1}
if many_to_one_bsa:
    for k, v in sorted(many_to_one_bsa.items(), key=lambda x: int(re.match(r"\d+", x[0]).group()) if re.match(r"\d+", x[0]) else 999):
        sources = df[df["BSA_Section_Clean"].str.contains(r"^" + re.escape(k) + r"(\(|\b)", regex=True)]["IEA_Section"].tolist()
        notes = df[df["BSA_Section_Clean"].str.contains(r"^" + re.escape(k) + r"(\(|\b)", regex=True)]["Notes"].tolist()
        print(f"   * BSA_{k} <- {v} IEA source sections: {sources}")
        print(f"     Notes: {set(notes)}")
else:
    print("   None")
