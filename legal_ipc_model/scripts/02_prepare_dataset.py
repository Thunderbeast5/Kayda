"""
02_prepare_dataset.py
=====================
Reads validated JSON files and produces clean train/val/test JSONL splits
in the exact format required by the SFT trainer.

Output format per record:
    {
        "instruction": "...",
        "input":       "...",
        "output":      "IPC Sections: 302, 34\nBNS Equivalents: 101, 3(5)"
    }

Leakage prevention: section numbers are masked in the input fields.

Usage:
    python scripts/02_prepare_dataset.py --data_dir sample_dataset
    python scripts/02_prepare_dataset.py --data_dir data/raw
    python scripts/02_prepare_dataset.py --data_dir data/raw --val_ratio 0.1 --test_ratio 0.1
"""

import json
import re
import random
import argparse
from pathlib import Path
from collections import Counter

# ── IPC → BNS 2023 mapping (officially validated) ────────────────────────────
IPC_TO_BNS: dict[str, str] = {
    "34": "3(5)", "107": "45", "109": "48", "120B": "61(2)",
    "148": "191(3)", "149": "190",
    "166A": "166A",
    "201": "238", "202": "239", "203": "240", "204": "241",
    "302": "101", "303": "102", "304": "105", "304A": "106",
    "304B": "80", "305": "107", "306": "108",
    "307": "109", "308": "110", "309": "226",
    "319": "114", "320": "115", "321": "116", "322": "117",
    "323": "115(2)", "324": "117(2)", "325": "116(2)",
    "326": "117(3)", "326A": "124", "326B": "125",
    "341": "126", "342": "127", "343": "128", "344": "129",
    "354": "74", "354A": "75", "354B": "76",
    "354C": "77", "354D": "78",
    "363": "137(2)", "364": "139", "364A": "140", "365": "141",
    "366": "142", "366A": "143", "366B": "144",
    "370": "143", "370A": "144",
    "375": "63", "376": "64", "376A": "66",
    "376AB": "65", "376B": "67", "376C": "68",
    "376(2)": "64(2)", "376(2)(g)": "70", "376D": "70",
    "378": "303", "379": "303(2)", "380": "305",
    "382": "307", "383": "308", "384": "308(2)",
    "390": "309", "391": "310", "392": "309(1)",
    "393": "309(4)", "394": "309(3)", "395": "310(2)", "396": "311",
    "397": "312", "399": "312",
    "406": "316(2)", "408": "316(2)", "409": "316(3)",
    "411": "317", "420": "318(4)", "424": "323",
    "447": "329(1)", "448": "329(2)", "450": "330", "452": "332",
    "454": "334", "457": "337", "458": "338",
    "465": "334", "467": "336", "468": "337", "469": "338", "471": "340",
    "498A": "86", "499": "356", "500": "356(2)", "506": "351",
    "509": "79",
}

# ── Leakage mask patterns ─────────────────────────────────────────────────────
# Applied to input text before training to prevent the model from just
# copying section numbers from the input.
_LEAKAGE_RE = re.compile(
    r'(?:'
    r'\b(?:IPC|Indian Penal Code)\s+[Ss](?:ection)?\s*\.?\s*\d{2,3}[A-Za-z]*|'
    r'\b[Ss](?:ection)?\s*\.?\s*\d{2,3}[A-Za-z]*\s+(?:of\s+)?IPC\b|'
    r'\bu/?s\.?\s*\d{2,3}[A-Za-z]*\s+IPC\b|'
    r'\bunder\s+[Ss]ection\s+\d{2,3}[A-Za-z]*\b|'
    r'\b[Ss]\.?\s*\d{2,3}[A-Za-z]*\s+of\s+(?:the\s+)?IPC\b|'
    r'\bconvicted\s+(?:under|u/s)\s+\d{2,3}[A-Za-z]*|'
    r'\b\d{2,3}\s+IPC\b|'
    r'\b\d{2,3}\s+of\s+(?:the\s+)?Indian\s+Penal\s+Code\b'
    r')',
    re.IGNORECASE
)

