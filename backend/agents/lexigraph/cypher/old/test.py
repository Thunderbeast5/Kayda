#!/usr/bin/env python3
"""
Test script for t3c.py - single crime queries.

It uses the same Neo4j connection and chain as the main script.
Before running, ensure:
  - Neo4j is running and populated.
  - Environment variables (NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD) are set.
  - The required fulltext indexes exist (checked by t3c.verify_runtime_schema).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

# Add the parent directory containing t3c.py to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from backend.agents.lexigraph.cypher.old.t3c import (
    _run_single_query,
    build_chain,
    run,
    verify_runtime_schema,
    NEO4J_URI,
    NEO4J_USER,
    NEO4J_PASSWORD,
)
from neo4j import GraphDatabase

# ----------------------------------------------------------------------
# DEFINE TEST CASES
# Each entry: (query, expected_act, expected_section)
# You MUST adjust these expected sections to match YOUR graph's actual mapping.
# Below are common BNS sections (based on IPC ↔ BNS conversion) – verify them!
# ----------------------------------------------------------------------
TEST_CASES = [
    # Offence type              query                                 expected (BNS)
    ("Theft",                   "a person stole a mobile phone",       ("BNS", "303")),
    ("Robbery",                 "someone robbed a bank at gunpoint",   ("BNS", "305")),
    ("Murder",                  "he killed his wife with a knife",     ("BNS", "101")),
    ("Culpable homicide not murder", "a man caused death without intent", ("BNS", "100")),  # BNS 100?
    ("Voluntarily causing hurt","he punched his neighbour",            ("BNS", "115")),
    ("Grievous hurt",           "she fractured her arm in a fight",    ("BNS", "117")),
    ("Kidnapping",              "a person took away a child for ransom", ("BNS", "137")),  # may be BNS 137
    ("Rape",                    "a man forced himself on a woman",     ("BNS", "64")),
    ("Outraging modesty",       "a man touched a woman inappropriately", ("BNS", "74")),  # BNS 74
    ("Cheating",                "he cheated the bank with false documents", ("BNS", "316")),
    ("Forgery",                 "she forged a signature on a will",    ("BNS", "336")),
    ("Criminal intimidation",   "he threatened to kill his boss",      ("BNS", "351")),
    ("Extortion",               "they demanded money and threatened",  ("BNS", "308")),
    ("House trespass",          "someone broke into a house at night", ("BNS", "330")),
    ("Stalking",                "he followed her every day",           ("BNS", "78")),      # BNS 78
    ("Dowry death",             "she died due to dowry harassment",    ("BNS", "80")),      # BNS 80
    ("Acid attack",             "he threw acid on her face",           ("BNS", "124")),     # BNS 124
    ("Causing death by negligence", "rash driving caused an accident", ("BNS", "106")),
    ("Unlawful assembly",       "a mob gathered to commit violence",   ("BNS", "191")),     # BNS 191
    ("Defamation",              "he spread false rumors about her",    ("BNS", "356")),
]

# ----------------------------------------------------------------------
# TESTING FUNCTIONS
# ----------------------------------------------------------------------

def get_top_bns_candidate(result: dict[str, Any]) -> tuple[str, str] | None:
    """
    Extract the top candidate that is a BNS section from the result dict.
    Returns (act, section) or None if not found.
    """
    candidates = result.get("top_candidates", [])
    for c in candidates:
        if c.get("act") == "BNS":
            return ("BNS", str(c.get("section", "")))
    return None

def run_single_test(query: str, chain, driver) -> dict:
    """Run a single query and return the structured result."""
    result = _run_single_query(query, chain, driver)
    # If error, return as is
    if result.get("error"):
        return result
    # Ensure top_candidates are ranked (already done inside _run_single_query)
    return result

def compute_accuracy(results: list[dict], test_cases: list) -> float:
    correct = 0
    total = len(test_cases)
    for i, (_, expected_act, expected_section) in enumerate(test_cases):
        res = results[i]
        top = get_top_bns_candidate(res)
        if top and top[0] == expected_act and top[1] == expected_section:
            correct += 1
        else:
            # Optionally, we can also accept IPC equivalents if mapping is missing
            # but we stick to exact BNS match.
            pass
    return correct / total if total else 0.0

def format_output(result: dict, query: str) -> str:
    """Format a single result for human reading (similar to run() output)."""
    if result.get("error"):
        return f"ERROR: {result['error']}"
    # We'll use the same formatting as _format_single_result but we need to import it?
    # Instead, we can mimic it.
    lines = []
    if result.get("answer"):
        lines.append("LEGAL ANALYSIS:")
        lines.append(result["answer"])
        lines.append("")
    if result.get("top_candidates"):
        lines.append("TOP MATCHING SECTIONS:")
        for c in result["top_candidates"]:
            act = c.get("act", "")
            sec = c.get("section", "")
            title = c.get("title", "")
            lines.append(f"\n[{act} {sec}] {title}")
            if c.get("description"):
                lines.append(f"  Description: {c['description']}")
            if c.get("punishment"):
                lines.append(f"  Punishment: {c['punishment']}")
            if c.get("counterpart_act") and c.get("counterpart_section"):
                lines.append(f"  (Corresponding {c['counterpart_act']} {c['counterpart_section']}: {c.get('counterpart_title')})")
        lines.append("")
    if result.get("related_candidates"):
        lines.append("RELATED LEGAL RULES:")
        for c in result["related_candidates"]:
            lines.append(f"\n[{c.get('act')} {c.get('section')}] {c.get('title')}")
            cond = c.get("condition") or "no condition specified"
            lines.append(f"  Relation: {c['relationship']} ({cond})")
    return "\n".join(lines)

# ----------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------
def main():
    # Check environment
    if not (NEO4J_URI and NEO4J_USER and NEO4J_PASSWORD):
        sys.exit("Set NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD (env or .env)")

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        # Verify indexes
        verify_runtime_schema(driver)
        # Build chain (this will create the LLM and graph objects)
        chain = build_chain()

        print("=" * 80)
        print("Running single‑crime tests...")
        print("=" * 80)

        results = []
        for idx, (label, query, expected) in enumerate(TEST_CASES, 1):
            print(f"\n--- Test {idx}: {label} ---")
            print(f"Query: {query}")
            print(f"Expected: {expected[0]} {expected[1]}")
            res = run_single_test(query, chain, driver)
            results.append(res)
            # Print the full output (like the main script would)
            print("\n" + format_output(res, query))
            # Also print a simple pass/fail line
            top = get_top_bns_candidate(res)
            if top:
                print(f"Top BNS section returned: {top[0]} {top[1]}")
                if top[0] == expected[0] and top[1] == expected[1]:
                    print("✅ PASS")
                else:
                    print("❌ FAIL")
            else:
                print("⚠️  No BNS section in top candidates")
            print("-" * 80)

        # Compute accuracy
        accuracy = compute_accuracy(results, TEST_CASES)
        print("\n" + "=" * 80)
        print(f"OVERALL ACCURACY (exact BNS section match): {accuracy:.2%}")
        print("=" * 80)

    finally:
        driver.close()

if __name__ == "__main__":
    main()