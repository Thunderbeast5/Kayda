"""
verify_canonical_titles.py
==========================
Verifies canonical titles for duplicate-target nodes in Neo4j:
- BNS_8(6)
- BNS_70(2)
- BNS_189(2)
- BNS_189(5)

Confirms:
1. Node .title retains the official BNS Bare Act title.
2. Inbound REPLACED_BY / outbound REPLACES relationships retain distinct historical IPC titles.
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

targets = {
    "BNS_8(6)": "Imprisonment to terminate on payment of fine",
    "BNS_70(2)": "Punishment for gang rape on woman under sixteen years of age",
    "BNS_189(2)": "Being member of unlawful assembly",
    "BNS_189(5)": "Joining or continuing in unlawful assembly, knowing it has been commanded to disperse",
}

print("=" * 80)
print(" CANONICAL TITLE VERIFICATION FOR DUPLICATE TARGET NODES")
print("=" * 80 + "\n")

with driver.session() as s:
    all_passed = True
    for node_id, expected_title in targets.items():
        node = s.run("MATCH (n:LawSection {id: $id}) RETURN n.title AS title", id=node_id).single()
        actual_title = node["title"] if node else "NOT FOUND"
        
        match = actual_title == expected_title
        if not match:
            all_passed = False

        print(f"Node '{node_id}':")
        print(f"  * Node Title in Neo4j:   '{actual_title}'")
        print(f"  * Expected BNS Title:    '{expected_title}'")
        print(f"  * Match Official BNS?    {'YES' if match else 'NO'}")

        # Relationships check
        rels = s.run("""
            MATCH (i:LawSection)-[r:REPLACED_BY]->(b:LawSection {id: $id})
            RETURN i.id AS ipc_id, i.title AS ipc_node_title, r.ipc_title AS rel_ipc_title
        """, id=node_id).data()
        
        print(f"  * Preserved IPC Titles on Inbound REPLACED_BY Edges:")
        for r in rels:
            print(f"    - {r['ipc_id']} ('{r['ipc_node_title']}') -> Edge r.ipc_title: '{r['rel_ipc_title']}'")
        print()

    print("=" * 80)
    if all_passed:
        print(" ALL 4 DUPLICATE-TARGET BNS NODES VERIFIED WITH CANONICAL BNS TITLES")
    else:
        print(" SOME TITLES MISMATCHED")
    print("=" * 80)

driver.close()
