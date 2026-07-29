"""
run_resolution.py
==================
Standalone batch resolver for pending predictions.

Usage:
    # From project root:
    python -m backend.agents.lexigraph.feedback.run_resolution

    # Or via cron (daily at 3 AM):
    # 0 3 * * * cd /path/to/MootCourt && python -m backend.agents.lexigraph.feedback.run_resolution

Resolves all predictions that haven't received human feedback by running
the LLM judge. Human-labeled predictions are always preserved as-is.
"""

import sys
from pathlib import Path

# Ensure project root is on sys.path for absolute imports
_project_root = Path(__file__).resolve().parents[4]  # MootCourt/
_backend_root = Path(__file__).resolve().parents[3]   # MootCourt/backend/
_agents_root = Path(__file__).resolve().parents[2]    # MootCourt/backend/agents/

for p in (_project_root, _backend_root, _agents_root):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from backend.agents.lexigraph.feedback.feedback_service import FeedbackService


def main():
    print("[run_resolution] Starting batch resolution of pending predictions...")
    svc = FeedbackService()

    pending_count = len(svc.logger.list_pending())
    print(f"[run_resolution] Found {pending_count} pending predictions.")

    if pending_count == 0:
        print("[run_resolution] Nothing to resolve. Exiting.")
        return

    resolved = svc.resolve_all_pending()
    print(f"[run_resolution] Resolved {len(resolved)} predictions.")

    for r in resolved:
        verdict = r["label"].get("overall_verdict", "unknown")
        source = r["label"].get("source", "unknown")
        print(f"  - {r['prediction_id']}: {verdict} (source={source})")

    print("[run_resolution] Done.")


if __name__ == "__main__":
    main()
