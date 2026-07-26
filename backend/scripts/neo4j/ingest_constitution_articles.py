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
from parse_constitution import parse_constitution_data

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

def ingest_constitution():
    if not all([NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD]):
        print("[ingest_constitution] Error: Missing Neo4j credentials in environment.")
        sys.exit(1)
        
    data_path = BASE_DIR.parent.parent.parent / "data" / "new" / "constitution.json"
    articles = parse_constitution_data(data_path)
    
    if not articles:
        print("[ingest_constitution] Error: No articles parsed.")
        sys.exit(1)
        
    print(f"[ingest_constitution] Parsed {len(articles)} articles from data file.")
    
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    with driver.session(database=NEO4J_DATABASE) as session:
        # Create uniqueness constraints
        print("[ingest_constitution] Ensuring constraints...")
        try:
            session.run("CREATE CONSTRAINT lawsection_unique IF NOT EXISTS FOR (n:LawSection) REQUIRE n.section IS UNIQUE")
        except Exception as e:
            print(f"  [Constraint Info] Skipping simple LawSection(section) constraint: {e}")
        try:
            session.run("CREATE CONSTRAINT lawsection_compound_unique IF NOT EXISTS FOR (n:LawSection) REQUIRE (n.section, n.act) IS UNIQUE")
        except Exception as e:
            print(f"  [Constraint Info] Skipping compound LawSection(section, act) constraint: {e}")
        try:
            session.run("CREATE CONSTRAINT const_article_unique IF NOT EXISTS FOR (n:ConstitutionalArticle) REQUIRE n.article IS UNIQUE")
        except Exception as e:
            print(f"  [Constraint Info] Skipping ConstitutionalArticle(article) constraint: {e}")
        
        # Ingest nodes and relationships
        print("[ingest_constitution] Ingesting ConstitutionalArticles...")
        for a in articles:
            # Create/Merge ConstitutionalArticle node
            session.run("""
                MERGE (art:ConstitutionalArticle {article: $article})
                SET art.title = $title,
                    art.description = $description,
                    art.source = $source
            """, article=a["article"], title=a["title"], description=a["description"], source=a["source"])
            
            # Create relationships
            for link in a["linked_sections"]:
                act = link["act"]
                section = link["section"]
                
                # Match LawSection and link with PROTECTED_BY
                res = session.run("""
                    MATCH (l:LawSection {act: $act, section: $section})
                    MATCH (art:ConstitutionalArticle {article: $article})
                    MERGE (l)-[r:PROTECTED_BY]->(art)
                    RETURN count(r) AS count
                """, act=act, section=section, article=a["article"])
                
                linked_count = res.single()["count"]
                if linked_count > 0:
                    print(f"  Linked {act} {section} -[:PROTECTED_BY]-> {a['article']}")
                else:
                    print(f"  ⚠️ Warning: Could not find node {act} {section} to link to {a['article']}")
                    
        # Print summary
        count = session.run("MATCH (n:ConstitutionalArticle) RETURN count(n) AS c").single()["c"]
        rel_count = session.run("MATCH ()-[r:PROTECTED_BY]->() RETURN count(r) AS c").single()["c"]
        print(f"[ingest_constitution] Success! Total ConstitutionalArticle nodes: {count}, Total PROTECTED_BY relations: {rel_count}")

    driver.close()

if __name__ == "__main__":
    ingest_constitution()
