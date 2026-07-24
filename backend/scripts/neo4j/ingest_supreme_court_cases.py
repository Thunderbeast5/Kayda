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

def ingest_sc_cases():
    if not all([NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD]):
        print("[ingest_sc_cases] Error: Missing Neo4j credentials in environment.")
        sys.exit(1)
        
    data_path = BASE_DIR.parent.parent.parent / "data" / "new" / "court_cases.json"
    sc_cases, _ = parse_cases_data(data_path)
    
    if not sc_cases:
        print("[ingest_sc_cases] Error: No Supreme Court cases parsed.")
        sys.exit(1)
        
    print(f"[ingest_sc_cases] Parsed {len(sc_cases)} Supreme Court cases.")
    
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    with driver.session(database=NEO4J_DATABASE) as session:
        # Create uniqueness constraints
        print("[ingest_sc_cases] Ensuring constraints...")
        try:
            session.run("CREATE CONSTRAINT lawsection_unique IF NOT EXISTS FOR (n:LawSection) REQUIRE n.section IS UNIQUE")
        except Exception as e:
            print(f"  [Constraint Info] Skipping simple LawSection(section) constraint: {e}")
        try:
            session.run("CREATE CONSTRAINT sc_case_unique IF NOT EXISTS FOR (n:SupremeCourtCase) REQUIRE n.citation IS UNIQUE")
        except Exception as e:
            print(f"  [Constraint Info] Skipping SupremeCourtCase(citation) constraint: {e}")
        
        # Ingest nodes and relationships
        print("[ingest_sc_cases] Ingesting SupremeCourtCases...")
        for c in sc_cases:
            # Create/Merge SupremeCourtCase node
            session.run("""
                MERGE (sc:SupremeCourtCase {citation: $citation})
                SET sc.case_name = $case_name,
                    sc.year = $year,
                    sc.summary = $summary,
                    sc.ratio_decidendi = $ratio_decidendi,
                    sc.court = $court,
                    sc.source = $source
            """, citation=c["citation"], case_name=c["case_name"], year=c["year"],
               summary=c["summary"], ratio_decidendi=c["ratio_decidendi"],
               court=c["court"], source=c["source"])
            
            # Link LawSection -[:INTERPRETED_BY]-> SupremeCourtCase
            for link in c["linked_sections"]:
                act = link["act"]
                section = link["section"]
                
                res = session.run("""
                    MATCH (l:LawSection {act: $act, section: $section})
                    MATCH (sc:SupremeCourtCase {citation: $citation})
                    MERGE (l)-[r:INTERPRETED_BY]->(sc)
                    RETURN count(r) AS count
                """, act=act, section=section, citation=c["citation"])
                
                if res.single()["count"] > 0:
                    print(f"  Linked {act} {section} -[:INTERPRETED_BY]-> {c['case_name']}")
                else:
                    print(f"  ⚠️ Warning: Could not find node {act} {section} to link to {c['case_name']}")
            
            # Link SupremeCourtCase -[:CITES]-> ConstitutionalArticle
            for art in c["cites_articles"]:
                res = session.run("""
                    MATCH (sc:SupremeCourtCase {citation: $citation})
                    MATCH (art:ConstitutionalArticle {article: $article})
                    MERGE (sc)-[r:CITES]->(art)
                    RETURN count(r) AS count
                """, citation=c["citation"], article=art)
                
                if res.single()["count"] > 0:
                    print(f"  Linked Case {c['case_name']} -[:CITES]-> {art}")
                else:
                    print(f"  ⚠️ Warning: Could not find ConstitutionalArticle {art} to link from case {c['case_name']}")
                    
        # Print summary
        count = session.run("MATCH (n:SupremeCourtCase) RETURN count(n) AS c").single()["c"]
        rel_count = session.run("MATCH ()-[r:INTERPRETED_BY]->() RETURN count(r) AS c").single()["c"]
        cites_count = session.run("MATCH ()-[r:CITES]->() RETURN count(r) AS c").single()["c"]
        print(f"[ingest_sc_cases] Success! Total SupremeCourtCase nodes: {count}, INTERPRETED_BY: {rel_count}, CITES: {cites_count}")

    driver.close()

if __name__ == "__main__":
    ingest_sc_cases()
