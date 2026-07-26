"""
dedupe_articles_and_constraints.py
==================================
1. Creates uniqueness constraints on Article and ConstitutionArticle nodes.
2. Deduplicates existing duplicate article nodes and merges relationships using APOC / Cypher refactoring.
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


def apply_constraints_and_dedupe():
    if not all([NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD]):
        print("[dedupe_articles] Error: Missing Neo4j credentials in environment.")
        sys.exit(1)

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    print("=" * 80)
    print("APPLYING ARTICLE CONSTRAINTS AND DEDUPLICATING ARTICLE NODES")
    print("=" * 80)

    with driver.session(database=NEO4J_DATABASE) as session:
        # Step 1: APOC or manual deduplication before constraint creation to avoid error on existing dupes
        print("\n1. Deduplicating existing ConstitutionArticle / Article nodes...")

        # APOC Node Merge Cypher
        apoc_dedupe_query = """
        MATCH (a)
        WHERE a:ConstitutionArticle OR a:Article
        WITH coalesce(a.article_number, a.article, a.code) AS code, collect(a) AS nodes
        WHERE code IS NOT NULL AND size(nodes) > 1
        CALL apoc.refactor.mergeNodes(nodes, {properties: "combine", mergeRels: true})
        YIELD node
        RETURN count(node) AS merged_count
        """

        # Fallback Cypher if APOC is not installed
        cypher_fallback_dedupe = """
        MATCH (a)
        WHERE a:ConstitutionArticle OR a:Article
        WITH coalesce(a.article_number, a.article, a.code) AS code, collect(a) AS nodes
        WHERE code IS NOT NULL AND size(nodes) > 1
        WITH nodes[0] AS keep, nodes[1..] AS dupes
        UNWIND dupes AS dupe
        MATCH (dupe)-[r]->(target)
        MERGE (keep)-[r2:TYPE(r)]->(target)
        WITH keep, dupe, r
        MATCH (source)-[r3]->(dupe)
        MERGE (source)-[r4:TYPE(r3)]->(keep)
        WITH dupe
        DETACH DELETE dupe
        RETURN count(dupe) AS deleted_dupes
        """

        try:
            res = session.run(apoc_dedupe_query).single()
            count = res["merged_count"] if res else 0
            print(f"   [OK] APOC deduplication merged {count} duplicate article clusters.")
        except Exception as e:
            print(f"   [WARN] APOC merge error ({e}), running Cypher fallback deduplication...")
            try:
                res = session.run(cypher_fallback_dedupe).single()
                count = res["deleted_dupes"] if res else 0
                print(f"   [OK] Fallback deduplication cleaned up {count} duplicate article nodes.")
            except Exception as e2:
                print(f"   [ERROR] Deduplication fallback error: {e2}")

        # Step 2: Create Uniqueness Constraints
        print("\n2. Ensuring Article Uniqueness Constraints...")

        constraints = [
            ("article_code_unique", "CREATE CONSTRAINT article_code_unique IF NOT EXISTS FOR (a:Article) REQUIRE a.code IS UNIQUE"),
            ("const_article_num", "CREATE CONSTRAINT const_article_num IF NOT EXISTS FOR (a:ConstitutionArticle) REQUIRE a.article_number IS UNIQUE"),
        ]

        for c_name, query in constraints:
            try:
                session.run(query)
                print(f"   [OK] Constraint '{c_name}' created/verified successfully.")
            except Exception as e:
                print(f"   [WARN] Could not enforce constraint '{c_name}': {e}")

    driver.close()
    print("=" * 80)


if __name__ == "__main__":
    apply_constraints_and_dedupe()
