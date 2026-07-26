# """
# Sprint 1: Legal Data Ingest Script
# Ingests IPC and BNS sections from data CSVs into Neo4j and Pinecone.

# Usage:
#     python ingest_neo4j.py              # ingest only
#     python ingest_neo4j.py --wipe       # wipe existing data then ingest
#     python ingest_neo4j.py --pinecone   # also ingest into Pinecone
# """

# import csv
# import os
# import re
# import ssl
# import sys
# import json
# from pathlib import Path

# import certifi
# from dotenv import load_dotenv
# from neo4j import GraphDatabase, TrustCustomCAs

# # --------------------------------------------------------------------
# # Load .env
# # --------------------------------------------------------------------
# BASE_DIR = Path(__file__).resolve().parent
# ENV_PATH = BASE_DIR.parent / ".env"

# load_dotenv(ENV_PATH)

# print(f"Loading .env: {ENV_PATH}")
# print(f".env exists: {ENV_PATH.exists()}")

# # --------------------------------------------------------------------
# # Neo4j Configuration
# # --------------------------------------------------------------------
# NEO4J_URI = os.getenv("NEO4J_URI")
# NEO4J_USER = os.getenv("NEO4J_USER")
# NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

# print("URI:", NEO4J_URI)
# print("USER:", NEO4J_USER)
# print("PASSWORD:", "***" if NEO4J_PASSWORD else None)

# if not NEO4J_URI or not NEO4J_USER or not NEO4J_PASSWORD:
#     raise ValueError(
#         "Neo4j credentials not found. Check your backend/.env file."
#     )

# # --------------------------------------------------------------------
# # Other Config
# # --------------------------------------------------------------------
# CSV_PATH = BASE_DIR.parent.parent / "data" / "ipc_sections.csv"
# JSON_PATH = BASE_DIR.parent.parent / "data" / "ipc.json"
# BNS_CSV_PATH = BASE_DIR.parent.parent / "data" / "bns_sections.csv"
# PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
# PINECONE_INDEX_NAME = "legal-embeddings"


# def clean(value: str | None) -> str:
#     """Normalise a CSV cell: strip whitespace, convert 'nan' to empty."""
#     if value is None:
#         return ""
#     value = str(value).strip()
#     return "" if value.lower() == "nan" else value


# def extract_section_number(section_str: str) -> str:
#     if not section_str:
#         return ""
#     match = re.search(r"(\d+[A-Za-z]*)", str(section_str).replace("_", ""))
#     return match.group(1) if match else str(section_str)


# def read_csv_rows(path: Path) -> list[dict]:
#     rows = []
#     if not path.exists():
#         print(f"Warning: File not found at {path}")
#         return rows

#     with open(path, "r", encoding="utf-8") as f:
#         reader = csv.DictReader(f)
#         for row in reader:
#             # Standardize Title/Offense early
#             if "Title" not in row or not row.get("Title"):
#                 row["Title"] = row.get("Offense", "") or row.get("Title_BNS", "")

#             row["Section_Number"] = extract_section_number(row.get("Section", ""))
#             rows.append(row)
#     return rows


# def load_ipc_titles() -> dict:
#     if not JSON_PATH.exists():
#         print(f"Warning: JSON lookup file not found at {JSON_PATH}")
#         return {}
        
#     with open(JSON_PATH, "r", encoding="utf-8") as f:
#         data = json.load(f)

#     lookup = {}
#     for item in data:
#         if "Section" in item and "section_title" in item:
#             lookup[str(item["Section"])] = item["section_title"]
#     return lookup


# def clean_rows(rows: list[dict], title_lookup: dict) -> list[dict]:
#     """Cleans up raw data fields, replaces strings like 'nan', and fixes quotes."""
#     for row in rows:
#         offense = str(row.get("Offense", "")).strip()

#         # Fill missing offense from lookup if available
#         if offense.lower() in ("nan", ""):
#             section = row.get("Section_Number", "")
#             offense = title_lookup.get(section, "")

#         # Clean quotes and clean string representations of NaN values
#         offense = offense.replace('"', '').strip()
#         row["Offense"] = offense
#         if not row.get("Title"):
#             row["Title"] = offense

#         punishment = str(row.get("Punishment", "")).strip()
#         if punishment.lower() == "nan":
#             punishment = ""
#         row["Punishment"] = punishment
        
#         chapter = str(row.get("Chapter_Title", "")).strip()
#         if chapter.lower() == "nan":
#             chapter = ""
#         row["Chapter_Title"] = chapter

