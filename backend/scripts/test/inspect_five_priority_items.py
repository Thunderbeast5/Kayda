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
    print("1. ACTUAL NEO4J NODE LABELS AND RELATIONSHIP TYPES IN USE")
    print("=" * 80)
    
    labels = session.run("CALL db.labels() YIELD label RETURN collect(label) AS labels").single()["labels"]
    rel_types = session.run("CALL db.relationshipTypes() YIELD relationshipType RETURN collect(relationshipType) AS rels").single()["rels"]
    
    print(f"Node Labels in DB       : {labels}")
    print(f"Relationship Types in DB: {rel_types}")
    
    print("\n" + "=" * 80)
    print("2. RAW LAWSECTION RECORDS FOR BNS 84 AND BNS 85")
    print("=" * 80)
    
    rows = session.run("""
        MATCH (n:LawSection)
        WHERE n.act = 'BNS' AND n.section IN ['84', '85', '80', '74', '355']
        RETURN n.act AS act, n.section AS section, n.title AS title, n.chapter AS chapter, n.description AS description
        ORDER BY n.section
    """).data()
    
    for r in rows:
        desc_preview = (r.get("description") or "")[:150].replace("\n", " ")
        print(f"  {r['act']} {r['section']} -> Title: '{r['title']}' | Chapter: '{r.get('chapter')}'")
        print(f"      Description Preview: {desc_preview}...")

driver.close()
