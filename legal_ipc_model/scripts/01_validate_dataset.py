"""
01_validate_dataset.py
======================
Validates all JSON case files before any training.

Checks:
- JSON parse errors
- Missing required fields (case_id, full_text, ipc_sections_referred)
- Empty / blank text
- Duplicate case IDs
- IPC section format and range (valid IPC = 100-511)
- Section frequency distribution
- Input text length distribution
- Potential label leakage (section numbers visible in input text)

Usage:
    python scripts/01_validate_dataset.py --data_dir sample_dataset
    python scripts/01_validate_dataset.py --data_dir data/raw
    python scripts/01_validate_dataset.py --data_dir data/raw --save_report logs/validation_report.json
"""

import json
import re
import argparse
from pathlib import Path
from collections import Counter, defaultdict


# ── IPC section range ─────────────────────────────────────────────────────────
# Valid IPC sections span 1–511; however sections below 100 are
# overwhelmingly definitional and rarely the "applicable" section in criminal
# cases.  We warn (not reject) when a section < 100 is found.
IPC_MIN = 100
IPC_MAX = 511

# Fields that MUST be present and non-empty
REQUIRED_FIELDS = ["case_id", "full_text", "ipc_sections_referred"]

# Patterns that indicate a section number is explicitly mentioned in the input,
# which could allow the model to copy-paste it (label leakage).
LEAKAGE_PATTERNS = [
    r'\bIPC\s*s(?:ection)?\s*\.?\s*(\d{2,3}[A-Za-z]*)\b',
    r'\bSection\s+(\d{2,3}[A-Za-z]*)\s+(?:of\s+)?(?:the\s+)?IPC\b',
    r'\bu/?s\.?\s*(\d{2,3}[A-Za-z]*)\s+IPC\b',
    r'\bs\.?\s*(\d{2,3}[A-Za-z]*)\s+IPC\b',
    r'\bunder\s+[Ss]ection\s+(\d{2,3}[A-Za-z]*)\b',
    r'\bconvicted\s+(?:under|u/s)\s+(?:s(?:ection)?)?\s*\.?\s*(\d{2,3})\b',
    r'\b(\d{2,3})\s+IPC\b',
    r'\b(\d{2,3})\s+of\s+(?:the\s+)?Indian\s+Penal\s+Code\b',
]

COMPILED_LEAKAGE = [re.compile(p, re.IGNORECASE) for p in LEAKAGE_PATTERNS]


def parse_section(raw: str) -> str | None:
    """Clean and return a section string, or None if invalid."""
    s = str(raw).strip()
    s = re.sub(r'(?i)\bsection\s*', '', s)
    s = re.sub(r'(?i)\bipc\b', '', s)
    s = re.sub(r'[^\w\(\)]', '', s).strip()
    if not re.search(r'\d', s):
        return None
    m = re.match(r'^(\d+)', s)
    if m:
        n = int(m.group(1))
        if n > IPC_MAX:
            return None
    return s if s else None


def extract_input_sections(text: str) -> set[str]:
    """Find section numbers mentioned anywhere in the input text."""
    found = set()
    for pat in COMPILED_LEAKAGE:
        for m in pat.finditer(text):
            sec = m.group(1).strip()
            if re.search(r'\d', sec):
                found.add(sec)
    return found


def validate_file(fp: Path) -> dict:
    result = {
        "file": fp.name,
        "valid": False,
        "errors": [],
        "warnings": [],
        "case_id": None,
        "ipc_sections": [],
        "input_length": 0,
        "leakage_sections": [],
    }

    # 1. Parse JSON
    try:
        with open(fp, encoding="utf-8") as f:
            case = json.load(f)
    except json.JSONDecodeError as e:
        result["errors"].append(f"JSON parse error: {e}")
        return result
    except Exception as e:
        result["errors"].append(f"File read error: {e}")
        return result

    # 2. Skip extractor-flagged errors
    if case.get("has_error"):
        result["errors"].append("Extractor flagged has_error=true")
        return result

    # 3. Required fields
    for field in REQUIRED_FIELDS:
        v = case.get(field)
        if v is None or (isinstance(v, (str, list)) and len(v) == 0):
            result["errors"].append(f"Missing/empty required field: {field}")

    if result["errors"]:
        return result

    result["case_id"] = case["case_id"]

    # 4. Input text length
    full_text = (case.get("full_text") or "").strip()
    issue     = (case.get("issue_for_consideration") or "").strip()
    headnotes = (case.get("headnotes") or "").strip()
    combined  = " ".join(x for x in [issue, headnotes, full_text[:500]] if x)
    result["input_length"] = len(combined.split())

    if result["input_length"] < 10:
        result["errors"].append("Input text too short (<10 words)")
        return result

    # 5. IPC sections
    raw_secs = case.get("ipc_sections_referred", [])
    if not isinstance(raw_secs, list):
        raw_secs = [str(raw_secs)]

    clean_secs = []
    for s in raw_secs:
        parsed = parse_section(s)
        if parsed:
            n = int(re.match(r'^(\d+)', parsed).group(1))
            if n < IPC_MIN:
                result["warnings"].append(
                    f"Section {parsed} (num={n}) is below {IPC_MIN} — "
                    "may be POCSO/CrPC, not IPC"
                )
            else:
                clean_secs.append(parsed)

    if not clean_secs:
        result["errors"].append("No valid IPC sections (100-511) found")
        return result

    result["ipc_sections"] = clean_secs

    # 6. Label leakage check
    # Use the input fields that will actually be fed to the model
    input_for_leakage = " ".join([issue, headnotes])
    input_sections = extract_input_sections(input_for_leakage)
    label_set      = set(re.sub(r'[^\d]', '', s) for s in clean_secs)
    leaked         = [s for s in input_sections if s in label_set]
    if leaked:
        result["warnings"].append(
            f"Potential label leakage: sections {leaked} visible in input text"
        )
        result["leakage_sections"] = leaked

    result["valid"] = True
    return result


