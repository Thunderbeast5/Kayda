"""
Pinecone-only retrieval test harness for LexiGraph.
=====================================================
Bypasses Groq (incident understanding) and Neo4j (enrichment / rule engine)
entirely. Calls `retrieve_from_pinecone()` from lg1.py directly against a
set of hand-built LegalEvent test cases, so you can judge embedding-model
retrieval quality in isolation before wiring Neo4j back in.

Usage
-----
    # point at whichever index/model you want to test
    export PINECONE_API_KEY=...
    export PINECONE_INDEX_NAME=legal-sections-v2-inlegal
    export LEXIGRAPH_EMBEDDING_MODEL=bhavyagiri/InLegal-Sbert

    python test_pinecone_retrieval.py

    # or compare two runs side by side
    export PINECONE_INDEX_NAME=legal-sections-v2          # old MiniLM index
    export LEXIGRAPH_EMBEDDING_MODEL=all-MiniLM-L6-v2
    python test_pinecone_retrieval.py --tag minilm

    export PINECONE_INDEX_NAME=legal-sections-v2-inlegal   # new index
    export LEXIGRAPH_EMBEDDING_MODEL=bhavyagiri/InLegal-Sbert
    python test_pinecone_retrieval.py --tag inlegal

IMPORTANT: EMBEDDING_MODEL and PINECONE_INDEX_NAME are read by lg1.py at
IMPORT time (module-level `os.getenv(...)` calls), so env vars must be set
in the shell / .env BEFORE this script runs — setting them after `import lg1`
inside Python has no effect.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Make lg1.py importable regardless of where this script lives relative to it.
# Adjust LG1_DIR if your actual path differs (backend/agents/legal_reasoning/).
# ---------------------------------------------------------------------------
LG1_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(LG1_DIR))

import backend.agents.lexigraph.legal_reasoning.lg1 as lg1  # noqa: E402  (import after sys.path manipulation, and after env vars are set by the shell)


# ---------------------------------------------------------------------------
# Test cases — each targets a specific rape-case nuance that plain
# keyword/MiniLM retrieval has historically blurred together. `expected`
# is what YOU believe the correct top section(s) should be; the harness
# just prints hits so you can eyeball whether expected shows up, and where.
# ---------------------------------------------------------------------------
TEST_CASES: list[dict] = [
    {
        "event": lg1.LegalEvent(
            event_id="t1",
            description=(
                "A man forcibly had sexual intercourse with an adult woman "
                "without her consent, using criminal force and threats."
            ),
            normalized_crime="rape",
            crime_family="sexual_offence",
            legal_concepts=["consent", "criminal force", "sexual assault"],
        ),
        "expected": ["IPC 375/376", "BNS 63/64"],
        "note": "Baseline rape — no aggravating factor",
    },
    {
        "event": lg1.LegalEvent(
            event_id="t2",
            description=(
                "A police officer raped a woman who was in his custody at "
                "the police station."
            ),
            normalized_crime="custodial rape",
            crime_family="sexual_offence",
            legal_concepts=["custodial rape", "abuse of position", "public servant"],
        ),
        "expected": ["IPC 376(2)", "BNS 65/70"],
        "note": "Custodial aggravation — must NOT collapse to plain rape section",
    },
    {
        "event": lg1.LegalEvent(
            event_id="t3",
            description=(
                "A 15-year-old girl was raped by a neighbour known to the family."
            ),
            normalized_crime="rape of a minor",
            crime_family="sexual_offence",
            legal_concepts=["minor victim", "POCSO overlap", "statutory rape"],
        ),
        "expected": ["IPC 376(3)", "BNS 65", "POCSO cross-reference if modeled"],
        "note": "Minor victim — age-based aggravation, distinct punishment band",
    },
    {
        "event": lg1.LegalEvent(
            event_id="t4",
            description=(
                "Several men took turns sexually assaulting a woman together "
                "in a moving vehicle."
            ),
            normalized_crime="gang rape",
            crime_family="sexual_offence",
            legal_concepts=["gang rape", "multiple offenders", "common intention"],
        ),
        "expected": ["IPC 376D", "BNS 70"],
        "note": "Gang rape — must retrieve the specific multi-offender section, not generic 376",
    },
    {
        "event": lg1.LegalEvent(
            event_id="t5",
            description=(
                "A husband forced his wife, who was living separately from him "
                "under a judicial separation order, to have intercourse without consent."
            ),
            normalized_crime="marital rape exception boundary",
            crime_family="sexual_offence",
            legal_concepts=["marital rape exception", "judicial separation", "spousal consent"],
        ),
        "expected": ["IPC 376B", "BNS 67"],
        "note": "Marital-exception carve-out case — classic area where generic embeddings fail",
    },
    {
        "event": lg1.LegalEvent(
            event_id="t6",
            description=(
                "A woman died from injuries sustained during a sexual assault "
                "that left her in a persistent vegetative state before death."
            ),
            normalized_crime="rape resulting in death",
            crime_family="sexual_offence",
            legal_concepts=["rape and murder", "death resulting", "vegetative state"],
        ),
        "expected": ["IPC 376A", "BNS 66"],
        "note": "Death/vegetative-state aggravation — high-severity distinct section",
    },
]


def run(tag: str, top_k: int) -> None:
    print(f"\n{'=' * 70}\nRUN [{tag}]  index={lg1.PINECONE_INDEX_NAME}  model={lg1.EMBEDDING_MODEL}\n{'=' * 70}")

    for case in TEST_CASES:
        event = case["event"]
        print(f"\n--- {event.event_id}: {case['note']} ---")
        print(f"Query text: {lg1.event_query(event)!r}")
        print(f"Expected  : {case['expected']}")

        try:
            candidates = lg1.retrieve_from_pinecone(event, top_k=top_k)
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR calling retrieve_from_pinecone: {exc}")
            continue

        if not candidates:
            print("  (no matches returned)")
            continue

        for rank, c in enumerate(candidates, start=1):
            print(
                f"  {rank}. {c.act} {c.section}  score={c.retrieval_score:.4f}  "
                f"title={c.title[:70]!r}"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Pinecone-only retrieval test harness (bypasses Neo4j/Groq)")
    parser.add_argument("--tag", default="run", help="Label for this run, useful when comparing two models/indexes")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    if not lg1.PINECONE_API_KEY:
        print("ERROR: PINECONE_API_KEY not set. Export it before running.")
        sys.exit(1)

    run(args.tag, args.top_k)


if __name__ == "__main__":
    main()