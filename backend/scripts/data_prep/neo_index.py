"""
LexiGraph — Text2Cypher prerequisite: full-text indexes
========================================================
Run this ONCE before using text2cypher_agent.py.

Why this is needed:
  Your current graph has no full-text index on LawSection, so any
  Text2Cypher-generated `WHERE l.description CONTAINS $x` query only
  matches exact substrings. A query for "kidnapped" will miss text that
  says "kidnaps" (different word form). Neo4j's built-in Lucene full-text
  index handles stemming/tokenization for you, which is what actually
  makes Text2Cypher usable for narrative queries instead of exact-string
  matching.

  It also indexes Crime.name, which is only ever a short IPC/BNS offense
  title (e.g. "Kidnapping for ransom, etc.") — cheap and useful as a
  secondary signal.

Usage:
    python setup_indexes.py
"""
from __future__ import annotations
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    for candidate in [Path(".env"), Path("../.env"), Path("../../.env")]:
        if candidate.exists():
            load_dotenv(candidate)
            break
except ImportError:
    pass

from neo4j import GraphDatabase

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")


INDEX_STATEMENTS = [
    # Main text search surface: title + description + punishment + keywords.
    # NOTE: 'keywords' currently only has real data for BNS sections (see
    # neo4j_v2.py — IPC rows never set a 'keywords' property). Indexing it
    # anyway is harmless and future-proofs this once you backfill IPC
    # keywords (see the graph-changes note in chat).
    """
    CREATE FULLTEXT INDEX lawSectionText IF NOT EXISTS
    FOR (l:LawSection) ON EACH [l.title, l.description, l.punishment, l.keywords]
    """,
    """
    CREATE FULLTEXT INDEX crimeName IF NOT EXISTS
    FOR (c:Crime) ON EACH [c.name]
    """,
]


def main() -> None:
    if not (NEO4J_URI and NEO4J_USER and NEO4J_PASSWORD):
        raise SystemExit("Set NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD (env or .env)")

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with driver.session() as session:
        for stmt in INDEX_STATEMENTS:
            session.run(stmt)
        # Wait for indexes to come online before first use
        session.run("CALL db.awaitIndexes(300)")
    driver.close()
    print("Full-text indexes ready: lawSectionText, crimeName")


if __name__ == "__main__":
    main()