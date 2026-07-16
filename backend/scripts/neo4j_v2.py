# """
# LexiGraph — Sprint 5: Knowledge Graph v1.1 Ingest Script
# =========================================================

# Builds on the existing Version 1 graph (Act -HAS_SECTION-> LawSection,
# Crime -DEFINED_BY-> LawSection) WITHOUT redesigning it. This script adds the
# next two items from the roadmap's priority list, plus a low-risk third:

#   Priority 1 — Chapter nodes
#       (Act)-[:HAS_CHAPTER]->(Chapter)-[:HAS_SECTION]->(LawSection)
#       Chapter data only exists for BNS in the source CSVs, so IPC sections
#       are still attached directly via (Act)-[:HAS_SECTION]->(LawSection) —
#       the same edge Version 1 already used — for backward compatibility.

#   Priority 2 — IPC <-> BNS mapping
#       (:LawSection {act:'IPC'})-[:REPLACED_BY {status}]->(:LawSection {act:'BNS'})
#       (:LawSection {act:'BNS'})-[:REPLACES {status}]->(:LawSection {act:'IPC'})
#       Built from BNS_IPC_Comparative.csv. Deleted IPC sections (no BNS
#       successor) and brand-new BNS sections (no IPC predecessor) are kept as
#       properties instead of dangling edges — see `mapping_status` below.

#   Priority 3 (partial) — Punishment nodes
#       (LawSection)-[:HAS_PUNISHMENT]->(Punishment {text})
#       Only the punishment string itself is lifted into a node (deduplicated
#       by exact text). Ingredient / EvidenceType / LandmarkCase nodes are
#       NOT built here — those require legal NLP/LLM extraction, not a CSV
#       merge, and fabricating them from this data would risk exactly the
#       "IPC section hallucination" problem the project already fixed once.
#       They stay as a Sprint 6+ task in the roadmap.

# Data reconciliation
# --------------------
# Two IPC sources are provided and were found to cover the exact same 442
# IPC sections, but with complementary gaps:
#   - ipc_complete_datatset.csv : richer description, has Cognizable/
#     Bailable/Court, but 63 rows missing Offense/Punishment
#   - ipc_sections.csv          : same content, 58/59 rows missing
#     Offense/Punishment (a different set of rows than the file above)
# They are merged section-by-section, filling gaps from whichever file has
# the value. 5 Offense values and 4 Punishment values are only recoverable
# because both files are used together.

# BNS_IPC_Comparative.csv references 549 distinct IPC sections, but the two
# IPC CSVs above only contain full detail for 427 of them. The remaining 122
# sections (e.g. old IPC 1, 10, 100, 101...) are added as *stub* LawSection
# nodes using only the title from the comparative file, tagged
# `data_complete: false`, so the mapping graph stays connected without
# inventing description/punishment text that isn't in any source file.

# All BNS sections referenced by the comparative file (358) are fully
# covered by bns_sections_clean.csv — no BNS stubs are needed.

# Usage
# -----
#     python ingest_neo4j_v2.py                # ingest into Neo4j only
#     python ingest_neo4j_v2.py --wipe          # wipe graph first, then ingest
#     python ingest_neo4j_v2.py --pinecone      # also (re)embed into Pinecone
#     python ingest_neo4j_v2.py --csv-dir DIR   # CSVs live somewhere else
#     python ingest_neo4j_v2.py --dry-run       # parse + validate CSVs only, no DB writes
# """

# from __future__ import annotations

# import argparse
# import csv
# import hashlib
# import os
# import re
# import sys
# from pathlib import Path
# from typing import Any

# # ----------------------------------------------------------------------
# # Paths / env
# # ----------------------------------------------------------------------
# BASE_DIR = Path(__file__).resolve().parent

# # Try to find .env in:
# # 1. BASE_DIR.parent (backend/)
# # 2. BASE_DIR.parent.parent (MootCourt/ root)
# # 3. BASE_DIR (scripts/)
# # 4. Current working directory
# env_candidates = [
#     BASE_DIR.parent / ".env",
#     BASE_DIR.parent.parent / ".env",
#     BASE_DIR / ".env",
#     Path(".env")
# ]
# ENV_PATH = None
# for candidate in env_candidates:
#     if candidate.exists():
#         ENV_PATH = candidate
#         break

# try:
#     from dotenv import load_dotenv
#     if ENV_PATH:
#         load_dotenv(ENV_PATH)
#     else:
#         load_dotenv()
# except ImportError:
#     pass

# NEO4J_URI = os.getenv("NEO4J_URI")
# NEO4J_USER = os.getenv("NEO4J_USER")
# NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
# PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
# PINECONE_INDEX_NAME = "legal-embeddings"

# BATCH_SIZE = 500

# # Try to find data/new in:
# # 1. BASE_DIR.parent.parent / "data" / "new" (MootCourt/data/new)
# # 2. BASE_DIR.parent / "data" / "new" (backend/data/new)
# # 3. BASE_DIR / "data" / "new"
# # 4. Path("data/new") relative to CWD
# csv_dir_candidates = [
#     BASE_DIR.parent.parent / "data" / "new",
#     BASE_DIR.parent / "data" / "new",
#     BASE_DIR / "data" / "new",
#     Path("data/new")
# ]
# DEFAULT_CSV_DIR = None
# for candidate in csv_dir_candidates:
#     if candidate.exists() and candidate.is_dir():
#         DEFAULT_CSV_DIR = candidate
#         break
# if not DEFAULT_CSV_DIR:
#     DEFAULT_CSV_DIR = BASE_DIR.parent.parent / "data" / "new"


# # CSV filenames expected inside --csv-dir (defaults to this file's directory)
# IPC_DETAIL_CSV = "ipc_complete_datatset.csv"      # URL, Description, Offense, Punishment, Cognizable, Bailable, Court
# IPC_ALT_CSV = "ipc_sections.csv"                  # Description, Offense, Punishment, Section
# BNS_CSV = "bns_sections_clean.csv"                # Section, Title, Description, Punishment, Chapter, Category, Keywords
# MAPPING_CSV = "BNS_IPC_Comparative.csv"           # BNS_Section, BNS_Title, Status, IPC_Section, IPC_Title


# # ----------------------------------------------------------------------
# # Small utilities
# # ----------------------------------------------------------------------
# def clean(value: Any) -> str:
#     """Normalise a CSV cell: strip whitespace, collapse newlines, drop NaN-ish values."""
#     if value is None:
#         return ""
#     value = str(value).strip().strip('"').strip()
#     if value.lower() in ("nan", "none", "n/a", ""):
#         return ""
#     return re.sub(r"\s+", " ", value)


# def stable_id(*parts: str) -> str:
#     """Deterministic short id for nodes that dedupe on content rather than a natural key."""
#     raw = "|".join(parts)
#     return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


# def extract_ipc_section_from_url(url: str) -> str | None:
#     m = re.search(r"section-(\d+[A-Za-z]*)", str(url))
#     return m.group(1) if m else None


# def extract_ipc_section_from_field(section_field: str) -> str | None:
#     m = re.search(r"(\d+[A-Za-z]*)", str(section_field).replace("IPC_", ""))
#     return m.group(1) if m else None


# def extract_ipc_section_generic(value: str) -> str | None:
#     """Used for the comparative CSV's IPC_Section column, e.g. '120B', '302'."""
#     if not value:
#         return None
#     m = re.match(r"\s*(\d+[A-Za-z]*)", str(value))
#     return m.group(1) if m else None


# def extract_bns_base_section(value: str) -> int | None:
#     """'1(2)' -> 1, '101' -> 101. BNS sections in the KG are stored at the
#     base-section granularity (matching bns_sections_clean.csv); sub-section
#     detail from the comparative file is not modeled as separate nodes."""
#     if value is None:
#         return None
#     m = re.match(r"\s*(\d+)", str(value))
#     return int(m.group(1)) if m else None


