"""
evaluation_runner.py
====================
Automated benchmark runner for LexiGraph GraphRAG Legal AI System.

Runs all 122 scenario fact patterns through LexiGraphAgent pipeline,
computes quantitative metrics using metrics.py,
diagnoses failures using failure_analyzer.py,
and outputs complete benchmark execution results.
"""

import sys
import os
import json
import time
from pathlib import Path
from typing import Dict, Any, List

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path("context/agent_context").resolve()))

import scenarios_data
from agents.lexigraph.lexigraph_agent import LexiGraphAgent
from agents.lexigraph.eval.metrics import BenchmarkMetrics
from agents.lexigraph.eval.failure_analyzer import FailureAnalyzer


class EvaluationRunner:
    """Automated Legal GraphRAG Evaluation Benchmark Runner."""

    def __init__(self, agent: LexiGraphAgent = None):
        self.agent = agent or LexiGraphAgent()
        self.metrics = BenchmarkMetrics()
        self.analyzer = FailureAnalyzer()

    def run_benchmark(self, limit: int = None, difficulty_filter: str = None) -> Dict[str, Any]:
        scenarios = scenarios_data.SCENARIOS

        if difficulty_filter:
            scenarios = [s for s in scenarios if s.get("difficulty") == difficulty_filter]

        if limit:
            scenarios = scenarios[:limit]

        total_count = len(scenarios)
        print("=" * 80)
        print(f"STARTING LEXIGRAPH LEGAL AI BENCHMARK RUNNER ({total_count} SCENARIOS)")
        print("=" * 80)

        results = []
        top1_hits = 0
        top3_hits = 0
        mrr_sum = 0.0
        neg_correct = 0
        neg_total = 0

        ev_precisions = []
        ev_recalls = []
        calibration_scores = []
        community_hits = 0
        stage_failures = {}

        start_time = time.time()

        for idx, scenario in enumerate(scenarios, 1):
            sid = scenario["id"]
            cat = scenario["category"]
            facts = scenario["facts"]
            is_neg = bool(scenario["is_negative_example"])
            exp_bns = scenario["expected_bns_sections"]
            exp_top1 = scenario.get("expected_top1")
            exp_evidence = scenario.get("expected_evidence") or []
            exp_community = scenario.get("expected_community")
            conf_range = scenario.get("expected_confidence_range") or [0.70, 1.00]

            print(f"\n[{idx}/{total_count}] Evaluating {sid} ({cat} | {scenario.get('difficulty')})...")

            try:
                out = self.agent.process_query(facts)
            except Exception as e:
                print(f"  [ERROR] Pipeline exception for scenario {sid}: {e}")
                out = {
                    "pipeline_confidence": 0.0,
                    "recommended_sections": [],
                    "supporting_evidence": [],
                    "community": {},
                    "rejected_sections": []
                }

            recs = out.get("recommended_sections") or []
            pred_sections = [f"{r.get('act')} {r.get('section')}".upper() for r in recs]
            pred_ev = out.get("supporting_evidence") or []
            pred_conf = float(out.get("pipeline_confidence") or 0.0)
            actual_comm = out.get("community", {}).get("community_id")

            # Metrics
            if is_neg:
                neg_total += 1
                is_correct_neg = len(pred_sections) == 0
                if is_correct_neg:
                    neg_correct += 1
                top1_hit = 1.0 if is_correct_neg else 0.0
                top3_hit = 1.0 if is_correct_neg else 0.0
                mrr_val = 1.0 if is_correct_neg else 0.0
            else:
                top1_hit = self.metrics.compute_top_k_hit(pred_sections, exp_bns, k=1)
                top3_hit = self.metrics.compute_top_k_hit(pred_sections, exp_bns, k=3)
                mrr_val = self.metrics.compute_mrr(pred_sections, exp_bns)

                top1_hits += top1_hit
                top3_hits += top3_hit
                mrr_sum += mrr_val

            # Evidence PR
            ev_pr = self.metrics.compute_array_precision_recall(pred_ev, exp_evidence)
            ev_precisions.append(ev_pr["precision"])
            ev_recalls.append(ev_pr["recall"])

            # Calibration
            cal_score = self.metrics.compute_confidence_calibration(pred_conf, conf_range)
            calibration_scores.append(cal_score)

            # Community
            comm_hit = 1.0 if (exp_community and actual_comm and exp_community == actual_comm) else 0.0
            community_hits += comm_hit

            # Failure Analysis
            fail_diag = self.analyzer.analyze_scenario_failure(scenario, out)
            for stg in fail_diag["failed_stages"]:
                stage_failures[stg] = stage_failures.get(stg, 0) + 1

            status_str = "PASS" if (top1_hit == 1.0 and fail_diag["failed_stages"] == ["NONE"]) else "FAIL"
            print(f"  Result: [{status_str}] Top-1 Hit: {top1_hit}, Top-3 Hit: {top3_hit}, Conf: {pred_conf:.2f} (Range: {conf_range})")

            results.append({
                "scenario_id": sid,
                "category": cat,
                "difficulty": scenario.get("difficulty"),
                "is_negative": is_neg,
                "expected_top1": exp_top1,
                "predicted_sections": pred_sections,
                "top1_hit": top1_hit,
                "top3_hit": top3_hit,
                "mrr": mrr_val,
                "evidence_precision": ev_pr["precision"],
                "evidence_recall": ev_pr["recall"],
                "confidence": pred_conf,
                "calibration_score": cal_score,
                "community_hit": comm_hit,
                "diagnosis": fail_diag
            })

        elapsed = time.time() - start_time
        pos_total = total_count - neg_total

        overall_metrics = {
            "total_scenarios": total_count,
            "positive_scenarios": pos_total,
            "negative_scenarios": neg_total,
            "top1_accuracy": round((top1_hits / pos_total) if pos_total > 0 else 1.0, 4),
            "top3_recall": round((top3_hits / pos_total) if pos_total > 0 else 1.0, 4),
            "mrr": round((mrr_sum / pos_total) if pos_total > 0 else 1.0, 4),
            "negative_rejection_precision": round((neg_correct / neg_total) if neg_total > 0 else 1.0, 4),
            "evidence_precision": round(sum(ev_precisions) / len(ev_precisions), 4) if ev_precisions else 0.0,
            "evidence_recall": round(sum(ev_recalls) / len(ev_recalls), 4) if ev_recalls else 0.0,
            "confidence_calibration_score": round(sum(calibration_scores) / len(calibration_scores), 4) if calibration_scores else 0.0,
            "community_alignment_accuracy": round(community_hits / total_count, 4) if total_count > 0 else 0.0,
            "stage_failures_breakdown": stage_failures,
            "elapsed_seconds": round(elapsed, 2)
        }

        print("\n" + "=" * 80)
        print("BENCHMARK EXECUTION SUMMARY")
        print("=" * 80)
        print(f"Top-1 Section Accuracy          : {overall_metrics['top1_accuracy'] * 100:.1f}%")
        print(f"Top-3 Section Recall            : {overall_metrics['top3_recall'] * 100:.1f}%")
        print(f"Mean Reciprocal Rank (MRR)       : {overall_metrics['mrr']:.4f}")
        print(f"Negative Precision (Rejection)   : {overall_metrics['negative_rejection_precision'] * 100:.1f}%")
        print(f"Evidence Precision / Recall      : {overall_metrics['evidence_precision'] * 100:.1f}% / {overall_metrics['evidence_recall'] * 100:.1f}%")
        print(f"Confidence Calibration Score    : {overall_metrics['confidence_calibration_score'] * 100:.1f}%")
        print(f"Community Cluster Alignment     : {overall_metrics['community_alignment_accuracy'] * 100:.1f}%")
        print(f"Stage Failures Breakdown        : {stage_failures}")
        print(f"Total Execution Time            : {elapsed:.2f}s")
        print("=" * 80)

        return {
            "metrics": overall_metrics,
            "scenario_results": results
        }
