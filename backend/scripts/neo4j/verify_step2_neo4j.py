"""
verify_step2_neo4j.py
=====================
Step 2 Neo4j Cypher Verification Script.
Executes verification queries against Neo4j to confirm the creation of:
  - BNSSection hierarchy nodes
  - HAS_SUBSECTION, HAS_CLAUSE, HAS_EXPLANATION edges
  - GeneratedNode intermediate nodes
  - IPC <-> BNS mapping relationship properties
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from neo4j import GraphDatabase

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

if not all([NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD]):
    raise EnvironmentError("Missing Neo4j credentials in environment.")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

print("=" * 80)
print(" STEP 2 NEO4J GRAPH VERIFICATION")
print("=" * 80 + "\n")

with driver.session() as s:
    # 1. BNSSection count
    c_bns = s.run("MATCH (n:BNSSection) RETURN count(n) AS c").single()["c"]
    print(f"1. Total (:BNSSection) Nodes: {c_bns}")

    # 2. Section 8(1) node check
    s8_1 = s.run("MATCH (s:BNSSection {section: '8(1)'}) RETURN s.id AS id, s.title AS title, s.node_type AS type").single()
    if s8_1:
        print(f"2. Sample BNS Section 8(1) Node: ID='{s8_1['id']}', Title='{s8_1['title']}', Type='{s8_1['type']}'")
    else:
        print("2. Sample BNS Section 8(1) Node: NOT FOUND")

    # 3. HAS_SUBSECTION count
    c_sub = s.run("MATCH (p)-[:HAS_SUBSECTION]->(c) RETURN count(*) AS c").single()["c"]
    print(f"3. Total HAS_SUBSECTION Relationships: {c_sub}")

    # 4. HAS_CLAUSE count & breakdown
    c_cl = s.run("MATCH (p)-[:HAS_CLAUSE]->(c) RETURN count(*) AS c").single()["c"]
    print(f"4. Total HAS_CLAUSE Relationships: {c_cl}")
    clause_rels = s.run("MATCH (p)-[:HAS_CLAUSE]->(c) RETURN p.section AS parent, c.section AS clause, c.node_type AS type LIMIT 5")
    for r in clause_rels:
        print(f"   * ({r['parent']})-[:HAS_CLAUSE]->({r['clause']}) [{r['type']}]")

    # 5. HAS_EXPLANATION count & breakdown
    c_exp = s.run("MATCH (p)-[:HAS_EXPLANATION]->(c) RETURN count(*) AS c").single()["c"]
    print(f"5. Total HAS_EXPLANATION Relationships: {c_exp}")
    exp_rels = s.run("MATCH (p)-[:HAS_EXPLANATION]->(c) RETURN p.section AS parent, c.section AS exp")
    for r in exp_rels:
        print(f"   * ({r['parent']})-[:HAS_EXPLANATION]->({r['exp']})")

    # 6. GeneratedNode count
    c_gen = s.run("MATCH (g:GeneratedNode) RETURN count(g) AS c").single()["c"]
    print(f"6. Total (:GeneratedNode) Intermediate Nodes: {c_gen}")

    # 7. Sample REPLACED_BY relationship metadata check (IPC 68 -> BNS 8(6))
    rel_sample = s.run("""
        MATCH (i:LawSection {id: 'IPC_68'})-[r:REPLACED_BY]->(b:LawSection {id: 'BNS_8(6)'})
        RETURN i.section AS ipc_sec, i.title AS ipc_node_title, r.ipc_title AS rel_ipc_title, b.section AS bns_sec, b.title AS bns_title
    """).single()
    if rel_sample:
        print(f"7. Preserved Relationship Metadata Check:")
        print(f"   * IPC Node: IPC_{rel_sample['ipc_sec']} ('{rel_sample['ipc_node_title']}')")
        print(f"   * Edge Property r.ipc_title: '{rel_sample['rel_ipc_title']}'")
        print(f"   * Target BNS Node: BNS_{rel_sample['bns_sec']} ('{rel_sample['bns_title']}')")

print("\n" + "=" * 80)
print(" STEP 2 VERIFICATION COMPLETE")
print("=" * 80)

driver.close()
