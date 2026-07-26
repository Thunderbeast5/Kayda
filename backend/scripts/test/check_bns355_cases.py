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
        MATCH (cs)-[:APPLIES_SECTION|INTERPRETS]->(n:LawSection {act: "BNS", section: "355"})
        RETURN cs.title AS title
    """).data()
    print("Direct cases for BNS 355:")
    for r in rows:
        print(" ", r["title"])

driver.close()