# def parse_chapter(raw_chapter: str) -> tuple[str, str]:
#     """'Chapter I: Preliminary' -> ('I', 'Preliminary')."""
#     m = re.match(r"Chapter\s+([IVXLCDM]+)\s*:\s*(.+)", raw_chapter.strip())
#     if m:
#         return m.group(1), m.group(2).strip()
#     return "", raw_chapter.strip()


# def read_csv(path: Path) -> list[dict]:
#     if not path.exists():
#         print(f"  WARNING: file not found: {path}")
#         return []
#     with open(path, "r", encoding="utf-8-sig", newline="") as f:
#         return list(csv.DictReader(f))


# # ----------------------------------------------------------------------
# # IPC loading — merge the two source files, fill gaps from either side
# # ----------------------------------------------------------------------
# def load_ipc_sections(csv_dir: Path) -> dict[str, dict]:
#     detail_rows = read_csv(csv_dir / IPC_DETAIL_CSV)
#     alt_rows = read_csv(csv_dir / IPC_ALT_CSV)

#     ipc: dict[str, dict] = {}

#     for row in detail_rows:
#         sec = extract_ipc_section_from_url(row.get("URL", ""))
#         if not sec:
#             continue
#         ipc[sec] = {
#             "act": "IPC",
#             "section": sec,
#             "title": clean(row.get("Offense")),
#             "description": clean(row.get("Description")),
#             "punishment": clean(row.get("Punishment")),
#             "cognizable": clean(row.get("Cognizable")),
#             "bailable": clean(row.get("Bailable")),
#             "court": clean(row.get("Court")),
#             "data_complete": True,
#         }

#     filled_offense = filled_punishment = added_from_alt = 0
#     for row in alt_rows:
#         sec = extract_ipc_section_from_field(row.get("Section", ""))
#         if not sec:
#             continue
#         alt_title = clean(row.get("Offense"))
#         alt_desc = clean(row.get("Description"))
#         alt_punish = clean(row.get("Punishment"))

#         if sec not in ipc:
#             ipc[sec] = {
#                 "act": "IPC",
#                 "section": sec,
#                 "title": alt_title,
#                 "description": alt_desc,
#                 "punishment": alt_punish,
#                 "cognizable": "",
#                 "bailable": "",
#                 "court": "",
#                 "data_complete": True,
#             }
#             added_from_alt += 1
#             continue

#         existing = ipc[sec]
#         if not existing["title"] and alt_title:
#             existing["title"] = alt_title
#             filled_offense += 1
#         if not existing["description"] and alt_desc:
#             existing["description"] = alt_desc
#         if not existing["punishment"] and alt_punish:
#             existing["punishment"] = alt_punish
#             filled_punishment += 1

#     # Fall back to description as title if Offense/title is still empty
#     for sec, row in ipc.items():
#         if not row["title"] and row["description"]:
#             row["title"] = row["description"][:80]

#     print(f"  IPC: {len(detail_rows)} detail rows + {len(alt_rows)} alt rows "
#           f"-> {len(ipc)} unique sections "
#           f"({added_from_alt} added from alt-only, "
#           f"{filled_offense} titles / {filled_punishment} punishments backfilled)")
#     return ipc


# # ----------------------------------------------------------------------
# # BNS loading — already clean, one row per section
# # ----------------------------------------------------------------------
# def load_bns_sections(csv_dir: Path) -> dict[str, dict]:
#     rows = read_csv(csv_dir / BNS_CSV)
#     bns: dict[str, dict] = {}
#     for row in rows:
#         sec_raw = clean(row.get("Section"))
#         if not sec_raw:
#             continue
#         sec = str(int(sec_raw)) if sec_raw.isdigit() else sec_raw
#         chapter_raw = clean(row.get("Chapter"))
#         chapter_num, chapter_title = parse_chapter(chapter_raw) if chapter_raw else ("", "")
#         bns[sec] = {
#             "act": "BNS",
#             "section": sec,
#             "title": clean(row.get("Title")),
#             "description": clean(row.get("Description")),
#             "punishment": clean(row.get("Punishment")),
#             "chapter_raw": chapter_raw,
#             "chapter_number": chapter_num,
#             "chapter_title": chapter_title,
#             "category": clean(row.get("Category")),
#             "keywords": clean(row.get("Keywords")),
#             "data_complete": True,
#         }
#     print(f"  BNS: {len(rows)} rows -> {len(bns)} unique sections")
#     return bns


# # ----------------------------------------------------------------------
# # Mapping loading — also produces IPC stub sections for the roadmap's
# # "IPC should NOT be removed" requirement when detail rows don't exist
# # ----------------------------------------------------------------------
# def load_mapping(csv_dir: Path, ipc: dict[str, dict], bns: dict[str, dict]) -> list[dict]:
#     rows = read_csv(csv_dir / MAPPING_CSV)
#     mappings = []
#     stubs_added = 0
#     skipped_no_bns_node = 0

#     for row in rows:
#         bns_raw = clean(row.get("BNS_Section"))
#         ipc_raw = clean(row.get("IPC_Section"))
#         status_raw = clean(row.get("Status")) or "Unchanged"
#         bns_title = clean(row.get("BNS_Title"))
#         ipc_title = clean(row.get("IPC_Title"))

#         bns_sec = str(extract_bns_base_section(bns_raw)) if bns_raw else None
#         ipc_sec = extract_ipc_section_generic(ipc_raw) if ipc_raw else None

#         # Ensure an IPC stub node exists so the section is represented even
#         # without full detail (Description/Punishment stay empty on purpose).
#         if ipc_sec and ipc_sec not in ipc:
#             ipc[ipc_sec] = {
#                 "act": "IPC",
#                 "section": ipc_sec,
#                 "title": ipc_title,
#                 "description": "",
#                 "punishment": "",
#                 "cognizable": "",
#                 "bailable": "",
#                 "court": "",
#                 "data_complete": False,
#             }
#             stubs_added += 1

#         if bns_sec and bns_sec not in bns:
#             # Every BNS section in the mapping file was found to exist in
#             # bns_sections_clean.csv already; this branch only triggers if
#             # a differently-versioned BNS CSV is swapped in later.
#             skipped_no_bns_node += 1
#             bns_sec = None

#         if not ipc_sec and not bns_sec:
#             continue  # can't link or stub anything useful from this row

#         mappings.append({
#             "ipc_section": ipc_sec,
#             "bns_section": bns_sec,
#             "status": status_raw,
#             "bns_title_hint": bns_title,
#             "ipc_title_hint": ipc_title,
#         })

#     print(f"  Mapping: {len(rows)} rows -> {len(mappings)} usable mapping rows "
#           f"({stubs_added} IPC stub sections added, {skipped_no_bns_node} rows skipped: BNS section not found)")
#     return mappings


# # ----------------------------------------------------------------------
# # Neo4j ingestion
# # ----------------------------------------------------------------------
# def get_driver():
#     from neo4j import GraphDatabase

#     if not NEO4J_URI or not NEO4J_USER or not NEO4J_PASSWORD:
#         raise ValueError(
#             "Neo4j credentials not found. Set NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD "
#             f"(checked {ENV_PATH})."
#         )
#     return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


# def wipe_graph(driver) -> None:
#     print("Wiping existing graph (all nodes/relationships)...")
#     with driver.session() as session:
#         session.run("MATCH (n) DETACH DELETE n")


# def create_constraints(driver) -> None:
#     statements = [
#         "CREATE CONSTRAINT act_code IF NOT EXISTS FOR (a:Act) REQUIRE a.code IS UNIQUE",
#         "CREATE CONSTRAINT lawsection_id IF NOT EXISTS FOR (l:LawSection) REQUIRE l.id IS UNIQUE",
#         "CREATE CONSTRAINT chapter_id IF NOT EXISTS FOR (c:Chapter) REQUIRE c.id IS UNIQUE",
#         "CREATE CONSTRAINT punishment_id IF NOT EXISTS FOR (p:Punishment) REQUIRE p.id IS UNIQUE",
#     ]
#     with driver.session() as session:
#         for stmt in statements:
#             session.run(stmt)
#     print("Constraints ensured (Act.code, LawSection.id, Chapter.id, Punishment.id).")


