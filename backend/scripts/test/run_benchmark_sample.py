"""
run_benchmark_sample.py
======================
Runs the automated evaluation runner over a sample of 5 scenarios to verify end-to-end suite execution.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agents.lexigraph.eval.evaluation_runner import EvaluationRunner
from agents.lexigraph.eval.evaluation_report import EvaluationReportGenerator

def main():
    runner = EvaluationRunner()
    results = runner.run_benchmark(limit=5)
    
    report = EvaluationReportGenerator.generate_markdown_report(
        results, 
        output_path="C:/Users/Admin/.gemini/antigravity-ide/brain/b9fafb30-ffcd-4148-9a35-916f7a06dc19/sample_benchmark_report.md"
    )
    print("\nSAMPLE BENCHMARK REPORT PREVIEW:\n")
    print(report[:1500])

if __name__ == "__main__":
    main()