#     return rows


# def ingest_neo4j(rows: list[dict], act: str) -> int:
#     driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
#     count = 0
#     skipped = 0

#     with driver.session() as session:
#         for row in rows:
#             section = row.get("Section_Number", "")
#             desc = row.get("Description", "").strip()
#             punish = row.get("Punishment", "").strip()

#             if not section:
#                 skipped += 1
#                 continue

#             if not crime_type:
#                 crime_type = desc[:80] if desc else "Unknown"

#             session.run(
#                 """
#                 MERGE (l:LawSection {act: $act, section: $section})
#                 SET
#                     l.title = $title,
#                     l.description = $desc,
#                     l.punishment = $punish,
#                     l.chapter = $chapter

#                 WITH l

#                 MERGE (a:Act {name: $act})
#                 MERGE (a)-[:HAS_SECTION]->(l)
#                 """,
#                 act=act,
#                 section=section,
#                 title=row.get("Title") or row.get("Offense", ""),
#                 desc=desc,
#                 punish=punish,
#                 chapter=row.get("Chapter_Title", "")
#             )

#             count += 1

#     driver.close()
#     print(f"  Skipped {skipped} rows (empty section or offense)")
#     return count


# def ingest_pinecone(rows: list[dict], act: str) -> int:
#     from sentence_transformers import SentenceTransformer
#     from pinecone import Pinecone, ServerlessSpec

#     if not PINECONE_API_KEY:
#         print("Skipping Pinecone: PINECONE_API_KEY not set")
#         return 0

#     print("Loading embedding model (all-MiniLM-L6-v2)...")
#     model = SentenceTransformer("all-MiniLM-L6-v2")
#     pc = Pinecone(api_key=PINECONE_API_KEY)

#     # Cleaned list comprehension check for safe modern SDK compatibility
#     existing_indexes = [idx.name for idx in pc.list_indexes()]
#     if PINECONE_INDEX_NAME not in existing_indexes:
#         print(f"Creating Pinecone index: {PINECONE_INDEX_NAME}")
#         pc.create_index(
#             name=PINECONE_INDEX_NAME,
#             dimension=384,
#             metric="cosine",
#             spec=ServerlessSpec(cloud="aws", region="us-east-1"),
#         )

#     index = pc.Index(PINECONE_INDEX_NAME)
#     vectors = []
#     uploaded_count = 0

#     for row in rows:
#         section = row.get("Section_Number", "")
#         desc = row.get("Description", "").strip()
#         if not section or not desc:
#             continue
#         title = row.get("Title") or row.get("Offense", "")

#         text = f"Act: {act}\nSection: {section}\nTitle:\n{title}\n\nDescription:\n{desc}\n\nPunishment:\n{row.get('Punishment','')}\n\nChapter:\n{row.get('Chapter_Title','')}"
#         embedding = model.encode(text).tolist()

#         # Using tuple structure (id, vector, metadata) for optimal SDK compatibility
#         vectors.append((
#             f"{act}_{section}",
#             embedding,
#             {
#                 "act": act,
#                 "section": section,
#                 "title": title,
#                 "punishment": row.get("Punishment", ""),
#                 "chapter": row.get("Chapter_Title", "")
#             }
#         ))

#         if len(vectors) >= 100:
#             index.upsert(vectors=vectors)
#             uploaded_count += len(vectors)
#             vectors.clear()

#     if vectors:
#         index.upsert(vectors=vectors)
#         uploaded_count += len(vectors)

#     return uploaded_count


# def main():
#     # Load fallback title dictionary
#     title_lookup = load_ipc_titles()

#     # 1. Process IPC
#     print(f"\nReading IPC CSV: {CSV_PATH}")
#     ipc_rows = read_csv_rows(CSV_PATH)
#     print(f"Found {len(ipc_rows)} raw IPC rows")
#     ipc_rows = clean_rows(ipc_rows, title_lookup)

#     print("\n--- IPC Neo4j Ingestion ---")
#     count = ingest_neo4j(ipc_rows, "IPC")
#     print(f"Ingested {count} nodes into Neo4j")

#     if "--pinecone" in sys.argv:
#         print("\n--- IPC Pinecone Ingestion ---")
#         pc_count = ingest_pinecone(ipc_rows, "IPC")
#         print(f"Uploaded {pc_count} vectors to Pinecone")

