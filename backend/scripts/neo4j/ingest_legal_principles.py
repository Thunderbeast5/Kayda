import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from neo4j import GraphDatabase

# Set up paths and sys.path
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR.parent.parent / ".env"
load_dotenv(ENV_PATH)

sys.path.append(str(BASE_DIR))

# Import the parser
from parse_principles import parse_principles_data

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

def ingest_principles():
    if not all([NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD]):
        print("[ingest_principles] Error: Missing Neo4j credentials in environment.")
        sys.exit(1)
        
    data_path = BASE_DIR.parent.parent.parent / "data" / "new" / "legal_principles.json"
    principles = parse_principles_data(data_path)
    
    if not principles:
        print("[ingest_principles] Error: No principles parsed.")
        sys.exit(1)
        
    print(f"[ingest_principles] Parsed {len(principles)} principles.")
    
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    with driver.session(database=NEO4J_DATABASE) as session:
        # Create uniqueness constraints
        print("[ingest_principles] Ensuring constraints...")
        try:
            session.run("CREATE CONSTRAINT lawsection_unique IF NOT EXISTS FOR (n:LawSection) REQUIRE n.section IS UNIQUE")
        except Exception as e:
            print(f"  [Constraint Info] Skipping simple LawSection(section) constraint: {e}")
        try:
            session.run("CREATE CONSTRAINT legal_principle_unique IF NOT EXISTS FOR (n:LegalPrinciple) REQUIRE n.name IS UNIQUE")
        except Exception as e:
            print(f"  [Constraint Info] Skipping LegalPrinciple(name) constraint: {e}")
        
        # Ingest nodes and relationships
        print("[ingest_principles] Ingesting LegalPrinciples...")
        for p in principles:
            # Create/Merge LegalPrinciple node
            session.run("""
                MERGE (lp:LegalPrinciple {name: $name})
                SET lp.description = $description,
                    lp.source = $source
            """, name=p["name"], description=p["description"], source=p["source"])
            
            # Link LegalPrinciple -[:APPLIES_TO]-> LawSection
            for link in p["linked_sections"]:
                act = link["act"]
                section = link["section"]
                
                res = session.run("""
                    MATCH (l:LawSection {act: $act, section: $section})
                    MATCH (lp:LegalPrinciple {name: $name})
                    MERGE (lp)-[r:APPLIES_TO]->(l)
                    RETURN count(r) AS count
                """, act=act, section=section, name=p["name"])
                
                if res.single()["count"] > 0:
                    print(f"  Linked LegalPrinciple {p['name']} -[:APPLIES_TO]-> {act} {section}")
                else:
                    print(f"  ⚠️ Warning: Could not find node {act} {section} to link from {p['name']}")
                    
        # Print summary
        count = session.run("MATCH (n:LegalPrinciple) RETURN count(n) AS c").single()["c"]
        rel_count = session.run("MATCH ()-[r:APPLIES_TO]->() RETURN count(r) AS c").single()["c"]
        print(f"[ingest_principles] Success! Total LegalPrinciple nodes: {count}, APPLIES_TO: {rel_count}")

    driver.close()

if __name__ == "__main__":
    ingest_principles()
