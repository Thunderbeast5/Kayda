"""
LexiGraph — Pinecone Ingest v2
================================
Standalone re-embedding script for the v2 data model (Chapters, IPC<->BNS
crosswalk, Punishment metadata). This is deliberately decoupled from
neo4j_v2.py's `ingest_pinecone()` — it is a full rebuild, not a patch:

  - New index name by default (legal-sections-v2) so it never touches or
    mixes with whatever is already sitting in the old "legal-embeddings"
    index. Old vectors are left alone unless you pass --wipe-old.
  - Richer embedding text per section: chapter, category, cognizable/
    bailable/court, AND the IPC<->BNS cross-reference (which the old
    embedding text never had, since it predates BNS_IPC_Comparative.csv
    being wired into the graph).
  - Same CSV reconciliation logic as neo4j_v2.py (load_ipc_sections /
    load_bns_sections / load_mapping), copied here rather than imported,
    so this script has no import-time dependency on the Neo4j script.

Usage
-----
    python pinecone_ingest_v2.py --dry-run              # inspect without any API calls
    python pinecone_ingest_v2.py                        # embed + upsert into legal-sections-v2
    python pinecone_ingest_v2.py --index-name my-index   # use a different index
    python pinecone_ingest_v2.py --wipe-old               # also delete the OLD "legal-embeddings" index
    python pinecone_ingest_v2.py --csv-dir /path/to/csvs
    python pinecone_ingest_v2.py --model BAAI/bge-small-en-v1.5   # swap embedding model
    python pinecone_ingest_v2.py --include-stubs          # also embed stub sections (title only, no description)

Requires: sentence-transformers, pinecone, python-dotenv (all already in
your existing environment per neo4j_v2.py).
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from pathlib import Path
from typing import Any

# ----------------------------------------------------------------------
# Paths / env
# ----------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent

env_candidates = [
    BASE_DIR.parent / ".env",
    BASE_DIR.parent.parent / ".env",
    BASE_DIR / ".env",
    Path(".env"),
]
ENV_PATH = next((c for c in env_candidates if c.exists()), None)

try:
    from dotenv import load_dotenv
    load_dotenv(ENV_PATH) if ENV_PATH else load_dotenv()
except ImportError:
    pass

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")

# Old index from ingest_neo4j.py / neo4j_v2.py — never written to by this
# script unless --wipe-old is explicitly passed.
OLD_INDEX_NAME = "legal-embeddings"

DEFAULT_INDEX_NAME = "legal-sections-v2"
DEFAULT_MODEL = "all-MiniLM-L6-v2"  # 384-dim, matches existing infra; override with --model

csv_dir_candidates = [
    BASE_DIR.parent.parent / "data" / "new",
    BASE_DIR.parent / "data" / "new",
    BASE_DIR / "data" / "new",
    Path("data/new"),
]
DEFAULT_CSV_DIR = next(
    (c for c in csv_dir_candidates if c.exists() and c.is_dir()),
    BASE_DIR.parent.parent / "data" / "new",
)

IPC_DETAIL_CSV = "ipc_complete_datatset.csv"
IPC_ALT_CSV = "ipc_sections.csv"
BNS_CSV = "bns_sections_clean.csv"
MAPPING_CSV = "BNS_IPC_Comparative.csv"


# ----------------------------------------------------------------------
# Small utilities (identical to neo4j_v2.py, copied to avoid coupling)
# ----------------------------------------------------------------------
def clean(value: Any) -> str:
    if value is None:
        return ""
    value = str(value).strip().strip('"').strip()
    if value.lower() in ("nan", "none", "n/a", ""):
        return ""
    return re.sub(r"\s+", " ", value)


def extract_ipc_section_from_url(url: str) -> str | None:
    m = re.search(r"section-(\d+[A-Za-z]*)", str(url))
    return m.group(1) if m else None


def extract_ipc_section_from_field(section_field: str) -> str | None:
    m = re.search(r"(\d+[A-Za-z]*)", str(section_field).replace("IPC_", ""))
    return m.group(1) if m else None


def extract_ipc_section_generic(value: str) -> str | None:
    if not value:
        return None
    m = re.match(r"\s*(\d+[A-Za-z]*)", str(value))
    return m.group(1) if m else None


def extract_bns_base_section(value: str) -> int | None:
    if value is None:
        return None
    m = re.match(r"\s*(\d+)", str(value))
    return int(m.group(1)) if m else None


def parse_chapter(raw_chapter: str) -> tuple[str, str]:
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


def batched(iterable: list, size: int):
    for i in range(0, len(iterable), size):
        yield iterable[i:i + size]


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

    added_from_alt = 0
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
        if not existing["description"] and alt_desc:
            existing["description"] = alt_desc
        if not existing["punishment"] and alt_punish:
            existing["punishment"] = alt_punish

    for sec, row in ipc.items():
        if not row["title"] and row["description"]:
            row["title"] = row["description"][:80]

    print(f"  IPC: {len(detail_rows)} detail rows + {len(alt_rows)} alt rows "
          f"-> {len(ipc)} unique sections ({added_from_alt} added from alt-only)")
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
# Mapping loading — produces IPC stub sections + the crosswalk used to
# enrich embedding text (this is the part the OLD embeddings never had)
# ----------------------------------------------------------------------
def load_mapping(csv_dir: Path, ipc: dict[str, dict], bns: dict[str, dict]) -> list[dict]:
    rows = read_csv(csv_dir / MAPPING_CSV)
    mappings = []
    stubs_added = 0

    for row in rows:
        bns_raw = clean(row.get("BNS_Section"))
        ipc_raw = clean(row.get("IPC_Section"))
        status_raw = clean(row.get("Status")) or "Unchanged"
        bns_title = clean(row.get("BNS_Title"))
        ipc_title = clean(row.get("IPC_Title"))

        bns_sec = str(extract_bns_base_section(bns_raw)) if bns_raw else None
        ipc_sec = extract_ipc_section_generic(ipc_raw) if ipc_raw else None

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
            bns_sec = None

        if not ipc_sec and not bns_sec:
            continue

        mappings.append({
            "ipc_section": ipc_sec,
            "bns_section": bns_sec,
            "status": status_raw,
            "bns_title_hint": bns_title,
            "ipc_title_hint": ipc_title,
        })

    print(f"  Mapping: {len(rows)} rows -> {len(mappings)} usable mapping rows "
          f"({stubs_added} IPC stub sections added)")
    return mappings


def build_crosswalk(mappings: list[dict]) -> tuple[dict[str, dict], dict[str, dict]]:
    """ipc_section -> {bns_section, status}, and the reverse."""
    ipc_to_bns: dict[str, dict] = {}
    bns_to_ipc: dict[str, dict] = {}
    for m in mappings:
        if m["ipc_section"] and m["bns_section"]:
            ipc_to_bns[m["ipc_section"]] = {"section": m["bns_section"], "status": m["status"]}
            bns_to_ipc[m["bns_section"]] = {"section": m["ipc_section"], "status": m["status"]}
        elif m["ipc_section"] and not m["bns_section"]:
            ipc_to_bns[m["ipc_section"]] = {"section": None, "status": "deleted_no_bns_successor"}
        elif m["bns_section"] and not m["ipc_section"]:
            bns_to_ipc[m["bns_section"]] = {"section": None, "status": "new_no_ipc_predecessor"}
    return ipc_to_bns, bns_to_ipc


# ----------------------------------------------------------------------
# Embedding text construction
# ----------------------------------------------------------------------
def build_embedding_text(r: dict, crosswalk: dict[str, dict]) -> str:
    lines = [f"Act: {r['act']}", f"Section: {r['section']}", f"Title: {r['title']}"]

    if r["act"] == "BNS" and r.get("chapter_title"):
        lines.append(f"Chapter: {r['chapter_title']}")
    if r["act"] == "BNS" and r.get("category"):
        lines.append(f"Category: {r['category']}")

    if r.get("description"):
        lines.append(f"\nDescription:\n{r['description']}")
    if r.get("punishment"):
        lines.append(f"\nPunishment:\n{r['punishment']}")

    if r["act"] == "IPC":
        if r.get("cognizable"):
            lines.append(f"Cognizable: {r['cognizable']}")
        if r.get("bailable"):
            lines.append(f"Bailable: {r['bailable']}")
        if r.get("court"):
            lines.append(f"Court: {r['court']}")

    xwalk = crosswalk.get(r["section"])
    if xwalk:
        other_act = "BNS" if r["act"] == "IPC" else "IPC"
        if xwalk["section"]:
            lines.append(f"\nEquivalent {other_act} section: {other_act} {xwalk['section']} "
                         f"(mapping status: {xwalk['status']})")
        else:
            lines.append(f"\nMapping status: {xwalk['status']}")

    if r["act"] == "BNS" and r.get("keywords"):
        lines.append(f"\nKeywords: {r['keywords']}")

    return "\n".join(lines)


def build_metadata(r: dict, crosswalk: dict[str, dict]) -> dict:
    xwalk = crosswalk.get(r["section"], {})
    meta = {
        "act": r["act"],
        "section": r["section"],
        "title": r["title"],
        "data_complete": r["data_complete"],
    }
    if r.get("punishment"):
        meta["punishment"] = r["punishment"][:500]  # Pinecone metadata size limits
    if r["act"] == "BNS":
        if r.get("chapter_title"):
            meta["chapter"] = r["chapter_title"]
        if r.get("category"):
            meta["category"] = r["category"]
    if r["act"] == "IPC":
        for k in ("cognizable", "bailable", "court"):
            if r.get(k):
                meta[k] = r[k]
    if xwalk.get("section"):
        other_act = "BNS" if r["act"] == "IPC" else "IPC"
        meta["equivalent_act"] = other_act
        meta["equivalent_section"] = xwalk["section"]
    if xwalk.get("status"):
        meta["mapping_status"] = xwalk["status"]
    return meta


# ----------------------------------------------------------------------
# Pinecone
# ----------------------------------------------------------------------
def get_pinecone_client():
    from pinecone import Pinecone
    if not PINECONE_API_KEY:
        raise ValueError("PINECONE_API_KEY not set (checked " + str(ENV_PATH) + ")")
    return Pinecone(api_key=PINECONE_API_KEY)


def ensure_index(pc, index_name: str, dimension: int, wipe: bool):
    from pinecone import ServerlessSpec

    existing = [idx.name for idx in pc.list_indexes()]
    if wipe and index_name in existing:
        print(f"--wipe set: deleting existing index '{index_name}'...")
        pc.delete_index(index_name)
        existing.remove(index_name)

    if index_name not in existing:
        print(f"Creating Pinecone index: {index_name} (dim={dimension})")
        pc.create_index(
            name=index_name,
            dimension=dimension,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
    return pc.Index(index_name)


def run_embedding(records: list[dict], crosswalk: dict[str, dict], model_name: str,
                   index_name: str, wipe: bool, batch_size: int, include_stubs: bool) -> int:
    from sentence_transformers import SentenceTransformer

    print(f"Loading embedding model: {model_name} ...")
    model = SentenceTransformer(model_name)
    dimension = model.get_sentence_embedding_dimension()

    pc = get_pinecone_client()
    index = ensure_index(pc, index_name, dimension, wipe)

    to_embed = []
    skipped = 0
    for r in records:
        if not r["data_complete"] and not include_stubs:
            skipped += 1
            continue
        if not r.get("description") and not include_stubs:
            skipped += 1
            continue
        to_embed.append(r)

    print(f"Embedding {len(to_embed)} sections ({skipped} skipped: no content; "
          f"pass --include-stubs to embed title-only stub sections)")

    vectors = []
    uploaded = 0
    for r in to_embed:
        text = build_embedding_text(r, crosswalk)
        embedding = model.encode(text).tolist()
        vectors.append((f"{r['act']}_{r['section']}", embedding, build_metadata(r, crosswalk)))

        if len(vectors) >= batch_size:
            index.upsert(vectors=vectors)
            uploaded += len(vectors)
            print(f"  upserted {uploaded}/{len(to_embed)}...")
            vectors.clear()

    if vectors:
        index.upsert(vectors=vectors)
        uploaded += len(vectors)

    print(f"Done: {uploaded} vectors upserted into '{index_name}' (dim={dimension}).")
    return uploaded


def wipe_old_index():
    """Explicit, opt-in deletion of the legacy index from ingest_neo4j.py / v1 pinecone runs."""
    pc = get_pinecone_client()
    existing = [idx.name for idx in pc.list_indexes()]
    if OLD_INDEX_NAME in existing:
        print(f"--wipe-old set: deleting legacy index '{OLD_INDEX_NAME}'...")
        pc.delete_index(OLD_INDEX_NAME)
    else:
        print(f"--wipe-old set but '{OLD_INDEX_NAME}' does not exist, nothing to do.")


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="LexiGraph Pinecone re-embed (v2 data model)")
    parser.add_argument("--csv-dir", type=Path, default=DEFAULT_CSV_DIR)
    parser.add_argument("--index-name", default=DEFAULT_INDEX_NAME,
                         help=f"Pinecone index to write to (default: {DEFAULT_INDEX_NAME})")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                         help=f"sentence-transformers model name (default: {DEFAULT_MODEL})")
    parser.add_argument("--wipe", action="store_true",
                         help="Delete and recreate --index-name before embedding")
    parser.add_argument("--wipe-old", action="store_true",
                         help=f"Also delete the legacy '{OLD_INDEX_NAME}' index (separate, explicit opt-in)")
    parser.add_argument("--include-stubs", action="store_true",
                         help="Also embed stub sections that have a title but no description")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true",
                         help="Parse + build embedding text only, no model load, no API calls")
    args = parser.parse_args()

    print(f"CSV directory: {args.csv_dir}")
    print("\n--- Loading & reconciling CSVs ---")
    ipc = load_ipc_sections(args.csv_dir)
    bns = load_bns_sections(args.csv_dir)
    mappings = load_mapping(args.csv_dir, ipc, bns)
    ipc_to_bns, bns_to_ipc = build_crosswalk(mappings)
    crosswalk = {**ipc_to_bns, **bns_to_ipc}

    records = list(ipc.values()) + list(bns.values())

    if args.dry_run:
        print(f"\n--dry-run set: {len(records)} total sections loaded "
              f"({len(ipc)} IPC, {len(bns)} BNS).")
        sample = next((r for r in records if r["data_complete"] and r["description"]), None)
        if sample:
            print("\nSample embedding text:\n" + "-" * 60)
            print(build_embedding_text(sample, crosswalk))
            print("-" * 60)
            print("\nSample metadata:")
            print(build_metadata(sample, crosswalk))
        return

    if args.wipe_old:
        wipe_old_index()

    run_embedding(records, crosswalk, args.model, args.index_name,
                  args.wipe, args.batch_size, args.include_stubs)

    print("\nDone.")


if __name__ == "__main__":
    main()