import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[3]
bnss_json = BASE_DIR / "backend" / "all_acts" / "bnss" / "bnss_all_sections.json"

with open(bnss_json, "r", encoding="utf-8") as f:
    data = json.load(f)

for item in data:
    sec = str(item.get("section_no", "")).strip()
    if sec in ["35", "37"]:
        print(f"=== BNSS SECTION {sec} ===")
        print("Title:", item.get("title"))
        print("Body:\n", item.get("body"))
        print("\n" + "="*50 + "\n")
