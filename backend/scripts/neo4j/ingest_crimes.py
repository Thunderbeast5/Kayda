import os
import sys
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

def ingest_crimes_relationships():
    if not all([NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD]):
        print("[ingest_crimes] Error: Missing Neo4j credentials in environment.")
        sys.exit(1)
        
    print("[ingest_crimes] Establishing Crime and LawSection relations...")
    
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    with driver.session(database=NEO4J_DATABASE) as session:
        # Create constraint for Crime name if not exists
        print("[ingest_crimes] Ensuring constraints...")
        try:
            session.run("CREATE CONSTRAINT crime_unique IF NOT EXISTS FOR (n:Crime) REQUIRE n.name IS UNIQUE")
        except Exception as e:
            print(f"  [Constraint Info] Skipping Crime(name) constraint: {e}")
        
        # 1. Create LawSection -[:APPLIES_TO]-> Crime for all existing (Crime)-[:DEFINED_BY]->(LawSection)
        print("[ingest_crimes] Creating LawSection -[:APPLIES_TO]-> Crime relationships...")
        res = session.run("""
            MATCH (c:Crime)-[:DEFINED_BY]->(l:LawSection)
            MERGE (l)-[r:APPLIES_TO]->(c)
            RETURN count(r) AS count
        """)
        applies_to_count = res.single()["count"]
        print(f"  Created {applies_to_count} APPLIES_TO relationships.")
        
        # 2. Create Crime -[:RELATED_TO]-> Crime for co-charged or related sections
        print("[ingest_crimes] Creating Crime -[:RELATED_TO]-> Crime relationships...")
        res = session.run("""
            MATCH (c1:Crime)-[:DEFINED_BY]->(l1:LawSection)-[:CO_CHARGED_WITH]-(l2:LawSection)<-[:DEFINED_BY]-(c2:Crime)
            WHERE id(c1) < id(c2)
            MERGE (c1)-[r:RELATED_TO]->(c2)
            RETURN count(r) AS count
        """)
        related_to_count = res.single()["count"]
        print(f"  Created {related_to_count} RELATED_TO relationships.")
        
        print(f"[ingest_crimes] Success! APPLIES_TO: {applies_to_count}, RELATED_TO: {related_to_count}")

    driver.close()

if __name__ == "__main__":
    ingest_crimes_relationships()
