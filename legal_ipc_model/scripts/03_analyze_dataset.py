"""
03_analyze_dataset.py
=====================
Inspects prepared JSONL splits and reports:
- Record counts per split
- Input / output token length distribution
- IPC section frequency and class imbalance
- Leakage audit on prepared inputs
- Sample records for manual review

Usage:
    python scripts/03_analyze_dataset.py
    python scripts/03_analyze_dataset.py --data_dir data/processed
"""

import json
import re
import argparse
from pathlib import Path
from collections import Counter


def load_jsonl(path: Path) -> list:
    if not path.exists():
        return []
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def word_count(text: str) -> int:
    return len(text.split()) if text else 0


def approx_tokens(text: str) -> int:
    """Rough token estimate: words * 1.3"""
    return int(word_count(text) * 1.3)


def bucket(n: int, thresholds: list) -> str:
    for lo, hi, label in thresholds:
        if lo <= n < hi:
            return label
    return thresholds[-1][2]


INPUT_BUCKETS  = [(0,50,"<50"), (50,150,"50-149"), (150,300,"150-299"),
                  (300,512,"300-511"), (512,1024,"512-1023"), (1024,99999,">=1024")]
OUTPUT_BUCKETS = [(0,10,"<10"), (10,30,"10-29"), (30,60,"30-59"),
                  (60,100,"60-99"), (100,99999,">=100")]

# Leakage patterns — same as 02_prepare_dataset but slightly broader
_LEAKAGE_RE = re.compile(
    r'\b(?:Section|Sec|s\.?)\s*\.?\s*\d{2,3}[A-Za-z\(\)]*\b|'
    r'\b\d{2,3}\s+IPC\b|'
    r'\bunder\s+[Ss]ection\s+\d{2,3}\b',
    re.IGNORECASE
)


def extract_ipc_from_output(output: str) -> list:
    m = re.search(r'IPC\s+Sections?:\s*(.*?)(?:\n|$)', output, re.IGNORECASE)
    if not m:
        return []
    raw = m.group(1)
    return [s.strip() for s in raw.split(',') if s.strip()]


def check_leakage(record: dict) -> list:
    """Return label sections that also appear in the input."""
    input_text = (record.get("instruction","") + " " + record.get("input",""))
    input_hits  = set(re.findall(r'\b(\d{2,3}[A-Za-z]*)\b',
                                 _LEAKAGE_RE.sub('[SEC]', input_text)))
    labels      = set(re.findall(r'\b(\d{2,3}[A-Za-z]*)\b',
                                 record.get("output", "")))
    # After masking, any label section digits should NOT appear raw
    raw_hits    = set(re.findall(r'\b(\d{2,3})\b', input_text))
    label_nums  = set(re.match(r'^(\d+)', s).group(1)
                      for s in labels if re.match(r'^(\d+)', s))
    return sorted(raw_hits & label_nums)


def analyze_split(name: str, records: list) -> dict:
    if not records:
        return {"name": name, "count": 0}

    input_tokens  = [approx_tokens(r.get("input","")) for r in records]
    output_tokens = [approx_tokens(r.get("output","")) for r in records]
    total_tokens  = [i+o for i,o in zip(input_tokens, output_tokens)]

    section_freq = Counter()
    for r in records:
        for s in extract_ipc_from_output(r.get("output", "")):
            section_freq[s] += 1

    leakage_cases = [r for r in records if check_leakage(r)]

    in_dist  = Counter(bucket(t, INPUT_BUCKETS)  for t in input_tokens)
    out_dist = Counter(bucket(t, OUTPUT_BUCKETS) for t in output_tokens)

    return {
        "name":          name,
        "count":         len(records),
        "input_tokens":  {"min": min(input_tokens), "max": max(input_tokens),
                          "avg": round(sum(input_tokens)/len(input_tokens))},
        "output_tokens": {"min": min(output_tokens), "max": max(output_tokens),
                          "avg": round(sum(output_tokens)/len(output_tokens))},
        "total_tokens":  {"min": min(total_tokens), "max": max(total_tokens),
                          "avg": round(sum(total_tokens)/len(total_tokens))},
        "section_freq":  dict(section_freq.most_common(20)),
        "leakage_count": len(leakage_cases),
        "input_dist":    dict(in_dist),
        "output_dist":   dict(out_dist),
    }