#     # 2. Process BNS
#     print(f"\nReading BNS CSV: {BNS_CSV_PATH}")
#     bns_rows = read_csv_rows(BNS_CSV_PATH)
#     print(f"Found {len(bns_rows)} raw BNS sections")
#     bns_rows = clean_rows(bns_rows, title_lookup={}) # No JSON lookup needed for BNS

#     print("\n--- BNS Neo4j Ingestion ---")
#     count = ingest_neo4j(bns_rows, "BNS")
#     print(f"Ingested {count} BNS sections into Neo4j")

#     if "--pinecone" in sys.argv:
#         print("\n--- BNS Pinecone Ingestion ---")
#         pc_count = ingest_pinecone(bns_rows, "BNS")
#         print(f"Uploaded {pc_count} BNS vectors to Pinecone")
        
#     print("\nDone.")

    
# if __name__ == "__main__":
#     main()

"""
Sprint 1: Legal Data Ingest Script
Ingests IPC and BNS sections from data CSVs into Neo4j and Pinecone.

Usage:
    python ingest_neo4j.py              # ingest only
    python ingest_neo4j.py --wipe       # wipe existing data then ingest
    python ingest_neo4j.py --pinecone   # also ingest into Pinecone
"""

import csv
import os
import re
import ssl
import sys
import json
from pathlib import Path

import certifi
from dotenv import load_dotenv
from neo4j import GraphDatabase, TrustCustomCAs

# --------------------------------------------------------------------
# Load .env
# --------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR.parent.parent / ".env"

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
CSV_PATH = BASE_DIR.parent.parent.parent / "data" / "cleaned" / "ipc.csv"
JSON_PATH = BASE_DIR.parent.parent.parent / "data" / "ipc.json"
BNS_CSV_PATH = BASE_DIR.parent.parent.parent / "data" / "cleaned" / "bns_sections_clean.csv"
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "ipc-index")


def clean(value: str | None) -> str:
    """Normalise a CSV cell: strip whitespace, convert 'nan' to empty."""
    if value is None:
        return ""
    value = str(value).strip()
    return "" if value.lower() == "nan" else value


def extract_section_number(section_str: str) -> str:
    if not section_str:
        return ""
    match = re.search(r"(\d+[A-Za-z]*)", str(section_str).replace("_", ""))
    return match.group(1) if match else str(section_str)


def read_csv_rows(path: Path) -> list[dict]:
    rows = []
    if not path.exists():
        print(f"Warning: File not found at {path}")
        return rows

    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Standardize Title/Offense early
            if "Title" not in row or not row.get("Title"):
                row["Title"] = row.get("Offense", "") or row.get("Title_BNS", "")

            row["Section_Number"] = extract_section_number(row.get("Section", ""))
            rows.append(row)
    return rows


def load_ipc_titles() -> dict:
    if not JSON_PATH.exists():
        print(f"Warning: JSON lookup file not found at {JSON_PATH}")
        return {}
        
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    lookup = {}
    for item in data:
        if "Section" in item and "section_title" in item:
            lookup[str(item["Section"])] = item["section_title"]
    return lookup


def clean_rows(rows: list[dict], title_lookup: dict) -> list[dict]:
    """Cleans up raw data fields, replaces strings like 'nan', and fixes quotes."""
    for row in rows:
        offense = str(row.get("Offense", "")).strip()

        # Fill missing offense from lookup if available
        if offense.lower() in ("nan", ""):
            section = row.get("Section_Number", "")
            offense = title_lookup.get(section, "")

        # Clean quotes and clean string representations of NaN values
        offense = offense.replace('"', '').strip()
        row["Offense"] = offense
        if not row.get("Title"):
            row["Title"] = offense

        punishment = str(row.get("Punishment", "")).strip()
        if punishment.lower() == "nan":
            punishment = ""
        row["Punishment"] = punishment
        
        chapter = str(row.get("Chapter_Title", "")).strip()
        if chapter.lower() == "nan":
            chapter = ""
        row["Chapter_Title"] = chapter

    return rows


