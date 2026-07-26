"""
fix_graph_mappings_and_constraints.py
======================================
1. Creates compound uniqueness constraint (n.act, n.section) on (:LawSection).
2. Cleans up duplicate / extraneous relationships so each section has exactly one primary official successor link.
3. Ensures official primary successor mappings:
   - BNS 355 -> IPC 354
   - BNS 74  -> IPC 354
   - BNS 76  -> IPC 354B
   - BNS 80  -> IPC 304B
   - BNS 63  -> IPC 375
   - BNS 124 -> IPC 326A
   - IPC 354 -> BNS 355
   - IPC 304B -> BNS 80
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from neo4j import GraphDatabase

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parents[2]
ENV_PATH = BASE_DIR / ".env"
load_dotenv(ENV_PATH)

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")


def fix_graph():
    if not all([NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD]):
        print("[fix_graph] Error: Missing Neo4j credentials in environment.")
        sys.exit(1)

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    print("=" * 80)
    print("STEP 1: MERGING DUPLICATE LAWSECTION NODES")
    print("=" * 80)

    with driver.session(database=NEO4J_DATABASE) as session:
        # Step 1: Merge duplicate LawSection nodes if any exist
        apoc_merge = """
        MATCH (n:LawSection)
        WITH n.act AS act, n.section AS section, collect(n) AS nodes, count(*) AS c
        WHERE c > 1 AND act IS NOT NULL AND section IS NOT NULL
        CALL apoc.refactor.mergeNodes(nodes, {properties: "combine", mergeRels: true})
        YIELD node
        RETURN count(node) AS count
        """
        cypher_fallback = """
        MATCH (n:LawSection)
        WITH n.act AS act, n.section AS section, collect(n) AS nodes, count(*) AS c
        WHERE c > 1 AND act IS NOT NULL AND section IS NOT NULL
        WITH nodes[0] AS keep, nodes[1..] AS dupes
        UNWIND dupes AS dupe
        MATCH (dupe)-[r]->(target)
        MERGE (keep)-[r2:TYPE(r)]->(target)
        WITH keep, dupe, r
        MATCH (source)-[r3]->(dupe)
        MERGE (source)-[r4:TYPE(r3)]->(keep)
        WITH dupe
        DETACH DELETE dupe
        RETURN count(dupe) AS count
        """

        try:
            res = session.run(apoc_merge).single()
            cnt = res["count"] if res else 0
            print(f"  [OK] APOC merged {cnt} duplicate LawSection clusters.")
        except Exception as e:
            print(f"  [WARN] APOC merge failed ({e}), running Cypher fallback...")
            try:
                res = session.run(cypher_fallback).single()
                cnt = res["count"] if res else 0
                print(f"  [OK] Cypher fallback merged {cnt} duplicate LawSection nodes.")
            except Exception as e2:
                print(f"  [ERROR] Fallback merge failed: {e2}")

        print("\n" + "=" * 80)
        print("STEP 6: ENFORCING COMPOUND UNIQUENESS CONSTRAINT ON LAWSECTION")
        print("=" * 80)

        constraint_query = """
        CREATE CONSTRAINT law_section_unique IF NOT EXISTS
        FOR (n:LawSection)
        REQUIRE (n.act, n.section) IS UNIQUE
        """
        try:
            session.run(constraint_query)
            print("  [OK] Constraint 'law_section_unique' for (n.act, n.section) created/verified.")
        except Exception as e:
            print(f"  [WARN] Constraint info: {e}")

        print("\n" + "=" * 80)
        print("STEP 2: FIXING INCORRECT / AMBIGUOUS SUCCESSOR MAPPINGS IN NEO4J")
        print("=" * 80)

        # 1. Remove incorrect BNS 355 -> IPC 510 mapping
        session.run("""
            MATCH (b:LawSection {act: 'BNS', section: '355'})-[r:REPLACES|REPLACED_BY]-(i:LawSection {act: 'IPC', section: '510'})
            DELETE r
        """)
        print("  [OK] Removed erroneous (BNS 355) <-> (IPC 510) relationship.")

        # 2. Remove secondary BNS 124 -> IPC 326B mapping
        session.run("""
            MATCH (b:LawSection {act: 'BNS', section: '124'})-[r:REPLACES|REPLACED_BY]-(i:LawSection {act: 'IPC', section: '326B'})
            DELETE r
        """)
        print("  [OK] Removed secondary (BNS 124) <-> (IPC 326B) relationship.")

        # 3. Clean all existing successor edges for key sections to rebuild exact 1-to-1 mappings
        key_secs = [
            ("BNS", "355"), ("BNS", "74"), ("BNS", "76"), ("BNS", "80"),
            ("BNS", "63"), ("BNS", "124"), ("IPC", "354"), ("IPC", "304B")
        ]
        for act, sec in key_secs:
            session.run("""
                MATCH (b:LawSection {act: $act, section: $sec})-[r:REPLACES|REPLACED_BY]-(i:LawSection)
                WHERE i.act <> $act
                DELETE r
            """, act=act, sec=sec)

        # 4. Re-create Official Single Target Mappings
        official_mappings = [
            ("BNS", "355", "IPC", "354"),
            ("BNS", "74",  "IPC", "354"),
            ("BNS", "76",  "IPC", "354B"),
            ("BNS", "80",  "IPC", "304B"),
            ("BNS", "63",  "IPC", "375"),
            ("BNS", "124", "IPC", "326A"),
            ("IPC", "354", "BNS", "355"),
            ("IPC", "304B", "BNS", "80"),
        ]

        for b_act, b_sec, i_act, i_sec in official_mappings:
            session.run("""
                MERGE (b:LawSection {act: $b_act, section: $b_sec})
                MERGE (i:LawSection {act: $i_act, section: $i_sec})
                MERGE (b)-[:REPLACES]->(i)
                MERGE (b)-[:REPLACED_BY]->(i)
            """, b_act=b_act, b_sec=b_sec, i_act=i_act, i_sec=i_sec)
            print(f"  [OK] Rebuilt exact official mapping: ({b_act} {b_sec}) -> ({i_act} {i_sec})")

    driver.close()
    print("=" * 80)


if __name__ == "__main__":
    fix_graph()
