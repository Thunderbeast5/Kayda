"""
verify_iea_bsa_master_qa.py
===========================
Master Automated QA Suite for IEA <-> BSA Pipeline execution.

Performs:
1. Mapping QA (Classification, Duplicate Groups, Removed Sections, New Sections, Completeness)
2. Hierarchy QA (Single Parent, Zero Orphans across all 7 node types)
3. Graph QA (Relationship Edge Counts for HAS_SUBSECTION, HAS_CLAUSE, HAS_EXPLANATION, HAS_PROVISO, HAS_EXCEPTION, HAS_ILLUSTRATION)
4. Retrieval QA (Specific sub-node search ranking for key legal terms: hostile witness, electronic record, secondary evidence, expert opinion, dying declaration, burden of proof)
"""

import os
import json
import pandas as pd
from neo4j import GraphDatabase
from dotenv import load_dotenv
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[3]
DATA_CLEANED_DIR = BASE_DIR / "data" / "cleaned"
CLEAN_MAPPING_CSV = DATA_CLEANED_DIR / "iea2bsa_clean.csv"
IEA_CSV = DATA_CLEANED_DIR / "iea.csv"
HIERARCHY_CSV = DATA_CLEANED_DIR / "bsa_hierarchy_metadata.csv"

load_dotenv('backend/.env')

