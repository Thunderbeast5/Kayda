import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[3]
load_dotenv(BASE_DIR / "backend" / ".env")

JSON_DIR = BASE_DIR / "data" / "constitution_jsons"

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")


# ── SPECIFIC OUTWARD STATUTORY-CONSTITUTIONAL MAPPINGS ────────────────────────
OUTWARD_CONSTITUTIONAL_MAPPINGS = [
    # BNS 80 / IPC 304B (Dowry Death)
    {"act": "BNS", "section": "80", "article": "Article 14", "rel": "GOVERNED_BY"},
    {"act": "BNS", "section": "80", "article": "Article 15", "rel": "DERIVES_FROM"},
    {"act": "BNS", "section": "80", "article": "Article 21", "rel": "PROTECTED_BY"},
    {"act": "BNS", "section": "80", "article": "Article 51A", "rel": "UPHOLDS"},
    {"act": "IPC", "section": "304B", "article": "Article 14", "rel": "GOVERNED_BY"},
    {"act": "IPC", "section": "304B", "article": "Article 15", "rel": "DERIVES_FROM"},
    {"act": "IPC", "section": "304B", "article": "Article 21", "rel": "PROTECTED_BY"},
    {"act": "IPC", "section": "304B", "article": "Article 51A", "rel": "UPHOLDS"},

    # BNS 85 / IPC 498A (Cruelty by Husband/Relatives)
    {"act": "BNS", "section": "85", "article": "Article 14", "rel": "GOVERNED_BY"},
    {"act": "BNS", "section": "85", "article": "Article 15", "rel": "DERIVES_FROM"},
    {"act": "BNS", "section": "85", "article": "Article 21", "rel": "PROTECTED_BY"},
    {"act": "BNS", "section": "85", "article": "Article 51A", "rel": "UPHOLDS"},
    {"act": "IPC", "section": "498A", "article": "Article 14", "rel": "GOVERNED_BY"},
    {"act": "IPC", "section": "498A", "article": "Article 15", "rel": "DERIVES_FROM"},
    {"act": "IPC", "section": "498A", "article": "Article 21", "rel": "PROTECTED_BY"},
    {"act": "IPC", "section": "498A", "article": "Article 51A", "rel": "UPHOLDS"},

    # BNS 63 / IPC 375 (Rape)
    {"act": "BNS", "section": "63", "article": "Article 14", "rel": "GOVERNED_BY"},
    {"act": "BNS", "section": "63", "article": "Article 15", "rel": "DERIVES_FROM"},
    {"act": "BNS", "section": "63", "article": "Article 21", "rel": "PROTECTED_BY"},
    {"act": "BNS", "section": "63", "article": "Article 51A", "rel": "UPHOLDS"},
    {"act": "IPC", "section": "375", "article": "Article 14", "rel": "GOVERNED_BY"},
    {"act": "IPC", "section": "375", "article": "Article 15", "rel": "DERIVES_FROM"},
    {"act": "IPC", "section": "375", "article": "Article 21", "rel": "PROTECTED_BY"},

    # BNS 143 (Human Trafficking)
    {"act": "BNS", "section": "143", "article": "Article 23", "rel": "PROHIBITED_BY"},
    {"act": "BNS", "section": "143", "article": "Article 21", "rel": "PROTECTED_BY"},

    # BNS 101 / IPC 302 (Murder)
    {"act": "BNS", "section": "101", "article": "Article 21", "rel": "PROTECTED_BY"},
    {"act": "BNS", "section": "101", "article": "Article 20", "rel": "GOVERNED_BY"},
    {"act": "IPC", "section": "302", "article": "Article 21", "rel": "PROTECTED_BY"},
    {"act": "IPC", "section": "302", "article": "Article 20", "rel": "GOVERNED_BY"}
]