# def batched(iterable: list, size: int):
#     for i in range(0, len(iterable), size):
#         yield iterable[i:i + size]


# def ingest_acts(driver) -> None:
#     with driver.session() as session:
#         session.run(
#             """
#             UNWIND $acts AS act
#             MERGE (a:Act {code: act.code})
#             SET a.name = act.name
#             """,
#             acts=[
#                 {"code": "IPC", "name": "Indian Penal Code, 1860"},
#                 {"code": "BNS", "name": "Bharatiya Nyaya Sanhita, 2023"},
#             ],
#         )
#     print("Act nodes ensured: IPC, BNS.")


# def ingest_chapters(driver, bns: dict[str, dict]) -> int:
#     chapters = {}
#     for row in bns.values():
#         if not row["chapter_raw"]:
#             continue
#         cid = stable_id("BNS", row["chapter_raw"])
#         chapters[cid] = {
#             "id": cid,
#             "act": "BNS",
#             "number": row["chapter_number"],
#             "title": row["chapter_title"],
#             "raw": row["chapter_raw"],
#         }

#     payload = list(chapters.values())
#     with driver.session() as session:
#         for batch in batched(payload, BATCH_SIZE):
#             session.run(
#                 """
#                 UNWIND $rows AS row
#                 MERGE (c:Chapter {id: row.id})
#                 SET c.act = row.act, c.number = row.number,
#                     c.title = row.title, c.raw = row.raw
#                 WITH c, row
#                 MATCH (a:Act {code: row.act})
#                 MERGE (a)-[:HAS_CHAPTER]->(c)
#                 """,
#                 rows=batch,
#             )
#     print(f"Chapter nodes ensured: {len(payload)} (BNS only — no chapter data in the IPC source CSVs).")
#     return len(payload)


# def ingest_law_sections(driver, ipc: dict[str, dict], bns: dict[str, dict]) -> None:
#     ipc_rows = []
#     for r in ipc.values():
#         ipc_rows.append({
#             "id": f"IPC_{r['section']}",
#             "act": "IPC",
#             "section": r["section"],
#             "title": r["title"],
#             "description": r["description"],
#             "punishment": r["punishment"],
#             "cognizable": r["cognizable"],
#             "bailable": r["bailable"],
#             "court": r["court"],
#             "data_complete": r["data_complete"],
#         })

#     bns_rows = []
#     for r in bns.values():
#         bns_rows.append({
#             "id": f"BNS_{r['section']}",
#             "act": "BNS",
#             "section": r["section"],
#             "title": r["title"],
#             "description": r["description"],
#             "punishment": r["punishment"],
#             "category": r["category"],
#             "keywords": r["keywords"],
#             "chapter_id": stable_id("BNS", r["chapter_raw"]) if r["chapter_raw"] else None,
#             "data_complete": r["data_complete"],
#         })

#     with driver.session() as session:
#         for batch in batched(ipc_rows, BATCH_SIZE):
#             session.run(
#                 """
#                 UNWIND $rows AS row
#                 MERGE (l:LawSection {id: row.id})
#                 SET l.act = row.act, l.section = row.section, l.title = row.title,
#                     l.description = row.description, l.punishment = row.punishment,
#                     l.cognizable = row.cognizable, l.bailable = row.bailable,
#                     l.court = row.court, l.data_complete = row.data_complete
#                 WITH l, row
#                 MATCH (a:Act {code: row.act})
#                 MERGE (a)-[:HAS_SECTION]->(l)
#                 """,
#                 rows=batch,
#             )

#         for batch in batched(bns_rows, BATCH_SIZE):
#             session.run(
#                 """
#                 UNWIND $rows AS row
#                 MERGE (l:LawSection {id: row.id})
#                 SET l.act = row.act, l.section = row.section, l.title = row.title,
#                     l.description = row.description, l.punishment = row.punishment,
#                     l.category = row.category, l.keywords = row.keywords,
#                     l.data_complete = row.data_complete
#                 WITH l, row
#                 MATCH (a:Act {code: row.act})
#                 MERGE (a)-[:HAS_SECTION]->(l)
#                 WITH l, row
#                 CALL {
#                     WITH l, row
#                     WITH l, row WHERE row.chapter_id IS NOT NULL
#                     MATCH (c:Chapter {id: row.chapter_id})
#                     MERGE (c)-[:HAS_SECTION]->(l)
#                     RETURN count(*) AS linked
#                 }
#                 RETURN count(*)
#                 """,
#                 rows=batch,
#             )
#     print(f"LawSection nodes ensured: {len(ipc_rows)} IPC + {len(bns_rows)} BNS.")


# def ingest_punishments(driver, ipc: dict[str, dict], bns: dict[str, dict]) -> int:
#     rows = []
#     for r in list(ipc.values()) + list(bns.values()):
#         text = r["punishment"]
#         if not text:
#             continue
#         rows.append({
#             "law_id": f"{r['act']}_{r['section']}",
#             "punishment_id": stable_id("PUNISHMENT", text),
#             "text": text,
#         })

#     with driver.session() as session:
#         for batch in batched(rows, BATCH_SIZE):
#             session.run(
#                 """
#                 UNWIND $rows AS row
#                 MERGE (p:Punishment {id: row.punishment_id})
#                 SET p.text = row.text
#                 WITH p, row
#                 MATCH (l:LawSection {id: row.law_id})
#                 MERGE (l)-[:HAS_PUNISHMENT]->(p)
#                 """,
#                 rows=batch,
#             )
#     distinct = len({r["punishment_id"] for r in rows})
#     print(f"Punishment nodes ensured: {distinct} distinct punishment texts, {len(rows)} HAS_PUNISHMENT edges.")
#     return distinct


# def ingest_mappings(driver, mappings: list[dict]) -> None:
#     rows = []
#     ipc_only = bns_only = both = 0
#     for m in mappings:
#         ipc_id = f"IPC_{m['ipc_section']}" if m["ipc_section"] else None
#         bns_id = f"BNS_{m['bns_section']}" if m["bns_section"] else None
#         if ipc_id and bns_id:
#             both += 1
#             rows.append({"ipc_id": ipc_id, "bns_id": bns_id, "status": m["status"]})
#         elif ipc_id and not bns_id:
#             ipc_only += 1  # deleted, no successor — recorded as a property below
#         elif bns_id and not ipc_id:
#             bns_only += 1  # brand-new BNS section — recorded as a property below

#     with driver.session() as session:
#         for batch in batched(rows, BATCH_SIZE):
#             session.run(
#                 """
#                 UNWIND $rows AS row
#                 MATCH (i:LawSection {id: row.ipc_id})
#                 MATCH (b:LawSection {id: row.bns_id})
#                 MERGE (i)-[r1:REPLACED_BY]->(b)
#                 SET r1.status = row.status
#                 MERGE (b)-[r2:REPLACES]->(i)
#                 SET r2.status = row.status
#                 """,
#                 rows=batch,
#             )

#         # Tag sections with no counterpart instead of leaving them silently unlinked
#         session.run(
#             """
#             UNWIND $ids AS id
#             MATCH (l:LawSection {id: id})
#             SET l.mapping_status = 'deleted_no_bns_successor'
#             """,
#             ids=[f"IPC_{m['ipc_section']}" for m in mappings
#                  if m["ipc_section"] and not m["bns_section"]],
#         )
#         session.run(
#             """
#             UNWIND $ids AS id
#             MATCH (l:LawSection {id: id})
#             SET l.mapping_status = 'new_no_ipc_predecessor'
#             """,
#             ids=[f"BNS_{m['bns_section']}" for m in mappings
#                  if m["bns_section"] and not m["ipc_section"]],
#         )

#     print(f"Mapping edges ensured: {both} IPC<->BNS pairs linked "
#           f"(REPLACED_BY / REPLACES), {ipc_only} IPC sections tagged as deleted, "
#           f"{bns_only} BNS sections tagged as new.")