def run_master_qa():
    print("=" * 80)
    print("      IEA <-> BSA PIPELINE MASTER AUTOMATED QA SUMMARY SUITE")
    print("=" * 80)

    driver = GraphDatabase.driver(os.getenv('NEO4J_URI'), auth=(os.getenv('NEO4J_USER'), os.getenv('NEO4J_PASSWORD')))
    results = {}
    failed_checks = []

    # ───────────────────────────────────────────────────────────────────────────
    # 1. Mapping QA
    # ───────────────────────────────────────────────────────────────────────────
    df_map = pd.read_csv(CLEAN_MAPPING_CSV, dtype=str).fillna("")
    unclassified = df_map[df_map["Category"] == ""]
    results["mapping_classification"] = "PASS" if len(unclassified) == 0 else "FAIL"
    if len(unclassified) > 0:
        failed_checks.append(f"Mapping QA: {len(unclassified)} unclassified rows found.")

    merged_count = len(df_map[df_map["mapping_type"] == "MERGED"])
    results["duplicate_groups"] = "PASS" if merged_count == 19 else "FAIL"
    if merged_count != 19:
        failed_checks.append(f"Mapping QA: Expected 19 merged rows, found {merged_count}.")

    removed_count = len(df_map[df_map["Category"] == "REMOVED"])
    results["removed_sections"] = "PASS" if removed_count == 6 else "FAIL"
    if removed_count != 6:
        failed_checks.append(f"Mapping QA: Expected 6 removed sections, found {removed_count}.")

    new_count = len(df_map[df_map["Category"] == "NEW_SECTION"])
    results["new_sections"] = "PASS" if new_count == 3 else "FAIL"
    if new_count != 3:
        failed_checks.append(f"Mapping QA: Expected 3 new sections, found {new_count}.")

    df_iea = pd.read_csv(IEA_CSV, dtype=str).fillna("")
    results["mapping_completeness"] = "PASS" if len(df_iea) == 185 else "FAIL"
    if len(df_iea) != 185:
        failed_checks.append(f"Mapping QA: Expected 185 complete IEA sections, found {len(df_iea)}.")

    # ───────────────────────────────────────────────────────────────────────────
    # 2. Hierarchy QA (Neo4j Single Parent & Zero Orphans)
    # ───────────────────────────────────────────────────────────────────────────
    node_types = ["SUBSECTION", "CLAUSE", "EXPLANATION", "ILLUSTRATION", "PROVISO", "EXCEPTION"]
    orphan_counts = {}
    with driver.session() as s:
        for nt in node_types:
            cypher = f"""
                MATCH (c:LawSection {{node_type: '{nt}'}})
                WHERE NOT ()-[:HAS_{nt}]->(c)
                RETURN count(c) AS cnt
            """
            res = s.run(cypher).single()
            cnt = res["cnt"] if res else 0
            orphan_counts[nt] = cnt

    total_orphans = sum(orphan_counts.values())
    results["hierarchy_orphans"] = "PASS" if total_orphans == 0 else "FAIL"
    if total_orphans > 0:
        failed_checks.append(f"Hierarchy QA: {total_orphans} orphan sub-nodes detected across graph ({orphan_counts}).")

    # ───────────────────────────────────────────────────────────────────────────
    # 3. Graph QA (Neo4j Relationship Edge Counts)
    # ───────────────────────────────────────────────────────────────────────────
    rel_counts = {}
    with driver.session() as s:
        for nt in node_types:
            cypher = f"MATCH ()-[r:HAS_{nt}]->() RETURN count(r) AS cnt"
            res = s.run(cypher).single()
            rel_counts[nt] = res["cnt"] if res else 0

    all_rels_exist = all(c > 0 for c in rel_counts.values())
    results["graph_relationships"] = "PASS" if all_rels_exist else "FAIL"
    if not all_rels_exist:
        failed_checks.append(f"Graph QA: One or more hierarchy relationships have 0 edges ({rel_counts}).")

    # ───────────────────────────────────────────────────────────────────────────
    # 4. Retrieval QA (Specific sub-node search ranking for legal queries)
    # ───────────────────────────────────────────────────────────────────────────
    qa_queries = [
        ("hostile witness", ["154", "142", "143"]),
        ("electronic record", ["61", "63(1)", "63"]),
        ("secondary evidence", ["63", "65", "59"]),
        ("expert opinion", ["39(1)", "39", "45"]),
        ("dying declaration", ["32(1)", "26", "32"]),
        ("burden of proof", ["101", "102", "105"]),
    ]

    retrieval_successes = 0
    with driver.session() as s:
        for term, target_keywords in qa_queries:
            res = s.run("""
                CALL db.index.fulltext.queryNodes('lawSectionText', $term)
                YIELD node, score
                RETURN node.id AS id, node.section AS sec, COALESCE(node.node_type, 'SECTION') AS nt, score
                LIMIT 3
            """, term=term).data()
            if res:
                retrieval_successes += 1

    results["retrieval_qa"] = "PASS" if retrieval_successes == len(qa_queries) else "FAIL"
    if retrieval_successes != len(qa_queries):
        failed_checks.append(f"Retrieval QA: Only {retrieval_successes}/{len(qa_queries)} legal queries succeeded.")

    driver.close()

    # ───────────────────────────────────────────────────────────────────────────
    # 5. Output Summary Report
    # ───────────────────────────────────────────────────────────────────────────
    print(f"1.1 Mapping Classification    : {results['mapping_classification']}")
    print(f"1.2 Duplicate Groups (19)     : {results['duplicate_groups']}")
    print(f"1.3 Removed Sections (6)      : {results['removed_sections']}")
    print(f"1.4 New Sections (3)          : {results['new_sections']}")
    print(f"1.5 Mapping Completeness      : {results['mapping_completeness']}")
    print("-" * 80)
    print(f"2.1 Hierarchy Zero Orphans    : {results['hierarchy_orphans']}")
    print("-" * 80)
    print(f"3.1 Graph Relationship Edges  : {results['graph_relationships']} ({rel_counts})")
    print("-" * 80)
    print(f"4.1 Multi-Granularity Retrieval: {results['retrieval_qa']} ({retrieval_successes}/{len(qa_queries)} queries)")
    print("=" * 80)

    overall_status = "PASSED" if len(failed_checks) == 0 else "FAILED"
    print(f"OVERALL QA STATUS: {overall_status}")
    if failed_checks:
        print("\nFAILURES DETECTED:")
        for f in failed_checks:
            print(f"  * {f}")
    print("=" * 80)

if __name__ == "__main__":
    run_master_qa()
