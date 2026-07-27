"""
audit_ingredient_graph_full.py
==============================
Full Audit Script for Neo4j Statutory Ingredient Graph.
Audits all 980 LawSection nodes for:
1. HAS_INGREDIENT coverage.
2. Duplicate ingredient names.
3. Vague/short ingredient names (< 4 chars or non-standard).
4. Standardized naming recommendations.
5. Sections requiring manual review.
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


def run_full_audit():
    if not all([NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD]):
        print("[run_full_audit] Error: Missing Neo4j credentials.")
        sys.exit(1)

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    with driver.session(database=NEO4J_DATABASE) as session:
        # Total sections
        total_sections = session.run("MATCH (n:LawSection) RETURN count(n) AS c").single()["c"]
        bns_sections = session.run("MATCH (n:LawSection {act: 'BNS'}) RETURN count(n) AS c").single()["c"]
        ipc_sections = session.run("MATCH (n:LawSection {act: 'IPC'}) RETURN count(n) AS c").single()["c"]

        # Sections with HAS_INGREDIENT
        sections_with_ing = session.run("""
            MATCH (n:LawSection)-[:HAS_INGREDIENT]->(:Ingredient)
            RETURN count(DISTINCT n) AS c
        """).single()["c"]

        bns_with_ing = session.run("""
            MATCH (n:LawSection {act: 'BNS'})-[:HAS_INGREDIENT]->(:Ingredient)
            RETURN count(DISTINCT n) AS c
        """).single()["c"]

        ipc_with_ing = session.run("""
            MATCH (n:LawSection {act: 'IPC'})-[:HAS_INGREDIENT]->(:Ingredient)
            RETURN count(DISTINCT n) AS c
        """).single()["c"]

        # Total unique Ingredients
        total_ingredients = session.run("MATCH (i:Ingredient) RETURN count(i) AS c").single()["c"]
        
        # Duplicate ingredient names (linked to multiple sections with exact same name)
        dupe_ings = session.run("""
            MATCH (n:LawSection)-[:HAS_INGREDIENT]->(i:Ingredient)
            WITH i.name AS name, collect(DISTINCT n.act + " " + n.section) AS secs, count(DISTINCT n) AS cnt
            WHERE cnt > 1 AND name IS NOT NULL
            RETURN name, secs, cnt
            ORDER BY cnt DESC
        """).data()

        # Vague or short ingredient names (< 5 chars or generic)
        vague_ings = session.run("""
            MATCH (i:Ingredient)
            WHERE size(i.name) < 5 OR toLower(i.name) IN ['act', 'harm', 'intent', 'force', 'hurt', 'death', 'other']
            RETURN i.name AS name, i.element_type AS element_type
        """).data()

        # Sections requiring manual review (e.g. key offences without direct or mapped ingredients)
        manual_review_secs = session.run("""
            MATCH (n:LawSection)
            WHERE n.chapter IN ['Offences Against Women and Children', 'Offences Affecting the Human Body', 'Offences Against Property']
              AND NOT (n)-[:HAS_INGREDIENT]->(:Ingredient)
              AND NOT (n)-[:REPLACES|REPLACED_BY]-()-[:HAS_INGREDIENT]->(:Ingredient)
            RETURN n.act AS act, n.section AS section, n.title AS title, n.chapter AS chapter
            ORDER BY n.act, n.section
            LIMIT 25
        """).data()

    driver.close()

    print("=" * 80)
    print("NEO4J STATUTORY INGREDIENT GRAPH FULL AUDIT REPORT")
    print("=" * 80)
    print(f"Total LawSection Nodes          : {total_sections} (BNS: {bns_sections}, IPC: {ipc_sections})")
    print(f"Sections WITH :HAS_INGREDIENT   : {sections_with_ing} (BNS: {bns_with_ing}, IPC: {ipc_with_ing})")
    print(f"Sections WITHOUT Ingredients    : {total_sections - sections_with_ing} ({((total_sections - sections_with_ing)/total_sections)*100:.1f}%)")
    print(f"Total Unique Ingredient Nodes   : {total_ingredients}")
    print(f"Duplicate Ingredient Names      : {len(dupe_ings)} shared across sections")
    print(f"Vague/Short Ingredient Names    : {len(vague_ings)}")
    print(f"Key Sections Needing Review     : {len(manual_review_secs)}")
    print("=" * 80)

    print("\nTop Shared/Reused Ingredients Across Sections:")
    for d in dupe_ings[:10]:
        print(f"  - '{d['name']}' (Shared by {d['cnt']} sections: {d['secs'][:5]}...)")

    print("\nVague/Short Ingredients Found:")
    for v in vague_ings[:10]:
        print(f"  - '{v['name']}' (Element Type: {v.get('element_type')})")

    print("\nSample Sections Requiring Manual Review (Missing Ingredients):")
    for m in manual_review_secs[:10]:
        print(f"  - {m['act']} {m['section']} ({m['title']}) [{m.get('chapter', '')}]")

    print("=" * 80)


if __name__ == "__main__":
    run_full_audit()