# def print_summary(driver) -> None:
#     queries = {
#         "Act nodes": "MATCH (a:Act) RETURN count(a) AS c",
#         "Chapter nodes": "MATCH (c:Chapter) RETURN count(c) AS c",
#         "LawSection nodes (IPC)": "MATCH (l:LawSection {act:'IPC'}) RETURN count(l) AS c",
#         "LawSection nodes (BNS)": "MATCH (l:LawSection {act:'BNS'}) RETURN count(l) AS c",
#         "Punishment nodes": "MATCH (p:Punishment) RETURN count(p) AS c",
#         "HAS_CHAPTER edges": "MATCH ()-[r:HAS_CHAPTER]->() RETURN count(r) AS c",
#         "HAS_SECTION edges": "MATCH ()-[r:HAS_SECTION]->() RETURN count(r) AS c",
#         "HAS_PUNISHMENT edges": "MATCH ()-[r:HAS_PUNISHMENT]->() RETURN count(r) AS c",
#         "REPLACED_BY edges (IPC->BNS)": "MATCH ()-[r:REPLACED_BY]->() RETURN count(r) AS c",
#         "IPC sections marked deleted": "MATCH (l:LawSection {mapping_status:'deleted_no_bns_successor'}) RETURN count(l) AS c",
#         "BNS sections marked new": "MATCH (l:LawSection {mapping_status:'new_no_ipc_predecessor'}) RETURN count(l) AS c",
#         "IPC stub sections (data_complete=false)": "MATCH (l:LawSection {act:'IPC', data_complete:false}) RETURN count(l) AS c",
#     }
#     print("\n--- Graph summary ---")
#     with driver.session() as session:
#         for label, q in queries.items():
#             result = session.run(q).single()
#             print(f"  {label}: {result['c']}")


# # ----------------------------------------------------------------------
# # Pinecone (unchanged in spirit from v1, extended to cover stub/mapping data)
# # ----------------------------------------------------------------------
# def ingest_pinecone(ipc: dict[str, dict], bns: dict[str, dict]) -> int:
#     from sentence_transformers import SentenceTransformer
#     from pinecone import Pinecone, ServerlessSpec

#     if not PINECONE_API_KEY:
#         print("Skipping Pinecone: PINECONE_API_KEY not set")
#         return 0

#     print("Loading embedding model (all-MiniLM-L6-v2)...")
#     model = SentenceTransformer("all-MiniLM-L6-v2")
#     pc = Pinecone(api_key=PINECONE_API_KEY)

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
#     uploaded = 0

#     for r in list(ipc.values()) + list(bns.values()):
#         if not r["data_complete"] or not r["description"]:
#             continue  # don't embed stub sections with no real content
#         text = (
#             f"Act: {r['act']}\nSection: {r['section']}\nTitle:\n{r['title']}\n\n"
#             f"Description:\n{r['description']}\n\nPunishment:\n{r['punishment']}\n\n"
#             f"Chapter:\n{r.get('chapter_title', '')}"
#         )
#         embedding = model.encode(text).tolist()
#         vectors.append((
#             f"{r['act']}_{r['section']}",
#             embedding,
#             {
#                 "act": r["act"],
#                 "section": r["section"],
#                 "title": r["title"],
#                 "punishment": r["punishment"],
#                 "chapter": r.get("chapter_title", ""),
#             },
#         ))
#         if len(vectors) >= 100:
#             index.upsert(vectors=vectors)
#             uploaded += len(vectors)
#             vectors.clear()

#     if vectors:
#         index.upsert(vectors=vectors)
#         uploaded += len(vectors)

#     print(f"Uploaded {uploaded} vectors to Pinecone.")
#     return uploaded


# # ----------------------------------------------------------------------
# # Main
# # ----------------------------------------------------------------------
# def main() -> None:
#     parser = argparse.ArgumentParser(description="LexiGraph Neo4j ingest v1.1 (Chapters + IPC<->BNS mapping)")
#     parser.add_argument("--csv-dir", type=Path, default=DEFAULT_CSV_DIR, help="Directory containing the 4 source CSVs")
#     parser.add_argument("--wipe", action="store_true", help="Wipe the graph before ingesting")
#     parser.add_argument("--pinecone", action="store_true", help="Also (re)embed sections into Pinecone")
#     parser.add_argument("--dry-run", action="store_true", help="Parse & validate CSVs only, skip all DB writes")
#     args = parser.parse_args()

#     print(f"CSV directory: {args.csv_dir}")
#     print("\n--- Loading & reconciling CSVs ---")
#     ipc = load_ipc_sections(args.csv_dir)
#     bns = load_bns_sections(args.csv_dir)
#     mappings = load_mapping(args.csv_dir, ipc, bns)

#     if args.dry_run:
#         print("\n--dry-run set: skipping Neo4j/Pinecone writes.")
#         print(f"Would ingest: {len(ipc)} IPC sections, {len(bns)} BNS sections, "
#               f"{len(mappings)} mapping rows.")
#         return

#     driver = get_driver()
#     try:
#         if args.wipe:
#             wipe_graph(driver)

#         print("\n--- Neo4j ingestion ---")
#         create_constraints(driver)
#         ingest_acts(driver)
#         ingest_chapters(driver, bns)
#         ingest_law_sections(driver, ipc, bns)
#         ingest_punishments(driver, ipc, bns)
#         ingest_mappings(driver, mappings)
#         print_summary(driver)
#     finally:
#         driver.close()

#     if args.pinecone:
#         print("\n--- Pinecone ingestion ---")
#         ingest_pinecone(ipc, bns)

#     print("\nDone.")


