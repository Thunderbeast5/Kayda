"""
audit_community_leaks.py
========================
Audits case leaks caused by community membership traversal instead of direct typed
one-hop (:CourtCase)-[:INTERPRETS]->(:LawSection) edges.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from neo4j import GraphDatabase

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parents[2]
ENV_PATH = BASE_DIR / ".env"
load_dotenv(ENV_PATH)

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")


def audit_community_leaks():
    if not all([NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD]):
        print("[audit_community_leaks] Error: Missing Neo4j credentials in environment.")
        sys.exit(1)

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    print("=" * 80)
    print("AUDITING COMMUNITY CASE LEAKS ACROSS GRAPH")
    print("=" * 80)

    audit_query = """
    MATCH (s:LawSection)-[:BELONGS_TO]->(comm:Community)<-[:BELONGS_TO]-(c)
    WHERE (c:Case OR c:CourtCase OR c:SupremeCourtCase)
      AND NOT (c)-[:INTERPRETS|APPLIES_SECTION]->(s)
      AND NOT (s)-[:INTERPRETED_IN]->(c)
    RETURN coalesce(s.act, '') + ' ' + coalesce(s.section, s.code, '') AS section_code,
           comm.community_id AS community_id,
           count(DISTINCT c) AS leaked_cases,
           collect(DISTINCT coalesce(c.title, c.case_name))[..5] AS sample_leaked_cases
    ORDER BY leaked_cases DESC
    """

    with driver.session(database=NEO4J_DATABASE) as session:
        rows = session.run(audit_query).data()
        total_leaks = sum(r["leaked_cases"] for r in rows)
        print(f"\nFound {len(rows)} sections with community case leakage (Total leaked instances: {total_leaks}):\n")
        print(f"{'Section Code':<20} | {'Comm ID':<10} | {'Leaked Cases':<12} | Sample Leaked Cases")
        print("-" * 80)
        for r in rows[:15]:
            samples = ", ".join(r["sample_leaked_cases"])
            print(f"{r['section_code']:<20} | {str(r['community_id']):<10} | {r['leaked_cases']:<12} | {samples}")

    driver.close()
    print("=" * 80)


if __name__ == "__main__":
    audit_community_leaks()
