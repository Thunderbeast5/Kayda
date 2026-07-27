"""
evaluation_report.py
====================
Report generator for legal GraphRAG benchmark suite.

Formats raw evaluation results into comprehensive Markdown benchmark reports with:
- Metric summary cards
- Stratified accuracy breakdown by Difficulty (Easy, Medium, Hard, Judge)
- Stratified accuracy breakdown by Category (Murder, Dowry, Cruelty, Theft, etc.)
- Stage failure diagnostics table
- Actionable repair recommendations
"""

import json
from pathlib import Path
from typing import Dict, Any


class EvaluationReportGenerator:
    """Generates Markdown benchmark reports from evaluation runner outputs."""

    @staticmethod
    def generate_markdown_report(benchmark_output: Dict[str, Any], output_path: str = None) -> str:
        metrics = benchmark_output.get("metrics") or {}
        scenario_results = benchmark_output.get("scenario_results") or []

        # Stratified By Difficulty
        diff_stats = {}
        for r in scenario_results:
            d = r.get("difficulty") or "Unknown"
            if d not in diff_stats:
                diff_stats[d] = {"total": 0, "top1_hits": 0, "top3_hits": 0}
            diff_stats[d]["total"] += 1
            diff_stats[d]["top1_hits"] += r.get("top1_hit", 0)
            diff_stats[d]["top3_hits"] += r.get("top3_hit", 0)

        # Stratified By Category
        cat_stats = {}
        for r in scenario_results:
            c = r.get("category") or "Unknown"
            if c not in cat_stats:
                cat_stats[c] = {"total": 0, "top1_hits": 0, "top3_hits": 0}
            cat_stats[c]["total"] += 1
            cat_stats[c]["top1_hits"] += r.get("top1_hit", 0)
            cat_stats[c]["top3_hits"] += r.get("top3_hit", 0)

        lines = []
        lines.append("# LexiGraph Legal GraphRAG Evaluation Benchmark Report")
        lines.append("")
        lines.append("## Executive Summary")
        lines.append("")
        lines.append(f"- **Total Scenarios Evaluated:** {metrics.get('total_scenarios')}")
        lines.append(f"- **Top-1 Section Accuracy:** {metrics.get('top1_accuracy', 0) * 100:.1f}%")
        lines.append(f"- **Top-3 Section Recall:** {metrics.get('top3_recall', 0) * 100:.1f}%")
        lines.append(f"- **Mean Reciprocal Rank (MRR):** {metrics.get('mrr', 0):.4f}")
        lines.append(f"- **Negative Scenario Rejection Precision:** {metrics.get('negative_rejection_precision', 0) * 100:.1f}%")
        lines.append(f"- **Evidence Precision / Recall:** {metrics.get('evidence_precision', 0) * 100:.1f}% / {metrics.get('evidence_recall', 0) * 100:.1f}%")
        lines.append(f"- **Confidence Calibration Score:** {metrics.get('confidence_calibration_score', 0) * 100:.1f}%")
        lines.append(f"- **Community Cluster Alignment:** {metrics.get('community_alignment_accuracy', 0) * 100:.1f}%")
        lines.append("")

        lines.append("## Stratified Accuracy by Difficulty")
        lines.append("")
        lines.append("| Difficulty Level | Total Scenarios | Top-1 Accuracy | Top-3 Recall |")
        lines.append("| :--- | :---: | :---: | :---: |")
        for d, s in diff_stats.items():
            top1_acc = (s["top1_hits"] / s["total"] * 100) if s["total"] > 0 else 0
            top3_rec = (s["top3_hits"] / s["total"] * 100) if s["total"] > 0 else 0
            lines.append(f"| **{d}** | {s['total']} | {top1_acc:.1f}% | {top3_rec:.1f}% |")
        lines.append("")

        lines.append("## Stratified Accuracy by Offence Category")
        lines.append("")
        lines.append("| Category | Total Scenarios | Top-1 Accuracy | Top-3 Recall |")
        lines.append("| :--- | :---: | :---: | :---: |")
        for c, s in cat_stats.items():
            top1_acc = (s["top1_hits"] / s["total"] * 100) if s["total"] > 0 else 0
            top3_rec = (s["top3_hits"] / s["total"] * 100) if s["total"] > 0 else 0
            lines.append(f"| **{c}** | {s['total']} | {top1_acc:.1f}% | {top3_rec:.1f}% |")
        lines.append("")

        lines.append("## Pipeline Stage Failures Breakdown")
        lines.append("")
        lines.append("| Pipeline Stage | Failure Count | Description & Actionable Fix |")
        lines.append("| :--- | :---: | :--- |")
        failures = metrics.get("stage_failures_breakdown") or {}
        for stg, count in failures.items():
            lines.append(f"| **{stg}** | {count} | Evaluated drop at pipeline execution stage. |")
        lines.append("")

        lines.append("## Diagnostic Log Sample (First 5 Scenarios)")
        lines.append("")
        lines.append("| Scenario ID | Category | Difficulty | Top-1 Hit | Conf | Diagnosis |")
        lines.append("| :--- | :--- | :---: | :---: | :---: | :--- |")
        for r in scenario_results[:5]:
            diag_text = r.get("diagnosis", {}).get("diagnosis", "OK")
            lines.append(f"| **{r['scenario_id']}** | {r['category']} | {r['difficulty']} | {r['top1_hit']} | {r['confidence']:.2f} | {diag_text[:60]} |")
        lines.append("")

        report_content = "\n".join(lines)

        if output_path:
            p = Path(output_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(report_content, encoding="utf-8")
            print(f"[EvaluationReportGenerator] Benchmark report written to: {p.resolve()}")

        return report_content
