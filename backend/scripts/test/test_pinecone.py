"""
LexiGraph — Pinecone Retrieval Test
=====================================
Sanity-checks semantic retrieval quality against the index built by
pinecone_ingest_v2.py: for each test query, does the expected section
come back as the top hit (or at least within top-k)?

Usage
-----
    python test_pinecone_retrieval.py                     # run built-in test_cases
    python test_pinecone_retrieval.py --top-k 10
    python test_pinecone_retrieval.py --index-name legal-sections-v2
    python test_pinecone_retrieval.py --model all-MiniLM-L6-v2
    python test_pinecone_retrieval.py --verbose            # show all top-k hits per query

NOTE: --model must match whatever model pinecone_ingest_v2.py used to build
the index, or the vector space won't line up and results will be meaningless.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

env_candidates = [
    BASE_DIR.parent / ".env",
    BASE_DIR.parent.parent / ".env",
    BASE_DIR / ".env",
    Path(".env"),
]
ENV_PATH = next((c for c in env_candidates if c.exists()), None)

try:
    from dotenv import load_dotenv
    load_dotenv(ENV_PATH) if ENV_PATH else load_dotenv()
except ImportError:
    pass

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
DEFAULT_INDEX_NAME = "legal-sections-v2"
DEFAULT_MODEL = "all-MiniLM-L6-v2"

# ----------------------------------------------------------------------
# Test cases — id format matches pinecone_ingest_v2.py's vector ids:
# "{act}_{section}", e.g. IPC_302, BNS_103. Add more cases below as needed.
# ----------------------------------------------------------------------
test_cases = [
    {"query": "murder", "expected": "IPC_302"},
    {"query": "theft", "expected": "IPC_378"},
    {"query": "theft by servant", "expected": "IPC_381"},
    {"query": "rape", "expected": "IPC_376"},
    {"query": "kidnapping", "expected": "IPC_363"},
]


def run_tests(index_name: str, model_name: str, top_k: int, verbose: bool) -> bool:
    from sentence_transformers import SentenceTransformer
    from pinecone import Pinecone

    if not PINECONE_API_KEY:
        print(f"ERROR: PINECONE_API_KEY not set (checked {ENV_PATH})")
        sys.exit(1)

    print(f"Loading model: {model_name} ...")
    model = SentenceTransformer(model_name)

    pc = Pinecone(api_key=PINECONE_API_KEY)
    existing = [idx.name for idx in pc.list_indexes()]
    if index_name not in existing:
        print(f"ERROR: index '{index_name}' not found. Available: {existing}")
        sys.exit(1)
    index = pc.Index(index_name)

    top1_hits = 0
    topk_hits = 0
    results = []

    for case in test_cases:
        query, expected = case["query"], case["expected"]
        embedding = model.encode(query).tolist()
        response = index.query(vector=embedding, top_k=top_k, include_metadata=True)
        matches = response.get("matches", [])
        ids = [m["id"] for m in matches]

        top1_ok = bool(ids) and ids[0] == expected
        rank = ids.index(expected) + 1 if expected in ids else None
        topk_ok = rank is not None

        top1_hits += int(top1_ok)
        topk_hits += int(topk_ok)

        results.append({
            "query": query, "expected": expected, "top1_ok": top1_ok,
            "rank": rank, "top1_actual": ids[0] if ids else None, "matches": matches,
        })

    print("\n--- Results ---")
    for r in results:
        status = "PASS" if r["top1_ok"] else ("PARTIAL" if r["rank"] else "FAIL")
        rank_note = f"(found at rank {r['rank']})" if r["rank"] and not r["top1_ok"] else ""
        print(f"[{status:7}] '{r['query']}' -> expected {r['expected']}, "
              f"got {r['top1_actual']} {rank_note}")
        if verbose:
            for i, m in enumerate(r["matches"], 1):
                title = (m.get("metadata") or {}).get("title", "")
                print(f"    {i}. {m['id']}  score={m['score']:.4f}  {title[:70]}")

    n = len(test_cases)
    print(f"\nTop-1 accuracy: {top1_hits}/{n} ({100 * top1_hits / n:.1f}%)")
    print(f"Top-{top_k} hit rate: {topk_hits}/{n} ({100 * topk_hits / n:.1f}%)")

    return top1_hits == n


def main() -> None:
    parser = argparse.ArgumentParser(description="Test retrieval quality of the v2 Pinecone index")
    parser.add_argument("--index-name", default=DEFAULT_INDEX_NAME)
    parser.add_argument("--model", default=DEFAULT_MODEL,
                         help="Must match the model used to build the index")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--verbose", action="store_true", help="Show all top-k hits per query")
    args = parser.parse_args()

    all_passed = run_tests(args.index_name, args.model, args.top_k, args.verbose)
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()