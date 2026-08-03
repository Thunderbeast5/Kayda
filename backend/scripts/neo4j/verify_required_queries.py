"""
verify_required_queries.py
==========================
Runs exact required Cypher verification queries requested in the prompt,
including relationship edge property checks (level & type).
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from neo4j import GraphDatabase

BASE_DIR = Path(__file__).resolve().parents[3]
ENV_PATH = BASE_DIR / "backend" / ".env" if (BASE_DIR / "backend" / ".env").exists() else BASE_DIR / ".env"
load_dotenv(ENV_PATH)

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

print("=" * 80)
print(" REQUIRED CYPHER VERIFICATION QUERIES & EDGE PROPERTY CHECKS")
print("=" * 80 + "\n")

with driver.session() as s:
    # 1. Subsection count
    q1 = "MATCH (n:BNSSection) WHERE n.node_type='SUBSECTION' RETURN count(n) AS c"
    c1 = s.run(q1).single()["c"]
    print(f"1. SUBSECTION count: {c1}")

    # 2. Clause count
    q2 = "MATCH (n:BNSSection) WHERE n.node_type='CLAUSE' RETURN count(n) AS c"
    c2 = s.run(q2).single()["c"]
    print(f"2. CLAUSE count: {c2}")

    # 3. Explanation count
    q3 = "MATCH (n:BNSSection) WHERE n.node_type='EXPLANATION' RETURN count(n) AS c"
    c3 = s.run(q3).single()["c"]
    print(f"3. EXPLANATION count: {c3}")

    # 4. GeneratedNode count
    q4 = "MATCH (n:GeneratedNode) RETURN count(n) AS c"
    c4 = s.run(q4).single()["c"]
    print(f"4. GeneratedNode count: {c4}")

    # 5. Section 8 hierarchy path & edge property level=1 check
    q5 = "MATCH (p:BNSSection {section:'8'})-[r:HAS_SUBSECTION]->(c:BNSSection {section:'8(1)'}) RETURN p, r, c"
    r5 = s.run(q5).single()
    if r5:
        p = r5["p"]
        r = r5["r"]
        c = r5["c"]
        print(f"\n5. Section 8 Hierarchy Path Found:")
        print(f"   ({p['id']}:{p['node_type']}) -[HAS_SUBSECTION {{level: {r.get('level')}}}]-> ({c['id']}:{c['node_type']})")
        print(f"   End Node Title: '{c['title']}'")

    # 6. Section 137 hierarchy children & clause edge property level=2 check
    q6 = "MATCH (p:BNSSection {section:'137'})-[r:HAS_SUBSECTION]->(c:BNSSection {section:'137(1)'})-[r2:HAS_CLAUSE]->(cl) RETURN c.id AS sub_id, r2.level AS clause_level, cl.id AS clause_id, cl.node_type AS clause_type"
    r6 = s.run(q6).data()
    print(f"\n6. Section 137 Hierarchy Traversal with Edge Properties ({len(r6)} clauses under 137(1)):")
    for row in r6:
        print(f"   * ({row['sub_id']}) -[HAS_CLAUSE {{level: {row['clause_level']}}}]-> ({row['clause_id']} [{row['clause_type']}])")

    # 7. Check explanation edge property type='EXPLANATION'
    q7 = "MATCH (p)-[r:HAS_EXPLANATION]->(c) RETURN p.id AS parent_id, r.type AS rel_type, c.id AS exp_id"
    r7 = s.run(q7).single()
    if r7:
        print(f"\n7. Explanation Relationship Edge Property Check:")
        print(f"   * ({r7['parent_id']}) -[HAS_EXPLANATION {{type: '{r7['rel_type']}'}}]-> ({r7['exp_id']})")

driver.close()
