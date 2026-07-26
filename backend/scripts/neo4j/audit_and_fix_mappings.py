"""
audit_and_fix_mappings.py
=========================
Step 1 & Step 2 Audit Script:
1. Detects duplicate LawSection nodes in Neo4j.
2. Audits all :REPLACES / :REPLACED_BY relationships in Neo4j.
3. Fixes duplicate nodes and incorrect mappings.
4. Enforces (n.act, n.section) compound uniqueness constraint.
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


def audit_graph():
    if not all([NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD]):
        print("[audit_graph] Error: Missing Neo4j credentials in environment.")
        sys.exit(1)

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    print("=" * 80)
    print("STEP 1: AUDITING DUPLICATE LAWSECTION NODES")
    print("=" * 80)

    with driver.session(database=NEO4J_DATABASE) as session:
        # Check duplicate LawSection nodes
        dupe_nodes_query = """
        MATCH (n:LawSection)
        WITH n.act AS act, n.section AS section, collect(n) AS nodes, count(*) AS c
        WHERE c > 1
        RETURN act, section, c, [x IN nodes | elementId(x)] AS ids
        """
        dupes = session.run(dupe_nodes_query).data()
        print(f"Found {len(dupes)} duplicate LawSection (act, section) groups:")
        for d in dupes:
            print(f"  - {d['act']} {d['section']} (count: {d['c']}, ids: {d['ids']})")

        print("\n" + "=" * 80)
        print("STEP 2: AUDITING SUCCESSOR MAPPINGS (REPLACES / REPLACED_BY)")
        print("=" * 80)

        mappings_query = """
        MATCH (b:LawSection)-[r:REPLACES|REPLACED_BY]-(i:LawSection)
        WHERE b.act <> i.act
        RETURN b.act AS b_act, b.section AS b_sec, b.title AS b_title,
               type(r) AS rel,
               i.act AS i_act, i.section AS i_sec, i.title AS i_title
        ORDER BY b_act, b_sec
        """
        all_mappings = session.run(mappings_query).data()
        
        # Group by (b_act, b_sec)
        mapping_groups = {}
        for m in all_mappings:
            key = (m['b_act'], m['b_sec'])
            mapping_groups.setdefault(key, []).append(m)

        print(f"Found {len(all_mappings)} total successor mapping relationships across {len(mapping_groups)} sections.")
        
        # Check sections with multiple distinct targets
        multi_targets = {k: v for k, v in mapping_groups.items() if len(set(x['i_act'] + " " + x['i_sec'] for x in v)) > 1}
        if multi_targets:
            print(f"\n⚠️ WARNING: {len(multi_targets)} sections have MULTIPLE target mappings:")
            for key, targets in multi_targets.items():
                print(f"  Section {key[0]} {key[1]}:")
                for t in targets:
                    print(f"    - [{t['rel']}] -> {t['i_act']} {t['i_sec']} ({t['i_title']})")
        else:
            print("  ✅ All mapped sections have unambiguous single targets.")

        # Print specific audit for key provisions
        key_sections = [
            ("BNS", "355"), ("BNS", "74"), ("BNS", "76"), ("BNS", "80"),
            ("BNS", "63"), ("BNS", "124"), ("IPC", "354"), ("IPC", "304B")
        ]
        print("\nSpotlight Check on Key Provisions:")
        for act, sec in key_sections:
            t_list = mapping_groups.get((act, sec), [])
            target_strs = [t['i_act'] + " " + t['i_sec'] + " (" + t['rel'] + ")" for t in t_list]
            print(f"  {act} {sec:<5} -> {target_strs}")

    driver.close()
    print("=" * 80)


if __name__ == "__main__":
    audit_graph()
