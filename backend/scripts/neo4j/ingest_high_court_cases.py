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
from parse_cases import parse_cases_data

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

def ingest_hc_cases():
    if not all([NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD]):
        print("[ingest_hc_cases] Error: Missing Neo4j credentials in environment.")
        sys.exit(1)
        
    data_path = BASE_DIR.parent.parent.parent / "data" / "new" / "court_cases.json"
    _, hc_cases = parse_cases_data(data_path)
    
    if not hc_cases:
        print("[ingest_hc_cases] Error: No High Court cases parsed.")
        sys.exit(1)
        
    print(f"[ingest_hc_cases] Parsed {len(hc_cases)} High Court cases.")
    
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    with driver.session(database=NEO4J_DATABASE) as session:
        # Create uniqueness constraints
        print("[ingest_hc_cases] Ensuring constraints...")
        try:
            session.run("CREATE CONSTRAINT lawsection_unique IF NOT EXISTS FOR (n:LawSection) REQUIRE n.section IS UNIQUE")
        except Exception as e:
            print(f"  [Constraint Info] Skipping simple LawSection(section) constraint: {e}")
        try:
            session.run("CREATE CONSTRAINT hc_case_unique IF NOT EXISTS FOR (n:HighCourtCase) REQUIRE n.citation IS UNIQUE")
        except Exception as e:
            print(f"  [Constraint Info] Skipping HighCourtCase(citation) constraint: {e}")
        
        # Ingest nodes and relationships
        print("[ingest_hc_cases] Ingesting HighCourtCases...")
        for c in hc_cases:
            # Create/Merge HighCourtCase node
            session.run("""
                MERGE (hc:HighCourtCase {citation: $citation})
                SET hc.case_name = $case_name,
                    hc.year = $year,
                    hc.summary = $summary,
                    hc.court = $court,
                    hc.source = $source
            """, citation=c["citation"], case_name=c["case_name"], year=c["year"],
               summary=c["summary"], court=c["court"], source=c["source"])
            
            # Link LawSection -[:FOLLOWED_BY]-> HighCourtCase
            for link in c["linked_sections"]:
                act = link["act"]
                section = link["section"]
                
                res = session.run("""
                    MATCH (l:LawSection {act: $act, section: $section})
                    MATCH (hc:HighCourtCase {citation: $citation})
                    MERGE (l)-[r:FOLLOWED_BY]->(hc)
                    RETURN count(r) AS count
                """, act=act, section=section, citation=c["citation"])
                
                if res.single()["count"] > 0:
                    print(f"  Linked {act} {section} -[:FOLLOWED_BY]-> {c['case_name']}")
                else:
                    print(f"  ⚠️ Warning: Could not find node {act} {section} to link to {c['case_name']}")
            
            # Link HighCourtCase -[:FOLLOWS]-> SupremeCourtCase
            follows_name = c.get("follows_sc_case", "")
            if follows_name:
                res = session.run("""
                    MATCH (hc:HighCourtCase {citation: $citation})
                    MATCH (sc:SupremeCourtCase {case_name: $follows_name})
                    MERGE (hc)-[r:FOLLOWS]->(sc)
                    RETURN count(r) AS count
                """, citation=c["citation"], follows_name=follows_name)
                
                if res.single()["count"] > 0:
                    print(f"  Linked Case {c['case_name']} -[:FOLLOWS]-> SupremeCourtCase: {follows_name}")
                else:
                    print(f"  ⚠️ Warning: Could not find SupremeCourtCase with name '{follows_name}' to link from case {c['case_name']}")
                    
        # Print summary
        count = session.run("MATCH (n:HighCourtCase) RETURN count(n) AS c").single()["c"]
        rel_count = session.run("MATCH ()-[r:FOLLOWED_BY]->() RETURN count(r) AS c").single()["c"]
        follows_count = session.run("MATCH ()-[r:FOLLOWS]->() RETURN count(r) AS c").single()["c"]
        print(f"[ingest_hc_cases] Success! Total HighCourtCase nodes: {count}, FOLLOWED_BY: {rel_count}, FOLLOWS: {follows_count}")

    driver.close()

if __name__ == "__main__":
    ingest_hc_cases()
