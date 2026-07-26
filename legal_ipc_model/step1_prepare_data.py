"""
step1_prepare_data.py
=====================
Reads all JSON files from sample_dataset/ (or your 26k folder),
builds a clean JSONL training file ready for fine-tuning.

Usage:
    python step1_prepare_data.py --data_dir sample_dataset
    python step1_prepare_data.py --data_dir /path/to/26000/json/files
"""
import json
import re
import random
import argparse
from pathlib import Path
from collections import Counter

# ── IPC section → BNS 2023 mapping ───────────────────────────────────────────
IPC_TO_BNS = {
    "34": "3(5)", "109": "48", "120B": "61(2)",
    "302": "101", "303": "102", "304": "105", "304A": "106",
    "304B": "80", "306": "108", "307": "109", "308": "110",
    "309": "226", "323": "115(2)", "324": "117(2)", "325": "116(2)",
    "326": "117(3)", "326A": "124", "326B": "125",
    "354": "74", "354A": "75", "354B": "76", "354C": "77", "354D": "78",
    "363": "137(2)", "364": "139", "364A": "140", "365": "141",
    "366": "142", "366A": "143", "370": "143", "370A": "144",
    "375": "63", "376": "64", "376A": "66", "376AB": "65",
    "376B": "67", "376C": "68", "376D": "70",
    "376(2)": "64(2)", "376(2)(g)": "70",
    "378": "303", "379": "303(2)", "380": "305", "382": "307",
    "383": "308", "384": "308(2)", "390": "309", "391": "310",
    "392": "309(1)", "394": "309(3)", "395": "310(2)", "396": "311",
    "406": "316(2)", "408": "316(2)", "409": "316(3)",
    "411": "317", "420": "318(4)",
    "450": "330", "452": "332", "454": "334", "457": "337",
    "465": "334", "467": "336", "468": "337", "469": "338", "471": "340",
    "499": "356", "500": "356(2)", "506": "351",
}

# Section → human-readable crime type
SECTION_LABELS = {
    "376": "rape", "376A": "rape causing death", "376AB": "rape of minor under 12",
    "376(2)": "aggravated rape", "376(2)(g)": "gang rape",
    "376B": "marital rape during separation", "376C": "rape by authority",
    "376D": "gang rape", "375": "rape (definition)",
    "302": "murder", "303": "murder by life-convict", "304": "culpable homicide",
    "304A": "causing death by negligence", "304B": "dowry death",
    "306": "abetment of suicide", "307": "attempt to murder",
    "34": "common intention", "120B": "criminal conspiracy",
    "363": "kidnapping", "364": "kidnapping to murder", "364A": "kidnapping for ransom",
    "365": "wrongful confinement", "366": "kidnapping woman to marry",
    "354": "assault on woman", "354A": "sexual harassment",
    "354B": "assault to disrobe", "354C": "voyeurism", "354D": "stalking",
    "323": "voluntarily causing hurt", "324": "hurt by dangerous weapon",
    "325": "grievous hurt", "326": "grievous hurt by dangerous weapon",
    "498A": "cruelty by husband", "406": "criminal breach of trust",
    "420": "cheating", "379": "theft", "392": "robbery", "395": "dacoity",
    "396": "dacoity with murder", "506": "criminal intimidation",
    "450": "house-trespass to commit offence", "452": "house-trespass after preparation",
}

INSTRUCTION = (
    "You are an expert in Indian criminal law. Given the following facts from a "
    "Supreme Court of India judgment, identify all applicable IPC sections and their "
    "BNS 2023 equivalents. Provide a brief legal reasoning."
)


def clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'\x08', '', text)          # backspace artifacts
    text = re.sub(r'\s+', ' ', text)          # normalise whitespace
    text = re.sub(r'\[[\d\s]+\]', '', text)   # remove citation brackets [2017] 13 S.C.R.
    text = re.sub(r'\b[A-H]\s(?=[A-Z])', '', text)  # SCC column markers
    return text.strip()


def standardise_section(s: str) -> str:
    s = str(s).strip()
    s = re.sub(r'(?i)\bsection\s*', '', s)
    s = re.sub(r'(?i)\bipc\b', '', s)
    s = re.sub(r'[^\w\(\)/.]', '', s).strip()
    s = s.upper().replace("(G)", "(g)").replace("(V)", "(v)")
    if not re.search(r'\d', s):
        return ""
    # IPC sections are numbered 1–511
    # Known non-IPC low numbers that get mis-tagged from POCSO/other acts
    KNOWN_NON_IPC = {"1","2","3","4","5","6","7","8","9","10","11","12","13",
                     "14","15","16","17","18","19","20","21","22","23","24","25",
                     "41","42","42A","43","44","45","46","47","48","49","50","51",
                     "52","53","60","63","64","65","66","67","68","69","70","71",
                     "72","73","74","75","76","77","78","79","80","86","87","88",
                     "89","90","91","92"}
    num_match = re.match(r'^(\d+)', s)
    if num_match:
        num = int(num_match.group(1))
        if num < 100 and s in KNOWN_NON_IPC:
            return ""   # likely POCSO/CrPC/other act section
        if num > 511:
            return ""
    return s


def get_bns(ipc: str) -> str:
    return IPC_TO_BNS.get(ipc, IPC_TO_BNS.get(ipc.split("(")[0], ""))


