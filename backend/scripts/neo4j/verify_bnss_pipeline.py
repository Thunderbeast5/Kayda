"""
verify_bnss_pipeline.py
========================
Permanent automated regression test suite for the BNSS <-> CrPC pipeline.
Executes 10 automated QA checks against the live Neo4j database and prints a
deterministic production summary report.
"""

import os
import sys
from pathlib import Path
from neo4j import GraphDatabase
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[3]
env_path = BASE_DIR / "backend" / ".env"
load_dotenv(dotenv_path=env_path)

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")


def main():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    results = {}
    failed_checks = []
    
    with driver.session() as s:
        # Check 1: Preprocessing & Data Completeness
        crpc_count = s.run("MATCH (n:LawSection {act:'CrPC'}) RETURN count(n) AS c").single()["c"]
        crpc_stubs = s.run("MATCH (n:LawSection {act:'CrPC'}) WHERE n.data_complete <> true RETURN count(n) AS c").single()["c"]
        results["step1"] = "PASS" if crpc_count == 534 and crpc_stubs == 0 else "FAIL"
        if crpc_stubs > 0:
            failed_checks.append(f"CrPC stubs remaining: {crpc_stubs}")
            
        # Check 2: Source Backfill
        results["step2"] = "PASS" if crpc_count >= 534 else "FAIL"
        
        # Check 3: Hierarchy Construction & Annotation Validation
        sub_count = s.run("MATCH (p:LawSection)-[:HAS_SUBSECTION]->(c:LawSection) WHERE p.id STARTS WITH 'BNSS' RETURN count(c) AS c").single()["c"]
        clause_count = s.run("MATCH (p:LawSection)-[:HAS_CLAUSE]->(c:LawSection) WHERE p.id STARTS WITH 'BNSS' RETURN count(c) AS c").single()["c"]
        total_hierarchy = sub_count + clause_count
        
        fake_nodes = s.run("MATCH (n:LawSection) WHERE n.id IN ['BNSS_396(Subs)', 'BNSS_397(Subs)'] RETURN count(n) AS c").single()["c"]
        
        results["step3"] = "PASS" if sub_count == 2 and clause_count == 1 and total_hierarchy == 3 and fake_nodes == 0 else "FAIL"
        if fake_nodes > 0:
            failed_checks.append(f"Fake annotation nodes exist: {fake_nodes}")
            
        # Check 4: Text Segmentation
        desc_35_3 = s.run("MATCH (n:LawSection {id:'BNSS_35(3)'}) RETURN n.description AS d").single()
        len_35_3 = len(desc_35_3["d"]) if desc_35_3 and desc_35_3["d"] else 9999
        results["step4"] = "PASS" if len_35_3 < 600 else "FAIL"
        if len_35_3 >= 600:
            failed_checks.append(f"BNSS_35(3) text not properly segmented (Length: {len_35_3})")
            
        # Check 5: Structural Inheritance & Judicial Isolation
        jud_edges = s.run("""
            MATCH (c:LawSection)-[r:INTERPRETS|APPLIES_SECTION|CITES_CASE]->(target)
            WHERE r.inherited = true
            RETURN count(r) AS c
        """).single()["c"]
        results["step5"] = "PASS" if jud_edges == 0 else "FAIL"
        if jud_edges > 0:
            failed_checks.append(f"Inherited judicial edges detected: {jud_edges}")
            
        # Check 6: Cross-Act Mapping & Tag Counts
        deleted_tags = s.run("MATCH (n:LawSection {act:'CrPC', mapping_status:'deleted_no_bnss_successor'}) RETURN count(n) AS c").single()["c"]
        new_tags = s.run("MATCH (n:LawSection {act:'BNSS', mapping_status:'new_no_crpc_predecessor'}) RETURN count(n) AS c").single()["c"]
        
        results["step6"] = "PASS" if deleted_tags == 11 and new_tags >= 5 else "FAIL"
        if deleted_tags != 11:
            failed_checks.append(f"Expected 11 deleted CrPC section tags, got {deleted_tags}")
        if new_tags < 5:
            failed_checks.append(f"Expected at least 5 new BNSS section tags, got {new_tags}")
            
        # Check 7: GraphRAG Indexing & Search Retrieval
        search_35_3 = s.run("""
            CALL db.index.fulltext.queryNodes('lawSectionText', 'notice of appearance') YIELD node, score
            WHERE node.id IN ['BNSS_35(3)', 'BNSS_35', 'CrPC_41A']
            RETURN node.id AS id, score
            LIMIT 5
        """).data()
        results["step7"] = "PASS" if len(search_35_3) > 0 else "FAIL"
        
        # Check 8: Automated QA Assertions
        garbage_nodes = s.run("MATCH (n:LawSection {act:'BNSS'}) WHERE NOT n.section =~ '^[0-9].*' RETURN count(n) AS c").single()["c"]
        orphans = s.run("""
            MATCH (c:LawSection {act:'BNSS'})
            WHERE c.node_type IN ['SUBSECTION', 'CLAUSE']
            AND NOT (c)<-[:HAS_SUBSECTION|HAS_CLAUSE]-(:LawSection)
            RETURN count(c) AS c
        """).single()["c"]
        
        results["step8"] = "PASS" if garbage_nodes == 0 and orphans == 0 else "FAIL"
        if garbage_nodes > 0:
            failed_checks.append(f"Garbage BNSS section nodes detected: {garbage_nodes}")
        if orphans > 0:
            failed_checks.append(f"Orphan BNSS sub-nodes detected: {orphans}")

    driver.close()
    
    # Deterministic Production Summary Report
    all_passed = all(status == "PASS" for status in results.values()) and len(failed_checks) == 0
    status_str = "PRODUCTION READY" if all_passed else "FAILED - REQUIRES REVIEW"
    
    print("\n==========================================")
    print("      BNSS <-> CrPC INGESTION SUMMARY      ")
    print("==========================================")
    print(f"Step 1  Preprocessing               {results['step1']}")
    print(f"Step 2  Source Backfill             {results['step2']}")
    print(f"Step 3  Hierarchy Construction      {results['step3']}")
    print(f"Step 4  Text Segmentation           {results['step4']}")
    print(f"Step 5  Structural Inheritance      {results['step5']}")
    print(f"Step 6  Cross-Act Mapping           {results['step6']}")
    print(f"Step 7  GraphRAG Indexing           {results['step7']}")
    print(f"Step 8  Validation & QA             {results['step8']}")
    print("------------------------------------------")
    print(f"Deleted Sections Verified:        {deleted_tags}")
    print(f"New BNSS Sections Verified:        {new_tags}")
    print(f"Hierarchy Nodes Created:           {total_hierarchy}")
    print(f"Fake Annotation Nodes:             {fake_nodes}")
    print(f"Hierarchy Orphans:                 {orphans}")
    print(f"Inherited Judicial Edges:          {jud_edges}")
    print(f"Stub Nodes Remaining:              {crpc_stubs}")
    print("------------------------------------------")
    print("GRAPH STATUS")
    print(f" {status_str} ")
    print("==========================================\n")
    
    if not all_passed:
        print("FAILURES DETECTED:")
        for fc in failed_checks:
            print(f"  * {fc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
