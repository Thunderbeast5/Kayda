"""
04_test_base_model.py
=====================
Tests the unmodified base model (Qwen2-0.5B-Instruct) on the test set
BEFORE any fine-tuning. Saves predictions to logs/ for later comparison.

This establishes the baseline metrics:
  - Exact match
  - Micro-averaged Precision / Recall / F1
  - Per-section F1

Model: Qwen/Qwen2-0.5B-Instruct  (~1 GB RAM — safe on 16 GB machine)
Downloads automatically from HuggingFace on first run.

Usage:
    python scripts/04_test_base_model.py
    python scripts/04_test_base_model.py --limit 50
    python scripts/04_test_base_model.py --data_dir data/processed
"""

import json
import re
import argparse
import time
from pathlib import Path
from collections import defaultdict


BASE_MODEL   = "Qwen/Qwen2-0.5B-Instruct"
MAX_NEW_TOK  = 80    # output is short: "IPC Sections: 302, 34\nBNS: ..."


def load_jsonl(path: Path) -> list:
    if not path.exists():
        return []
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def parse_predicted_sections(text: str) -> list:
    """Extract section numbers from model output."""
    m = re.search(r'IPC\s+Sections?:\s*(.*?)(?:\n|$)', text, re.IGNORECASE)
    raw = m.group(1) if m else text
    found = re.findall(r'(\d{2,3}[A-Za-z]*(?:\(\d+\))?(?:\([a-z]\))?)', raw)
    return list(dict.fromkeys(s for s in found if re.search(r'\d', s)))


def parse_true_sections(output: str) -> list:
    return parse_predicted_sections(output)  # same format


def prf(pred: set, true: set):
    tp = len(pred & true)
    fp = len(pred - true)
    fn = len(true - pred)
    p  = tp / (tp + fp) if (tp + fp) > 0 else (1.0 if not true else 0.0)
    r  = tp / (tp + fn) if (tp + fn) > 0 else (1.0 if not pred  else 0.0)
    f1 = 2*p*r / (p+r) if (p+r) > 0 else 0.0
    return round(p, 3), round(r, 3), round(f1, 3)


def run_baseline(records: list, model, tokenizer, device: str,
                 limit: int = 0) -> list:
    if limit > 0:
        records = records[:limit]

    results = []
    for i, rec in enumerate(records):
        instruction = rec.get("instruction", "")
        input_text  = rec.get("input", "")
        true_output = rec.get("output", "")

        # Build prompt using tokenizer chat template where available
        messages = [
            {"role": "system",    "content": instruction},
            {"role": "user",      "content": input_text},
        ]
        try:
            prompt = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
        except Exception:
            prompt = f"{instruction}\n\n{input_text}\n\nAnswer:"

        inputs = tokenizer(prompt, return_tensors="pt",
                           truncation=True, max_length=600).to(device)

        import torch
        t0 = time.time()
        with torch.no_grad():
            out_ids = model.generate(
                **inputs,
                max_new_tokens   = MAX_NEW_TOK,
                do_sample        = False,      # greedy for baseline consistency
                temperature      = 1.0,
                pad_token_id     = tokenizer.eos_token_id,
            )
        elapsed = time.time() - t0

        response = tokenizer.decode(
            out_ids[0][inputs["input_ids"].shape[1]:],
            skip_special_tokens=True
        ).strip()

        pred_secs = set(parse_predicted_sections(response))
        true_secs = set(parse_true_sections(true_output))
        p, r, f1  = prf(pred_secs, true_secs)

        results.append({
            "case_id":    rec.get("_meta", {}).get("case_id", str(i)),
            "true":       sorted(true_secs),
            "pred":       sorted(pred_secs),
            "exact":      pred_secs == true_secs,
            "precision":  p,
            "recall":     r,
            "f1":         f1,
            "response":   response,
            "elapsed_s":  round(elapsed, 2),
        })

        if (i+1) % 5 == 0 or (i+1) == len(records):
            running_f1 = sum(r2["f1"] for r2 in results) / len(results)
            print(f"  [{i+1:>4}/{len(records)}] running F1={running_f1:.3f}  "
                  f"last: true={results[-1]['true']} pred={results[-1]['pred']}")

    return results


