"""
DynamicRetrievalTrigger — Phase 3
===================================
Fires fresh legal retrieval mid-hearing when the IssueDetector
identifies new sections, articles, or precedents not in the
current context packages.

Architecture position (from JUDGE_AGENT.md §7):
  Judge Agent
      │
      │ new_issue detected
      ▼
  DynamicRetrievalTrigger
      ├─ → LexiGraph Retrieval Agent  (new sections / articles)
      └─ → Precedent Retrieval Agent  (new cases)
      │
      ▼
  Updated Legal Context Package
  Updated Precedent Context
      │
      ▼
  AI Courtroom Orchestrator (merged context)
  CourtRoomStateMemory (updated)
      │
      ▼
  Hearing resumes

Design
------
- The trigger itself never calls LexiGraph or Pinecone directly.
- In the current implementation it provides a clean interface that
  the Orchestrator (Phase 4) will hook up to real retrieval agents.
- For Phase 3, retrieval is simulated via a callback function that
  the caller can inject (easy to swap with real LexiGraph calls).
- If no callback is injected, the trigger returns the existing
  context unchanged (safe no-op).
- Max retrieval calls: 2 per hearing (guards against infinite loops).

Integration
-----------
Inject a real retrieval callback when wiring to the full pipeline:

    def my_retrieval(issues, legal_pkg, prec_ctx):
        # call LexiGraph + Precedent agents
        return updated_legal_pkg, updated_prec_ctx

    trigger = DynamicRetrievalTrigger(retrieval_callback=my_retrieval)

Leave retrieval_callback=None during Phase 3 (no-op safe mode).
"""

from __future__ import annotations

from typing import Callable, Optional
from pydantic import BaseModel, Field

from .services.issue_detector import IssueDetectionResult, NewLegalIssue
from .courtroom_memory import CourtRoomStateMemory


# ── Result model ───────────────────────────────────────────────────────────────

class RetrievalResult(BaseModel):
    """
    Outcome of a single dynamic retrieval cycle.

    triggered        : whether retrieval was actually invoked
    issues_resolved  : list of issue references that were resolved
    issues_unresolved: issues that retrieval could not resolve
    updated_legal_context_package : merged legal package (or original if no-op)
    updated_precedent_context     : merged precedent context (or original if no-op)
    retrieval_count  : total retrievals triggered so far this hearing
    """
    triggered:          bool
    issues_resolved:    list[str] = Field(default_factory=list)
    issues_unresolved:  list[str] = Field(default_factory=list)
    updated_legal_context_package: dict = Field(default_factory=dict)
    updated_precedent_context:     dict = Field(default_factory=dict)
    retrieval_count:    int = 0


# ── Retrieval callback type ────────────────────────────────────────────────────

RetrievalCallback = Callable[
    [list[NewLegalIssue], dict, dict],   # issues, legal_pkg, prec_ctx
    tuple[dict, dict],                    # updated_legal_pkg, updated_prec_ctx
]


# ── Context merger ─────────────────────────────────────────────────────────────

def _merge_legal_packages(original: dict, updated: dict) -> dict:
    """
    Merge an updated legal context package into the original.
    New recommended_sections are appended (no duplicates by section key).
    Other fields from updated override original.
    """
    if not updated:
        return original

    merged = dict(original)

    orig_secs = {s.get("section", ""): s for s in original.get("recommended_sections") or []}
    for sec in updated.get("recommended_sections") or []:
        key = sec.get("section", "")
        if key and key not in orig_secs:
            orig_secs[key] = sec

    merged["recommended_sections"] = list(orig_secs.values())

    orig_arts = set(original.get("supporting_articles") or [])
    for art in updated.get("supporting_articles") or []:
        orig_arts.add(art)
    merged["supporting_articles"] = sorted(orig_arts)

    for field in ("supporting_evidence", "supporting_principles", "community"):
        if field in updated:
            merged[field] = updated[field]

    return merged


def _merge_precedent_contexts(original: dict | list, updated: dict | list) -> dict:
    """
    Merge updated precedent context into original.
    Deduplicates by case_name.
    """
    def _to_list(ctx) -> list:
        if isinstance(ctx, list):
            return ctx
        if isinstance(ctx, dict):
            return (ctx.get("similar_cases") or []) + (ctx.get("supporting_cases") or [])
        return []

    orig_list    = _to_list(original)
    updated_list = _to_list(updated)

    seen_names = {(c.get("case_name") or "").lower() for c in orig_list}
    merged = list(orig_list)
    for case in updated_list:
        name = (case.get("case_name") or "").lower()
        if name and name not in seen_names:
            merged.append(case)
            seen_names.add(name)

    return {"similar_cases": merged, "supporting_cases": []}


# ── DynamicRetrievalTrigger ────────────────────────────────────────────────────

