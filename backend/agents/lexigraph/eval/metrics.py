"""
metrics.py
==========
Quantitative evaluation metrics suite for legal GraphRAG benchmark.

Computes:
- Top-1 Section Accuracy
- Top-3 Section Recall & Precision
- Mean Reciprocal Rank (MRR)
- Ingredient Validation Accuracy
- Evidence Precision & Recall
- Community Cluster Alignment Accuracy
- Confidence Calibration (Expected Calibration Error - ECE)
- Negative Scenario Precision (False Positive Rejection)
"""

import math
import re
from typing import Dict, Any, List


class BenchmarkMetrics:
    """Computes legal retrieval and reasoning evaluation metrics."""

    @staticmethod
    def _clean_sec(sec_str: str) -> str:
        if not sec_str:
            return ""
        s = str(sec_str).upper().strip()
        s = re.sub(r"^(BNS|IPC|SECTION)\s*", "", s).strip()
        return s

    @classmethod
    def compute_top_k_hit(cls, predicted_sections: List[str], expected_sections: List[str], k: int = 1) -> float:
        if not expected_sections:
            return 1.0 if not predicted_sections else 0.0
        preds_k = [cls._clean_sec(p) for p in predicted_sections[:k] if cls._clean_sec(p)]
        exp_k = [cls._clean_sec(e) for e in expected_sections if cls._clean_sec(e)]

        for pred in preds_k:
            for exp in exp_k:
                if pred == exp or exp in pred or pred in exp:
                    return 1.0
        return 0.0

    @classmethod
    def compute_mrr(cls, predicted_sections: List[str], expected_sections: List[str]) -> float:
        if not expected_sections:
            return 1.0 if not predicted_sections else 0.0
        exp_k = [cls._clean_sec(e) for e in expected_sections if cls._clean_sec(e)]

        for rank, pred in enumerate(predicted_sections, 1):
            pred_clean = cls._clean_sec(pred)
            if not pred_clean:
                continue
            for exp in exp_k:
                if pred_clean == exp or exp in pred_clean or pred_clean in exp:
                    return 1.0 / rank
        return 0.0

    @staticmethod
    def compute_array_precision_recall(predicted: List[str], expected: List[str]) -> Dict[str, float]:
        if not expected:
            return {"precision": 1.0 if not predicted else 0.0, "recall": 1.0}
        if not predicted:
            return {"precision": 0.0, "recall": 0.0}

        pred_set = {p.lower().strip() for p in predicted}
        exp_set = {e.lower().strip() for e in expected}

        hits = sum(1 for p in pred_set if any(e in p or p in e for e in exp_set))
        precision = hits / len(pred_set)
        recall = hits / len(exp_set)
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

        return {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4)
        }

    @staticmethod
    def compute_confidence_calibration(predicted_conf: float, conf_range: List[float]) -> float:
        """Returns calibration score (1.0 if inside expected range, linear penalty if outside)."""
        if not conf_range or len(conf_range) < 2:
            return 1.0
        min_c, max_c = conf_range[0], conf_range[1]
        if min_c <= predicted_conf <= max_c:
            return 1.0
        elif predicted_conf < min_c:
            diff = min_c - predicted_conf
            return max(0.0, 1.0 - (diff * 2.0))
        else:
            diff = predicted_conf - max_c
            return max(0.0, 1.0 - (diff * 2.0))
