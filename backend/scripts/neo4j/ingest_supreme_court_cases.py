import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[3]
load_dotenv(BASE_DIR / "backend" / ".env")

JSON_DIR = BASE_DIR / "data" / "supreme_court_jsons"

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")


def ingest_supreme_court_cases():
    """
    Ingests landmark Supreme Court case JSONs into Neo4j as (:SupremeCourtCase) nodes
    and creates rich precedent graph relationships:
    - (:LawSection)-[:INTERPRETED_IN]->(:SupremeCourtCase)
    - (:SupremeCourtCase)-[:INTERPRETS]->(:LawSection)
    - (:SupremeCourtCase)-[:BINDING_UNDER]->(:ConstitutionArticle {article_number: "Article 141"})
    - (:SupremeCourtCase)-[:ESTABLISHES]->(:LegalPrinciple)
    - (:SupremeCourtCase)-[:REQUIRES]->(:EvidenceType)
    - (:SupremeCourtCase)-[:CITES]->(:ConstitutionArticle)
    """
    print("=" * 80, flush=True)
    print("INGESTING SUPREME COURT PRECEDENT GRAPH INTO NEO4J", flush=True)
    print("=" * 80, flush=True)

    if not all([NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD]):
        print("[Error] Neo4j credentials missing in environment.", flush=True)
        sys.exit(1)

    try:
        from neo4j import GraphDatabase
    except ImportError:
        print("[Error] neo4j python package missing.", flush=True)
        sys.exit(1)

    if not JSON_DIR.exists():
        print(f"[Error] JSON directory {JSON_DIR} does not exist.", flush=True)
        sys.exit(1)

    json_files = list(JSON_DIR.glob("*.json"))
    print(f"Found {len(json_files)} Supreme Court case JSON files.", flush=True)

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    with driver.session(database=NEO4J_DATABASE) as session:
        # 1. Create Constraint & Indexes
        try:
            session.run("CREATE CONSTRAINT sc_case_name IF NOT EXISTS FOR (c:SupremeCourtCase) REQUIRE c.case_name IS UNIQUE")
        except Exception as e:
            print(f"  [Constraint Info] {e}", flush=True)

        total_cases = 0
        total_interprets = 0
        total_binding = 0
        total_establishes = 0
        total_requires = 0
        total_cites = 0

        for jfile in json_files:
            with open(jfile, "r", encoding="utf-8") as f:
                data = json.load(f)

            cname = data.get("case_name")
            citation = data.get("citation")
            court = data.get("court", "Supreme Court of India")
            year = data.get("year", 2020)
            bench = data.get("bench", "")
            jdate = data.get("judgment_date", "")
            summary = data.get("summary", "")
            ratio = data.get("ratio_decidendi", "")
            holding = data.get("holding", "")
            keywords = data.get("keywords", [])

            # Merge (:SupremeCourtCase) and generic (:Case)
            session.run("""
                MERGE (sc:SupremeCourtCase {case_name: $cname})
                SET sc.case_id = $cname,
                    sc.citation = $citation,
                    sc.court = $court,
                    sc.year = $year,
                    sc.bench = $bench,
                    sc.judgment_date = $jdate,
                    sc.summary = $summary,
                    sc.ratio_decidendi = $ratio,
                    sc.holding = $holding,
                    sc.keywords = $keywords,
                    sc.source = "Supreme Court Reports"
                WITH sc
                MERGE (c:Case {title: $cname})
                SET c.case_id = $cname,
                    c.citation = $citation,
                    c.court = $court,
                    c.year = $year,
                    c.summary = $summary,
                    c.ratio_decidendi = $ratio,
                    c.holding = $holding
            """, cname=cname, citation=citation, court=court, year=year, bench=bench,
               jdate=jdate, summary=summary, ratio=ratio, holding=holding, keywords=keywords)
            total_cases += 1

            # 1. (:LawSection)-[:INTERPRETED_IN]->(:SupremeCourtCase) & (:SupremeCourtCase)-[:INTERPRETS]->(:LawSection)
            for sec_item in data.get("interpreted_sections", []):
                act = sec_item.get("act")
                sec = sec_item.get("section")
                session.run("""
                    MATCH (sc:SupremeCourtCase {case_name: $cname})
                    MERGE (l:LawSection {act: $act, section: $sec})
                    MERGE (l)-[:INTERPRETED_IN]->(sc)
                    MERGE (sc)-[:INTERPRETS]->(l)
                """, cname=cname, act=act, sec=sec)
                total_interprets += 1

            # 2. (:SupremeCourtCase)-[:BINDING_UNDER]->(:ConstitutionArticle {article_number: "Article 141"})
            session.run("""
                MATCH (sc:SupremeCourtCase {case_name: $cname})
                MERGE (a141:ConstitutionArticle {article_number: "Article 141"})
                SET a141.title = coalesce(a141.title, "Law declared by Supreme Court to be binding on all courts")
                MERGE (sc)-[:BINDING_UNDER]->(a141)
            """, cname=cname)
            total_binding += 1

            # 3. (:SupremeCourtCase)-[:ESTABLISHES]->(:LegalPrinciple)
            for pname in data.get("legal_principles", []):
                session.run("""
                    MATCH (sc:SupremeCourtCase {case_name: $cname})
                    MERGE (lp:LegalPrinciple {name: $pname})
                    MERGE (sc)-[:ESTABLISHES]->(lp)
                    MERGE (lp)-[:ESTABLISHED_BY]->(sc)
                """, cname=cname, pname=pname)
                total_establishes += 1

            # 4. (:SupremeCourtCase)-[:REQUIRES]->(:EvidenceType)
            for ev_name in data.get("related_evidence", []):
                session.run("""
                    MATCH (sc:SupremeCourtCase {case_name: $cname})
                    MERGE (e:EvidenceType {name: $ev_name})
                    MERGE (sc)-[:REQUIRES]->(e)
                """, cname=cname, ev_name=ev_name)
                total_requires += 1

            # 5. (:SupremeCourtCase)-[:CITES]->(:ConstitutionArticle)
            for art_str in data.get("constitutional_articles", []):
                session.run("""
                    MATCH (sc:SupremeCourtCase {case_name: $cname})
                    MERGE (a:ConstitutionArticle {article_number: $art_str})
                    MERGE (sc)-[:CITES]->(a)
                    MERGE (a)-[:INTERPRETED_IN]->(sc)
                """, cname=cname, art_str=art_str)
                total_cites += 1

        print("\n" + "=" * 80, flush=True)
        print("SUPREME COURT PRECEDENT GRAPH INGESTION COMPLETE", flush=True)
        print("=" * 80, flush=True)
        print(f"  - SupremeCourtCase Nodes   : {total_cases}", flush=True)
        print(f"  - INTERPRETS / IN Edges    : {total_interprets}", flush=True)
        print(f"  - BINDING_UNDER Edges      : {total_binding}", flush=True)
        print(f"  - ESTABLISHES Edges        : {total_establishes}", flush=True)
        print(f"  - REQUIRES Evidence Edges  : {total_requires}", flush=True)
        print(f"  - CITES Article Edges      : {total_cites}", flush=True)
        print("=" * 80 + "\n", flush=True)

    driver.close()


if __name__ == "__main__":
    ingest_supreme_court_cases()