def ingest_neo4j(rows: list[dict], act: str) -> int:
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    seen_sections = set()
    batch = []
    skipped = 0

    for row in rows:
        section = row.get("Section_Number", "")
        desc = row.get("Description", "").strip()
        punish = row.get("Punishment", "").strip()
        if not section or section in seen_sections:
            skipped += 1
            continue
        seen_sections.add(section)
        batch.append({
            "section": section,
            "title": row.get("Title") or row.get("Offense", ""),
            "desc": desc,
            "punish": punish,
            "chapter": row.get("Chapter_Title", "")
        })

    with driver.session() as session:
        session.run(
            """
            UNWIND $batch AS item
            MERGE (l:LawSection {act: $act, section: item.section})
            SET
                l.title = item.title,
                l.description = item.desc,
                l.punishment = item.punish,
                l.chapter = item.chapter

            WITH l, item
            MERGE (a:Act {name: $act})
            MERGE (a)-[:HAS_SECTION]->(l)
            """,
            act=act,
            batch=batch
        )

    driver.close()
    print(f"  Skipped {skipped} rows (empty section or offense)")
    return len(batch)


def ingest_pinecone(rows: list[dict], act: str) -> int:
    from sentence_transformers import SentenceTransformer
    from pinecone import Pinecone, ServerlessSpec

    if not PINECONE_API_KEY:
        print("Skipping Pinecone: PINECONE_API_KEY not set")
        return 0

    print("Loading embedding model (all-MiniLM-L6-v2)...")
    model = SentenceTransformer("all-MiniLM-L6-v2")
    pc = Pinecone(api_key=PINECONE_API_KEY)

    # Cleaned list comprehension check for safe modern SDK compatibility
    existing_indexes = [idx.name for idx in pc.list_indexes()]
    if PINECONE_INDEX_NAME not in existing_indexes:
        print(f"Creating Pinecone index: {PINECONE_INDEX_NAME}")
        pc.create_index(
            name=PINECONE_INDEX_NAME,
            dimension=384,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )

    index = pc.Index(PINECONE_INDEX_NAME)
    vectors = []
    uploaded_count = 0

    for row in rows:
        section = row.get("Section_Number", "")
        desc = (row.get("Description") or row.get("Legal_Description") or row.get("Simple_Words") or "").strip()
        if not section or not desc:
            continue
        title = row.get("Title") or row.get("Offense", "")

        text = f"Act: {act}\nSection: {section}\nTitle:\n{title}\n\nDescription:\n{desc}\n\nPunishment:\n{row.get('Punishment','')}\n\nChapter:\n{row.get('Chapter_Title','')}"
        embedding = model.encode(text).tolist()

        # Using tuple structure (id, vector, metadata) for optimal SDK compatibility
        vectors.append((
            f"{act}_{section}",
            embedding,
            {
                "act": act,
                "section": section,
                "title": title,
                "punishment": row.get("Punishment", ""),
                "chapter": row.get("Chapter_Title", "")
            }
        ))

        if len(vectors) >= 100:
            index.upsert(vectors=vectors)
            uploaded_count += len(vectors)
            vectors.clear()

    if vectors:
        index.upsert(vectors=vectors)
        uploaded_count += len(vectors)

    return uploaded_count


def main():
    # Load fallback title dictionary
    title_lookup = load_ipc_titles()

    # 1. Process IPC
    print(f"\nReading IPC CSV: {CSV_PATH}")
    ipc_rows = read_csv_rows(CSV_PATH)
    print(f"Found {len(ipc_rows)} raw IPC rows")
    ipc_rows = clean_rows(ipc_rows, title_lookup)

    print("\n--- IPC Neo4j Ingestion ---")
    count = ingest_neo4j(ipc_rows, "IPC")
    print(f"Ingested {count} nodes into Neo4j")

    if "--pinecone" in sys.argv:
        print("\n--- IPC Pinecone Ingestion ---")
        pc_count = ingest_pinecone(ipc_rows, "IPC")
        print(f"Uploaded {pc_count} vectors to Pinecone")

    # 2. Process BNS
    print(f"\nReading BNS CSV: {BNS_CSV_PATH}")
    bns_rows = read_csv_rows(BNS_CSV_PATH)
    print(f"Found {len(bns_rows)} raw BNS sections")
    bns_rows = clean_rows(bns_rows, title_lookup={}) # No JSON lookup needed for BNS

    print("\n--- BNS Neo4j Ingestion ---")
    count = ingest_neo4j(bns_rows, "BNS")
    print(f"Ingested {count} BNS sections into Neo4j")

    if "--pinecone" in sys.argv:
        print("\n--- BNS Pinecone Ingestion ---")
        pc_count = ingest_pinecone(bns_rows, "BNS")
        print(f"Uploaded {pc_count} BNS vectors to Pinecone")
        
    print("\nDone.")

    
if __name__ == "__main__":
    main()