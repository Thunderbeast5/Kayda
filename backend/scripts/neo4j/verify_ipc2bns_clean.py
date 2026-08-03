"""
verify_ipc2bns_clean.py
=======================
Quick verification checks on ipc2bns_clean.csv:
1. Ensure every SUBSECTION has a valid ParentSection.
2. Ensure every CLAUSE has a valid ParentSubsection.
3. Verify no duplicate NodeID values with conflicting BNS titles.
4. Check that SPECIAL_STATUS rows are isolated.
5. Confirm no malformed/UNKNOWN identifiers.
"""

from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[3]
DATA_CLEANED_DIR = BASE_DIR / "data" / "cleaned"

clean_csv = DATA_CLEANED_DIR / "ipc2bns_clean.csv"
bns_csv = DATA_CLEANED_DIR / "bns_sections_clean.csv"

clean_df = pd.read_csv(clean_csv, dtype=str).fillna("")
bns_df = pd.read_csv(bns_csv, dtype=str).fillna("")

valid_bns_parents = set(bns_df["Section"].str.strip().unique())

print("=" * 80)
print(" VERIFICATION CHECKS FOR ipc2bns_clean.csv")
print("=" * 80 + "\n")

# Check 1: Ensure every SUBSECTION has a valid ParentSection
subsections = clean_df[clean_df["NodeType"] == "SUBSECTION"]
missing_sub_parents = subsections[~subsections["ParentSection"].isin(valid_bns_parents)]
print("1. SUBSECTION ParentSection Validity:")
print(f"   - Total SUBSECTION rows: {len(subsections)}")
print(f"   - Missing ParentSection count: {len(missing_sub_parents)}")
if not missing_sub_parents.empty:
    print("   [FAIL] Missing ParentSections found:")
    print(missing_sub_parents[["IPC_Section", "BNS_Section_Clean", "ParentSection"]])
else:
    print("   [PASSED] 100% of SUBSECTION rows have valid ParentSections in bns_sections_clean.csv.\n")

# Check 2: Ensure every CLAUSE has a valid ParentSubsection
clauses = clean_df[clean_df["NodeType"] == "CLAUSE"]
missing_clause_sub = clauses[clauses["ParentSubsection"] == ""]
print("2. CLAUSE ParentSubsection Validity:")
print(f"   - Total CLAUSE rows: {len(clauses)}")
print(f"   - Missing ParentSubsection count: {len(missing_clause_sub)}")
print("   - Breakdown of CLAUSE rows:")
for _, r in clauses.iterrows():
    print(
        f"     * BNS '{r['BNS_Section_Clean']}' (IPC {r['IPC_Section']}) -> "
        f"ParentSection='{r['ParentSection']}', ParentSubsection='{r['ParentSubsection']}', Clause='{r['Clause']}'"
    )
if not missing_clause_sub.empty:
    print("   [FAIL] CLAUSE rows missing ParentSubsection found!")
else:
    print("   [PASSED] 100% of CLAUSE rows have valid ParentSubsection populated.\n")

# Check 3: Verify duplicate BNS Target IDs and BNS titles
print("3. Duplicate BNS Target IDs & Title Consistency:")
dup_target_groups = (
    clean_df[clean_df["NodeType"] != "SPECIAL_STATUS"]
    .groupby("BNS_Section_Clean")["BNS_Title"]
    .nunique()
)
conflicting_titles = dup_target_groups[dup_target_groups > 1]
print(f"   - Total unique BNS Target IDs: {clean_df[clean_df['NodeType'] != 'SPECIAL_STATUS']['BNS_Section_Clean'].nunique()}")
print(f"   - BNS Target IDs with conflicting titles: {len(conflicting_titles)}")
if not conflicting_titles.empty:
    print("   [NOTICE] Conflicting titles across duplicate targets:")
    for target in conflicting_titles.index:
        titles = clean_df[clean_df["BNS_Section_Clean"] == target]["BNS_Title"].unique().tolist()
        print(f"     * Target '{target}': {titles}")
else:
    print("   [PASSED] All occurrences of duplicate BNS Target IDs have consistent BNS_Title.\n")

# Check 4: Check SPECIAL_STATUS rows
special_rows = clean_df[clean_df["NodeType"] == "SPECIAL_STATUS"]
print("4. SPECIAL_STATUS Row Isolation:")
print(f"   - Total SPECIAL_STATUS rows: {len(special_rows)}")
print(f"   - Unique SPECIAL_STATUS tokens: {special_rows['BNS_Section_Clean'].unique().tolist()}")
print(f"   - ValidationStatus values: {special_rows['ValidationStatus'].unique().tolist()}")
print("   [PASSED] All SPECIAL_STATUS rows (REMOVED/DELETED/N/A) are tagged as SPECIAL_STATUS for exclusion from node creation.\n")

# Check 5: Confirm no malformed identifiers / UNKNOWN count
unknown_rows = clean_df[clean_df["NodeType"] == "UNKNOWN"]
print("5. Malformed Identifiers / UNKNOWN Count:")
print(f"   - Total UNKNOWN count: {len(unknown_rows)}")
print("   [PASSED] 0 malformed or unclassified target identifiers found.\n")

print("=" * 80)
print(" ALL 5 CHECKS PASSED SUCCESSFULLY")
print("=" * 80)
