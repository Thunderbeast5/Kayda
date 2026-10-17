"""
Final selection of role-specific precedents for Precedent Retrieval Pipeline.

WHY THIS EXISTS
The calibrated score measures how relevant a precedent is, not which side it helps. Ranking supporting and
adverse cases in one list put an adverse case (Anna Waman, DISTINGUISHABLE) above the best supporting case and
filled prosecution slots 5-10 with defence-favouring authorities.

Each role's output is now three blocks, each ranked on its own:

    rely        precedents that support this side and are factually on point
    adverse     on-point precedents that cut against this side ("expect and distinguish")
    principle   cases from a different fact pattern whose issues/holdings closely match a legal issue the input
                raises (retrieved by the index's issue channel; never forced in by name)

Everything else (principle-only, low-fact, marginal) is returned as `background_ids` for the audit trail but is
not shown, and lists are cut by a score threshold instead of padded to a fixed size.

Pure python: works on pydantic objects or dicts.
"""

from typing import Any, Dict, Iterable, List, Optional

RELY_TYPES = {"DIRECTLY_SUPPORTING", "STRONGLY_SUPPORTING"}
ADVERSE_TYPES = {"DIRECTLY_OPPOSING", "STRONGLY_OPPOSING", "DISTINGUISHABLE"}
ON_POINT_FACT = {"HIGH", "MODERATE"}

MAX_RELY = 6
MAX_ADVERSE = 4
MAX_PRINCIPLE = 3
MIN_RELY_SCORE = 0.0
MIN_ADVERSE_SCORE = 0.0


def _get(obj: Any, *path: str, default: Any = None) -> Any:
    cur = obj
    for key in path:
        if cur is None:
            return default
        cur = cur.get(key) if isinstance(cur, dict) else getattr(cur, key, None)
    return default if cur is None else cur


def item_view(item: Any) -> Dict[str, Any]:
    return {
        "case_id": _get(item, "case_id", default=""),
        "type": str(_get(item, "relevance_evaluation", "relevance_type", default="BACKGROUND")).upper(),
        "fact": str(_get(item, "compact_summary", "factual_match", default="LOW")).upper(),
        "score": float(_get(item, "final_relevance_score", default=0.0)),
    }


def classify(item: Any, principle_ids: Iterable[str]) -> str:
    """principle | rely | adverse | background | drop"""
    v = item_view(item)
    if v["type"] == "LOW_RELEVANCE":
        return "drop"
    if v["case_id"] in set(principle_ids):
        # issue-matched cross-domain case: keep only if the evaluator found it to bear on this side at all
        return "principle" if v["type"] != "BACKGROUND" else "background"
    if v["type"] in RELY_TYPES and v["fact"] in ON_POINT_FACT and v["score"] >= MIN_RELY_SCORE:
        return "rely"
    if v["type"] in ADVERSE_TYPES and v["fact"] in ON_POINT_FACT and v["score"] >= MIN_ADVERSE_SCORE:
        return "adverse"
    return "background"


def select_sections(
    items: List[Any],
    principle_ids: Optional[Iterable[str]] = None,
    max_rely: int = MAX_RELY,
    max_adverse: int = MAX_ADVERSE,
    max_principle: int = MAX_PRINCIPLE,
) -> Dict[str, Any]:
    """
    Returns {"ordered": [...items in display order...],
             "sections": {"rely": [ids], "principle_only_fallback": [ids],
                           "adverse": [ids], "principle": [ids]},
             "background_ids": [...]}
    """
    principle = set(principle_ids or [])
    buckets: Dict[str, List[Any]] = {"rely": [], "adverse": [], "principle": [], "background": []}
    for it in items:
        kind = classify(it, principle)
        if kind != "drop":
            buckets[kind].append(it)

    def by_score(xs: List[Any]) -> List[Any]:
        return sorted(xs, key=lambda x: item_view(x)["score"], reverse=True)

    rely = by_score(buckets["rely"])[:max_rely]
    adverse = by_score(buckets["adverse"])[:max_adverse]
    principle_items = by_score(buckets["principle"])[:max_principle]
    background = by_score(buckets["background"])

    # Never return an empty "rely" block just because the threshold was strict: fall back to the best
    # background items so the lawyer still gets starting points, clearly labelled as principle-only.
    fallback: List[Any] = []
    if not rely:
        fallback = background[:3]
        background = background[3:]

    ordered = rely + fallback + adverse + principle_items
    return {
        "ordered": ordered,
        "sections": {
            "rely": [item_view(x)["case_id"] for x in rely],
            "principle_only_fallback": [item_view(x)["case_id"] for x in fallback],
            "adverse": [item_view(x)["case_id"] for x in adverse],
            "principle": [item_view(x)["case_id"] for x in principle_items],
        },
        "background_ids": [item_view(x)["case_id"] for x in background],
    }
