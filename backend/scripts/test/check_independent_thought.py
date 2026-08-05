import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from neo4j import GraphDatabase

BASE_DIR = Path(__file__).resolve().parents[2]
ENV_PATH = BASE_DIR / ".env"
load_dotenv(ENV_PATH)

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

with driver.session(database=NEO4J_DATABASE) as session:
    rows = session.run("""
        MATCH (c)-[r]->(n:LawSection)
        WHERE c.title CONTAINS "INDEPENDENT THOUGHT" OR c.case_name CONTAINS "INDEPENDENT THOUGHT"
        RETURN type(r) AS rel, n.act AS act, n.section AS section, c.title AS case_title
    """).data()
    print("Direct outgoing edges from INDEPENDENT THOUGHT to LawSection:")
    for r in rows:
        print(f"  ({r['case_title']}) -[:{r['rel']}]-> ({r['act']} {r['section']})")

    rows2 = session.run("""
        MATCH (n:LawSection)-[r]->(c)
        WHERE c.title CONTAINS "INDEPENDENT THOUGHT" OR c.case_name CONTAINS "INDEPENDENT THOUGHT"
        RETURN type(r) AS rel, n.act AS act, n.section AS section, c.title AS case_title
    """).data()
    print("Direct incoming edges to INDEPENDENT THOUGHT from LawSection:")
    for r in rows2:
        print(f"  ({r['act']} {r['section']}) -[:{r['rel']}]-> ({r['case_title']})")

driver.close()