# ── IPC section validity ──────────────────────────────────────────────────────
# Low-number POCSO/CrPC sections that often end up mis-tagged as IPC
_NON_IPC_SECTIONS: set[str] = {
    "1","2","3","4","5","6","7","8","9","10","11","12","13","14","15","16",
    "17","18","19","20","21","22","23","24","25","26","27","28","29","30",
    "41","42","42A","43","44","45","46","47","48","49","50","51","52","53",
    "60","63","64","65","66","67","68","69","70","71","72","73","74","75",
    "76","77","78","79","80","82","85","86","87","88","89","90","91","92",
    "93","94","95","96","97","98","99",
}

INSTRUCTION = (
    "You are a legal classification model for Indian criminal law. "
    "Given the following case facts, identify the applicable IPC sections. "
    "Respond ONLY in the specified format."
)


def clean_text(text: str) -> str:
    if not isinstance(text, str):
        return ""
    text = re.sub(r'\x08', '', text)        # backspace from SCC PDFs
    text = re.sub(r'\[[\d\s]+\]', '', text) # citation brackets
    text = re.sub(r'\b[A-H]\s(?=[A-Z])', '', text)  # SCC column markers
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def mask_leakage(text: str) -> str:
    """Replace explicit section references with [SEC] to prevent leakage."""
    return _LEAKAGE_RE.sub('[SEC]', text)


def parse_section(raw: str) -> str | None:
    """
    Return normalised section string or None.
    Handles: "376", "376(2)", "376(2)(g)", "376AB"
    Rejects:  non-IPC numbers, > 511
    """
    s = str(raw).strip()
    # Strip prefixes
    s = re.sub(r'(?i)\bsection\s*', '', s)
    s = re.sub(r'(?i)\bipc\b', '', s)
    # Keep digits, letters, parentheses
    s = re.sub(r'[^\w\(\)]', '', s).strip()
    # Normalise case for letter suffixes: 376(2)(G) → 376(2)(g)
    s = re.sub(r'\(([A-Z])\)', lambda m: f'({m.group(1).lower()})', s)
    if not re.search(r'\d', s):
        return None
    # Extract base number
    m = re.match(r'^(\d+)', s)
    if not m:
        return None
    base = m.group(1)
    if int(base) > 511:
        return None
    if base in _NON_IPC_SECTIONS and s == base:
        return None
    return s


def build_input(case: dict) -> str:
    """
    Build model input from case fields.
    Applies leakage masking.
    Truncates to keep inputs concise (~512 tokens → ~350 words).
    """
    parts = []

    issue = clean_text(case.get("issue_for_consideration", "") or "")
    if issue and len(issue) > 20:
        parts.append(f"Issue: {mask_leakage(issue)[:400]}")

    headnotes = clean_text(case.get("headnotes", "") or "")
    if headnotes and len(headnotes) > 20:
        parts.append(f"Summary: {mask_leakage(headnotes)[:500]}")

    jt = clean_text(case.get("judgment_text", "") or "")
    if jt and len(jt) > 30:
        parts.append(f"Judgment: {mask_leakage(jt[:400])}")

    kw = case.get("list_of_keywords", []) or []
    if kw:
        parts.append(f"Keywords: {', '.join(str(k) for k in kw[:10])}")

    acts = case.get("list_of_acts", []) or case.get("acts_referred", []) or []
    if acts:
        parts.append(f"Acts: {', '.join(str(a) for a in acts[:6])}")

    return "\n".join(parts)


def build_output(ipc_sections: list[str]) -> str:
    """
    Build structured output string.
    Format:
        IPC Sections: 302, 34, 201
        BNS Equivalents: 101, 3(5), 238
    Simple, clean, easy to parse during evaluation.
    """
    bns_parts = []
    for s in ipc_sections:
        bns = IPC_TO_BNS.get(s) or IPC_TO_BNS.get(s.split("(")[0])
        if bns:
            bns_parts.append(bns)

    lines = [f"IPC Sections: {', '.join(ipc_sections)}"]
    if bns_parts:
        lines.append(f"BNS Equivalents: {', '.join(bns_parts)}")
    return "\n".join(lines)