def build_input(case: dict) -> str:
    parts = []
    issue = clean_text(case.get("issue_for_consideration", ""))
    if issue and len(issue) > 20:
        parts.append(f"Issue: {issue[:500]}")

    headnotes = clean_text(case.get("headnotes", "") or case.get("full_text", "")[:600])
    if headnotes and len(headnotes) > 30:
        # Remove section numbers to avoid leaking labels into input
        hn = re.sub(r'\bs\.?\s*\d{2,3}[A-Za-z\(\)]*\b', '[SECTION]', headnotes)
        parts.append(f"Summary: {hn[:700]}")

    jt = clean_text(case.get("judgment_text", ""))
    if jt and len(jt) > 50:
        parts.append(f"Judgment: {jt[:500]}")

    kw = case.get("list_of_keywords", [])
    if kw:
        parts.append(f"Keywords: {', '.join(str(k) for k in kw[:10])}")

    acts = case.get("list_of_acts", []) or case.get("acts_referred", [])
    if acts:
        parts.append(f"Acts: {', '.join(str(a) for a in acts[:6])}")

    return "\n".join(parts)


def build_output(ipc_sections: list, case: dict) -> str:
    clean_secs = []
    for s in ipc_sections:
        cs = standardise_section(s)
        if cs:
            clean_secs.append(cs)
    clean_secs = list(dict.fromkeys(clean_secs))  # deduplicate

    if not clean_secs:
        return "IPC Sections: None identified\nBNS Equivalents: None\nReasoning: Insufficient information to identify applicable sections."

    # Build section list with labels
    sec_parts = []
    bns_parts = []
    crime_types = set()

    for s in clean_secs:
        label = SECTION_LABELS.get(s, SECTION_LABELS.get(s.split("(")[0], ""))
        sec_parts.append(f"Section {s}" + (f" ({label})" if label else ""))
        if label:
            crime_types.add(label)
        bns = get_bns(s)
        if bns:
            bns_parts.append(f"BNS {bns} (replaces IPC {s})")

    # Build reasoning
    if crime_types:
        ct_str = ", ".join(sorted(crime_types))
        reasoning = f"The facts establish offences involving {ct_str}."
    else:
        reasoning = "The identified sections are applicable based on the facts presented."

    # POCSO note
    all_text = str(case.get("full_text", "")).lower()
    acts = " ".join(str(a) for a in (case.get("list_of_acts", []) or [])).lower()
    if "pocso" in acts or "minor" in all_text[:500] or "child" in all_text[:500]:
        reasoning += " POCSO Act provisions may additionally apply if the victim is below 18 years of age."

    lines = [
        f"IPC Sections: {', '.join(sec_parts)}",
        f"BNS Equivalents: {', '.join(bns_parts) if bns_parts else 'Refer BNS 2023'}",
        f"Reasoning: {reasoning}",
    ]
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
    if not raw_secs:
        return None   # skip cases without IPC sections

    ipc_sections = [standardise_section(s) for s in raw_secs]
    ipc_sections = [s for s in ipc_sections if s]
    if not ipc_sections:
        return None

    input_text = build_input(case)
    if not input_text or len(input_text) < 40:
        return None

    output_text = build_output(ipc_sections, case)

    return {
        "instruction": INSTRUCTION,
        "input":       input_text,
        "output":      output_text,
        # kept for evaluation — not used in training
        "_meta": {
            "case_id":      case.get("case_id", fp.stem),
            "ipc_sections": ipc_sections,
        }
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_dir",   default="sample_dataset",
                        help="Folder with JSON files (sample or full 26k)")
    parser.add_argument("--output_dir", default="data/processed",
                        help="Where to save train/val/test splits")
    parser.add_argument("--val_ratio",  type=float, default=0.1)
    parser.add_argument("--test_ratio", type=float, default=0.1)
    parser.add_argument("--seed",       type=int,   default=42)
    args = parser.parse_args()

    random.seed(args.seed)
    data_dir = Path(args.data_dir)
    out_dir  = Path(args.output_dir)

    json_files = list(data_dir.glob("*.json"))
    print(f"Found {len(json_files)} JSON files in {data_dir}")

    records = []
    skipped = 0
    section_counter = Counter()

    for fp in json_files:
        rec = process_file(fp)
        if rec:
            records.append(rec)
            for s in rec["_meta"]["ipc_sections"]:
                section_counter[s] += 1
        else:
            skipped += 1

    print(f"Valid records: {len(records)}  |  Skipped (no IPC sections): {skipped}")
    if not records:
        print("ERROR: No valid records. Check your data directory.")
        return

    # Top sections
    print("\nTop 10 IPC sections in dataset:")
    for sec, cnt in section_counter.most_common(10):
        print(f"  Section {sec}: {cnt} cases")

    # Split
    random.shuffle(records)
    n      = len(records)
    n_test = max(1, int(n * args.test_ratio))
    n_val  = max(1, int(n * args.val_ratio))
    test   = records[:n_test]
    val    = records[n_test:n_test + n_val]
    train  = records[n_test + n_val:]

    print(f"\nSplit → train:{len(train)}  val:{len(val)}  test:{len(test)}")

    # Save
    def save_split(recs: list, name: str):
        split_dir = out_dir / name
        split_dir.mkdir(parents=True, exist_ok=True)
        path = split_dir / "dataset.jsonl"
        with open(path, "w", encoding="utf-8") as f:
            for r in recs:
                line = {k: v for k, v in r.items() if not k.startswith("_")}
                f.write(json.dumps(line, ensure_ascii=False) + "\n")
        print(f"  Saved {len(recs)} records → {path}")

    save_split(train, "train")
    save_split(val,   "val")
    save_split(test,  "test")

    # Save test with _meta for evaluation
    meta_path = out_dir / "test" / "dataset_with_meta.jsonl"
    with open(meta_path, "w", encoding="utf-8") as f:
        for r in test:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\nData preparation complete.")
    print(f"Next step → run: python step2_train.py")


if __name__ == "__main__":
    main()
