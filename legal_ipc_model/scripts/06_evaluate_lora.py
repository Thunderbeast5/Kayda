"""
06_evaluate_lora.py
===================
Evaluates the fine-tuned LoRA adapter against the baseline.
Prints a side-by-side comparison and saves metrics.

Usage:
    python scripts/06_evaluate_lora.py
    python scripts/06_evaluate_lora.py --adapter models/adapters/legal-ipc-lora/final
    python scripts/06_evaluate_lora.py --limit 50
"""

import json
import re
import argparse
from pathlib import Path
from collections import defaultdict


BASE_MODEL  = "google/gemma-3-4b-it"
MAX_NEW_TOK = 80


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


def parse_sections(text: str) -> list:
    m = re.search(r'IPC\s+Sections?:\s*(.*?)(?:\n|$)', text, re.IGNORECASE)
    raw = m.group(1) if m else text
    found = re.findall(r'(\d{2,3}[A-Za-z]*(?:\(\d+\))?(?:\([a-z]\))?)', raw)
    return list(dict.fromkeys(s for s in found if re.search(r'\d', s)))


def prf(pred: set, true: set):
    tp = len(pred & true); fp = len(pred - true); fn = len(true - pred)
    p  = tp/(tp+fp) if (tp+fp) > 0 else (1.0 if not true else 0.0)
    r  = tp/(tp+fn) if (tp+fn) > 0 else (1.0 if not pred  else 0.0)
    f1 = 2*p*r/(p+r) if (p+r) > 0 else 0.0
    return round(p,3), round(r,3), round(f1,3)


def evaluate(records: list, model, tokenizer, device: str, limit: int = 0) -> list:
    import torch
    if limit > 0:
        records = records[:limit]
    results = []
    for i, rec in enumerate(records):
        instruction = rec.get("instruction", "")
        input_text  = rec.get("input", "")
        true_output = rec.get("output", "")

        messages = [
            {"role": "system", "content": instruction},
            {"role": "user",   "content": input_text},
        ]
        try:
            prompt = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
        except Exception:
            prompt = f"System: {instruction}\nUser: {input_text}\nAssistant:"

        inputs = tokenizer(prompt, return_tensors="pt",
                           truncation=True, max_length=600).to(device)
        with torch.no_grad():
            out_ids = model.generate(
                **inputs, max_new_tokens=MAX_NEW_TOK,
                do_sample=False, pad_token_id=tokenizer.eos_token_id,
            )
        response = tokenizer.decode(
            out_ids[0][inputs["input_ids"].shape[1]:],
            skip_special_tokens=True
        ).strip()

        pred_secs = set(parse_sections(response))
        true_secs = set(parse_sections(true_output))
        p, r, f1  = prf(pred_secs, true_secs)

        results.append({
            "case_id":   rec.get("_meta", {}).get("case_id", str(i)) if isinstance(rec.get("_meta"), dict) else str(i),
            "true":      sorted(true_secs),
            "pred":      sorted(pred_secs),
            "exact":     pred_secs == true_secs,
            "precision": p, "recall": r, "f1": f1,
            "response":  response,
        })
        if (i+1) % 5 == 0 or (i+1) == len(records):
            rf1 = sum(x["f1"] for x in results) / len(results)
            print(f"  [{i+1:>4}/{len(records)}] F1={rf1:.3f}")
    return results