class DynamicRetrievalTrigger:
    """
    Manages dynamic retrieval calls during a hearing.

    Parameters
    ----------
    retrieval_callback : optional function that actually calls LexiGraph /
                         Precedent agents and returns updated context dicts.
                         Signature: (issues, legal_pkg, prec_ctx) → (new_legal_pkg, new_prec_ctx)
                         If None, trigger runs in no-op (safe) mode.
    max_retrievals     : maximum number of retrieval calls per hearing (default 2)
    """

    def __init__(
        self,
        retrieval_callback: Optional[RetrievalCallback] = None,
        max_retrievals: int = 2,
    ):
        self._callback        = retrieval_callback
        self._max_retrievals  = max_retrievals
        self._retrieval_count = 0

    @property
    def retrieval_count(self) -> int:
        return self._retrieval_count

    def can_trigger(self) -> bool:
        return self._retrieval_count < self._max_retrievals

    def trigger(
        self,
        detection_result: IssueDetectionResult,
        legal_context_package: dict,
        precedent_context: dict | list,
        memory: Optional[CourtRoomStateMemory] = None,
        case_id: str = "",
        debate_round: int = 1,
    ) -> RetrievalResult:
        """
        Fire dynamic retrieval based on the IssueDetectionResult.

        Parameters
        ----------
        detection_result      : from IssueDetector.detect()
        legal_context_package : current legal package to merge into
        precedent_context     : current precedents to merge into
        memory                : CourtRoomStateMemory to record the trigger event
        case_id               : for logging
        debate_round          : current round

        Returns
        -------
        RetrievalResult with updated context packages
        """
        if not detection_result.retrieval_required:
            return RetrievalResult(
                triggered=False,
                updated_legal_context_package=dict(legal_context_package),
                updated_precedent_context=(
                    dict(precedent_context)
                    if isinstance(precedent_context, dict)
                    else {"similar_cases": precedent_context}
                ),
                retrieval_count=self._retrieval_count,
            )

        if not self.can_trigger():
            print(
                f"[DynamicRetrieval] [{case_id}] Max retrievals ({self._max_retrievals}) "
                f"reached — skipping."
            )
            return RetrievalResult(
                triggered=False,
                issues_unresolved=[i.reference for i in detection_result.new_issues],
                updated_legal_context_package=dict(legal_context_package),
                updated_precedent_context=(
                    dict(precedent_context)
                    if isinstance(precedent_context, dict)
                    else {"similar_cases": list(precedent_context) if isinstance(precedent_context, list) else []}
                ),
                retrieval_count=self._retrieval_count,
            )

        self._retrieval_count += 1
        issues = detection_result.new_issues

        # Log trigger to memory
        if memory:
            issue_refs = ", ".join(i.reference for i in issues)
            memory.add_turn(
                "System",
                "finding",
                f"[DynamicRetrieval] Triggered for: {issue_refs}. "
                f"Target agents: {detection_result.target_agents}. "
                f"Retrieval #{self._retrieval_count}.",
                round=debate_round,
            )

        print(
            f"[DynamicRetrieval] [{case_id}] Retrieval #{self._retrieval_count} — "
            f"{len(issues)} new issue(s): "
            f"{[i.reference for i in issues]}"
        )

        # ── Invoke callback (real or simulated) ──
        if self._callback is not None:
            try:
                updated_legal, updated_prec = self._callback(
                    issues, legal_context_package, precedent_context
                )
                resolved   = [i.reference for i in issues]
                unresolved = []
            except Exception as e:
                print(f"[DynamicRetrieval] Callback failed: {e} — returning originals.")
                updated_legal = {}
                updated_prec  = {}
                resolved   = []
                unresolved = [i.reference for i in issues]
        else:
            # No-op mode — return originals unchanged
            print(
                f"[DynamicRetrieval] No callback registered — "
                f"running in no-op mode (Phase 3 safe mode)."
            )
            updated_legal = {}
            updated_prec  = {}
            resolved   = []
            unresolved = [i.reference for i in issues]

        # ── Merge contexts ──
        merged_legal = _merge_legal_packages(dict(legal_context_package), updated_legal)
        merged_prec  = _merge_precedent_contexts(precedent_context, updated_prec)

        # Log resolution to memory
        if memory:
            memory.add_turn(
                "System",
                "finding",
                f"[DynamicRetrieval] Complete. "
                f"Resolved: {resolved}. Unresolved: {unresolved}. "
                f"Hearing resumes.",
                round=debate_round,
            )

        return RetrievalResult(
            triggered=True,
            issues_resolved=resolved,
            issues_unresolved=unresolved,
            updated_legal_context_package=merged_legal,
            updated_precedent_context=merged_prec,
            retrieval_count=self._retrieval_count,
        )
