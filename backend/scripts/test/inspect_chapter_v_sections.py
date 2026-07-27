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

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

sections_to_check = ["63", "74", "80", "85"]

print("=" * 80)
print("INSPECTING RAW NEO4J RECORDS FOR BNS 63, BNS 74, BNS 80, BNS 85")
print("=" * 80)

with driver.session(database=NEO4J_DATABASE) as session:
    for sec_num in sections_to_check:
        sec_rows = session.run("""
            MATCH (n:LawSection {act: 'BNS', section: $sec_num})
            RETURN n.act AS act, n.section AS section, n.title AS title, n.description AS description
        """, sec_num=sec_num).data()

        if not sec_rows:
            print(f"\n--- Section BNS {sec_num}: NOT FOUND ---")
            continue

        sec = sec_rows[0]
        print(f"\n==================================================")
        print(f"Section: {sec['act']} {sec['section']} - '{sec['title']}'")
        print(f"Description: {sec['description']}")
        print(f"--------------------------------------------------")

        # 1. Ingredients (:HAS_INGREDIENT)
        ing_rows = session.run("""
            MATCH (n:LawSection {act: 'BNS', section: $sec_num})-[:HAS_INGREDIENT]->(i:Ingredient)
            OPTIONAL MATCH (i)-[:REQUIRES_EVIDENCE]->(e:EvidenceType)
            RETURN i.name AS name, i.element_type AS element_type, i.description AS description, collect(e.name) AS evidence
        """, sec_num=sec_num).data()

        print(f"  Ingredients (:HAS_INGREDIENT) [{len(ing_rows)}]:")
        for i in ing_rows:
            ev_str = f" -> Evidence: {i['evidence']}" if i['evidence'] and i['evidence'] != [None] else ""
            print(f"    - [{i.get('element_type') or 'INGREDIENT'}] '{i['name']}': {i.get('description')}{ev_str}")

        # 2. Exceptions (:HAS_EXCEPTION)
        ex_rows = session.run("""
            MATCH (n:LawSection {act: 'BNS', section: $sec_num})-[:HAS_EXCEPTION]->(ex)
            RETURN labels(ex) AS labels, properties(ex) AS props
        """, sec_num=sec_num).data()
        print(f"  Exceptions (:HAS_EXCEPTION) [{len(ex_rows)}]:")
        for ex in ex_rows:
            print(f"    - {ex['labels']}: {ex['props']}")

        # 3. Aggravating Factors / Punishments
        agg_rows = session.run("""
            MATCH (n:LawSection {act: 'BNS', section: $sec_num})-[r]->(agg)
            WHERE type(r) IN ['HAS_PUNISHMENT', 'HAS_AGGRAVATING_FACTOR', 'MORE_SPECIFIC_THAN'] OR labels(agg) IN [['AggravatingFactor'], ['Punishment']]
            RETURN type(r) AS rel_type, labels(agg) AS labels, properties(agg) AS props
        """, sec_num=sec_num).data()
        print(f"  Aggravating Factors / Punishments [{len(agg_rows)}]:")
        for agg in agg_rows:
            print(f"    - -[:{agg['rel_type']}]-> {agg['labels']}: {agg['props']}")

        # 4. Victim Rights (:PROTECTS_RIGHT / VictimRight)
        vr_rows = session.run("""
            MATCH (n:LawSection {act: 'BNS', section: $sec_num})-[r]->(vr)
            WHERE labels(vr) CONTAINS 'VictimRight' OR type(r) CONTAINS 'RIGHT'
            RETURN type(r) AS rel_type, labels(vr) AS labels, properties(vr) AS props
        """, sec_num=sec_num).data()
        print(f"  Victim Rights [{len(vr_rows)}]:")
        for vr in vr_rows:
            print(f"    - -[:{vr['rel_type']}]-> {vr['labels']}: {vr['props']}")

driver.close()
print("=" * 80)
