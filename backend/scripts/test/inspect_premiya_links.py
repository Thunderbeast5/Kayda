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

with driver.session(database=NEO4J_DATABASE) as session:
    print("=" * 80)
    print("INSPECTING PREMIYA CASE RELATIONSHIPS IN NEO4J")
    print("=" * 80)
    
    rows = session.run("""
        MATCH (cs:SupremeCourtCase)
        WHERE cs.case_name CONTAINS "Premiya" OR cs.case_name CONTAINS "PREMIYA"
        MATCH (cs)-[r]-(n)
        RETURN cs.case_name AS case_name, type(r) AS rel, labels(n) AS target_labels, n.act AS act, n.section AS section, n.title AS title, n.name AS name
    """).data()
    
    for r in rows:
        target_str = f"{r['act']} {r['section']} ({r['title']})" if r['act'] else r['name']
        print(f"  ({r['case_name']}) -[:{r['rel']}]-> {r['target_labels']} : {target_str}")

driver.close()
