"""
test_enrichment_regression.py
==============================
Regression Test Suite for Graph Retrieval & Enrichment Anti-Patterns.
Verifies that:
1. Problem 1 Fix: No community case leaks (Arnesh Kumar, Satbir Singh, Orilal) into BNS 355 / IPC 354 outputs.
2. Problem 2 Fix: Total principle count stays <= 6.
3. Problem 3 Fix: Evidence is scoped to statutory ingredient requirements.
4. Problem 4 Fix: Article numbers/titles are deduplicated by code.
5. Problem 5 Fix: Live graph counts are tracked cleanly and override stale cached summary claims.
"""

import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Add backend root to sys.path
BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.append(str(BASE_DIR))

from agents.lexigraph.services.community_retrieval_service import CommunityRetrievalService

PASS = "  [PASS]"
FAIL = "  [FAIL]"

def run_enrichment_regression_tests():
    print("=" * 80)
    print("RUNNING GRAPH ENRICHMENT REGRESSION SUITE")
    print("=" * 80)

    retrieval_service = CommunityRetrievalService()

    # Part A: Test BNS 355 alone (verifying direct typed one-hop query & zero community leakage)
    bns355_candidates = [{"act": "BNS", "section_num": "355", "vector_similarity": 0.95}]
    bns355_enriched = retrieval_service.retrieve_community_context(
        bns355_candidates,
        query="Assault or criminal force to woman with intent to outrage her modesty"
    )
    bns355_cases = bns355_enriched[0]["community"].get("related_cases", [])

    print("\n--- Part A: Testing BNS 355 Alone ---")
    print(f"BNS 355 Direct Cases: {bns355_cases}")
    
    UNWANTED_LEAK_CASES = ["Arnesh Kumar", "Satbir Singh", "Orilal"]
    found_bns355_leaks = [c for c in bns355_cases for leak in UNWANTED_LEAK_CASES if leak.lower() in c.lower()]

    if not found_bns355_leaks:
        print(f"{PASS}  PART A (Direct One-Hop Query): BNS 355 returned only direct precedents ({len(bns355_cases)} case(s)); zero community leaks.")
    else:
        print(f"{FAIL}  PART A (Direct One-Hop Query): BNS 355 returned leaked community cases: {found_bns355_leaks}")

    # Part B: Test BNS 355 + IPC 354 candidate batch
    test_candidates = [
        {"act": "BNS", "section_num": "355", "vector_similarity": 0.92},
        {"act": "IPC", "section_num": "354", "vector_similarity": 0.90}
    ]

    print("\n--- Part B: Testing BNS 355 + IPC 354 Candidate Batch ---")
    enriched = retrieval_service.retrieve_community_context(
        test_candidates,
        query="Assault or criminal force to woman with intent to outrage her modesty"
    )

    if not enriched:
        print(f"{FAIL}  No enriched candidates returned!")
        sys.exit(1)

    comm_data = enriched[0]["community"]
    retrieved_cases = comm_data.get("related_cases", [])
    retrieved_principles = comm_data.get("related_principles", [])
    retrieved_articles = comm_data.get("related_articles", [])
    supporting_evidence = comm_data.get("supporting_evidence", [])
    case_derived_evidence = comm_data.get("case_derived_evidence", [])
    live_case_count = comm_data.get("live_case_count", 0)

    print("\n--- Enrichment Payload Summary ---")
    print(f"Cases               : {retrieved_cases}")
    print(f"Principles          : {retrieved_principles}")
    print(f"Articles            : {retrieved_articles}")
    print(f"Supporting Evidence : {supporting_evidence}")
    print(f"Case Evidence       : {case_derived_evidence}")
    print(f"Live Case Count     : {live_case_count}")

    # TEST 1: Unrelated Community Case Leak Check
    found_leaks = [c for c in retrieved_cases for leak in UNWANTED_LEAK_CASES if leak.lower() in c.lower()]
    
    if not found_leaks:
        print(f"{PASS}  TEST 1 (No Community Leaks): Zero dowry/arrest leak cases (Arnesh Kumar, Satbir Singh, Orilal) found.")
    else:
        print(f"{FAIL}  TEST 1 (No Community Leaks): Leaked cases detected in output: {found_leaks}")

    # TEST 2: Principle Count Check (<= 6)
    if len(retrieved_principles) <= 6:
        print(f"{PASS}  TEST 2 (Scoped Principles): Principles count is {len(retrieved_principles)} (<= 6).")
    else:
        print(f"{FAIL}  TEST 2 (Scoped Principles): Principles count exploded to {len(retrieved_principles)} (> 6).")

    # TEST 3: Evidence Separation
    # Dowry evidence types should not be in statutory supporting evidence
    DOWRY_EVIDENCE = ["Marriage Certificate", "Bank Transaction"]
    found_dowry_ev = [e for e in supporting_evidence if e in DOWRY_EVIDENCE]
    if not found_dowry_ev:
        print(f"{PASS}  TEST 3 (Ingredient Evidence): No dowry evidence in statutory evidence list.")
    else:
        print(f"{FAIL}  TEST 3 (Ingredient Evidence): Dowry evidence leaked into statutory evidence: {found_dowry_ev}")

    # TEST 4: Article Deduplication Check
    article_codes = [a.split("-")[0].strip() for a in retrieved_articles if "-" in a]
    unique_codes = set(article_codes)
    if len(article_codes) == len(unique_codes):
        print(f"{PASS}  TEST 4 (Article Deduplication): All retrieved article titles are unique by code.")
    else:
        print(f"{FAIL}  TEST 4 (Article Deduplication): Duplicate article codes found: {article_codes}")

    # TEST 5: Live Count Verification
    if live_case_count == len(retrieved_cases):
        print(f"{PASS}  TEST 5 (Live Count Guard): Live case count ({live_case_count}) matches retrieved cases length.")
    else:
        print(f"{FAIL}  TEST 5 (Live Count Guard): Mismatch between live count {live_case_count} and cases length {len(retrieved_cases)}.")

    print("=" * 80)


if __name__ == "__main__":
    run_enrichment_regression_tests()
