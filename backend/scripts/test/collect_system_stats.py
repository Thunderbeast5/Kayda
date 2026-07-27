import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from neo4j import GraphDatabase
from pinecone import Pinecone

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parents[2]
ENV_PATH = BASE_DIR / ".env"
load_dotenv(ENV_PATH)

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "lexigraph-bns-ipc-v2")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(PINECONE_INDEX_NAME)
stats = index.describe_index_stats()
pinecone_vector_count = stats.total_vector_count

with driver.session(database=NEO4J_DATABASE) as session:
    def q(cypher):
        return session.run(cypher).single()

    total_sections = q("MATCH (n:LawSection) RETURN count(n) AS c")["c"]
    total_communities = q("MATCH (c:Community) RETURN count(c) AS c")["c"]
    total_cases = q("MATCH (cs) WHERE cs:Case OR cs:SupremeCourtCase OR cs:HighCourtCase RETURN count(DISTINCT cs) AS c")["c"]
    total_ev = q("MATCH (e:EvidenceType) RETURN count(e) AS c")["c"]
    total_ing = q("MATCH (i:Ingredient) RETURN count(i) AS c")["c"]
    total_art = q("MATCH (a) WHERE a:ConstitutionArticle OR a:ConstitutionalArticle OR a:Article RETURN count(DISTINCT a) AS c")["c"]
    total_lp = q("MATCH (p:LegalPrinciple) RETURN count(p) AS c")["c"]
    total_vr = q("MATCH (v:VictimRight) RETURN count(v) AS c")["c"]

    avg_cases_per_sec = q("""
        MATCH (n:LawSection)
        OPTIONAL MATCH (cs)-[:APPLIES_SECTION|INTERPRETS]->(n)
        WITH n, count(cs) AS csc
        RETURN avg(csc) AS avg_c
    """)["avg_c"]

    avg_ev_per_sec = q("""
        MATCH (n:LawSection)
        OPTIONAL MATCH (n)-[:HAS_INGREDIENT]->(ing)-[:REQUIRES_EVIDENCE]->(ev)
        WITH n, count(DISTINCT ev) AS evc
        RETURN avg(evc) AS avg_ev
    """)["avg_ev"]

    avg_lp_per_sec = q("""
        MATCH (n:LawSection)
        OPTIONAL MATCH (lp:LegalPrinciple)-[:APPLIES_TO]->(n)
        WITH n, count(DISTINCT lp) AS lpc
        RETURN avg(lpc) AS avg_lp
    """)["avg_lp"]

    sec_no_cases = q("""
        MATCH (n:LawSection)
        WHERE NOT (n)<-[:APPLIES_SECTION|INTERPRETS]-(:Case)
          AND NOT (n)-[:INTERPRETED_IN]->(:Case)
        RETURN count(n) AS c
    """)["c"]

    sec_no_ev = q("""
        MATCH (n:LawSection)
        WHERE NOT (n)-[:HAS_INGREDIENT]->()-[:REQUIRES_EVIDENCE]->()
          AND NOT (n)-[:REQUIRES_EVIDENCE]->()
        RETURN count(n) AS c
    """)["c"]

    sec_no_ing = q("""
        MATCH (n:LawSection)
        WHERE NOT (n)-[:HAS_INGREDIENT]->(:Ingredient)
        RETURN count(n) AS c
    """)["c"]

    comm_no_cases = q("""
        MATCH (c:Community)
        WHERE NOT (c)<-[:BELONGS_TO]-(:Case)
        RETURN count(c) AS c
    """)["c"]

print("=" * 80)
print("EMPIRICAL DATABASE STATISTICS FOR LEXIGRAPH SYSTEM")
print("=" * 80)
print(f"Total Vectors in Pinecone      : {pinecone_vector_count}")
print(f"Total LawSections              : {total_sections}")
print(f"Total Communities              : {total_communities}")
print(f"Total Cases                    : {total_cases}")
print(f"Total Evidence Types           : {total_ev}")
print(f"Total Ingredients              : {total_ing}")
print(f"Total Constitution Articles    : {total_art}")
print(f"Total Legal Principles         : {total_lp}")
print(f"Total Victim Rights            : {total_vr}")
print(f"Average cases per section      : {avg_cases_per_sec:.2f}")
print(f"Average evidence per section   : {avg_ev_per_sec:.2f}")
print(f"Average principles per section : {avg_lp_per_sec:.2f}")
print(f"Sections without cases         : {sec_no_cases}")
print(f"Sections without evidence      : {sec_no_ev}")
print(f"Sections without ingredients   : {sec_no_ing}")
print(f"Communities without cases      : {comm_no_cases}")
print("=" * 80)

driver.close()
