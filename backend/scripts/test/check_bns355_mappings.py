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
        MATCH (n:LawSection {act: 'BNS', section: '355'})-[r:REPLACED_BY|REPLACES]-(other:LawSection)
        RETURN n.act AS act, n.section AS section, type(r) AS rel, other.act AS other_act, other.section AS other_section, other.title AS other_title
    """).data()
    print("Mappings connected to BNS 355:")
    for r in rows:
        print(f"  (BNS 355) -[:{r['rel']}]- ({r['other_act']} {r['other_section']}) - {r['other_title']}")

    rows2 = session.run("""
        MATCH (n:LawSection {act: 'BNS', section: '74'})-[r:REPLACED_BY|REPLACES]-(other:LawSection)
        RETURN n.act AS act, n.section AS section, type(r) AS rel, other.act AS other_act, other.section AS other_section, other.title AS other_title
    """).data()
    print("Mappings connected to BNS 74:")
    for r in rows2:
        print(f"  (BNS 74) -[:{r['rel']}]- ({r['other_act']} {r['other_section']}) - {r['other_title']}")

    rows3 = session.run("""
        MATCH (n:LawSection {act: 'IPC', section: '354'})-[r:REPLACED_BY|REPLACES]-(other:LawSection)
        RETURN n.act AS act, n.section AS section, type(r) AS rel, other.act AS other_act, other.section AS other_section, other.title AS other_title
    """).data()
    print("Mappings connected to IPC 354:")
    for r in rows3:
        print(f"  (IPC 354) -[:{r['rel']}]- ({r['other_act']} {r['other_section']}) - {r['other_title']}")

driver.close()
