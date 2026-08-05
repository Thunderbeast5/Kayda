"""
Demo script — run the full Text-to-Cypher pipeline on example queries.

Usage:
    cd legal_text2cypher
    PYTHONPATH=.. python run_demo.py

Or from MootCourt root:
    PYTHONPATH=. python legal_text2cypher/run_demo.py
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
_THIS_FILE = Path(__file__).resolve()
# Find MootCourt root (directory containing 'backend')
_MOOT_COURT_ROOT = str(next(p for p in _THIS_FILE.parents if (p / "backend").exists()))
if _MOOT_COURT_ROOT not in sys.path:
    sys.path.insert(0, _MOOT_COURT_ROOT)

from backend.agents.lexigraph.cypher.legal_text2cypher.config.settings import get_settings
from backend.agents.lexigraph.cypher.legal_text2cypher.agents.pipeline import run_pipeline, shutdown


# ── Logging setup ─────────────────────────────────────────────────────────

def setup_logging():
    cfg = get_settings()
    logging.basicConfig(
        level=getattr(logging, cfg.log_level.upper(), logging.INFO),
        format=cfg.log_format,
        handlers=[logging.StreamHandler(sys.stdout)],
    )


# ── Example queries ───────────────────────────────────────────────────────

EXAMPLE_QUERIES = [
    # Basic punishment lookup
    "What is the punishment for murder?",

    # IPC → BNS mapping
    "What is the BNS equivalent of IPC Section 302?",

    # Crime lookup
    "Tell me about the crime of kidnapping under Indian law.",

    # Multi-crime
    "A child was kidnapped for ransom and murdered.",

    # Section lookup
    "What does IPC Section 376 cover?",

    # Comparison
    "Compare murder and culpable homicide.",

    # Legal explanation
    "Explain the legal provisions related to dowry death.",
]


def main():
    setup_logging()
    logger = logging.getLogger("demo")

    cfg = get_settings()
    logger.info("=" * 70)
    logger.info("Legal Text-to-Cypher Pipeline Demo")
    logger.info("Neo4j: %s | LLM: %s", cfg.neo4j_uri, cfg.groq_model)
    logger.info("=" * 70)

    # Allow custom query via CLI
    if len(sys.argv) > 1:
        queries = [" ".join(sys.argv[1:])]
    else:
        queries = EXAMPLE_QUERIES

    for i, query in enumerate(queries, 1):
        print(f"\n{'='*70}")
        print(f"  Query {i}/{len(queries)}: {query}")
        print(f"{'='*70}\n")

        try:
            result = run_pipeline(query)

            print(f"\n{'─'*50}")
            print(f"  Intent: {result.intent.value}")
            print(f"  Entities: {result.extracted_entities.crimes + result.extracted_entities.ipc_sections + result.extracted_entities.bns_sections}")
            print(f"  Cypher queries: {len(result.cypher_queries)}")
            print(f"  Records retrieved: {sum(len(r.records) for r in result.execution_results)}")
            print(f"  Total time: {result.total_time_ms:.0f}ms")
            print(f"{'─'*50}")

            print(f"\n  Stage Timings:")
            for stage, ms in result.stages_log.items():
                print(f"    {stage:30s} {ms:8.1f}ms")

            print(f"\n  Generated Cypher:")
            for j, cq in enumerate(result.cypher_queries):
                print(f"    [{j+1}] {cq.description}")
                print(f"        {cq.cypher[:150]}...")

            print(f"\n  Answer:")
            print(f"  {result.answer[:500]}")
            if len(result.answer) > 500:
                print(f"  ... ({len(result.answer)} chars total)")

        except Exception as exc:
            logger.error("Pipeline failed for query '%s': %s", query, exc, exc_info=True)

    shutdown()
    print(f"\n{'='*70}")
    print("  Demo complete.")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
