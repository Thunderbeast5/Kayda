import os
from dotenv import load_dotenv
from neo4j import GraphDatabase
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[3]
ENV_PATH = BASE_DIR / "backend" / ".env" if (BASE_DIR / "backend" / ".env").exists() else BASE_DIR / ".env"
load_dotenv(ENV_PATH)

driver = GraphDatabase.driver(os.getenv("NEO4J_URI"), auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD")))

print("=" * 80)
print(" AUDITING BNSS AND BSA SUBSECTION/CLAUSE HIERARCHY EDGES IN NEO4J")
print("=" * 80 + "\n")

with driver.session() as s:
    # 1. Audit BNSS nodes containing '('
    bnss_sub_nodes = s.run("""
        MATCH (n:LawSection {act:'BNSS'})
        WHERE n.id CONTAINS '('
        RETURN n.id AS id, n.section AS sec, n.node_type AS type
        ORDER BY n.id
    """).data()
    
    print(f"1. BNSS Sub-Nodes containing '(' ({len(bnss_sub_nodes)} nodes):")
    bnss_connected = 0
    for node in bnss_sub_nodes:
        nid = node["id"]
        rel = s.run("""
            MATCH (p:LawSection)-[r:HAS_SUBSECTION|HAS_CLAUSE|HAS_EXPLANATION]->(c:LawSection {id: $id})
            RETURN p.id AS parent_id, type(r) AS rel_type, r.level AS level
        """, id=nid).single()
        if rel:
            bnss_connected += 1
            print(f"   * {nid} [{node['type']}] <-[:{rel['rel_type']} {{level: {rel['level']}}}]-- {rel['parent_id']}")
        else:
            print(f"   * {nid} [{node['type']}] MISSING HIERARCHY EDGE")

    print(f"   --> BNSS Hierarchy Edge Status: {bnss_connected}/{len(bnss_sub_nodes)} connected\n")

    # 2. Audit BSA nodes containing '('
    bsa_sub_nodes = s.run("""
        MATCH (n:LawSection {act:'BSA'})
        WHERE n.id CONTAINS '('
        RETURN n.id AS id, n.section AS sec, n.node_type AS type
        ORDER BY n.id
    """).data()
    
    print(f"2. BSA Sub-Nodes containing '(' ({len(bsa_sub_nodes)} nodes):")
    bsa_connected = 0
    for node in bsa_sub_nodes:
        nid = node["id"]
        rel = s.run("""
            MATCH (p:LawSection)-[r:HAS_SUBSECTION|HAS_CLAUSE|HAS_EXPLANATION]->(c:LawSection {id: $id})
            RETURN p.id AS parent_id, type(r) AS rel_type, r.level AS level
        """, id=nid).single()
        if rel:
            bsa_connected += 1
            print(f"   * {nid} [{node['type']}] <-[:{rel['rel_type']} {{level: {rel['level']}}}]-- {rel['parent_id']}")
        else:
            print(f"   * {nid} [{node['type']}] MISSING HIERARCHY EDGE")

    print(f"   --> BSA Hierarchy Edge Status: {bsa_connected}/{len(bsa_sub_nodes)} connected\n")

driver.close()