# if __name__ == "__main__":
#     main()
"""
LexiGraph — Sprint 5: Knowledge Graph v1.1 Ingest Script
=========================================================

Builds on the existing Version 1 graph (Act -HAS_SECTION-> LawSection,
Crime -DEFINED_BY-> LawSection) WITHOUT redesigning it. This script adds the
next two items from the roadmap's priority list, plus a low-risk third:

  Priority 1 — Chapter nodes
      (Act)-[:HAS_CHAPTER]->(Chapter)-[:HAS_SECTION]->(LawSection)
      Chapter data only exists for BNS in the source CSVs, so IPC sections
      are still attached directly via (Act)-[:HAS_SECTION]->(LawSection) —
      the same edge Version 1 already used — for backward compatibility.

  Priority 2 — IPC <-> BNS mapping
      (:LawSection {act:'IPC'})-[:REPLACED_BY {status}]->(:LawSection {act:'BNS'})
      (:LawSection {act:'BNS'})-[:REPLACES {status}]->(:LawSection {act:'IPC'})
      Built from BNS_IPC_Comparative.csv. Deleted IPC sections (no BNS
      successor) and brand-new BNS sections (no IPC predecessor) are kept as
      properties instead of dangling edges — see `mapping_status` below.

  Priority 3 (partial) — Punishment nodes
      (LawSection)-[:HAS_PUNISHMENT]->(Punishment {text})
      Only the punishment string itself is lifted into a node (deduplicated
      by exact text). Ingredient / EvidenceType / LandmarkCase nodes are
      NOT built here — those require legal NLP/LLM extraction, not a CSV
      merge, and fabricating them from this data would risk exactly the
      "IPC section hallucination" problem the project already fixed once.
      They stay as a Sprint 6+ task in the roadmap.

  Priority 4 — Crime nodes
      (Crime {name})-[:DEFINED_BY]->(LawSection)
      Built from each section's existing title/offense text, deduplicated
      by exact name (same approach as Punishment). No new data is invented.

Data reconciliation
--------------------
Two IPC sources are provided and were found to cover the exact same 442
IPC sections, but with complementary gaps:
  - ipc_complete_datatset.csv : richer description, has Cognizable/
    Bailable/Court, but 63 rows missing Offense/Punishment
  - ipc_sections.csv          : same content, 58/59 rows missing
    Offense/Punishment (a different set of rows than the file above)
They are merged section-by-section, filling gaps from whichever file has
the value. 5 Offense values and 4 Punishment values are only recoverable
because both files are used together.

BNS_IPC_Comparative.csv references 549 distinct IPC sections, but the two
IPC CSVs above only contain full detail for 427 of them. The remaining 122
sections (e.g. old IPC 1, 10, 100, 101...) are added as *stub* LawSection
nodes using only the title from the comparative file, tagged
`data_complete: false`, so the mapping graph stays connected without
inventing description/punishment text that isn't in any source file.

All BNS sections referenced by the comparative file (358) are fully
covered by bns_sections_clean.csv — no BNS stubs are needed.

Usage
-----
    python ingest_neo4j_v2.py                # ingest into Neo4j only
    python ingest_neo4j_v2.py --wipe          # wipe graph first, then ingest
    python ingest_neo4j_v2.py --pinecone      # also (re)embed into Pinecone
    python ingest_neo4j_v2.py --csv-dir DIR   # CSVs live somewhere else
    python ingest_neo4j_v2.py --dry-run       # parse + validate CSVs only, no DB writes
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import re
import sys
from pathlib import Path
from typing import Any

# ----------------------------------------------------------------------
# Paths / env
# ----------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent

# Try to find .env in:
# 1. BASE_DIR.parent (backend/)
# 2. BASE_DIR.parent.parent (MootCourt/ root)
# 3. BASE_DIR (scripts/)
# 4. Current working directory
env_candidates = [
    BASE_DIR.parent / ".env",
    BASE_DIR.parent.parent / ".env",
    BASE_DIR / ".env",
    Path(".env")
]
ENV_PATH = None
for candidate in env_candidates:
    if candidate.exists():
        ENV_PATH = candidate
        break

try:
    from dotenv import load_dotenv
    if ENV_PATH:
        load_dotenv(ENV_PATH)
    else:
        load_dotenv()
except ImportError:
    pass

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = "legal-embeddings"

BATCH_SIZE = 500

# Try to find data/new in:
# 1. BASE_DIR.parent.parent / "data" / "new" (MootCourt/data/new)
# 2. BASE_DIR.parent / "data" / "new" (backend/data/new)
# 3. BASE_DIR / "data" / "new"
# 4. Path("data/new") relative to CWD
csv_dir_candidates = [
    BASE_DIR.parent.parent / "data" / "new",
    BASE_DIR.parent / "data" / "new",
    BASE_DIR / "data" / "new",
    Path("data/new")
]
DEFAULT_CSV_DIR = None
for candidate in csv_dir_candidates:
    if candidate.exists() and candidate.is_dir():
        DEFAULT_CSV_DIR = candidate
        break
if not DEFAULT_CSV_DIR:
    DEFAULT_CSV_DIR = BASE_DIR.parent.parent / "data" / "new"


# CSV filenames expected inside --csv-dir (defaults to this file's directory)
IPC_DETAIL_CSV = "ipc_complete_datatset.csv"      # URL, Description, Offense, Punishment, Cognizable, Bailable, Court
IPC_ALT_CSV = "ipc_sections.csv"                  # Description, Offense, Punishment, Section
BNS_CSV = "bns_sections_clean.csv"                # Section, Title, Description, Punishment, Chapter, Category, Keywords
MAPPING_CSV = "BNS_IPC_Comparative.csv"           # BNS_Section, BNS_Title, Status, IPC_Section, IPC_Title


# ----------------------------------------------------------------------
# Small utilities
# ----------------------------------------------------------------------
def clean(value: Any) -> str:
    """Normalise a CSV cell: strip whitespace, collapse newlines, drop NaN-ish values."""
    if value is None:
        return ""
    value = str(value).strip().strip('"').strip()
    if value.lower() in ("nan", "none", "n/a", ""):
        return ""
    return re.sub(r"\s+", " ", value)


def stable_id(*parts: str) -> str:
    """Deterministic short id for nodes that dedupe on content rather than a natural key."""
    raw = "|".join(parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def extract_ipc_section_from_url(url: str) -> str | None:
    m = re.search(r"section-(\d+[A-Za-z]*)", str(url))
    return m.group(1) if m else None


def extract_ipc_section_from_field(section_field: str) -> str | None:
    m = re.search(r"(\d+[A-Za-z]*)", str(section_field).replace("IPC_", ""))
    return m.group(1) if m else None


def extract_ipc_section_generic(value: str) -> str | None:
    """Used for the comparative CSV's IPC_Section column, e.g. '120B', '302'."""
    if not value:
        return None
    m = re.match(r"\s*(\d+[A-Za-z]*)", str(value))
    return m.group(1) if m else None


def extract_bns_base_section(value: str) -> int | None:
    """'1(2)' -> 1, '101' -> 101. BNS sections in the KG are stored at the
    base-section granularity (matching bns_sections_clean.csv); sub-section
    detail from the comparative file is not modeled as separate nodes."""
    if value is None:
        return None
    m = re.match(r"\s*(\d+)", str(value))
    return int(m.group(1)) if m else None


def parse_chapter(raw_chapter: str) -> tuple[str, str]:
    """'Chapter I: Preliminary' -> ('I', 'Preliminary')."""
    m = re.match(r"Chapter\s+([IVXLCDM]+)\s*:\s*(.+)", raw_chapter.strip())
    if m:
        return m.group(1), m.group(2).strip()
    return "", raw_chapter.strip()


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        print(f"  WARNING: file not found: {path}")
        return []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


# ----------------------------------------------------------------------
# IPC loading — merge the two source files, fill gaps from either side
# ----------------------------------------------------------------------
def load_ipc_sections(csv_dir: Path) -> dict[str, dict]:
    detail_rows = read_csv(csv_dir / IPC_DETAIL_CSV)
    alt_rows = read_csv(csv_dir / IPC_ALT_CSV)

    ipc: dict[str, dict] = {}

    for row in detail_rows:
        sec = extract_ipc_section_from_url(row.get("URL", ""))
        if not sec:
            continue
        ipc[sec] = {
            "act": "IPC",
            "section": sec,
            "title": clean(row.get("Offense")),
            "description": clean(row.get("Description")),
            "punishment": clean(row.get("Punishment")),
            "cognizable": clean(row.get("Cognizable")),
            "bailable": clean(row.get("Bailable")),
            "court": clean(row.get("Court")),
            "data_complete": True,
        }

    filled_offense = filled_punishment = added_from_alt = 0
    for row in alt_rows:
        sec = extract_ipc_section_from_field(row.get("Section", ""))
        if not sec:
            continue
        alt_title = clean(row.get("Offense"))
        alt_desc = clean(row.get("Description"))
        alt_punish = clean(row.get("Punishment"))

        if sec not in ipc:
            ipc[sec] = {
                "act": "IPC",
                "section": sec,
                "title": alt_title,
                "description": alt_desc,
                "punishment": alt_punish,
                "cognizable": "",
                "bailable": "",
                "court": "",
                "data_complete": True,
            }
            added_from_alt += 1
            continue

        existing = ipc[sec]
        if not existing["title"] and alt_title:
            existing["title"] = alt_title
            filled_offense += 1
        if not existing["description"] and alt_desc:
            existing["description"] = alt_desc
        if not existing["punishment"] and alt_punish:
            existing["punishment"] = alt_punish
            filled_punishment += 1

    # Fall back to description as title if Offense/title is still empty
    for sec, row in ipc.items():
        if not row["title"] and row["description"]:
            row["title"] = row["description"][:80]

    print(f"  IPC: {len(detail_rows)} detail rows + {len(alt_rows)} alt rows "
          f"-> {len(ipc)} unique sections "
          f"({added_from_alt} added from alt-only, "
          f"{filled_offense} titles / {filled_punishment} punishments backfilled)")
    return ipc


