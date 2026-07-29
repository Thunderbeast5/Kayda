"""
feedback_service.py
====================
Ties PredictionLogger + OutcomeVerificationService together and resolves a
label for any prediction:

    human feedback exists?  -> use it, source="human", trust=high
    else                    -> run the LLM judge, source="llm_judge", trust=soft

No UI required to start — submit_feedback() is callable directly from a Flask
route, a CLI, or a notebook. Every human-labeled record is worth more later:
once resolve_all_pending() has run for a while, filter by source="human" to
get a real training/eval set for weight-tuning, without touching the LLM
judge's soft labels.
"""

import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

from prediction_logger import PredictionLogger
from outcome_verification_service import OutcomeVerificationService

try:
    from agents.lexigraph.eval.failure_analyzer import FailureAnalyzer
except ModuleNotFoundError:
    FailureAnalyzer = None  # eval/ layout may differ in production; degrade gracefully


class FeedbackService:
    """Resolves labels for logged predictions and surfaces retuning signal."""

    def __init__(self, storage_dir: str = "feedback"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.human_feedback_path = self.storage_dir / "human_feedback.jsonl"

        self.logger = PredictionLogger(storage_dir=storage_dir)
        self.judge = OutcomeVerificationService()
        self.analyzer = FailureAnalyzer() if FailureAnalyzer else None

    # ------------------------------------------------------------------ #
    # Human feedback intake
    # ------------------------------------------------------------------ #

    def submit_feedback(
        self,
        prediction_id: str,
        correct: bool,
        corrected_section: Optional[str] = None,
        notes: str = "",
    ) -> Dict[str, Any]:
        """
        Records human feedback for a prediction_id. This is the highest-trust
        signal in the system — it always overrides any prior LLM-judge verdict
        when resolve_label() is next called for this prediction.
        """
        record = {
            "prediction_id": prediction_id,
            "timestamp": time.time(),
            "correct": correct,
            "corrected_section": corrected_section,
            "notes": notes,
            "source": "human",
        }
        with open(self.human_feedback_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

        # Immediately resolve so the prediction log doesn't sit stale.
        self._apply_label(prediction_id, self._human_record_to_label(record))
        return record

    def _human_record_to_label(self, human_record: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "source": "human",
            "trust": "high",
            "overall_verdict": "correct" if human_record["correct"] else "incorrect",
            "corrected_section": human_record.get("corrected_section"),
            "notes": human_record.get("notes", ""),
        }

    def _get_human_feedback(self, prediction_id: str) -> Optional[Dict[str, Any]]:
        if not self.human_feedback_path.exists():
            return None
        latest = None
        with open(self.human_feedback_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if rec.get("prediction_id") == prediction_id:
                    latest = rec  # last write wins if feedback was corrected
        return latest

    # ------------------------------------------------------------------ #
    # Label resolution
    # ------------------------------------------------------------------ #

    def resolve_label(self, prediction_id: str) -> Optional[Dict[str, Any]]:
        """
        human feedback exists -> use it (trusted)
        else                  -> run LLM judge (soft label)
        """
        prediction = self.logger.get_prediction(prediction_id)
        if not prediction:
            return None

        human_record = self._get_human_feedback(prediction_id)
        if human_record:
            label = self._human_record_to_label(human_record)
        else:
            label = self.judge.judge_prediction(prediction)
            label["trust"] = "soft"

        self._apply_label(prediction_id, label)
        return label

    def resolve_all_pending(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Batch-resolves every pending prediction (typically run on a schedule)."""
        pending = self.logger.list_pending(limit=limit)
        resolved = []
        for p in pending:
            label = self.resolve_label(p["prediction_id"])
            if label:
                resolved.append({"prediction_id": p["prediction_id"], "label": label})
        return resolved

    def _apply_label(self, prediction_id: str, label: Dict[str, Any]) -> None:
        self.logger.update_label(prediction_id, label)

    # ------------------------------------------------------------------ #
    # Closing the loop: route resolved labels through failure_analyzer
    # ------------------------------------------------------------------ #

    def get_failure_breakdown(self, min_trust: str = "soft") -> Dict[str, Any]:
        """
        Aggregates resolved, incorrect/partially-correct predictions into the
        same failure-stage buckets evaluation_runner.py produces for the
        offline benchmark — so production drift and benchmark regressions
        show up in one place, not two separate reports.

        min_trust="human" restricts this to human-labeled examples only,
        which is what you want once enough real feedback has accumulated
        to stop leaning on the LLM judge's own blind spots.
        """
        if not self.analyzer:
            return {"error": "FailureAnalyzer not importable in this environment."}

        all_predictions = self.logger._read_all()
        stage_failures: Dict[str, int] = {}
        examples: List[Dict[str, Any]] = []

        for p in all_predictions:
            label = p.get("label")
            if not label or p.get("label_status") != "resolved":
                continue
            if min_trust == "human" and label.get("source") != "human":
                continue

            verdict = label.get("overall_verdict")
            if verdict not in ("incorrect", "partially_correct"):
                continue

            # Reshape into the (scenario, pipeline_output) pair failure_analyzer expects.
            pseudo_scenario = {
                "id": p["prediction_id"],
                "is_negative_example": False,
                "expected_bns_sections": [],
                "expected_top1": (label.get("corrected_section")
                                   if label.get("source") == "human" else None),
                "expected_confidence_range": [0.0, 1.0],
            }
            pseudo_output = {
                "recommended_sections": p.get("recommended_sections") or [],
                "rejected_sections": p.get("rejected_sections") or [],
                "pipeline_confidence": p.get("pipeline_confidence") or 0.0,
                "community": p.get("community") or {},
            }

            diag = self.analyzer.analyze_scenario_failure(pseudo_scenario, pseudo_output)
            for stg in diag["failed_stages"]:
                stage_failures[stg] = stage_failures.get(stg, 0) + 1

            examples.append({
                "prediction_id": p["prediction_id"],
                "label_source": label.get("source"),
                "verdict": verdict,
                "diagnosis": diag,
            })

        return {
            "total_resolved_failures": len(examples),
            "stage_failures_breakdown": stage_failures,
            "examples": examples,
        }