def compute_metrics(results: list) -> dict:
    n       = len(results)
    exact   = sum(r["exact"]     for r in results) / n
    avg_p   = sum(r["precision"] for r in results) / n
    avg_r   = sum(r["recall"]    for r in results) / n
    avg_f1  = sum(r["f1"]        for r in results) / n

    # Per-section
    sec_tp = defaultdict(int)
    sec_fp = defaultdict(int)
    sec_fn = defaultdict(int)
    for r in results:
        ts = set(r["true"]); ps = set(r["pred"])
        for s in ps & ts: sec_tp[s] += 1
        for s in ps - ts: sec_fp[s] += 1
        for s in ts - ps: sec_fn[s] += 1

    per_section = {}
    for s in set(sec_tp) | set(sec_fn):
        tp = sec_tp[s]; fp = sec_fp[s]; fn = sec_fn[s]
        p2 = tp/(tp+fp) if (tp+fp) > 0 else 0
        r2 = tp/(tp+fn) if (tp+fn) > 0 else 0
        f2 = 2*p2*r2/(p2+r2) if (p2+r2) > 0 else 0
        per_section[s] = {"p": round(p2,3), "r": round(r2,3),
                          "f1": round(f2,3), "support": tp+fn}

    return {
        "total_cases":   n,
        "exact_match":   round(exact, 4),
        "avg_precision": round(avg_p, 4),
        "avg_recall":    round(avg_r, 4),
        "avg_f1":        round(avg_f1, 4),
        "per_section":   dict(sorted(per_section.items(),
                                     key=lambda x: -x[1]["support"])[:20]),
    }


def main():
    parser = argparse.ArgumentParser(description="Baseline evaluation of untuned model")
    parser.add_argument("--model",    default=BASE_MODEL)
    parser.add_argument("--data_dir", default="data/processed")
    parser.add_argument("--limit",    type=int, default=0,
                        help="Limit test cases (0=all)")
    args = parser.parse_args()

    test_path = Path(args.data_dir) / "test" / "dataset_with_meta.jsonl"
    if not test_path.exists():
        test_path = Path(args.data_dir) / "test" / "dataset.jsonl"
    if not test_path.exists():
        print(f"ERROR: Test data not found. Run 02_prepare_dataset.py first.")
        raise SystemExit(1)

    records = load_jsonl(test_path)
    if not records:
        print("ERROR: Empty test set.")
        raise SystemExit(1)

    limit = args.limit if args.limit > 0 else len(records)
    print(f"\nBaseline evaluation on {min(limit, len(records))} test cases")
    print(f"Model : {args.model}")

    # ── Load model ────────────────────────────────────────────────────────────
    print("Loading model (downloads ~1 GB on first run)...")
    from transformers import AutoTokenizer, AutoModelForCausalLM
    import torch

    device = "cpu"
    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    model     = AutoModelForCausalLM.from_pretrained(
        args.model,
        torch_dtype    = torch.float32,  # CPU requires float32
        trust_remote_code = True,
    ).to(device)
    model.eval()
    print(f"Model loaded on {device}\n")

    # ── Run baseline ──────────────────────────────────────────────────────────
    results = run_baseline(records, model, tokenizer, device, limit)
    metrics = compute_metrics(results)

    # ── Print ─────────────────────────────────────────────────────────────────
    print("\n" + "=" * 55)
    print("  BASELINE RESULTS (untuned model)")
    print("=" * 55)
    print(f"  Cases evaluated : {metrics['total_cases']}")
    print(f"  Exact Match     : {metrics['exact_match']:.1%}")
    print(f"  Avg Precision   : {metrics['avg_precision']:.1%}")
    print(f"  Avg Recall      : {metrics['avg_recall']:.1%}")
    print(f"  Avg F1          : {metrics['avg_f1']:.1%}")
    if metrics["per_section"]:
        print("\n  Per-section (top 10 by support):")
        for s, m in list(metrics["per_section"].items())[:10]:
            print(f"    IPC {s:<12} F1={m['f1']:.2f} "
                  f"P={m['p']:.2f} R={m['r']:.2f} support={m['support']}")
    print("=" * 55)

    # ── Save ──────────────────────────────────────────────────────────────────
    Path("logs").mkdir(exist_ok=True)
    out = {
        "model":   args.model,
        "phase":   "baseline_pretrain",
        "metrics": metrics,
        "details": results,
    }
    out_path = Path("logs/baseline_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"\n  Saved → {out_path}")
    print("  Next: python scripts/05_train_lora_cpu.py --limit 100")


if __name__ == "__main__":
    main()