# ----------------------------------------------------------------------
# BNS loading — already clean, one row per section
# ----------------------------------------------------------------------
def load_bns_sections(csv_dir: Path) -> dict[str, dict]:
    rows = read_csv(csv_dir / BNS_CSV)
    bns: dict[str, dict] = {}
    for row in rows:
        sec_raw = clean(row.get("Section"))
        if not sec_raw:
            continue
        sec = str(int(sec_raw)) if sec_raw.isdigit() else sec_raw
        chapter_raw = clean(row.get("Chapter"))
        chapter_num, chapter_title = parse_chapter(chapter_raw) if chapter_raw else ("", "")
        bns[sec] = {
            "act": "BNS",
            "section": sec,
            "title": clean(row.get("Title")),
            "description": clean(row.get("Description")),
            "punishment": clean(row.get("Punishment")),
            "chapter_raw": chapter_raw,
            "chapter_number": chapter_num,
            "chapter_title": chapter_title,
            "category": clean(row.get("Category")),
            "keywords": clean(row.get("Keywords")),
            "data_complete": True,
        }
    print(f"  BNS: {len(rows)} rows -> {len(bns)} unique sections")
    return bns


# ----------------------------------------------------------------------
# Mapping loading — also produces IPC stub sections for the roadmap's
# "IPC should NOT be removed" requirement when detail rows don't exist
# ----------------------------------------------------------------------
def load_mapping(csv_dir: Path, ipc: dict[str, dict], bns: dict[str, dict]) -> list[dict]:
    rows = read_csv(csv_dir / MAPPING_CSV)
    mappings = []
    stubs_added = 0
    skipped_no_bns_node = 0

    for row in rows:
        bns_raw = clean(row.get("BNS_Section"))
        ipc_raw = clean(row.get("IPC_Section"))
        status_raw = clean(row.get("Status")) or "Unchanged"
        bns_title = clean(row.get("BNS_Title"))
        ipc_title = clean(row.get("IPC_Title"))

        bns_sec = str(extract_bns_base_section(bns_raw)) if bns_raw else None
        ipc_sec = extract_ipc_section_generic(ipc_raw) if ipc_raw else None

        # Ensure an IPC stub node exists so the section is represented even
        # without full detail (Description/Punishment stay empty on purpose).
        if ipc_sec and ipc_sec not in ipc:
            ipc[ipc_sec] = {
                "act": "IPC",
                "section": ipc_sec,
                "title": ipc_title,
                "description": "",
                "punishment": "",
                "cognizable": "",
                "bailable": "",
                "court": "",
                "data_complete": False,
            }
            stubs_added += 1

        if bns_sec and bns_sec not in bns:
            # Every BNS section in the mapping file was found to exist in
            # bns_sections_clean.csv already; this branch only triggers if
            # a differently-versioned BNS CSV is swapped in later.
            skipped_no_bns_node += 1
            bns_sec = None

        if not ipc_sec and not bns_sec:
            continue  # can't link or stub anything useful from this row

        mappings.append({
            "ipc_section": ipc_sec,
            "bns_section": bns_sec,
            "status": status_raw,
            "bns_title_hint": bns_title,
            "ipc_title_hint": ipc_title,
        })

    print(f"  Mapping: {len(rows)} rows -> {len(mappings)} usable mapping rows "
          f"({stubs_added} IPC stub sections added, {skipped_no_bns_node} rows skipped: BNS section not found)")
    return mappings


# ----------------------------------------------------------------------
# Neo4j ingestion
# ----------------------------------------------------------------------
def get_driver():
    from neo4j import GraphDatabase

    if not NEO4J_URI or not NEO4J_USER or not NEO4J_PASSWORD:
        raise ValueError(
            "Neo4j credentials not found. Set NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD "
            f"(checked {ENV_PATH})."
        )
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def wipe_graph(driver) -> None:
    print("Wiping existing graph (all nodes/relationships)...")
    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")


def create_constraints(driver) -> None:
    statements = [
        "CREATE CONSTRAINT act_code IF NOT EXISTS FOR (a:Act) REQUIRE a.code IS UNIQUE",
        "CREATE CONSTRAINT lawsection_id IF NOT EXISTS FOR (l:LawSection) REQUIRE l.id IS UNIQUE",
        "CREATE CONSTRAINT chapter_id IF NOT EXISTS FOR (c:Chapter) REQUIRE c.id IS UNIQUE",
        "CREATE CONSTRAINT punishment_id IF NOT EXISTS FOR (p:Punishment) REQUIRE p.id IS UNIQUE",
        "CREATE CONSTRAINT crime_id IF NOT EXISTS FOR (c:Crime) REQUIRE c.id IS UNIQUE",
        "CREATE CONSTRAINT rule_id IF NOT EXISTS FOR (r:LegalRule) REQUIRE r.id IS UNIQUE",
    ]
    with driver.session() as session:
        for stmt in statements:
            session.run(stmt)
    print("Constraints ensured (Act.code, LawSection.id, Chapter.id, Punishment.id, Crime.id, LegalRule.id).")


def batched(iterable: list, size: int):
    for i in range(0, len(iterable), size):
        yield iterable[i:i + size]


def ingest_acts(driver) -> None:
    with driver.session() as session:
        session.run(
            """
            UNWIND $acts AS act
            MERGE (a:Act {code: act.code})
            SET a.name = act.name
            """,
            acts=[
                {"code": "IPC", "name": "Indian Penal Code, 1860"},
                {"code": "BNS", "name": "Bharatiya Nyaya Sanhita, 2023"},
            ],
        )
    print("Act nodes ensured: IPC, BNS.")


def ingest_chapters(driver, bns: dict[str, dict]) -> int:
    chapters = {}
    for row in bns.values():
        if not row["chapter_raw"]:
            continue
        cid = stable_id("BNS", row["chapter_raw"])
        chapters[cid] = {
            "id": cid,
            "act": "BNS",
            "number": row["chapter_number"],
            "title": row["chapter_title"],
            "raw": row["chapter_raw"],
        }

    payload = list(chapters.values())
    with driver.session() as session:
        for batch in batched(payload, BATCH_SIZE):
            session.run(
                """
                UNWIND $rows AS row
                MERGE (c:Chapter {id: row.id})
                SET c.act = row.act, c.number = row.number,
                    c.title = row.title, c.raw = row.raw
                WITH c, row
                MATCH (a:Act {code: row.act})
                MERGE (a)-[:HAS_CHAPTER]->(c)
                """,
                rows=batch,
            )
    print(f"Chapter nodes ensured: {len(payload)} (BNS only — no chapter data in the IPC source CSVs).")
    return len(payload)


def ingest_law_sections(driver, ipc: dict[str, dict], bns: dict[str, dict]) -> None:
    ipc_rows = []
    for r in ipc.values():
        ipc_rows.append({
            "id": f"IPC_{r['section']}",
            "act": "IPC",
            "section": r["section"],
            "title": r["title"],
            "description": r["description"],
            "punishment": r["punishment"],
            "cognizable": r["cognizable"],
            "bailable": r["bailable"],
            "court": r["court"],
            "data_complete": r["data_complete"],
        })

    bns_rows = []
    for r in bns.values():
        bns_rows.append({
            "id": f"BNS_{r['section']}",
            "act": "BNS",
            "section": r["section"],
            "title": r["title"],
            "description": r["description"],
            "punishment": r["punishment"],
            "category": r["category"],
            "keywords": r["keywords"],
            "chapter_id": stable_id("BNS", r["chapter_raw"]) if r["chapter_raw"] else None,
            "data_complete": r["data_complete"],
        })

    with driver.session() as session:
        for batch in batched(ipc_rows, BATCH_SIZE):
            session.run(
                """
                UNWIND $rows AS row
                MERGE (l:LawSection {id: row.id})
                SET l.act = row.act, l.section = row.section, l.title = row.title,
                    l.description = row.description, l.punishment = row.punishment,
                    l.cognizable = row.cognizable, l.bailable = row.bailable,
                    l.court = row.court, l.data_complete = row.data_complete
                WITH l, row
                MATCH (a:Act {code: row.act})
                MERGE (a)-[:HAS_SECTION]->(l)
                """,
                rows=batch,
            )

        for batch in batched(bns_rows, BATCH_SIZE):
            session.run(
                """
                UNWIND $rows AS row
                MERGE (l:LawSection {id: row.id})
                SET l.act = row.act, l.section = row.section, l.title = row.title,
                    l.description = row.description, l.punishment = row.punishment,
                    l.category = row.category, l.keywords = row.keywords,
                    l.data_complete = row.data_complete
                WITH l, row
                MATCH (a:Act {code: row.act})
                MERGE (a)-[:HAS_SECTION]->(l)
                WITH l, row
                CALL {
                    WITH l, row
                    WITH l, row WHERE row.chapter_id IS NOT NULL
                    MATCH (c:Chapter {id: row.chapter_id})
                    MERGE (c)-[:HAS_SECTION]->(l)
                    RETURN count(*) AS linked
                }
                RETURN count(*)
                """,
                rows=batch,
            )
    print(f"LawSection nodes ensured: {len(ipc_rows)} IPC + {len(bns_rows)} BNS.")