def print_analysis(stats: dict):
    name  = stats["name"]
    count = stats["count"]
    print(f"\n── {name.upper()} ({count} records) ─────────────────────────")
    if count == 0:
        print("  (empty)")
        return

    it = stats["input_tokens"]
    ot = stats["output_tokens"]
    tt = stats["total_tokens"]
    print(f"  Input tokens   : min={it['min']}  avg={it['avg']}  max={it['max']}")
    print(f"  Output tokens  : min={ot['min']}  avg={ot['avg']}  max={ot['max']}")
    print(f"  Total tokens   : min={tt['min']}  avg={tt['avg']}  max={tt['max']}")

    print(f"\n  Input token distribution:")
    for bucket_label in ["<50","50-149","150-299","300-511","512-1023",">=1024"]:
        c = stats["input_dist"].get(bucket_label, 0)
        if c:
            bar = "█" * min(c, 30)
            print(f"    {bucket_label:<12}: {bar} {c}")

    sec_freq = stats["section_freq"]
    if sec_freq:
        print(f"\n  IPC section distribution (top 15):")
        for s, c in list(sec_freq.items())[:15]:
            bar = "█" * min(c, 20)
            print(f"    {s:<14}: {bar} {c}")

    leak = stats["leakage_count"]
    if leak > 0:
        print(f"\n  ⚠  Potential leakage cases: {leak}/{count} "
              f"({100*leak//count}%) — review 02_prepare_dataset.py masking")
    else:
        print(f"\n  ✓ Leakage check: 0 cases")


def main():
    parser = argparse.ArgumentParser(description="Analyze prepared JSONL dataset")
    parser.add_argument("--data_dir", default="data/processed")
    args = parser.parse_args()

    base = Path(args.data_dir)

    train = load_jsonl(base / "train" / "dataset.jsonl")
    val   = load_jsonl(base / "val"   / "dataset.jsonl")
    test  = load_jsonl(base / "test"  / "dataset.jsonl")

    if not train and not val and not test:
        print(f"ERROR: No JSONL files found in {base}")
        print("Run 02_prepare_dataset.py first.")
        raise SystemExit(1)

    total = len(train) + len(val) + len(test)
    all_records = train + val + test

    print("\n" + "=" * 55)
    print("  DATASET ANALYSIS")
    print("=" * 55)
    print(f"  Total records  : {total}")
    print(f"  Train / Val / Test : {len(train)} / {len(val)} / {len(test)}")

    # Overall section frequency across all splits
    all_sections = Counter()
    for r in all_records:
        for s in extract_ipc_from_output(r.get("output", "")):
            all_sections[s] += 1

    print(f"\n  Unique IPC sections : {len(all_sections)}")
    rare = {s: c for s, c in all_sections.items() if c < 5}
    if rare:
        print(f"  Rare (<5 cases)    : {len(rare)} — {sorted(rare)}")
    very_rare = {s: c for s, c in all_sections.items() if c < 2}
    if very_rare:
        print(f"  Singleton sections : {sorted(very_rare)}")

    # Per-split analysis
    for name, records in [("train", train), ("val", val), ("test", test)]:
        stats = analyze_split(name, records)
        print_analysis(stats)

    # Sequence-length warning for training
    print("\n" + "=" * 55)
    print("  SEQUENCE LENGTH GUIDANCE")
    print("=" * 55)
    if train:
        total_toks = [approx_tokens(r.get("input","")) +
                      approx_tokens(r.get("output","")) for r in train]
        p95 = sorted(total_toks)[int(len(total_toks)*0.95)]
        p99 = sorted(total_toks)[int(len(total_toks)*0.99)]
        print(f"  Train total tokens: 95th pct={p95}  99th pct={p99}")
        if p95 <= 512:
            rec_len = 512
        elif p95 <= 1024:
            rec_len = 1024
        else:
            rec_len = 2048
        print(f"  Recommended max_seq_length: {rec_len}")
        print(f"  (Start with 512 for CPU smoke test regardless)")

    print("\n  Next: python scripts/04_test_base_model.py")
    print("=" * 55 + "\n")

    # Show 1 sample record
    if train:
        print("── SAMPLE TRAINING RECORD ──────────────────────────────")
        r = train[0]
        print(f"  INSTRUCTION: {r.get('instruction','')[:80]}...")
        print(f"  INPUT (first 200 chars): {r.get('input','')[:200]}")
        print(f"  OUTPUT: {r.get('output','')}")
        print("────────────────────────────────────────────────────────\n")


if __name__ == "__main__":
    main()
