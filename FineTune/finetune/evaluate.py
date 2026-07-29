"""
Phase 5 — Evaluation of the fine-tuned model on the held-out test set.

Runs the model on test.jsonl and computes:
  - ROUGE-L score (overlap with reference outputs)
  - Outcome classification accuracy (for outcome_classification pairs)
  - Manual review output (saves model outputs alongside expected for human review)

Run:
    python finetune/evaluate.py                         # evaluate merged model
    python finetune/evaluate.py --adapter-only          # evaluate with adapter (no merge needed)
    python finetune/evaluate.py --baseline              # evaluate base Gemma-2B (no fine-tuning)
"""

import argparse
import json
import logging
import re
import sys
from pathlib import Path
import os

# Redirect HF cache to D: before any HF import
_hf_cache = Path("D:/hf_cache")
_hf_cache.mkdir(parents=True, exist_ok=True)
os.environ["HF_HOME"] = str(_hf_cache)

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")
logger = logging.getLogger(__name__)

VALID_OUTCOMES = {"granted", "modified", "deleted", "refused", "dismissed", "referred", "interim"}


def load_model_for_inference(model_path: str, adapter_path: str | None = None):
    """Load model for inference. Returns (model, tokenizer)."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    logger.info(f"Loading model: {model_path}")
    tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    dtype = torch.float16 if torch.cuda.is_available() else torch.float32
    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        torch_dtype=dtype,
        device_map="auto" if torch.cuda.is_available() else "cpu",
        trust_remote_code=True,
    )

    if adapter_path:
        from peft import PeftModel
        logger.info(f"Loading adapter: {adapter_path}")
        model = PeftModel.from_pretrained(model, adapter_path)

    model.eval()
    return model, tokenizer


def generate_response(
    model, tokenizer, instruction: str, input_text: str,
    prompt_template: str, max_new_tokens: int = 300,
) -> str:
    """Generate model response for one example."""
    import torch

    prompt = prompt_template.format(
        instruction=instruction.strip(),
        input=input_text.strip(),
    )

    inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=1024)
    inputs = {k: v.to(model.device) for k, v in inputs.items()}

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,          # Greedy decoding for evaluation (deterministic)
            temperature=1.0,
            pad_token_id=tokenizer.eos_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )

    # Decode only the newly generated tokens (not the prompt)
    new_tokens = outputs[0][inputs["input_ids"].shape[1]:]
    response = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
    return response


def rouge_l_score(prediction: str, reference: str) -> float:
    """
    Compute ROUGE-L (longest common subsequence F1).
    Using word-level tokens for simplicity — no external library needed.
    """
    pred_words = prediction.lower().split()
    ref_words  = reference.lower().split()

    if not pred_words or not ref_words:
        return 0.0

    # LCS length using dynamic programming
    m, n = len(pred_words), len(ref_words)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if pred_words[i-1] == ref_words[j-1]:
                dp[i][j] = dp[i-1][j-1] + 1
            else:
                dp[i][j] = max(dp[i-1][j], dp[i][j-1])
    lcs = dp[m][n]

    precision = lcs / m if m else 0
    recall    = lcs / n if n else 0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) else 0
    return round(f1, 4)


def extract_outcome_label(text: str) -> str | None:
    """
    Try to extract an outcome label from model output.
    Looks for any of the valid outcome strings.
    """
    text_lower = text.lower()
    # Check for explicit label
    for outcome in VALID_OUTCOMES:
        if outcome in text_lower:
            return outcome
    return None


def run_evaluation(
    model, tokenizer, test_path: Path,
    prompt_template_inference: str,
    output_path: Path,
) -> dict:
    """Run full evaluation on test set."""
    import json

    test_pairs = []
    with open(test_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                test_pairs.append(json.loads(line))

    logger.info(f"Evaluating on {len(test_pairs)} test examples...")

    results = []
    rouge_scores = []
    outcome_correct = 0
    outcome_total = 0

    for i, pair in enumerate(test_pairs):
        response = generate_response(
            model, tokenizer,
            pair["instruction"],
            pair.get("input", ""),
            prompt_template_inference,
        )

        reference = pair["output"]
        rl = rouge_l_score(response, reference)
        rouge_scores.append(rl)

        result = {
            "instruction": pair["instruction"],
            "input":       pair.get("input", "")[:200],
            "expected":    reference,
            "predicted":   response,
            "rouge_l":     rl,
        }

        # Outcome accuracy
        if "outcome_classification" in pair.get("instruction", "").lower() or \
           "classify" in pair.get("instruction", "").lower():
            expected_label = extract_outcome_label(reference)
            predicted_label = extract_outcome_label(response)
            if expected_label:
                outcome_total += 1
                if expected_label == predicted_label:
                    outcome_correct += 1
                result["outcome_expected"] = expected_label
                result["outcome_predicted"] = predicted_label
                result["outcome_correct"] = (expected_label == predicted_label)

        results.append(result)

        if (i + 1) % 10 == 0:
            logger.info(f"  {i+1}/{len(test_pairs)} done | avg ROUGE-L so far: "
                        f"{sum(rouge_scores)/len(rouge_scores):.3f}")

    avg_rouge_l = sum(rouge_scores) / len(rouge_scores) if rouge_scores else 0
    outcome_acc = outcome_correct / outcome_total if outcome_total else None

    summary = {
        "total_examples": len(test_pairs),
        "avg_rouge_l":    round(avg_rouge_l, 4),
        "outcome_accuracy": round(outcome_acc, 4) if outcome_acc is not None else None,
        "outcome_total":  outcome_total,
    }

    # Save full results
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "results": results}, f, indent=2, ensure_ascii=False)

    return summary


def print_summary(summary: dict, model_label: str) -> None:
    print(f"\n{'='*55}")
    print(f"  EVALUATION RESULTS — {model_label}")
    print(f"{'='*55}")
    print(f"  Test examples    : {summary['total_examples']}")
    print(f"  Avg ROUGE-L      : {summary['avg_rouge_l']:.4f}")
    if summary["outcome_accuracy"] is not None:
        print(f"  Outcome accuracy : {summary['outcome_accuracy']:.1%} "
              f"({summary['outcome_total']} examples)")
    print(f"{'='*55}\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter-only", action="store_true",
                        help="Load base model + adapter instead of merged model")
    parser.add_argument("--baseline", action="store_true",
                        help="Evaluate the base Gemma-2B without fine-tuning")
    args = parser.parse_args()

    from finetune.config import (
        MODEL_ID, MODEL_OUTPUT_DIR, MERGED_OUTPUT_DIR,
        TEST_FILE, LOGS_DIR,
        PROMPT_TEMPLATE_INFERENCE,
    )

    if args.baseline:
        model_path = MODEL_ID
        adapter_path = None
        label = "BASE Gemma-2B (no fine-tuning)"
        out_path = LOGS_DIR / "eval_baseline.json"
    elif args.adapter_only:
        model_path = MODEL_ID
        adapter_path = str(MODEL_OUTPUT_DIR / "final_adapter")
        label = "Gemma-2B + LoRA adapter"
        out_path = LOGS_DIR / "eval_adapter.json"
    else:
        model_path = str(MERGED_OUTPUT_DIR)
        adapter_path = None
        label = "Gemma-2B fine-tuned (merged)"
        out_path = LOGS_DIR / "eval_finetuned.json"

    model, tokenizer = load_model_for_inference(model_path, adapter_path)

    summary = run_evaluation(model, tokenizer, TEST_FILE, PROMPT_TEMPLATE_INFERENCE, out_path)
    print_summary(summary, label)
    logger.info(f"Full results saved → {out_path}")


if __name__ == "__main__":
    main()
