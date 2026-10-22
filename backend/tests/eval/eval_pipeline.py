"""
End-to-end LexiGraph evaluation against gold_cases.json.

Usage (from backend/):
    python -m tests.eval.eval_pipeline            # runs the full pipeline on every gold case (LLM calls)
    python -m tests.eval.eval_pipeline --score-only tests/eval/out   # re-score saved outputs

Per case and layer it reports required-recall, precision (against required + acceptable),
forbidden violations, BNS mapping accuracy, precedent role consistency and wall-clock time.
Layer accuracy = F1(required-recall, precision), and is 0 if any forbidden section is attracted.
"""

import argparse
import io
import json
import contextlib
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Set

HERE = Path(__file__).resolve().parent
GOLD = HERE / "gold_cases.json"

_ATTRACTED = {"prima facie attracted", "partially attracted"}


def _base(sec: str) -> str:
    m = re.match(r"\s*([0-9]+[A-Z]*)", str(sec or "").upper())
    return m.group(1) if m else ""


def _score_layer(found: Set[str], gold: Dict[str, Any]) -> Dict[str, Any]:
    req_groups = [set(g) for g in gold.get("required", [])]
    allowed = set(gold.get("acceptable", [])) | {s for g in req_groups for s in g}
    forbidden = set(gold.get("forbidden", []))
    viol = sorted(found & forbidden)

    if not req_groups:
        # Empty gold layer: do not award 1.0 automatically!
        if viol:
            return {"found": sorted(found), "recall": None, "precision": 0.0, "forbidden_hits": viol,
                    "accuracy": 0.0, "missed_groups": [], "unexpected": sorted(found - allowed)}
        if not found:
            return {"found": [], "recall": None, "precision": None, "forbidden_hits": [],
                    "accuracy": None, "missed_groups": [], "unexpected": [], "status": "N/A (empty layer)"}
        prec = len(found & allowed) / len(found) if found else 1.0
        return {"found": sorted(found), "recall": None, "precision": round(prec, 3), "forbidden_hits": [],
                "accuracy": round(prec, 3), "missed_groups": [], "unexpected": sorted(found - allowed)}

    hit = sum(1 for g in req_groups if g & found)
    recall = hit / len(req_groups)
    precision = len(found & allowed) / len(found) if found else 0.0
    f1 = 0.0 if (recall + precision) == 0 else 2 * recall * precision / (recall + precision)
    return {"found": sorted(found), "recall": round(recall, 3), "precision": round(precision, 3),
            "forbidden_hits": viol, "accuracy": 0.0 if viol else round(f1, 3),
            "missed_groups": [sorted(g) for g in req_groups if not g & found],
            "unexpected": sorted(found - allowed - forbidden)}