def ingest_constitution_graph():
    """
    Ingests Constitutional Article JSONs into Neo4j as (:ConstitutionArticle) nodes
    and builds graph relationships:
    - (:LawSection)-[:PROTECTED_BY|DERIVES_FROM|UPHOLDS|PROHIBITED_BY|GOVERNED_BY]->(:ConstitutionArticle)
    - (:ConstitutionArticle)-[:INTERPRETED_IN]->(:Case)
    - (:Case)-[:BINDING_UNDER]->(:ConstitutionArticle {article_number: "Article 141"})
    - (:ConstitutionArticle)-[:RELATES_TO]->(:LegalPrinciple)
    - (:ConstitutionArticle)-[:RELEVANT_TO]->(:EvidenceType)
    - (:ConstitutionArticle)-[:BELONGS_TO]->(:ConstitutionPart)
    """
    print("=" * 80, flush=True)
    print("INGESTING CONSTITUTIONAL KNOWLEDGE GRAPH WITH OUTWARD TRAVERSAL SEMANTICS", flush=True)
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
    print(f"Found {len(json_files)} Constitutional Article JSON files.", flush=True)

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    with driver.session(database=NEO4J_DATABASE) as session:
        # 1. Create Constraints & Indexes
        try:
            session.run("CREATE CONSTRAINT const_article_num IF NOT EXISTS FOR (a:ConstitutionArticle) REQUIRE a.article_number IS UNIQUE")
            session.run("CREATE CONSTRAINT const_part_name IF NOT EXISTS FOR (p:ConstitutionPart) REQUIRE p.part IS UNIQUE")
        except Exception as e:
            print(f"  [Constraint Info] {e}", flush=True)

        total_articles = 0
        total_outward_edges = 0
        total_interpreted_in = 0
        total_relates_to = 0
        total_relevant_to = 0

        for jfile in json_files:
            with open(jfile, "r", encoding="utf-8") as f:
                data = json.load(f)

            art_num = data.get("article_number")
            title = data.get("title")
            part = data.get("part")
            chapter = data.get("chapter")
            category = data.get("category")
            full_text = data.get("full_text")
            summary = data.get("summary")
            importance = data.get("importance_score", 0.90)
            relevance_reason = data.get("relevance_reason", "")
            keywords = data.get("keywords", [])

            # Merge (:ConstitutionArticle)
            session.run("""
                MERGE (a:ConstitutionArticle {article_number: $art_num})
                SET a.article = $art_num,
                    a.title = $title,
                    a.part = $part,
                    a.chapter = $chapter,
                    a.category = $category,
                    a.full_text = $full_text,
                    a.summary = $summary,
                    a.importance_score = $importance,
                    a.relevance_reason = $relevance_reason,
                    a.keywords = $keywords,
                    a.source = "Constitution of India"
            """, art_num=art_num, title=title, part=part, chapter=chapter, category=category,
               full_text=full_text, summary=summary, importance=importance,
               relevance_reason=relevance_reason, keywords=keywords)
            total_articles += 1

            # Merge (:ConstitutionPart) and BELONGS_TO
            session.run("""
                MERGE (cp:ConstitutionPart {part: $part})
                WITH cp
                MATCH (a:ConstitutionArticle {article_number: $art_num})
                MERGE (a)-[:BELONGS_TO]->(cp)
            """, part=part, art_num=art_num)

            rel_dict = data.get("graph_relationships", {})

            # 1. (:ConstitutionArticle)-[:INTERPRETED_IN]->(:Case) AND (:Case)-[:BINDING_UNDER]->(Article 141)
            for cname in rel_dict.get("possible_landmark_cases", []):
                session.run("""
                    MATCH (a:ConstitutionArticle {article_number: $art_num})
                    MERGE (c:Case {title: $cname})
                    SET c.case_id = coalesce(c.case_id, $cname)
                    MERGE (a)-[:INTERPRETED_IN]->(c)
                    WITH c
                    MATCH (a141:ConstitutionArticle {article_number: "Article 141"})
                    MERGE (c)-[:BINDING_UNDER]->(a141)
                """, art_num=art_num, cname=cname)
                total_interpreted_in += 1

            # 2. (:ConstitutionArticle)-[:RELATES_TO]->(:LegalPrinciple)
            for pname in data.get("legal_principles", []) + rel_dict.get("related_constitutional_principles", []):
                session.run("""
                    MATCH (a:ConstitutionArticle {article_number: $art_num})
                    MERGE (lp:LegalPrinciple {name: $pname})
                    MERGE (a)-[:RELATES_TO]->(lp)
                """, art_num=art_num, pname=pname)
                total_relates_to += 1

            # 3. (:ConstitutionArticle)-[:RELEVANT_TO]->(:EvidenceType)
            for ev_name in rel_dict.get("recommended_evidence_types", []):
                session.run("""
                    MATCH (a:ConstitutionArticle {article_number: $art_num})
                    MERGE (e:EvidenceType {name: $ev_name})
                    MERGE (a)-[:RELEVANT_TO]->(e)
                """, art_num=art_num, ev_name=ev_name)
                total_relevant_to += 1

        # 4. Outward Specific Statutory-Constitutional Edges: (:LawSection)-[:PROTECTED_BY|DERIVES_FROM|UPHOLDS|PROHIBITED_BY|GOVERNED_BY]->(:ConstitutionArticle)
        print("Ingesting Outward Statutory-Constitutional Edges...", flush=True)
        for map_item in OUTWARD_CONSTITUTIONAL_MAPPINGS:
            act, sec, art, rel = map_item["act"], map_item["section"], map_item["article"], map_item["rel"]
            cypher = f"""
                MATCH (l:LawSection {{act: $act, section: $sec}})
                MATCH (a:ConstitutionArticle {{article_number: $art}})
                MERGE (l)-[:{rel}]->(a)
                MERGE (l)-[:PROTECTED_BY]->(a)
            """
            session.run(cypher, act=act, sec=sec, art=art)
            total_outward_edges += 1

        print("\n" + "=" * 80, flush=True)
        print("CONSTITUTIONAL KNOWLEDGE GRAPH INGESTION COMPLETE", flush=True)
        print("=" * 80, flush=True)
        print(f"  - ConstitutionArticle Nodes : {total_articles}", flush=True)
        print(f"  - Outward Statutory Edges   : {total_outward_edges}", flush=True)
        print(f"  - INTERPRETED_IN Edges      : {total_interpreted_in}", flush=True)
        print(f"  - RELATES_TO Edges          : {total_relates_to}", flush=True)
        print(f"  - RELEVANT_TO Edges         : {total_relevant_to}", flush=True)
        print("=" * 80 + "\n", flush=True)

    driver.close()


if __name__ == "__main__":
    ingest_constitution_graph()
