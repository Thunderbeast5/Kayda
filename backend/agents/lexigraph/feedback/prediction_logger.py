"""
prediction_logger.py
=====================
Persists every LexiGraphAgent.process_query() call as a labelable record.

Design notes:
- JSONL storage to start (feedback/predictions.jsonl). No schema migration risk
  while the label pipeline is still evolving; swap for SQLite/Postgres later by
  reimplementing _append() / _read_all() and keeping the public API identical.
- Each record captures not just the final recommended sections but the ranking
  signals that produced them (score_breakdown from reranking_service), so a
  future retrain/re-weighting pass doesn't need to re-run retrieval to see
  "why" a section scored the way it did.
- label_status starts "pending" and is flipped by feedback_service.py once a
  human or the LLM judge resolves it.
"""

import json
import uuid
import time
from pathlib import Path
from typing import Dict, Any, List, Optional


class PredictionLogger:
    """Append-only log of production predictions awaiting label resolution."""

    def __init__(self, storage_dir: str = "feedback"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.predictions_path = self.storage_dir / "predictions.jsonl"

    def log_prediction(
        self,
        query: str,
        extracted_facts: Dict[str, Any],
        pipeline_output: Dict[str, Any],
        ranked_candidates: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """
        Persists one process_query() call. Returns the prediction_id so the
        caller (e.g. the Flask route that invoked the agent) can later attach
        human feedback to this exact prediction.
        """
        prediction_id = str(uuid.uuid4())

        recommended = pipeline_output.get("recommended_sections") or []
        rejected = pipeline_output.get("rejected_sections") or []

        # Pull score_breakdown for each recommended section from ranked_candidates
        # if available, so the signals that produced the ranking survive even
        # after the LLM reasoning step reformats the output.
        signal_by_section = {}
        for c in (ranked_candidates or []):
            key = f"{c.get('act', '')}_{c.get('section_num') or c.get('section', '')}".upper()
            signal_by_section[key] = c.get("score_breakdown")

        recommended_with_signals = []
        for r in recommended:
            key = f"{r.get('act', '')}_{r.get('section', '')}".upper()
            recommended_with_signals.append({
                **r,
                "score_breakdown": signal_by_section.get(key),
            })

        record = {
            "prediction_id": prediction_id,
            "timestamp": time.time(),
            "query": query,
            "extracted_facts": extracted_facts,
            "recommended_sections": recommended_with_signals,
            "rejected_sections": rejected,
            "pipeline_confidence": pipeline_output.get("pipeline_confidence"),
            "supporting_evidence": pipeline_output.get("supporting_evidence"),
            "community": pipeline_output.get("community"),
            "label_status": "pending",  # pending | resolved
            "label": None,              # filled in by feedback_service.resolve_label()
        }

        self._append(record)
        return prediction_id

    def get_prediction(self, prediction_id: str) -> Optional[Dict[str, Any]]:
        for record in self._read_all():
            if record.get("prediction_id") == prediction_id:
                return record
        return None

    def list_pending(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        pending = [r for r in self._read_all() if r.get("label_status") == "pending"]
        return pending[:limit] if limit else pending

    def update_label(self, prediction_id: str, label: Dict[str, Any]) -> bool:
        """
        Rewrites the record with label_status='resolved' and the given label.
        JSONL doesn't support in-place updates, so this does a full rewrite —
        fine at prototype scale, revisit if predictions.jsonl grows past
        low tens-of-thousands of rows.
        """
        records = self._read_all()
        found = False
        for r in records:
            if r.get("prediction_id") == prediction_id:
                r["label_status"] = "resolved"
                r["label"] = label
                found = True
                break

        if not found:
            return False

        with open(self.predictions_path, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")
        return True

    def _append(self, record: Dict[str, Any]) -> None:
        with open(self.predictions_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def _read_all(self) -> List[Dict[str, Any]]:
        if not self.predictions_path.exists():
            return []
        records = []
        with open(self.predictions_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records