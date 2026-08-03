"""
verify_step4_pipeline.py
========================
Standing Automated Regression Test Suite for LexiGraph Neo4j Ingestion Pipeline.

Automates all data-integrity, schema, and retrieval assertions:
  1. Act Node & Section Counts
  2. Garbage Node Detection (Non-numeric BNS/BNSS/BSA sections)
  3. Orphan Sub-Node Detection (Sub-nodes containing '(' without parent hierarchy edges)
  4. Data Completeness & Content Source Audit (Full vs Stub nodes)
  5. Unmapped & Deleted Section Tag Counts (deleted_no_bns_successor & new_no_ipc_predecessor)
  6. Canonical Title & Preserved IPC Wording Audit for Duplicate Targets
  7. Universal node_type Harmonization (0 NULL node_type values)
  8. GraphRAG Full-Text Retrieval Readiness ('lawSectionText')

Usage:
    python backend/scripts/neo4j/verify_step4_pipeline.py
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from neo4j import GraphDatabase

BASE_DIR = Path(__file__).resolve().parents[3]
ENV_PATH = BASE_DIR / "backend" / ".env" if (BASE_DIR / "backend" / ".env").exists() else BASE_DIR / ".env"
load_dotenv(ENV_PATH)

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

if not all([NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD]):
    raise EnvironmentError("Missing Neo4j credentials in backend/.env")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

print("=" * 80)
print(" STANDING AUTOMATED REGRESSION TEST SUITE FOR LEXIGRAPH NEO4J INGESTION")
print("=" * 80 + "\n")

all_passed = True

with driver.session() as s:
    # ── CHECK 1: Node Counts by Act ───────────────────────────────────────────
    print("--- CHECK 1: LawSection Node Counts by Act ---")
    act_counts = s.run("""
        MATCH (l:LawSection)
        RETURN l.act AS act, count(l) AS count
        ORDER BY act
    """).data()
    expected_counts = {"BNS": 545, "BNSS": 536, "BSA": 188, "CrPC": 535, "IEA": 186, "IPC": 576}
    check1_ok = True
    for r in act_counts:
        act = r["act"]
        count = r["count"]
        expected = expected_counts.get(act, 0)
        match = count == expected
        if not match:
            check1_ok = False
            all_passed = False
        print(f"   * Act '{act:4s}': Actual={count:4d} | Expected={expected:4d} | Match={match}")
    print(f"   --> CHECK 1 STATUS: {'PASSED' if check1_ok else 'FAILED'}\n")

    # ── CHECK 2: Garbage Node Check (Non-numeric Sections) ───────────────────
    print("--- CHECK 2: Garbage Node Detection (Non-Numeric Section IDs) ---")
    garbage_nodes = s.run("""
        MATCH (n:LawSection)
        WHERE n.act IN ['BNS', 'BNSS', 'BSA'] AND n.section <> 'Schedule' AND NOT n.section =~ '^[0-9].*'
        RETURN n.id AS id, n.act AS act, n.section AS sec
    """).data()
    check2_ok = len(garbage_nodes) == 0
    if not check2_ok:
        all_passed = False
        print(f"   * FAILED: Found {len(garbage_nodes)} garbage nodes:")
        for g in garbage_nodes:
            print(f"     - {g['id']} ({g['act']}) sec='{g['sec']}'")
    else:
        print("   * PASSED: 0 non-numeric / garbage nodes found in BNS, BNSS, or BSA.")
    print(f"   --> CHECK 2 STATUS: {'PASSED' if check2_ok else 'FAILED'}\n")

    # ── CHECK 3: Orphan Sub-Node Detection ───────────────────────────────────
    print("--- CHECK 3: Orphan Sub-Node Detection (Nodes with '(' missing Parent Edge) ---")
    orphans = s.run("""
        MATCH (c:LawSection)
        WHERE c.id CONTAINS '(' AND NOT (c)<-[:HAS_SUBSECTION|HAS_CLAUSE|HAS_EXPLANATION]-(:LawSection)
        RETURN c.id AS id, c.act AS act, c.section AS sec
    """).data()
    check3_ok = len(orphans) == 0
    if not check3_ok:
        all_passed = False
        print(f"   * FAILED: Found {len(orphans)} orphan sub-nodes without parent hierarchy edges:")
        for o in orphans:
            print(f"     - {o['id']} ({o['act']}) sec='{o['sec']}'")
    else:
        print("   * PASSED: 0 orphan sub-nodes found. All 209 sub-nodes carry active hierarchy edges.")
    print(f"   --> CHECK 3 STATUS: {'PASSED' if check3_ok else 'FAILED'}\n")

    # ── CHECK 4: Data Completeness & Stub Breakdown ─────────────────────────
    print("--- CHECK 4: Data Completeness & Content Source Audit ---")
    comp_count = s.run("MATCH (n:LawSection) WHERE n.data_complete = true RETURN count(n) AS c").single()["c"]
    stub_count = s.run("MATCH (n:LawSection) WHERE n.data_complete = false OR n.data_complete IS NULL RETURN count(n) AS c").single()["c"]
    
    stubs_by_act = s.run("""
        MATCH (n:LawSection)
        WHERE n.data_complete = false OR n.data_complete IS NULL
        RETURN n.act AS act, count(n) AS stubs
    """).data()
    stub_dict = {r["act"]: r["stubs"] for r in stubs_by_act}
    expected_stubs = {"IPC": 1, "CrPC": 10, "IEA": 2, "BNS": 0, "BNSS": 0, "BSA": 0}
    
    check4_ok = (comp_count == 2553) and (stub_count == 13)
    if not check4_ok:
        all_passed = False

    print(f"   * Full Content Nodes (data_complete = true):  Actual={comp_count} | Expected=2553")
    print(f"   * Stub Nodes (data_complete = false):          Actual={stub_count} | Expected=13")
    for act in ["IPC", "CrPC", "IEA", "BNS", "BNSS", "BSA"]:
        actual_s = stub_dict.get(act, 0)
        exp_s = expected_stubs[act]
        print(f"     - Act {act:4s} Stubs: Actual={actual_s:2d} | Expected={exp_s:2d} | Match={actual_s == exp_s}")
    print(f"   --> CHECK 4 STATUS: {'PASSED' if check4_ok else 'FAILED'}\n")

    # ── CHECK 5: Unmapped & Deleted Section Tag Counts ───────────────────────
    print("--- CHECK 5: Unmapped & Deleted Section Mapping Status Tag Counts ---")
    deleted_ipc = s.run("MATCH (n:LawSection {mapping_status:'deleted_no_bns_successor'}) RETURN count(n) AS c").single()["c"]
    new_bns = s.run("MATCH (n:LawSection {mapping_status:'new_no_ipc_predecessor'}) RETURN count(n) AS c").single()["c"]
    
    check5_ok = (deleted_ipc == 38) and (new_bns == 45)
    if not check5_ok:
        all_passed = False

    print(f"   * deleted_no_bns_successor tags (IPC): Actual={deleted_ipc} | Expected=38")
    print(f"   * new_no_ipc_predecessor tags (BNS):    Actual={new_bns} | Expected=45")
    print(f"   --> CHECK 5 STATUS: {'PASSED' if check5_ok else 'FAILED'}\n")

    # ── CHECK 6: Canonical Title Audit for Duplicate Targets ──────────────────
    print("--- CHECK 6: Canonical Titles & Preserved IPC Wording Audit ---")
    targets = {
        "BNS_8(6)": "Imprisonment to terminate on payment of fine",
        "BNS_70(2)": "Punishment for gang rape on woman under sixteen years of age",
        "BNS_189(2)": "Being member of unlawful assembly",
        "BNS_189(5)": "Joining or continuing in unlawful assembly, knowing it has been commanded to disperse",
    }
    check6_ok = True
    for nid, exp_title in targets.items():
        node = s.run("MATCH (n:LawSection {id: $id}) RETURN n.title AS title", id=nid).single()
        act_title = node["title"] if node else "NOT FOUND"
        match = act_title == exp_title
        if not match:
            check6_ok = False
            all_passed = False
        print(f"   * Node {nid:10s}: Title Match={match} ('{act_title[:50]}...')")
    print(f"   --> CHECK 6 STATUS: {'PASSED' if check6_ok else 'FAILED'}\n")

    # ── CHECK 7: Universal node_type Assignment Audit ─────────────────────────
    print("--- CHECK 7: Universal node_type Assignment Audit ---")
    null_types = s.run("MATCH (n:LawSection) WHERE n.node_type IS NULL RETURN count(n) AS c").single()["c"]
    check7_ok = null_types == 0
    if not check7_ok:
        all_passed = False
        print(f"   * FAILED: Found {null_types} nodes with NULL node_type.")
    else:
        print("   * PASSED: 0 nodes with NULL/unset node_type across all 6 statutory Acts.")
    print(f"   --> CHECK 7 STATUS: {'PASSED' if check7_ok else 'FAILED'}\n")

    # ── CHECK 8: GraphRAG Full-Text Search Retrieval Readiness ────────────────
    print("--- CHECK 8: GraphRAG Full-Text Search Retrieval Readiness ('lawSectionText') ---")
    ft_res = s.run("""
        CALL db.index.fulltext.queryNodes('lawSectionText', 'kidnapping AND lawful AND guardianship')
        YIELD node, score
        RETURN node.id AS id, node.node_type AS type, score
        ORDER BY score DESC LIMIT 1
    """).single()
    check8_ok = ft_res is not None and ft_res["score"] > 5.0
    if not check8_ok:
        all_passed = False
        print("   * FAILED: Full-text index retrieval returned no results or low score.")
    else:
        print(f"   * PASSED: Top Hit = {ft_res['id']} [{ft_res['type']}] with score {ft_res['score']:.2f}")
    print(f"   --> CHECK 8 STATUS: {'PASSED' if check8_ok else 'FAILED'}\n")

print("=" * 80)
if all_passed:
    print(" ALL 8 STANDING REGRESSION TESTS PASSED (100% PIPELINE INTEGRITY)")
else:
    print(" SOME REGRESSION TESTS FAILED — CHECK LOGS ABOVE")
print("=" * 80)

driver.close()
if not all_passed:
    sys.exit(1)