def process_file(fp: Path) -> dict | None:
    try:
        with open(fp, encoding="utf-8") as f:
            case = json.load(f)
    except Exception:
        return None

    if case.get("has_error"):
        return None

    raw_secs = case.get("ipc_sections_referred", [])
    if not isinstance(raw_secs, list):
        raw_secs = [str(raw_secs)]

    ipc_sections = list(dict.fromkeys(
        s for s in (parse_section(r) for r in raw_secs) if s
    ))
    if not ipc_sections:
        return None

    input_text = build_input(case)
    if not input_text or len(input_text.split()) < 10:
        return None

    return {
        "instruction": INSTRUCTION,
        "input":       input_text,
        "output":      build_output(ipc_sections),
        # _meta kept only in test split for evaluation
        "_meta": {
            "case_id":      case.get("case_id", fp.stem),
            "ipc_sections": ipc_sections,
        },
    }


def save_split(records: list[dict], path: Path, include_meta: bool = False):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            if include_meta:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            else:
                line = {k: v for k, v in r.items() if not k.startswith("_")}
                f.write(json.dumps(line, ensure_ascii=False) + "\n")
    print(f"  Saved {len(records):>5} records → {path}")


def main():
    parser = argparse.ArgumentParser(description="Prepare training dataset from JSON cases")
    parser.add_argument("--data_dir",   default="sample_dataset")
    parser.add_argument("--output_dir", default="data/processed")
    parser.add_argument("--val_ratio",  type=float, default=0.1)
    parser.add_argument("--test_ratio", type=float, default=0.1)
    parser.add_argument("--seed",       type=int,   default=42)
    args = parser.parse_args()

    random.seed(args.seed)
    data_dir = Path(args.data_dir)
    out_dir  = Path(args.output_dir)

    json_files = sorted(data_dir.rglob("*.json"))  # rglob = recursive subfolders
    print(f"\nFound {len(json_files)} JSON files in {data_dir} (including subfolders)")

    records        = []
    skipped        = 0
    section_freq   = Counter()

    for fp in json_files:
        rec = process_file(fp)
        if rec:
            records.append(rec)
            for s in rec["_meta"]["ipc_sections"]:
                section_freq[s] += 1
        else:
            skipped += 1

    print(f"Valid records : {len(records)}")
    print(f"Skipped       : {skipped}")

    if not records:
        print("ERROR: No valid records. Run 01_validate_dataset.py first.")
        raise SystemExit(1)

    print(f"\nTop 10 IPC sections:")
    for s, c in section_freq.most_common(10):
        print(f"  Section {s:<12}: {c}")

    # ── Split ─────────────────────────────────────────────────────────────────
    random.shuffle(records)
    n      = len(records)
    n_test = max(1, int(n * args.test_ratio))
    n_val  = max(1, int(n * args.val_ratio))
    # Ensure at least 1 record in each split even with small datasets
    if n <= 3:
        n_test = 1
        n_val  = 1

    test   = records[:n_test]
    val    = records[n_test:n_test + n_val]
    train  = records[n_test + n_val:]

    # Guard: if train would be empty, take from val/test
    if not train:
        train = [records[0]]
        val   = [records[1]] if len(records) > 1 else []
        test  = [records[2]] if len(records) > 2 else []

    print(f"\nSplit → train:{len(train)}  val:{len(val)}  test:{len(test)}")

    # ── Save ──────────────────────────────────────────────────────────────────
    print("\nSaving splits:")
    save_split(train, out_dir / "train" / "dataset.jsonl", include_meta=False)
    save_split(val,   out_dir / "val"   / "dataset.jsonl", include_meta=False)
    save_split(test,  out_dir / "test"  / "dataset.jsonl", include_meta=False)
    # Test split WITH _meta for evaluation
    save_split(test,  out_dir / "test"  / "dataset_with_meta.jsonl", include_meta=True)

    print(f"\nDataset ready in: {out_dir}")
    print("Next: python scripts/03_analyze_dataset.py")


if __name__ == "__main__":
    main()
