"""
inherit_structural_context.py
==============================
Inherits structural legal context (keywords, punishments, chapters, statutory ingredients,
exceptions, illustrations, evidence types) from parent legal provisions down to child
subsections, clauses, and explanations in Neo4j.

Explicitly EXCLUDES judicial case relationships:
  INTERPRETS, APPLIES_SECTION, CITES_CASE, USES_EVIDENCE, DECIDED_BY.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from neo4j import GraphDatabase

BASE_DIR = Path(__file__).resolve().parents[3]
ENV_PATH = BASE_DIR / "backend" / ".env" if (BASE_DIR / "backend" / ".env").exists() else BASE_DIR / ".env"
load_dotenv(ENV_PATH)

# Structural relationship types to inherit (outgoing from Section)
STRUCTURAL_OUTGOING_RELS = [
    "HAS_KEYWORD",
    "HAS_PUNISHMENT",
    "DEFINED_BY",
    "HAS_INGREDIENT",
    "HAS_EXCEPTION",
    "HAS_ILLUSTRATION",
    "SUPPORTED_BY",
]

# Structural relationship types to inherit (incoming to Section)
STRUCTURAL_INCOMING_RELS = [
    "HAS_INGREDIENT",
    "SUPPORTED_BY",
    "HAS_EXCEPTION",
    "HAS_ILLUSTRATION",
]


def inherit_structural_context(driver):
    with driver.session() as s:
        # 1. Inherit Chapter HAS_SECTION relationships (Chapter -> Section -> Child)
        s.run(
            """
            MATCH (c:Chapter)-[:HAS_SECTION]->(parent:LawSection)
            MATCH (parent)-[:HAS_SUBSECTION|HAS_CLAUSE|HAS_EXPLANATION]->(child:LawSection)
            MERGE (c)-[r:HAS_SECTION]->(child)
            ON CREATE SET r.inherited = true,
                          r.inherited_from = parent.id,
                          r.inheritance_level = CASE WHEN parent.node_type = 'SUBSECTION' THEN 2 ELSE 1 END
            """
        )

        # 2. Inherit outgoing structural relationships (parent -> target)
        for rel_type in STRUCTURAL_OUTGOING_RELS:
            query = f"""
                MATCH (parent:LawSection)-[r:{rel_type}]->(target)
                MATCH (parent)-[:HAS_SUBSECTION|HAS_CLAUSE|HAS_EXPLANATION]->(child:LawSection)
                MERGE (child)-[r_new:{rel_type}]->(target)
                ON CREATE SET r_new.inherited = true,
                              r_new.inherited_from = parent.id,
                              r_new.inheritance_level = CASE WHEN parent.node_type = 'SUBSECTION' THEN 2 ELSE 1 END
            """
            s.run(query)

        # 3. Inherit incoming structural relationships (source -> parent)
        for rel_type in STRUCTURAL_INCOMING_RELS:
            query = f"""
                MATCH (source)-[r:{rel_type}]->(parent:LawSection)
                MATCH (parent)-[:HAS_SUBSECTION|HAS_CLAUSE|HAS_EXPLANATION]->(child:LawSection)
                MERGE (source)-[r_new:{rel_type}]->(child)
                ON CREATE SET r_new.inherited = true,
                              r_new.inherited_from = parent.id,
                              r_new.inheritance_level = CASE WHEN parent.node_type = 'SUBSECTION' THEN 2 ELSE 1 END
            """
            s.run(query)

        # 4. Level-2 Grandparent propagation for Clauses (grandparent -> sub -> clause)
        for rel_type in STRUCTURAL_OUTGOING_RELS:
            query = f"""
                MATCH (grandparent:LawSection)-[r:{rel_type}]->(target)
                MATCH (grandparent)-[:HAS_SUBSECTION]->(sub:LawSection)-[:HAS_CLAUSE]->(clause:LawSection)
                MERGE (clause)-[r_new:{rel_type}]->(target)
                ON CREATE SET r_new.inherited = true,
                              r_new.inherited_from = grandparent.id,
                              r_new.inheritance_level = 2
            """
            s.run(query)

    print("Structural context inheritance complete.")


if __name__ == "__main__":
    NEO4J_URI = os.getenv("NEO4J_URI")
    NEO4J_USER = os.getenv("NEO4J_USER")
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        inherit_structural_context(driver)
    finally:
        driver.close()