def score_case(case: Dict[str, Any], out: Dict[str, Any]) -> Dict[str, Any]:
    s4 = out.get("stage4_statutory_verification") or {}
    ipc = {str(v.get("section_number")) for v in s4.get("verified_offences", [])
           if str(v.get("overall_status", "")).strip().lower() in _ATTRACTED}
    bnss = {str(s.get("section_number")) for s in (out.get("stage3c_bnss_retrieval") or {}).get("relevant_sections", [])}
    bsa = {str(s.get("section_number")) for s in (out.get("stage3b_bsa_retrieval") or {}).get("relevant_sections", [])}

    res = {"ipc": _score_layer(ipc, case["ipc"]), "bnss": _score_layer(bnss, case["bnss"]),
           "bsa": _score_layer(bsa, case["bsa"])}

    # Stage 2 candidate recall (isolates retrieval from Stage 4 adjudication)
    s2 = out.get("stage2_result") or out.get("stage2_subquery_mapping") or {}
    s2_cands = set()
    for m in s2.get("mappings", []):
        for sec in m.get("candidate_sections", []):
            s2_cands.add(str(sec).strip())
        for key in ("primary_candidate_sections", "secondary_candidate_sections", "conditional_candidate_sections"):
            for item in m.get(key, []):
                sec = item.get("section_number") if isinstance(item, dict) else str(item)
                if sec:
                    s2_cands.add(str(sec).strip())
    req_groups_ipc = [set(g) for g in case["ipc"].get("required", [])]
    s2_hit = sum(1 for g in req_groups_ipc if g & s2_cands)
    s2_recall = round(s2_hit / len(req_groups_ipc), 3) if req_groups_ipc else 1.0
    res["retrieval_recall_at_candidates"] = {
        "candidate_count": len(s2_cands),
        "recall": s2_recall,
        "missed_groups": [sorted(g) for g in req_groups_ipc if not g & s2_cands]
    }

    mapping = {str(m.get("ipc_section")): _base(m.get("bns_equivalent")) for m in s4.get("ipc_to_bns_equivalents", [])}
    checks = [(ipc_sec, bns, mapping.get(ipc_sec)) for ipc_sec, bns in case.get("bns", {}).items() if ipc_sec in mapping]
    res["bns_mapping"] = {"checked": len(checks), "correct": sum(1 for _, e, g in checks if e == g),
                          "errors": [f"IPC {i}: expected BNS {e}, got {g}" for i, e, g in checks if e != g],
                          "accuracy": round(sum(1 for _, e, g in checks if e == g) / len(checks), 3) if checks else None}

    prec = ((out.get("stage5_precedent_retrieval") or {}).get("verified_precedent_object") or {})
    pros = {p.get("case_id") for p in prec.get("prosecution_precedents", [])}
    dfn = {p.get("case_id") for p in prec.get("defense_precedents", [])}
    all_items = prec.get("prosecution_precedents", []) + prec.get("defense_precedents", [])
    offence_matched = [p.get("case_name") for p in all_items
                       if any(m.get("matched_via_act") in ("IPC", "BNS") for m in p.get("matched_statutes", []))]
    res["precedents"] = {
        "prosecution": len(pros), "defense": len(dfn), "in_both_lists": sorted(pros & dfn),
        "not_supporting_in_own_list": [p.get("case_name") for p in all_items
                                       if not (p.get("compact_summary") or {}).get("supports_role", True)],
        "offence_matched": len(set(offence_matched)), "total_listed": len(pros | dfn),
        "consistent": not (pros & dfn),
    }
    layer_acc = [res[k]["accuracy"] for k in ("ipc", "bnss", "bsa") if res[k]["accuracy"] is not None]
    if res["bns_mapping"]["accuracy"] is not None:
        layer_acc.append(res["bns_mapping"]["accuracy"])
    res["overall_accuracy"] = round(sum(layer_acc) / len(layer_acc), 3) if layer_acc else 0.0
    return res


def run_case(text: str) -> Dict[str, Any]:
    from lexigraphbe.runner import run_full_pipeline
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        return run_full_pipeline(text=text, legal_regime_override="IPC + CrPC")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--score-only", type=str, default=None, help="directory with <case_id>.json outputs")
    ap.add_argument("--out", type=str, default=str(HERE / "out"))
    ap.add_argument("--case", type=str, default=None)
    args = ap.parse_args()
    gold = json.loads(GOLD.read_text(encoding="utf-8"))["cases"]
    if args.case:
        gold = [c for c in gold if c["id"] == args.case]
    out_dir = Path(args.score_only or args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    report = []
    for case in gold:
        path = out_dir / f"{case['id']}.json"
        if args.score_only:
            out, secs = json.loads(path.read_text(encoding="utf-8")), None
        else:
            t = time.time()
            out = run_case(case["text"])
            secs = round(time.time() - t, 1)
            path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
        r = score_case(case, out)
        r["case"], r["seconds"] = case["id"], secs
        report.append(r)
        print(json.dumps(r, indent=2))
    overall = round(sum(r["overall_accuracy"] for r in report) / len(report), 3) if report else 0.0
    print(f"\nOVERALL ACCURACY: {overall}  over {len(report)} case(s)")
    (out_dir / "report.json").write_text(json.dumps({"overall": overall, "cases": report}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    sys.path.insert(0, str(HERE.parent.parent))
    main()
