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

def ingest_punishments():
    if not all([NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD]):
        print("[ingest_punishments] Error: Missing Neo4j credentials in environment.")
        sys.exit(1)
        
    data_path = BASE_DIR.parent.parent.parent / "data" / "new" / "punishments.json"
    if not data_path.exists():
        print(f"[ingest_punishments] Error: File not found at {data_path}")
        sys.exit(1)
        
    with open(data_path, "r", encoding="utf-8") as f:
        punishment_data = json.load(f)
        
    print(f"[ingest_punishments] Parsed {len(punishment_data)} punishments.")
    
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    with driver.session(database=NEO4J_DATABASE) as session:
        # Create uniqueness constraints
        print("[ingest_punishments] Ensuring constraints...")
        try:
            session.run("CREATE CONSTRAINT lawsection_unique IF NOT EXISTS FOR (n:LawSection) REQUIRE n.section IS UNIQUE")
        except Exception as e:
            print(f"  [Constraint Info] Skipping simple LawSection(section) constraint: {e}")
        
        # Ingest nodes and relationships
        print("[ingest_punishments] Ingesting Punishments...")
        for p in punishment_data:
            section = p["section"]
            act = p["act"]
            
            # Match LawSection first
            res = session.run("""
                MATCH (l:LawSection {act: $act, section: $section})
                RETURN id(l) AS id
            """, act=act, section=section)
            
            records = list(res)
            if not records:
                print(f"  ⚠️ Warning: Could not find node {act} {section} to link punishment")
                continue
                
            # Create a Punishment node and link it via HAS_PUNISHMENT
            session.run("""
                MATCH (l:LawSection {act: $act, section: $section})
                CREATE (pun:Punishment {
                    minimum: $minimum,
                    maximum: $maximum,
                    fine: $fine,
                    life_imprisonment: $life_imprisonment,
                    death_penalty: $death_penalty
                })
                MERGE (l)-[r:HAS_PUNISHMENT]->(pun)
            """, act=act, section=section,
               minimum=p.get("minimum", "None"),
               maximum=p.get("maximum", "None"),
               fine=p.get("fine", "Yes"),
               life_imprisonment=bool(p.get("life_imprisonment", False)),
               death_penalty=bool(p.get("death_penalty", False)))
            
            print(f"  Linked Punishment to {act} {section}")
            
        # Print summary
        count = session.run("MATCH (n:Punishment) RETURN count(n) AS c").single()["c"]
        rel_count = session.run("MATCH ()-[r:HAS_PUNISHMENT]->() RETURN count(r) AS c").single()["c"]
        print(f"[ingest_punishments] Success! Total Punishment nodes: {count}, HAS_PUNISHMENT relations: {rel_count}")

    driver.close()

if __name__ == "__main__":
    ingest_punishments()
