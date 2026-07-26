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

def ingest_illustrations():
    if not all([NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD]):
        print("[ingest_illustrations] Error: Missing Neo4j credentials in environment.")
        sys.exit(1)
        
    data_path = BASE_DIR.parent.parent.parent / "data" / "new" / "illustrations.json"
    if not data_path.exists():
        print(f"[ingest_illustrations] Error: File not found at {data_path}")
        sys.exit(1)
        
    with open(data_path, "r", encoding="utf-8") as f:
        illustrations_data = json.load(f)
        
    print(f"[ingest_illustrations] Parsed {len(illustrations_data)} illustrations.")
    
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    with driver.session(database=NEO4J_DATABASE) as session:
        # Ingest nodes and relationships
        print("[ingest_illustrations] Ingesting Illustrations...")
        for i in illustrations_data:
            section = i["section"]
            act = i["act"]
            description = i["description"]
            
            res = session.run("""
                MATCH (l:LawSection {act: $act, section: $section})
                RETURN id(l) AS id
            """, act=act, section=section)
            
            records = list(res)
            if not records:
                print(f"  ⚠️ Warning: Could not find node {act} {section} to link illustration")
                continue
                
            # Create an Illustration node and link via HAS_ILLUSTRATION
            session.run("""
                MATCH (l:LawSection {act: $act, section: $section})
                CREATE (ex:Illustration {description: $description})
                MERGE (l)-[r:HAS_ILLUSTRATION]->(ex)
            """, act=act, section=section, description=description)
            
            print(f"  Linked Illustration to {act} {section}")
            
        # Print summary
        count = session.run("MATCH (n:Illustration) RETURN count(n) AS c").single()["c"]
        rel_count = session.run("MATCH ()-[r:HAS_ILLUSTRATION]->() RETURN count(r) AS c").single()["c"]
        print(f"[ingest_illustrations] Success! Total Illustration nodes: {count}, HAS_ILLUSTRATION relations: {rel_count}")

    driver.close()

if __name__ == "__main__":
    ingest_illustrations()
