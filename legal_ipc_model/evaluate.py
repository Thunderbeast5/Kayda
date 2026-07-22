"""
evaluate.py — Step 3: Evaluate trained model on test set.

Usage:
    python evaluate.py
    python evaluate.py --model_path models/legal_model/final
    python evaluate.py --model_path models/legal_model/final --samples 500
"""
import argparse
import json
import os
import sys
sys.path.insert(0, "src")

from utils.logger_setup import setup_logger
from model.evaluator import LegalModelEvaluator

logger = setup_logger()


def load_jsonl(path: str) -> list:
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                r = json.loads(line)
                # Re-attach _meta placeholder so evaluator can use it
                if "_meta" not in r:
                    r["_meta"] = {
                        "case_id": "", "citation": "",
                        "ipc_sections": [], "bns_sections": [],
                        "has_sections": True
                    }
                records.append(r)
    return records


def main():
    parser = argparse.ArgumentParser(description="Evaluate legal IPC model")
    parser.add_argument("--model_path",
                        default="models/legal_model/final",
                        help="Path to saved LoRA adapter")
    parser.add_argument("--base_model",
                        default="mistralai/Mistral-7B-Instruct-v0.2")
    parser.add_argument("--data_dir",  default="data/processed")
    parser.add_argument("--samples",   type=int, default=0,
                        help="Max test samples (0 = all)")
    args = parser.parse_args()

    test_path = f"{args.data_dir}/test/dataset.jsonl"
    if not os.path.exists(test_path):
        logger.error(f"Test data not found: {test_path}")
        sys.exit(1)

    # Load test set — need JSONL with _meta for section labels
    # If _meta was stripped during saving, load from dataset_summary.csv instead
    # and reconstruct
    logger.info(f"Loading test data from {test_path}")
    test_records = load_jsonl(test_path)

    if args.samples > 0:
        test_records = test_records[:args.samples]
        logger.info(f"Using {args.samples} samples for evaluation")

    logger.info(f"Evaluating on {len(test_records)} test cases")

    # Init evaluator
    evaluator = LegalModelEvaluator(
        model_path = args.model_path,
        base_model = args.base_model,
    )

    # Run evaluation
    metrics = evaluator.evaluate(test_records)

    # Print summary
    print("\n" + "=" * 55)
    print("  EVALUATION RESULTS")
    print("=" * 55)
    print(f"  Total cases    : {metrics['total_cases']}")
    print(f"  Exact Match    : {metrics['exact_match']:.1%}")
    print(f"  Avg Precision  : {metrics['avg_precision']:.1%}")
    print(f"  Avg Recall     : {metrics['avg_recall']:.1%}")
    print(f"  Avg F1         : {metrics['avg_f1']:.1%}")
    print("-" * 55)
    print("  Top Section Performance:")
    for sec, s in list(metrics["per_section"].items())[:10]:
        print(f"    IPC {sec:<8} F1={s['f1']:.2f}  "
              f"(P={s['precision']:.2f} R={s['recall']:.2f})  "
              f"support={s['support']}")
    print("=" * 55)
    print("  Full results saved to: logs/eval_results.json")


if __name__ == "__main__":
    main()
