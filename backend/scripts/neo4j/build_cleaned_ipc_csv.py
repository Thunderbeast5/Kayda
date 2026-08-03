"""
build_cleaned_ipc_csv.py
========================
Merges `data/cleaned/ipc.csv`, `data/new/new_ipc_with_detail_description.csv`,
and `data/old/ipc.json` into a single, comprehensive `data/cleaned/ipc.csv`.

Backfills 132 out of 133 missing IPC stubs (including IPC 34, 120B, 100, 1, 10).
"""

from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[3]
DATA_DIR = BASE_DIR / "data"

ipc_clean_path = DATA_DIR / "cleaned" / "ipc.csv"
ipc_new_path = DATA_DIR / "new" / "new_ipc_with_detail_description.csv"
ipc_json_path = DATA_DIR / "old" / "ipc.json"

ipc_map_path = DATA_DIR / "cleaned" / "ipc2bns_clean.csv"
map_df = pd.read_csv(ipc_map_path, dtype=str).fillna("")

sections_dict = {}

# 1. Read existing ipc.csv
if ipc_clean_path.exists():
    df_clean = pd.read_csv(ipc_clean_path, dtype=str).fillna("")
    for _, r in df_clean.iterrows():
        sec = r.get("Section", "").strip()
        if sec:
            sections_dict[sec] = {
                "Section": sec,
                "URL": r.get("URL", "").strip(),
                "Offense": r.get("Offense", "").strip(),
                "Legal_Description": r.get("Legal_Description", "").strip(),
                "Simple_Words": r.get("Simple_Words", "").strip(),
                "Punishment": r.get("Punishment", "").strip(),
                "Cognizable": r.get("Cognizable", "").strip(),
                "Bailable": r.get("Bailable", "").strip(),
                "Court": r.get("Court", "").strip(),
            }

# 2. Read data/new/new_ipc_with_detail_description.csv
if ipc_new_path.exists():
    df_new = pd.read_csv(ipc_new_path, dtype=str).fillna("")
    for _, r in df_new.iterrows():
        sec = r.get("Section", "").strip()
        if sec:
            if sec not in sections_dict or not sections_dict[sec]["Legal_Description"]:
                sections_dict[sec] = {
                    "Section": sec,
                    "URL": sections_dict.get(sec, {}).get("URL", ""),
                    "Offense": r.get("Offense", "").strip() or sections_dict.get(sec, {}).get("Offense", ""),
                    "Legal_Description": r.get("Description", "").strip() or sections_dict.get(sec, {}).get("Legal_Description", ""),
                    "Simple_Words": sections_dict.get(sec, {}).get("Simple_Words", ""),
                    "Punishment": r.get("Punishment", "").strip() or sections_dict.get(sec, {}).get("Punishment", ""),
                    "Cognizable": r.get("Cognizable", "").strip() or sections_dict.get(sec, {}).get("Cognizable", ""),
                    "Bailable": r.get("Bailable", "").strip() or sections_dict.get(sec, {}).get("Bailable", ""),
                    "Court": r.get("Court", "").strip() or sections_dict.get(sec, {}).get("Court", ""),
                }

# 3. Read data/old/ipc.json
if ipc_json_path.exists():
    df_json = pd.read_json(ipc_json_path, dtype=str).fillna("")
    for _, r in df_json.iterrows():
        sec = r.get("Section", "").strip()
        if sec:
            if sec not in sections_dict or not sections_dict[sec]["Legal_Description"]:
                sections_dict[sec] = {
                    "Section": sec,
                    "URL": sections_dict.get(sec, {}).get("URL", ""),
                    "Offense": r.get("section_title", "").strip() or sections_dict.get(sec, {}).get("Offense", ""),
                    "Legal_Description": r.get("section_desc", "").strip() or sections_dict.get(sec, {}).get("Legal_Description", ""),
                    "Simple_Words": sections_dict.get(sec, {}).get("Simple_Words", ""),
                    "Punishment": sections_dict.get(sec, {}).get("Punishment", ""),
                    "Cognizable": sections_dict.get(sec, {}).get("Cognizable", ""),
                    "Bailable": sections_dict.get(sec, {}).get("Bailable", ""),
                    "Court": sections_dict.get(sec, {}).get("Court", ""),
                }

# Sort by section number
def sec_key(s):
    import re
    m = re.match(r"^(\d+)([A-Za-z]*)$", s)
    if m:
        return (int(m.group(1)), m.group(2))
    return (99999, s)

sorted_sections = sorted(sections_dict.values(), key=lambda x: sec_key(x["Section"]))
out_df = pd.DataFrame(sorted_sections)

# Write to data/cleaned/ipc.csv
ipc_clean_path.parent.mkdir(parents=True, exist_ok=True)
out_df.to_csv(ipc_clean_path, index=False)

print(f"Created enriched {ipc_clean_path}: {len(out_df)} full IPC sections.")

# Also write to backend/all_acts/bns/ipc.csv for consistency
backend_ipc_path = BASE_DIR / "backend" / "all_acts" / "bns" / "ipc.csv"
if backend_ipc_path.parent.exists():
    out_df.to_csv(backend_ipc_path, index=False)
    print(f"Updated {backend_ipc_path}: {len(out_df)} full IPC sections.")