def main():
    parser = argparse.ArgumentParser(description="Validate JSON case dataset")
    parser.add_argument("--data_dir",    default="sample_dataset",
                        help="Folder containing JSON case files")
    parser.add_argument("--save_report", default="logs/validation_report.json",
                        help="Path to save JSON validation report")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        print(f"ERROR: Directory not found: {data_dir}")
        return

    json_files = sorted(data_dir.glob("*.json"))
    if not json_files:
        print(f"ERROR: No JSON files found in {data_dir}")
        return

    print(f"\nValidating {len(json_files)} files in: {data_dir}\n")

    # ── Run validation ────────────────────────────────────────────────────────
    results        = []
    seen_ids       = {}
    section_freq   = Counter()
    length_buckets = Counter()
    leakage_count  = 0

    valid_count    = 0
    error_count    = 0
    warning_count  = 0
    duplicate_count= 0

    for fp in json_files:
        r = validate_file(fp)
        results.append(r)

        if r["errors"]:
            error_count += 1
        else:
            valid_count += 1
            for s in r["ipc_sections"]:
                section_freq[re.sub(r'[^\d]', '', s)] += 1

            wc = r["input_length"]
            if wc < 50:    length_buckets["<50 words"] += 1
            elif wc < 150: length_buckets["50-150 words"] += 1
            elif wc < 300: length_buckets["150-300 words"] += 1
            elif wc < 600: length_buckets["300-600 words"] += 1
            else:          length_buckets[">600 words"] += 1

        if r["warnings"]:
            warning_count += 1
            if r["leakage_sections"]:
                leakage_count += 1

        # Duplicate check
        cid = r.get("case_id")
        if cid:
            if cid in seen_ids:
                duplicate_count += 1
                r["errors"].append(f"Duplicate case_id (first seen: {seen_ids[cid]})")
            else:
                seen_ids[cid] = fp.name

    # ── Section rarity ────────────────────────────────────────────────────────
    rare_sections = {s: c for s, c in section_freq.items() if c < 10}

    # ── Print report ──────────────────────────────────────────────────────────
    print("=" * 55)
    print("  DATASET VALIDATION REPORT")
    print("=" * 55)
    print(f"  Total files        : {len(json_files)}")
    print(f"  Valid records      : {valid_count}")
    print(f"  Invalid (errors)   : {error_count}")
    print(f"  Duplicate case IDs : {duplicate_count}")
    print(f"  With warnings      : {warning_count}")
    print(f"  Potential leakage  : {leakage_count}")
    print()
    print(f"  Unique IPC sections: {len(section_freq)}")
    print()
    print("  Top 15 IPC sections:")
    for sec, cnt in section_freq.most_common(15):
        bar = "█" * min(int(cnt / max(section_freq.values()) * 20), 20)
        print(f"    Section {sec:<8} {bar} {cnt}")
    print()
    if rare_sections:
        print(f"  Rare sections (<10 cases): {len(rare_sections)}")
        print(f"    {sorted(rare_sections.keys())}")
        print()
    print("  Input word-count distribution:")
    for bucket, cnt in sorted(length_buckets.items()):
        print(f"    {bucket:<20}: {cnt}")
    print()

    # Show first 5 errors
    error_files = [r for r in results if r["errors"]]
    if error_files:
        print(f"  First 5 errors:")
        for r in error_files[:5]:
            print(f"    {r['file']}: {r['errors']}")
    print("=" * 55)

    # ── Save report ───────────────────────────────────────────────────────────
    report = {
        "summary": {
            "total_files":       len(json_files),
            "valid_records":     valid_count,
            "invalid_records":   error_count,
            "duplicate_ids":     duplicate_count,
            "with_warnings":     warning_count,
            "leakage_cases":     leakage_count,
            "unique_ipc_sections": len(section_freq),
        },
        "section_frequency": dict(section_freq.most_common()),
        "rare_sections":     rare_sections,
        "length_distribution": dict(length_buckets),
        "errors": [r for r in results if r["errors"]],
        "warnings": [r for r in results if r["warnings"] and not r["errors"]],
    }

    save_path = Path(args.save_report)
    save_path.parent.mkdir(parents=True, exist_ok=True)
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n  Full report saved: {save_path}")

    # Exit code: 0 if valid records exist, 1 if none
    if valid_count == 0:
        print("\nERROR: No valid records found. Fix errors before proceeding.")
        raise SystemExit(1)
    print(f"\n  {valid_count} valid records ready for training.\n")


if __name__ == "__main__":
    main()