def compute_metrics(results: list) -> dict:
    n     = len(results)
    exact = sum(r["exact"]     for r in results) / n
    avg_p = sum(r["precision"] for r in results) / n
    avg_r = sum(r["recall"]    for r in results) / n
    avg_f = sum(r["f1"]        for r in results) / n
    sec_tp = defaultdict(int); sec_fp = defaultdict(int); sec_fn = defaultdict(int)
    for r in results:
        ts = set(r["true"]); ps = set(r["pred"])
        for s in ps & ts: sec_tp[s] += 1
        for s in ps - ts: sec_fp[s] += 1
        for s in ts - ps: sec_fn[s] += 1
    per_sec = {}
    for s in set(sec_tp) | set(sec_fn):
        tp=sec_tp[s]; fp=sec_fp[s]; fn=sec_fn[s]
        p2=tp/(tp+fp) if (tp+fp)>0 else 0
        r2=tp/(tp+fn) if (tp+fn)>0 else 0
        f2=2*p2*r2/(p2+r2) if (p2+r2)>0 else 0
        per_sec[s]={"p":round(p2,3),"r":round(r2,3),"f1":round(f2,3),"support":tp+fn}
    return {
        "total_cases": n, "exact_match": round(exact,4),
        "avg_precision": round(avg_p,4), "avg_recall": round(avg_r,4),
        "avg_f1": round(avg_f,4),
        "per_section": dict(sorted(per_sec.items(), key=lambda x: -x[1]["support"])[:20]),
    }


def load_baseline() -> dict | None:
    p = Path("logs/baseline_results.json")
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f).get("metrics")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter",  default="models/adapters/gemma3-legal-lora/final")
    parser.add_argument("--model",    default=BASE_MODEL)
    parser.add_argument("--data_dir", default="data/processed")
    parser.add_argument("--limit",    type=int, default=0)
    args = parser.parse_args()

    test_path = Path(args.data_dir) / "test" / "dataset_with_meta.jsonl"
    if not test_path.exists():
        test_path = Path(args.data_dir) / "test" / "dataset.jsonl"
    records = load_jsonl(test_path)
    if not records:
        print("ERROR: No test data. Run 02_prepare_dataset.py first.")
        raise SystemExit(1)

    if not Path(args.adapter).exists():
        print(f"ERROR: Adapter not found at {args.adapter}")
        print("Run 05_train_lora_cpu.py first.")
        raise SystemExit(1)

    print(f"\nEvaluating fine-tuned adapter: {args.adapter}")
    from transformers import AutoTokenizer, AutoModelForCausalLM
    from peft import PeftModel
    import torch

    tokenizer = AutoTokenizer.from_pretrained(args.adapter, trust_remote_code=True)
    base      = AutoModelForCausalLM.from_pretrained(
        args.model, torch_dtype=torch.float32, trust_remote_code=True
    )
    model     = PeftModel.from_pretrained(base, args.adapter)
    model.eval()

    results  = evaluate(records, model, tokenizer, "cpu", args.limit)
    metrics  = compute_metrics(results)
    baseline = load_baseline()

    print("\n" + "=" * 60)
    print("  EVALUATION COMPARISON")
    print("=" * 60)
    header = f"  {'Metric':<20} {'Baseline':>12} {'Fine-tuned':>12} {'Δ':>8}"
    print(header)
    print("-" * 60)
    for key, label in [
        ("exact_match",   "Exact Match"),
        ("avg_precision", "Precision"),
        ("avg_recall",    "Recall"),
        ("avg_f1",        "F1"),
    ]:
        ft_val = metrics[key]
        bl_val = baseline[key] if baseline else None
        delta  = f"{ft_val - bl_val:+.1%}" if bl_val is not None else "N/A"
        bl_str = f"{bl_val:.1%}" if bl_val is not None else "N/A"
        print(f"  {label:<20} {bl_str:>12} {ft_val:>11.1%} {delta:>8}")
    print("=" * 60)

    if metrics.get("per_section"):
        print("\n  Per-section (top 10):")
        for s, m in list(metrics["per_section"].items())[:10]:
            print(f"    IPC {s:<12} F1={m['f1']:.2f} "
                  f"P={m['p']:.2f} R={m['r']:.2f} support={m['support']}")

    # Save
    Path("logs").mkdir(exist_ok=True)
    out_path = Path("logs/lora_eval_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"adapter": args.adapter, "metrics": metrics,
                   "details": results}, f, indent=2, ensure_ascii=False)
    print(f"\n  Saved → {out_path}")
    print("  Next: python scripts/07_merge_lora.py")


if __name__ == "__main__":
    main()
