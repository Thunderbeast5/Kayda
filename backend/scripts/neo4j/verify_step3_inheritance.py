"""
verify_step3_inheritance.py
============================
Verification script for Step 3: Inherit Structural Context.
Checks that:
1. Structural context relationships (HAS_KEYWORD, HAS_PUNISHMENT, DEFINED_BY, HAS_SECTION, etc.)
   are inherited down to child hierarchy nodes (BNS_8(1), BNS_137(1)(A), BNS_5_EXPL).
2. Inherited relationships carry r.inherited = true, r.inherited_from, and r.inheritance_level.
3. 0 judicial case relationships (INTERPRETS, APPLIES_SECTION, CITES_CASE, USES_EVIDENCE, DECIDED_BY)
   are inherited to child nodes.
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
print(" STEP 3 STRUCTURAL CONTEXT INHERITANCE VERIFICATION")
print("=" * 80 + "\n")

with driver.session() as s:
    # 1. Total Inherited Relationships by Type
    print("1. Inherited Relationships Summary:")
    inherited_types = s.run("""
        MATCH ()-[r]->()
        WHERE r.inherited = true
        RETURN type(r) AS rel_type, count(r) AS c
        ORDER BY c DESC
    """).data()
    for row in inherited_types:
        print(f"   * -[{row['rel_type']} {{inherited: true}}]-> count: {row['c']}")

    # 2. Sample Verification on BNS_8(1) (Subsection level-1 inheritance)
    print("\n2. Sample Sub-node Verification (BNS_8(1)):")
    s8_1_inherited = s.run("""
        MATCH (c:BNSSection {id: 'BNS_8(1)'})-[r]->(target)
        WHERE r.inherited = true
        RETURN type(r) AS rel_type, r.inherited_from AS from_id, r.inheritance_level AS level, target.id AS target_id LIMIT 5
    """).data()
    for row in s8_1_inherited:
        print(f"   * (BNS_8(1)) -[:{row['rel_type']} {{inherited_from: '{row['from_id']}', level: {row['level']}}}]-> ({row['target_id']})")

    # 3. Sample Level-2 Verification on Clauses (BNS_137(1)(A))
    print("\n3. Sample Clause Verification (BNS_137(1)(A)):")
    clause_inherited = s.run("""
        MATCH (c:BNSSection {id: 'BNS_137(1)(A)'})-[r]->(target)
        WHERE r.inherited = true
        RETURN type(r) AS rel_type, r.inherited_from AS from_id, r.inheritance_level AS level, target.id AS target_id LIMIT 5
    """).data()
    if clause_inherited:
        for row in clause_inherited:
            print(f"   * (BNS_137(1)(A)) -[:{row['rel_type']} {{inherited_from: '{row['from_id']}', level: {row['level']}}}]-> ({row['target_id']})")
    else:
        print("   * No inherited edges found for BNS_137(1)(A) (check parent/grandparent edge existence)")

    # 4. Judicial Relationship Exclusion Check
    print("\n4. Judicial Case Relationships Exclusion Check:")
    judicial_on_children = s.run("""
        MATCH (child:BNSSection)-[r]->()
        WHERE child.node_type IN ['SUBSECTION', 'CLAUSE', 'EXPLANATION']
          AND type(r) IN ['INTERPRETS', 'APPLIES_SECTION', 'CITES_CASE', 'USES_EVIDENCE', 'DECIDED_BY']
        RETURN type(r) AS rel_type, count(r) AS c
    """).data()
    print(f"   * Total judicial relationships inherited on SUBSECTION/CLAUSE/EXPLANATION nodes: {len(judicial_on_children)}")
    if len(judicial_on_children) == 0:
        print("   * SUCCESS: 0 judicial relationships were inherited to child hierarchy nodes!")

driver.close()
