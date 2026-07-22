"""
evaluator.py
Evaluates the fine-tuned model on the test set.
Metrics: Exact match, Partial match (F1), Section-level accuracy.
"""
import re
import json
import torch
from pathlib import Path
from typing import Dict, List, Tuple
from collections import defaultdict
from tqdm import tqdm
from loguru import logger

from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel


class LegalModelEvaluator:
    def __init__(self, model_path: str, base_model: str = "mistralai/Mistral-7B-Instruct-v0.2"):
        self.model_path = Path(model_path)
        self.base_model = base_model
        self.device     = "cuda" if torch.cuda.is_available() else "cpu"
        self._load()

    def _load(self):
        logger.info(f"Loading model from {self.model_path}")
        self.tokenizer = AutoTokenizer.from_pretrained(str(self.model_path))

        base = AutoModelForCausalLM.from_pretrained(
            self.base_model,
            torch_dtype=torch.float16,
            device_map="auto",
        )
        self.model = PeftModel.from_pretrained(base, str(self.model_path))
        self.model.eval()
        logger.info("Model loaded")

    def predict(self, instruction: str, input_text: str,
                max_new_tokens: int = 256) -> str:
        user_msg = f"{instruction}\n\n{input_text}" if input_text else instruction
        prompt   = f"<s>[INST] {user_msg} [/INST]"

        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens    = max_new_tokens,
                temperature       = 0.1,
                do_sample         = True,
                top_p             = 0.95,
                repetition_penalty= 1.1,
                pad_token_id      = self.tokenizer.eos_token_id,
            )
        response = self.tokenizer.decode(
            outputs[0][inputs["input_ids"].shape[1]:],
            skip_special_tokens=True
        ).strip()
        return response

    def evaluate(self, test_records: List[Dict]) -> Dict:
        """
        Returns:
          exact_match        — fraction where predicted == actual (set equality)
          partial_f1         — macro-averaged F1 at section level
          precision / recall — averaged across all test cases
          per_section_stats  — per-section accuracy for the 20 most common sections
        """
        results = []
        for rec in tqdm(test_records, desc="Evaluating"):
            pred_text = self.predict(rec["instruction"], rec["input"])
            pred_secs = self._parse_sections(pred_text)
            true_secs = set(rec["_meta"]["ipc_sections"])

            p, r, f1  = self._prf(pred_secs, true_secs)
            exact      = (set(pred_secs) == true_secs)

            results.append({
                "case_id":  rec["_meta"]["case_id"],
                "true":     list(true_secs),
                "pred":     pred_secs,
                "exact":    exact,
                "precision":p, "recall": r, "f1": f1,
                "raw_output": pred_text,
            })

        # Aggregate
        n          = len(results)
        exact_acc  = sum(r["exact"]     for r in results) / n
        avg_p      = sum(r["precision"] for r in results) / n
        avg_r      = sum(r["recall"]    for r in results) / n
        avg_f1     = sum(r["f1"]        for r in results) / n

        # Per-section stats
        sec_tp = defaultdict(int)
        sec_fp = defaultdict(int)
        sec_fn = defaultdict(int)
        for r in results:
            true_s = set(r["true"])
            pred_s = set(r["pred"])
            for s in pred_s & true_s:
                sec_tp[s] += 1
            for s in pred_s - true_s:
                sec_fp[s] += 1
            for s in true_s - pred_s:
                sec_fn[s] += 1

        per_section = {}
        all_secs = set(sec_tp) | set(sec_fn)
        for s in all_secs:
            tp = sec_tp[s]; fp = sec_fp[s]; fn = sec_fn[s]
            prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            rec  = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1   = 2*prec*rec/(prec+rec) if (prec+rec) > 0 else 0.0
            per_section[s] = {"precision": round(prec,3),
                               "recall": round(rec,3), "f1": round(f1,3),
                               "support": tp + fn}

        metrics = {
            "total_cases":   n,
            "exact_match":   round(exact_acc, 4),
            "avg_precision": round(avg_p, 4),
            "avg_recall":    round(avg_r, 4),
            "avg_f1":        round(avg_f1, 4),
            "per_section":   dict(sorted(per_section.items(),
                                         key=lambda x: -x[1]["support"])[:25]),
        }

        logger.info(
            f"Results — Exact: {exact_acc:.3f} | "
            f"P: {avg_p:.3f} | R: {avg_r:.3f} | F1: {avg_f1:.3f}"
        )

        # Save detailed results
        out = Path("logs/eval_results.json")
        out.parent.mkdir(exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump({"metrics": metrics, "details": results[:200]},
                      f, ensure_ascii=False, indent=2)
        logger.info(f"Detailed results saved to {out}")

        return metrics

    # ── helpers ───────────────────────────────────────────────────────────────

    def _parse_sections(self, text: str) -> List[str]:
        """Extract IPC section numbers from model output."""
        # Match after "IPC Sections:" label
        m = re.search(r'IPC\s+Sections?:\s*(.*?)(?:\n|BNS|$)',
                      text, re.IGNORECASE | re.DOTALL)
        if m:
            raw = m.group(1)
        else:
            raw = text

        # Extract section numbers like 376, 376(2), 376AB, 34
        found = re.findall(r'\b(\d{2,3}[A-Za-z]*(?:\(\d+\))?(?:\([a-z]\))?)\b', raw)
        # Normalise
        out = []
        for s in found:
            s = s.strip().rstrip(".,;")
            if s and re.search(r'\d', s):
                out.append(s)
        return list(dict.fromkeys(out))  # deduplicate preserving order

    def _prf(self, pred: List[str],
             true: set) -> Tuple[float, float, float]:
        pred_s = set(pred)
        tp = len(pred_s & true)
        fp = len(pred_s - true)
        fn = len(true - pred_s)
        p  = tp / (tp + fp) if (tp + fp) > 0 else (1.0 if not true else 0.0)
        r  = tp / (tp + fn) if (tp + fn) > 0 else (1.0 if not pred_s else 0.0)
        f1 = 2*p*r/(p+r) if (p+r) > 0 else 0.0
        return p, r, f1
