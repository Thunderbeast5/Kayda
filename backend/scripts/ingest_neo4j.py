"""
Sprint 1: Legal Data Ingest Script
Ingests IPC sections from data/ipc_sections.csv into Neo4j and Pinecone.

Usage:
    python ingest_neo4j.py
    python ingest_neo4j.py --pinecone
"""

import csv
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

# --------------------------------------------------------------------
# Load .env
# --------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR.parent / ".env"

load_dotenv(ENV_PATH)

print(f"Loading .env: {ENV_PATH}")
print(f".env exists: {ENV_PATH.exists()}")

# --------------------------------------------------------------------
# Neo4j Configuration
# --------------------------------------------------------------------
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

print("URI:", NEO4J_URI)
print("USER:", NEO4J_USER)
print("PASSWORD:", "***" if NEO4J_PASSWORD else None)

if not NEO4J_URI or not NEO4J_USER or not NEO4J_PASSWORD:
    raise ValueError(
        "Neo4j credentials not found. Check your backend/.env file."
    )

# --------------------------------------------------------------------
# Other Config
# --------------------------------------------------------------------
CSV_PATH = BASE_DIR.parent.parent / "data" / "ipc_sections.csv"

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = "legal-embeddings"


def extract_section_number(section_str: str) -> str:
    match = re.search(r"(\d+[A-Za-z]*)", section_str.replace("_", ""))
    return match.group(1) if match else section_str


def read_csv_rows(path: str) -> list[dict]:
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row["Section_Number"] = extract_section_number(row.get("Section", ""))
            rows.append(row)
    return rows


def ingest_neo4j(rows: list[dict]):
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    count = 0

    with driver.session() as session:
        for row in rows:
            crime_type = row.get("Offense", "").strip()
            section = row.get("Section_Number", "")
            desc = row.get("Description", "").strip()
            punish = row.get("Punishment", "").strip()

            if not section:
                continue

            session.run(
                """
                MERGE (c:Crime {name: $crime_type})
                MERGE (l:IPC {section: $section, description: $desc, punishment: $punish})
                MERGE (c)-[:DEFINED_BY]->(l)
                """,
                crime_type=crime_type,
                section=section,
                desc=desc,
                punish=punish,
            )
            count += 1

    driver.close()
    return count


def ingest_pinecone(rows: list[dict]):
    from sentence_transformers import SentenceTransformer
    from pinecone import Pinecone, ServerlessSpec

    if not PINECONE_API_KEY:
        print("Skipping Pinecone: PINECONE_API_KEY not set")
        return 0

    print("Loading embedding model (all-MiniLM-L6-v2)...")
    model = SentenceTransformer("all-MiniLM-L6-v2")
    pc = Pinecone(api_key=PINECONE_API_KEY)

    if PINECONE_INDEX_NAME not in pc.list_indexes().names():
        pc.create_index(
            name=PINECONE_INDEX_NAME,
            dimension=384,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )

    index = pc.Index(PINECONE_INDEX_NAME)

    vectors = []
    for i, row in enumerate(rows):
        section = row.get("Section_Number", "")
        desc = row.get("Description", "").strip()
        if not section or not desc:
            continue

        embedding = model.encode(desc).tolist()

        vectors.append(
            {
                "id": f"IPC_{section}",
                "values": embedding,
                "metadata": {
                    "section": section,
                    "offense": row.get("Offense", ""),
                    "punishment": row.get("Punishment", ""),
                },
            }
        )

        if len(vectors) >= 100:
            index.upsert(vectors=vectors)
            vectors.clear()

    if vectors:
        index.upsert(vectors=vectors)

    return len(rows)


def main():
    print(f"Reading CSV: {CSV_PATH}")
    rows = read_csv_rows(CSV_PATH)
    print(f"Found {len(rows)} rows")

    print("\n--- Neo4j Ingestion ---")
    count = ingest_neo4j(rows)
    print(f"Ingested {count} nodes into Neo4j")

    if "--pinecone" in sys.argv:
        print("\n--- Pinecone Ingestion ---")
        pc_count = ingest_pinecone(rows)
        print(f"Uploaded {pc_count} vectors to Pinecone")

    print("\nDone.")


if __name__ == "__main__":
    main()