def ingest_punishments(driver, ipc: dict[str, dict], bns: dict[str, dict]) -> int:
    rows = []
    for r in list(ipc.values()) + list(bns.values()):
        text = r["punishment"]
        if not text:
            continue
        rows.append({
            "law_id": f"{r['act']}_{r['section']}",
            "punishment_id": stable_id("PUNISHMENT", text),
            "text": text,
        })

    with driver.session() as session:
        for batch in batched(rows, BATCH_SIZE):
            session.run(
                """
                UNWIND $rows AS row
                MERGE (p:Punishment {id: row.punishment_id})
                SET p.text = row.text
                WITH p, row
                MATCH (l:LawSection {id: row.law_id})
                MERGE (l)-[:HAS_PUNISHMENT]->(p)
                """,
                rows=batch,
            )
    distinct = len({r["punishment_id"] for r in rows})
    print(f"Punishment nodes ensured: {distinct} distinct punishment texts, {len(rows)} HAS_PUNISHMENT edges.")
    return distinct


def ingest_crimes(driver, ipc: dict[str, dict], bns: dict[str, dict]) -> int:
    """(Crime {name})-[:DEFINED_BY]->(LawSection).

    The crime name is the section's existing title/offense text (Offense for
    IPC, Title for BNS) — no new data is invented. Deduplicated by exact
    title text, the same approach already used for Punishment nodes, so
    e.g. every IPC/BNS section titled "Murder" points at one Crime node.
    """
    rows = []
    for r in list(ipc.values()) + list(bns.values()):
        name = r["title"]
        if not name:
            continue
        rows.append({
            "law_id": f"{r['act']}_{r['section']}",
            "crime_id": stable_id("CRIME", name),
            "name": name,
        })

    with driver.session() as session:
        for batch in batched(rows, BATCH_SIZE):
            session.run(
                """
                UNWIND $rows AS row
                MERGE (c:Crime {id: row.crime_id})
                SET c.name = row.name
                WITH c, row
                MATCH (l:LawSection {id: row.law_id})
                MERGE (c)-[:DEFINED_BY]->(l)
                """,
                rows=batch,
            )
    distinct = len({r["crime_id"] for r in rows})
    print(f"Crime nodes ensured: {distinct} distinct crime names, {len(rows)} DEFINED_BY edges.")
    return distinct


def ingest_mappings(driver, mappings: list[dict]) -> None:
    rows = []
    ipc_only = bns_only = both = 0
    for m in mappings:
        ipc_id = f"IPC_{m['ipc_section']}" if m["ipc_section"] else None
        bns_id = f"BNS_{m['bns_section']}" if m["bns_section"] else None
        if ipc_id and bns_id:
            both += 1
            rows.append({"ipc_id": ipc_id, "bns_id": bns_id, "status": m["status"]})
        elif ipc_id and not bns_id:
            ipc_only += 1  # deleted, no successor — recorded as a property below
        elif bns_id and not ipc_id:
            bns_only += 1  # brand-new BNS section — recorded as a property below

    with driver.session() as session:
        for batch in batched(rows, BATCH_SIZE):
            session.run(
                """
                UNWIND $rows AS row
                MATCH (i:LawSection {id: row.ipc_id})
                MATCH (b:LawSection {id: row.bns_id})
                MERGE (i)-[r1:REPLACED_BY]->(b)
                SET r1.status = row.status
                MERGE (b)-[r2:REPLACES]->(i)
                SET r2.status = row.status
                """,
                rows=batch,
            )

        # Tag sections with no counterpart instead of leaving them silently unlinked
        session.run(
            """
            UNWIND $ids AS id
            MATCH (l:LawSection {id: id})
            SET l.mapping_status = 'deleted_no_bns_successor'
            """,
            ids=[f"IPC_{m['ipc_section']}" for m in mappings
                 if m["ipc_section"] and not m["bns_section"]],
        )
        session.run(
            """
            UNWIND $ids AS id
            MATCH (l:LawSection {id: id})
            SET l.mapping_status = 'new_no_ipc_predecessor'
            """,
            ids=[f"BNS_{m['bns_section']}" for m in mappings
                 if m["bns_section"] and not m["ipc_section"]],
        )

    print(f"Mapping edges ensured: {both} IPC<->BNS pairs linked "
          f"(REPLACED_BY / REPLACES), {ipc_only} IPC sections tagged as deleted, "
          f"{bns_only} BNS sections tagged as new.")


def ingest_reasoning_rules(driver) -> int:
    """Seed deterministic legal reasoning relationships.

    These are deliberately conservative and section-id based. The reasoning
    engine can use them explainably without relying on an LLM to invent legal
    precedence at runtime.
    """
    rules = [
        {
            "id": "ipc_364a_over_363",
            "source": "IPC_364A",
            "target": "IPC_363",
            "relationship": "OVERRIDES",
            "condition": "Kidnapping or abduction is alleged with ransom, hostage pressure, death threat, or hurt threat.",
            "confidence": 0.95,
        },
        {
            "id": "ipc_392_more_specific_390",
            "source": "IPC_392",
            "target": "IPC_390",
            "relationship": "MORE_SPECIFIC_THAN",
            "condition": "Robbery is punishable under IPC 392 after the definition under IPC 390 is satisfied.",
            "confidence": 0.9,
        },
        {
            "id": "ipc_302_more_specific_300",
            "source": "IPC_302",
            "target": "IPC_300",
            "relationship": "MORE_SPECIFIC_THAN",
            "condition": "Murder is punishable under IPC 302 after the definition under IPC 300 is satisfied.",
            "confidence": 0.92,
        },
        {
            "id": "ipc_302_over_304_when_intentional_death",
            "source": "IPC_302",
            "target": "IPC_304",
            "relationship": "OVERRIDES",
            "condition": "Intentional or knowledge-based killing facts support murder rather than culpable homicide not amounting to murder.",
            "confidence": 0.75,
        },
        {
            "id": "ipc_394_enhances_392",
            "source": "IPC_394",
            "target": "IPC_392",
            "relationship": "ENHANCES",
            "condition": "Voluntary hurt is caused while committing or attempting robbery.",
            "confidence": 0.88,
        },
        {
            "id": "ipc_397_enhances_392",
            "source": "IPC_397",
            "target": "IPC_392",
            "relationship": "ENHANCES",
            "condition": "Robbery or dacoity involves a deadly weapon, grievous hurt, or attempted death/grievous hurt.",
            "confidence": 0.88,
        },
        {
            "id": "ipc_395_more_specific_392",
            "source": "IPC_395",
            "target": "IPC_392",
            "relationship": "MORE_SPECIFIC_THAN",
            "condition": "Robbery is committed by five or more persons, making it dacoity.",
            "confidence": 0.9,
        },
        {
            "id": "ipc_396_enhances_395",
            "source": "IPC_396",
            "target": "IPC_395",
            "relationship": "ENHANCES",
            "condition": "Murder is committed by any one of five or more persons conjointly committing dacoity.",
            "confidence": 0.9,
        },
        {
            "id": "ipc_379_more_specific_378",
            "source": "IPC_379",
            "target": "IPC_378",
            "relationship": "MORE_SPECIFIC_THAN",
            "condition": "Theft is punishable under IPC 379 after the definition under IPC 378 is satisfied.",
            "confidence": 0.9,
        },
        {
            "id": "ipc_420_more_specific_415",
            "source": "IPC_420",
            "target": "IPC_415",
            "relationship": "MORE_SPECIFIC_THAN",
            "condition": "Cheating induces delivery of property or alteration/destruction of valuable security.",
            "confidence": 0.9,
        },
        {
            "id": "ipc_506_more_specific_503",
            "source": "IPC_506",
            "target": "IPC_503",
            "relationship": "MORE_SPECIFIC_THAN",
            "condition": "Criminal intimidation is punishable under IPC 506 after the definition under IPC 503 is satisfied.",
            "confidence": 0.9,
        },
    ]
    with driver.session() as session:
        for rel_type in {
            "OVERRIDES",
            "MORE_SPECIFIC_THAN",
            "INCLUDES_ELEMENTS_OF",
            "CANNOT_COEXIST_WITH",
            "ENHANCES",
        }:
            rel_rows = [r for r in rules if r["relationship"] == rel_type]
            if not rel_rows:
                continue
            session.run(
                f"""
                UNWIND $rows AS row
                MATCH (source:LawSection {{id: row.source}})
                MATCH (target:LawSection {{id: row.target}})
                MERGE (source)-[rel:{rel_type}]->(target)
                SET rel.rule_id = row.id,
                    rel.condition = row.condition,
                    rel.confidence = row.confidence
                MERGE (rule:LegalRule {{id: row.id}})
                SET rule.relationship = row.relationship,
                    rule.condition = row.condition,
                    rule.confidence = row.confidence
                MERGE (rule)-[:APPLIES_FROM]->(source)
                MERGE (rule)-[:APPLIES_TO]->(target)
                """,
                rows=rel_rows,
            )
    print(f"Reasoning rules ensured: {len(rules)} rules across precedence/enhancement relationships.")
    return len(rules)


