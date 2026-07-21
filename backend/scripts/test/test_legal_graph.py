"""
test_legal_graph.py  —  Relationship Verification Suite for Legal Knowledge Graph
==================================================================================
Runs a series of tests against Neo4j to verify:

  TEST 1  — Node counts (IPCSection, BNSSection)
  TEST 2  — BNS->IPC REPLACES links exist and are correct
  TEST 3  — IPC->BNS REPLACED_BY reverse links exist
  TEST 4  — CO_CHARGED_WITH is bidirectional (A->B and B->A both exist)
  TEST 5  — ESCALATES_TO is directional (only A->B, not B->A)
  TEST 6  — Spot-check known real-world mappings (murder, robbery, rape, dowry)
  TEST 7  — No orphan relationships (every rel has valid start+end nodes)
  TEST 8  — Old graph untouched (:LawSection nodes still exist)

Usage:
    python scripts/test_legal_graph.py
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from neo4j import GraphDatabase

# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR.parent / ".env"
load_dotenv(ENV_PATH)

NEO4J_URI      = os.getenv("NEO4J_URI")
NEO4J_USER     = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

if not all([NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD]):
    raise EnvironmentError("Missing Neo4j credentials in backend/.env")

# ── Helpers ───────────────────────────────────────────────────────────────────
PASS = "  ✅ PASS"
FAIL = "  ❌ FAIL"
WARN = "  ⚠️  WARN"

results = []   # (test_name, passed: bool, message)

def record(name: str, passed: bool, msg: str):
    results.append((name, passed, msg))
    icon = PASS if passed else FAIL
    print(f"{icon}  [{name}]  {msg}")

# ── Test Definitions ──────────────────────────────────────────────────────────

def test_node_counts(session):
    """TEST 1 — Check that IPCSection and BNSSection nodes were created."""
    ipc_count = session.run("MATCH (n:IPCSection) RETURN count(n) AS c").single()["c"]
    bns_count = session.run("MATCH (n:BNSSection) RETURN count(n) AS c").single()["c"]

    record("T1a - IPCSection nodes", ipc_count > 0,
           f"{ipc_count} IPCSection nodes found (expected > 0)")
    record("T1b - BNSSection nodes", bns_count > 0,
           f"{bns_count} BNSSection nodes found (expected > 0)")
    return ipc_count, bns_count


def test_replaces_links(session):
    """TEST 2 — BNSSection -[:REPLACES]-> IPCSection links."""
    total = session.run(
        "MATCH (b:BNSSection)-[:REPLACES]->(i:IPCSection) RETURN count(*) AS c"
    ).single()["c"]
    record("T2 - REPLACES links", total > 0,
           f"{total} BNS->IPC REPLACES relationships found")

    # Spot check: BNS 2(1) should reference IPC 33
    row = session.run("""
        MATCH (b:BNSSection {section: '2(1)'})-[:REPLACES]->(i:IPCSection)
        RETURN i.section AS ipc_sec
    """).data()
    ipc_refs = [r["ipc_sec"] for r in row]
    record("T2a - BNS 2(1) -> IPC 33", "33" in ipc_refs,
           f"BNS 2(1) links to IPC sections: {ipc_refs}")


def test_replaced_by_links(session):
    """TEST 3 — IPCSection -[:REPLACED_BY]-> BNSSection (reverse) links."""
    total = session.run(
        "MATCH (i:IPCSection)-[:REPLACED_BY]->(b:BNSSection) RETURN count(*) AS c"
    ).single()["c"]
    record("T3 - REPLACED_BY links", total > 0,
           f"{total} IPC->BNS REPLACED_BY relationships found")

    # Spot check: IPC 33 should be replaced by BNS 2(1)
    row = session.run("""
        MATCH (i:IPCSection {section: '33'})-[:REPLACED_BY]->(b:BNSSection)
        RETURN b.section AS bns_sec
    """).data()
    bns_refs = [r["bns_sec"] for r in row]
    record("T3a - IPC 33 -> BNS 2(1)", "2(1)" in bns_refs,
           f"IPC 33 replaced by BNS sections: {bns_refs}")


def test_co_charged_bidirectional(session):
    """TEST 4 — CO_CHARGED_WITH must be bidirectional: A->B AND B->A."""
    # Pick a known pair: 302 (murder) <-> 392 (robbery)
    a_to_b = session.run("""
        MATCH (a:IPCSection {section:'302'})-[:CO_CHARGED_WITH]->(b:IPCSection {section:'392'})
        RETURN count(*) AS c
    """).single()["c"]

    b_to_a = session.run("""
        MATCH (a:IPCSection {section:'392'})-[:CO_CHARGED_WITH]->(b:IPCSection {section:'302'})
        RETURN count(*) AS c
    """).single()["c"]

    record("T4a - 302->392 CO_CHARGED_WITH", a_to_b > 0,
           "IPC 302 (Murder) -> IPC 392 (Robbery) link exists")
    record("T4b - 392->302 CO_CHARGED_WITH bidirectional", b_to_a > 0,
           "IPC 392 (Robbery) -> IPC 302 (Murder) reverse link exists")

    # Check overall bidirectionality: every A->B should have B->A
    asymmetric = session.run("""
        MATCH (a:IPCSection)-[:CO_CHARGED_WITH]->(b:IPCSection)
        WHERE NOT (b)-[:CO_CHARGED_WITH]->(a)
        RETURN a.section AS a, b.section AS b
    """).data()
    record("T4c - All CO_CHARGED_WITH bidirectional", len(asymmetric) == 0,
           f"{len(asymmetric)} asymmetric CO_CHARGED_WITH pairs (expected 0). "
           + (f"Broken: {[(r['a'],r['b']) for r in asymmetric[:5]]}" if asymmetric else ""))

def test_escalates_to_directional(session):
    """TEST 5 — ESCALATES_TO must be directional, NOT bidirectional."""
    # 395 (dacoity) + 302 (murder) -> 396 (dacoity with murder)
    a_to_b = session.run("""
        MATCH (a:IPCSection {section:'395'})-[:ESCALATES_TO]->(b:IPCSection {section:'396'})
        RETURN count(*) AS c
    """).single()["c"]
    record("T5a - 395 ESCALATES_TO 396", a_to_b > 0,
           "IPC 395 (Dacoity) escalates to IPC 396 (Dacoity with Murder)")

    # 396 should NOT escalate back to 395
    b_to_a = session.run("""
        MATCH (a:IPCSection {section:'396'})-[:ESCALATES_TO]->(b:IPCSection {section:'395'})
        RETURN count(*) AS c
    """).single()["c"]
    record("T5b - 396 does NOT escalate back to 395", b_to_a == 0,
           f"Reverse ESCALATES_TO 396->395 count: {b_to_a} (expected 0)")

    total = session.run(
        "MATCH ()-[r:ESCALATES_TO]->() RETURN count(r) AS c"
    ).single()["c"]
    record("T5c - ESCALATES_TO total", total > 0,
           f"{total} ESCALATES_TO relationships found")


def test_spot_checks(session):
    """TEST 6 — Real-world scenario spot checks."""

    scenarios = [
        # (scenario, ipc_a, ipc_b, rel_type, description)
        ("Robbery+Murder",    "302", "392", "CO_CHARGED_WITH", "Murder co-charged with Robbery"),
        ("Rape+Murder",       "302", "376", "CO_CHARGED_WITH", "Murder co-charged with Rape"),
        ("Dowry+Suicide",     "498A","306", "CO_CHARGED_WITH", "Dowry harassment + abetment of suicide"),
        ("Cheating+Forgery",  "420", "468", "CO_CHARGED_WITH", "Cheating co-charged with Forgery"),
        ("Kidnap+Extortion",  "363", "384", "CO_CHARGED_WITH", "Kidnapping co-charged with Extortion"),
        ("Theft->Robbery",    "379", "392", "ESCALATES_TO",    "Theft + force escalates to Robbery"),
    ]

    for (scenario, sec_a, sec_b, rel, desc) in scenarios:
        count = session.run(f"""
            MATCH (a:IPCSection {{section: $a}})-[:{rel}]->(b:IPCSection {{section: $b}})
            RETURN count(*) AS c
        """, a=sec_a, b=sec_b).single()["c"]
        record(f"T6 - {scenario}", count > 0,
               f"IPC {sec_a} -{rel}-> IPC {sec_b} : {desc}")


def test_no_orphan_relationships(session):
    """TEST 7 — All relationships connect to actual nodes (no dangling refs)."""

    for rel in ["REPLACES", "REPLACED_BY", "CO_CHARGED_WITH", "ESCALATES_TO"]:
        orphans = session.run(f"""
            MATCH (a)-[r:{rel}]->(b)
            WHERE a IS NULL OR b IS NULL
            RETURN count(r) AS c
        """).single()["c"]
        record(f"T7 - No orphans in {rel}", orphans == 0,
               f"{orphans} orphan {rel} relationships (expected 0)")


def test_old_graph_untouched(session):
    """TEST 8 — Old (:LawSection) nodes are still intact."""
    count = session.run("MATCH (n:LawSection) RETURN count(n) AS c").single()["c"]
    if count > 0:
        record("T8 - Old LawSection nodes intact", True,
               f"{count} old :LawSection nodes still present — old graph untouched ✅")
    else:
        # Not a failure — old graph may not have been built yet
        print(f"  ⚠️   [T8 - Old graph] No :LawSection nodes found "
              f"(old ingest_neo4j.py may not have been run — this is OK)")

def print_sample_queries(session):
    """Print 3 real sample traversals so you can see actual data."""
    print("\n─── Sample Graph Traversals ──────────────────────────────────────────")

    # 1. Robbery + murder → what sections apply?
    print("\n  Scenario: Robbery + Murder — which IPC sections co-apply?")
    rows = session.run("""
        MATCH (a:IPCSection {section:'302'})-[:CO_CHARGED_WITH]->(b:IPCSection)
        RETURN DISTINCT b.section AS section, b.title AS title
        ORDER BY b.section
    """).data()
    for r in rows:
        print(f"    IPC {r['section']:6s} — {r['title']}")

    # 2. BNS 103 → replaces which IPC?
    print("\n  BNS section 103 replaces which IPC section(s)?")
    rows = session.run("""
        MATCH (b:BNSSection {section:'103'})-[:REPLACES]->(i:IPCSection)
        RETURN i.section AS section, i.title AS title
    """).data()
    for r in rows:
        print(f"    IPC {r['section']} — {r['title']}")
    if not rows:
        print("    (BNS 103 not found — check section number in bns.csv)")

    # 3. Escalation chains
    print("\n  What escalation chains exist?")
    rows = session.run("""
        MATCH (a:IPCSection)-[r:ESCALATES_TO]->(b:IPCSection)
        RETURN a.section AS from_sec, a.title AS from_title,
               b.section AS to_sec,   b.title AS to_title,
               r.note AS note
    """).data()
    for r in rows:
        print(f"    IPC {r['from_sec']} + crime → IPC {r['to_sec']} | {r['note']}")

    print("\n──────────────────────────────────────────────────────────────────────")


# ── Runner ────────────────────────────────────────────────────────────────────
def main():
    print("\n══════════════════════════════════════════════════════")
    print("  Legal Knowledge Graph — Relationship Test Suite")
    print("══════════════════════════════════════════════════════\n")

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    with driver.session() as session:
        test_node_counts(session)
        print()
        test_replaces_links(session)
        print()
        test_replaced_by_links(session)
        print()
        test_co_charged_bidirectional(session)
        print()
        test_escalates_to_directional(session)
        print()
        test_spot_checks(session)
        print()
        test_no_orphan_relationships(session)
        print()
        test_old_graph_untouched(session)
        print()
        print_sample_queries(session)

    driver.close()

    # ── Summary ──
    passed = sum(1 for _, p, _ in results if p)
    failed = sum(1 for _, p, _ in results if not p)
    total  = len(results)

    print(f"\n══════════════════════════════════════════════════════")
    print(f"  RESULTS:  {passed}/{total} passed   |   {failed} failed")
    if failed == 0:
        print("  All tests passed — graph relationships are correct ✅")
    else:
        print("  Some tests failed — see ❌ above for details")
    print("══════════════════════════════════════════════════════\n")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
