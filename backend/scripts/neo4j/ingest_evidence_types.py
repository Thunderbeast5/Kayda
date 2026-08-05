import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv
from neo4j import GraphDatabase

# Set up paths and sys.path
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR.parent.parent / ".env"
load_dotenv(ENV_PATH)

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

def ingest_evidence():
    if not all([NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD]):
        print("[ingest_evidence] Error: Missing Neo4j credentials in environment.")
        sys.exit(1)
        
    data_path = BASE_DIR.parent.parent.parent / "data" / "new" / "evidence_types.json"
    if not data_path.exists():
        print(f"[ingest_evidence] Error: File not found at {data_path}")
        sys.exit(1)
        
    with open(data_path, "r", encoding="utf-8") as f:
        evidence_data = json.load(f)
        
    print(f"[ingest_evidence] Parsed {len(evidence_data)} evidence types.")
    
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    with driver.session(database=NEO4J_DATABASE) as session:
        # Create uniqueness constraints
        print("[ingest_evidence] Ensuring constraints...")
        try:
            session.run("CREATE CONSTRAINT lawsection_unique IF NOT EXISTS FOR (n:LawSection) REQUIRE n.section IS UNIQUE")
        except Exception as e:
            print(f"  [Constraint Info] Skipping simple LawSection(section) constraint: {e}")
        try:
            session.run("CREATE CONSTRAINT evidence_type_unique IF NOT EXISTS FOR (n:EvidenceType) REQUIRE n.name IS UNIQUE")
        except Exception as e:
            print(f"  [Constraint Info] Skipping EvidenceType(name) constraint: {e}")
        
        # Ingest nodes and relationships
        print("[ingest_evidence] Ingesting EvidenceTypes...")
        for e in evidence_data:
            # Create/Merge EvidenceType node
            session.run("""
                MERGE (et:EvidenceType {name: $name})
            """, name=e["name"])
            
            # Link LawSection -[:SUPPORTED_BY]-> EvidenceType
            for link in e["linked_sections"]:
                act = link["act"]
                section = link["section"]
                
                res = session.run("""
                    MATCH (l:LawSection {act: $act, section: $section})
                    MATCH (et:EvidenceType {name: $name})
                    MERGE (l)-[r:SUPPORTED_BY]->(et)
                    RETURN count(r) AS count
                """, act=act, section=section, name=e["name"])
                
                if res.single()["count"] > 0:
                    print(f"  Linked {act} {section} -[:SUPPORTED_BY]-> EvidenceType: {e['name']}")
                else:
                    print(f"  ⚠️ Warning: Could not find node {act} {section} to link from evidence {e['name']}")
                    
        # Print summary
        count = session.run("MATCH (n:EvidenceType) RETURN count(n) AS c").single()["c"]
        rel_count = session.run("MATCH ()-[r:SUPPORTED_BY]->() RETURN count(r) AS c").single()["c"]
        print(f"[ingest_evidence] Success! Total EvidenceType nodes: {count}, SUPPORTED_BY: {rel_count}")

    driver.close()

if __name__ == "__main__":
    ingest_evidence()