def print_summary(driver) -> None:
    queries = {
        "Act nodes": "MATCH (a:Act) RETURN count(a) AS c",
        "Chapter nodes": "MATCH (c:Chapter) RETURN count(c) AS c",
        "LawSection nodes (IPC)": "MATCH (l:LawSection {act:'IPC'}) RETURN count(l) AS c",
        "LawSection nodes (BNS)": "MATCH (l:LawSection {act:'BNS'}) RETURN count(l) AS c",
        "Punishment nodes": "MATCH (p:Punishment) RETURN count(p) AS c",
        "Crime nodes": "MATCH (c:Crime) RETURN count(c) AS c",
        "HAS_CHAPTER edges": "MATCH ()-[r:HAS_CHAPTER]->() RETURN count(r) AS c",
        "HAS_SECTION edges": "MATCH ()-[r:HAS_SECTION]->() RETURN count(r) AS c",
        "HAS_PUNISHMENT edges": "MATCH ()-[r:HAS_PUNISHMENT]->() RETURN count(r) AS c",
        "DEFINED_BY edges": "MATCH ()-[r:DEFINED_BY]->() RETURN count(r) AS c",
        "REPLACED_BY edges (IPC->BNS)": "MATCH ()-[r:REPLACED_BY]->() RETURN count(r) AS c",
        "LegalRule nodes": "MATCH (r:LegalRule) RETURN count(r) AS c",
        "OVERRIDES edges": "MATCH ()-[r:OVERRIDES]->() RETURN count(r) AS c",
        "MORE_SPECIFIC_THAN edges": "MATCH ()-[r:MORE_SPECIFIC_THAN]->() RETURN count(r) AS c",
        "ENHANCES edges": "MATCH ()-[r:ENHANCES]->() RETURN count(r) AS c",
        "IPC sections marked deleted": "MATCH (l:LawSection {mapping_status:'deleted_no_bns_successor'}) RETURN count(l) AS c",
        "BNS sections marked new": "MATCH (l:LawSection {mapping_status:'new_no_ipc_predecessor'}) RETURN count(l) AS c",
        "IPC stub sections (data_complete=false)": "MATCH (l:LawSection {act:'IPC', data_complete:false}) RETURN count(l) AS c",
    }
    print("\n--- Graph summary ---")
    with driver.session() as session:
        for label, q in queries.items():
            result = session.run(q).single()
            print(f"  {label}: {result['c']}")


# ----------------------------------------------------------------------
# Pinecone (unchanged in spirit from v1, extended to cover stub/mapping data)
# ----------------------------------------------------------------------
def ingest_pinecone(ipc: dict[str, dict], bns: dict[str, dict]) -> int:
    from sentence_transformers import SentenceTransformer
    from pinecone import Pinecone, ServerlessSpec

    if not PINECONE_API_KEY:
        print("Skipping Pinecone: PINECONE_API_KEY not set")
        return 0

    print("Loading embedding model (all-MiniLM-L6-v2)...")
    model = SentenceTransformer("all-MiniLM-L6-v2")
    pc = Pinecone(api_key=PINECONE_API_KEY)

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
    uploaded = 0

    for r in list(ipc.values()) + list(bns.values()):
        if not r["data_complete"] or not r["description"]:
            continue  # don't embed stub sections with no real content
        text = (
            f"Act: {r['act']}\nSection: {r['section']}\nTitle:\n{r['title']}\n\n"
            f"Description:\n{r['description']}\n\nPunishment:\n{r['punishment']}\n\n"
            f"Chapter:\n{r.get('chapter_title', '')}"
        )
        embedding = model.encode(text).tolist()
        vectors.append((
            f"{r['act']}_{r['section']}",
            embedding,
            {
                "act": r["act"],
                "section": r["section"],
                "title": r["title"],
                "punishment": r["punishment"],
                "chapter": r.get("chapter_title", ""),
            },
        ))
        if len(vectors) >= 100:
            index.upsert(vectors=vectors)
            uploaded += len(vectors)
            vectors.clear()

    if vectors:
        index.upsert(vectors=vectors)
        uploaded += len(vectors)

    print(f"Uploaded {uploaded} vectors to Pinecone.")
    return uploaded


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="LexiGraph Neo4j ingest v1.1 (Chapters + IPC<->BNS mapping)")
    parser.add_argument("--csv-dir", type=Path, default=DEFAULT_CSV_DIR, help="Directory containing the 4 source CSVs")
    parser.add_argument("--wipe", action="store_true", help="Wipe the graph before ingesting")
    parser.add_argument("--pinecone", action="store_true", help="Also (re)embed sections into Pinecone")
    parser.add_argument("--dry-run", action="store_true", help="Parse & validate CSVs only, skip all DB writes")
    args = parser.parse_args()

    print(f"CSV directory: {args.csv_dir}")
    print("\n--- Loading & reconciling CSVs ---")
    ipc = load_ipc_sections(args.csv_dir)
    bns = load_bns_sections(args.csv_dir)
    mappings = load_mapping(args.csv_dir, ipc, bns)

    if args.dry_run:
        print("\n--dry-run set: skipping Neo4j/Pinecone writes.")
        print(f"Would ingest: {len(ipc)} IPC sections, {len(bns)} BNS sections, "
              f"{len(mappings)} mapping rows.")
        return

    driver = get_driver()
    try:
        if args.wipe:
            wipe_graph(driver)

        print("\n--- Neo4j ingestion ---")
        create_constraints(driver)
        ingest_acts(driver)
        ingest_chapters(driver, bns)
        ingest_law_sections(driver, ipc, bns)
        ingest_punishments(driver, ipc, bns)
        ingest_crimes(driver, ipc, bns)
        ingest_mappings(driver, mappings)
        ingest_reasoning_rules(driver)
        print_summary(driver)
    finally:
        driver.close()

    if args.pinecone:
        print("\n--- Pinecone ingestion ---")
        ingest_pinecone(ipc, bns)

    print("\nDone.")


if __name__ == "__main__":
    main()
