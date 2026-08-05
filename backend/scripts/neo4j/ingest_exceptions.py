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

def ingest_exceptions():
    if not all([NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD]):
        print("[ingest_exceptions] Error: Missing Neo4j credentials in environment.")
        sys.exit(1)
        
    data_path = BASE_DIR.parent.parent.parent / "data" / "new" / "exceptions.json"
    if not data_path.exists():
        print(f"[ingest_exceptions] Error: File not found at {data_path}")
        sys.exit(1)
        
    with open(data_path, "r", encoding="utf-8") as f:
        exceptions_data = json.load(f)
        
    print(f"[ingest_exceptions] Parsed {len(exceptions_data)} exceptions.")
    
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    with driver.session(database=NEO4J_DATABASE) as session:
        # Ingest nodes and relationships
        print("[ingest_exceptions] Ingesting Exceptions...")
        for e in exceptions_data:
            section = e["section"]
            act = e["act"]
            description = e["description"]
            
            res = session.run("""
                MATCH (l:LawSection {act: $act, section: $section})
                RETURN id(l) AS id
            """, act=act, section=section)
            
            records = list(res)
            if not records:
                print(f"  ⚠️ Warning: Could not find node {act} {section} to link exception")
                continue
                
            # Create an Exception node and link via HAS_EXCEPTION
            session.run("""
                MATCH (l:LawSection {act: $act, section: $section})
                CREATE (ex:Exception {description: $description})
                MERGE (l)-[r:HAS_EXCEPTION]->(ex)
            """, act=act, section=section, description=description)
            
            print(f"  Linked Exception to {act} {section}")
            
        # Print summary
        count = session.run("MATCH (n:Exception) RETURN count(n) AS c").single()["c"]
        rel_count = session.run("MATCH ()-[r:HAS_EXCEPTION]->() RETURN count(r) AS c").single()["c"]
        print(f"[ingest_exceptions] Success! Total Exception nodes: {count}, HAS_EXCEPTION relations: {rel_count}")

    driver.close()

if __name__ == "__main__":
    ingest_exceptions()
