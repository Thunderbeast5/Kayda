"""
LexiGraph — Pinecone Ingest v2
================================
Standalone re-embedding script for the v2 data model (Chapters, Punishment
metadata, IPC/BNS/BNSS/CrPC/BSA/IEA sections). This is deliberately
decoupled from neo4j_v2.py's `ingest_pinecone()` — it is a full rebuild,
not a patch.

Usage
-----
    python pinecone_v2.py --dry-run              # inspect without any API calls
    python pinecone_v2.py                        # embed + upsert into the index
    python pinecone_v2.py --index-name my-index   # use a different index
    python pinecone_v2.py --csv-dir /path/to/csvs
    python pinecone_v2.py --model BAAI/bge-small-en-v1.5   # swap embedding model
    python pinecone_v2.py --include-stubs          # also embed stub sections (title only, no description)

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

DEFAULT_INDEX_NAME = "ipc"
DEFAULT_MODEL = "all-MiniLM-L6-v2"  # 384-dim, matches existing infra; override with --model

csv_dir_candidates = [
    BASE_DIR,  # <--- CSVs are right here in the pinecone folder!
    BASE_DIR.parent.parent / "data" / "new",
    BASE_DIR.parent / "data" / "new",
    Path("data/new"),
]
DEFAULT_CSV_DIR = next(
    (c for c in csv_dir_candidates if c.exists() and c.is_dir()),
    BASE_DIR,  # Fallback to current folder
)

# Updated to match exact filenames from your VS Code tree
IPC_DETAIL_CSV = "ipc_Sections.csv"
IPC_ALT_CSV = "ipc_Sections.csv"
BNS_CSV = "bns_Sections.csv"

# --- New acts -----------------------------------------------------------
BNSS_CSV = "BNSS_Sections.csv"  # Bharatiya Nagarik Suraksha Sanhita
CRPC_CSV = "CrPC_Sections.csv"  # Code of Criminal Procedure
BSA_CSV = "BSA_Sections.csv"    # Bharatiya Sakshya Adhiniyam
IEA_CSV = "IEA_Sections.csv"    # Indian Evidence Act


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

    boilerplate_re = re.compile(
        r"^Description of IPC Section \S+\s*According to section \S+ of Indian penal code,?\s*",
        re.IGNORECASE,
    )
    for sec, row in ipc.items():
        if not row["title"] and row["description"]:
            stripped = boilerplate_re.sub("", row["description"])
            row["title"] = stripped[:80].rsplit(" ", 1)[0]

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
# Generic act loader — for BNSS, CrPC, BSA, IEA, or any other simple
# one-row-per-section CSV. Auto-detects common column header names so it
# works without editing code, as long as your CSV has recognizable
# headers. If your CSV uses unusual headers, add them to the candidate
# lists below (first match wins).
# ----------------------------------------------------------------------
HEADER_CANDIDATES = {
    "section": ["Section", "Section Number", "Section_Number", "Sec", "Sec.", "Clause"],
    "title": ["Title", "Offense", "Offence", "Heading", "Section Title", "Name", "Subject"],
    "description": ["Description", "Content", "Text", "Provision", "Details"],
    "punishment": ["Punishment", "Penalty", "Sentence"],
    "chapter": ["Chapter"],
    "category": ["Category", "Type"],
    "keywords": ["Keywords", "Tags"],
}


def load_generic_act_sections(csv_dir: Path, filename: str | None, act_name: str) -> dict[str, dict]:
    if not filename:
        print(f"  {act_name}: no CSV configured, skipping.")
        return {}

    rows = read_csv(csv_dir / filename)
    if not rows:
        return {}

    headers = list(rows[0].keys())

    def find_header(field: str) -> str | None:
        for cand in HEADER_CANDIDATES[field]:
            for h in headers:
                if h and h.strip().lower() == cand.lower():
                    return h
        return None

    section_h = find_header("section")
    title_h = find_header("title")
    desc_h = find_header("description")
    punish_h = find_header("punishment")
    chapter_h = find_header("chapter")
    category_h = find_header("category")
    keywords_h = find_header("keywords")

    if not section_h:
        print(f"  WARNING: {act_name}: could not find a 'Section' column in {filename} "
              f"(headers found: {headers}). Add your header name to HEADER_CANDIDATES['section']. Skipping.")
        return {}

    out: dict[str, dict] = {}
    for row in rows:
        sec_raw = clean(row.get(section_h))
        if not sec_raw:
            continue
        sec = str(int(sec_raw)) if sec_raw.isdigit() else sec_raw

        chapter_raw = clean(row.get(chapter_h)) if chapter_h else ""
        chapter_num, chapter_title = parse_chapter(chapter_raw) if chapter_raw else ("", "")

        out[sec] = {
            "act": act_name,
            "section": sec,
            "title": clean(row.get(title_h)) if title_h else "",
            "description": clean(row.get(desc_h)) if desc_h else "",
            "punishment": clean(row.get(punish_h)) if punish_h else "",
            "chapter_raw": chapter_raw,
            "chapter_number": chapter_num,
            "chapter_title": chapter_title,
            "category": clean(row.get(category_h)) if category_h else "",
            "keywords": clean(row.get(keywords_h)) if keywords_h else "",
            "data_complete": True,
        }

    print(f"  {act_name}: {len(rows)} rows -> {len(out)} unique sections "
          f"(columns used: section={section_h!r}, title={title_h!r}, "
          f"description={desc_h!r}, chapter={chapter_h!r})")
    return out


# ----------------------------------------------------------------------
# Embedding text construction
# ----------------------------------------------------------------------
def build_embedding_text(r: dict) -> str:
    lines = [f"Act: {r['act']}", f"Section: {r['section']}", f"Title: {r['title']}"]

    if r.get("chapter_title"):
        lines.append(f"Chapter: {r['chapter_title']}")
    if r.get("category"):
        lines.append(f"Category: {r['category']}")

    if r.get("description"):
        lines.append(f"\nDescription:\n{r['description']}")
    if r.get("punishment"):
        lines.append(f"\nPunishment:\n{r['punishment']}")

    if r.get("cognizable"):
        lines.append(f"Cognizable: {r['cognizable']}")
    if r.get("bailable"):
        lines.append(f"Bailable: {r['bailable']}")
    if r.get("court"):
        lines.append(f"Court: {r['court']}")

    if r.get("keywords"):
        lines.append(f"\nKeywords: {r['keywords']}")

    return "\n".join(lines)


def build_metadata(r: dict) -> dict:
    meta = {
        "act": r["act"],
        "section": r["section"],
        "title": r["title"],
        "data_complete": r["data_complete"],
    }
    if r.get("punishment"):
        meta["punishment"] = r["punishment"][:500]  # Pinecone metadata size limits
    if r.get("chapter_title"):
        meta["chapter"] = r["chapter_title"]
    if r.get("category"):
        meta["category"] = r["category"]
    for k in ("cognizable", "bailable", "court"):
        if r.get(k):
            meta[k] = r[k]
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


def run_embedding(records: list[dict], model_name: str,
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
        text = build_embedding_text(r)
        embedding = model.encode(text).tolist()
        vectors.append((f"{r['act']}_{r['section']}", embedding, build_metadata(r)))

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


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="LexiGraph Pinecone re-embed (v2 data model)")
    parser.add_argument("--csv-dir", type=Path, default=DEFAULT_CSV_DIR,
                         help="Folder containing ALL the CSVs below (IPC, BNS, BNSS, CrPC, BSA, IEA)")
    parser.add_argument("--bnss-csv", default=BNSS_CSV,
                         help=f"BNSS CSV filename inside --csv-dir (default: {BNSS_CSV}). Pass '' to skip.")
    parser.add_argument("--crpc-csv", default=CRPC_CSV,
                         help=f"CrPC CSV filename inside --csv-dir (default: {CRPC_CSV}). Pass '' to skip.")
    parser.add_argument("--bsa-csv", default=BSA_CSV,
                         help=f"BSA CSV filename inside --csv-dir (default: {BSA_CSV}). Pass '' to skip.")
    parser.add_argument("--iea-csv", default=IEA_CSV,
                         help=f"IEA CSV filename inside --csv-dir (default: {IEA_CSV}). Pass '' to skip.")
    parser.add_argument("--index-name", default=DEFAULT_INDEX_NAME,
                         help=f"Pinecone index to write to (default: {DEFAULT_INDEX_NAME})")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                         help=f"sentence-transformers model name (default: {DEFAULT_MODEL})")
    parser.add_argument("--wipe", action="store_true",
                         help="Delete and recreate --index-name before embedding")
    parser.add_argument("--include-stubs", action="store_true",
                         help="Also embed stub sections that have a title but no description")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true",
                         help="Parse + build embedding text only, no model load, no API calls")
    args = parser.parse_args()

    print(f"CSV directory: {args.csv_dir}")
    print("\n--- Loading CSVs ---")
    ipc = load_ipc_sections(args.csv_dir)
    bns = load_bns_sections(args.csv_dir)
    bnss = load_generic_act_sections(args.csv_dir, args.bnss_csv or None, "BNSS")
    crpc = load_generic_act_sections(args.csv_dir, args.crpc_csv or None, "CRPC")
    bsa = load_generic_act_sections(args.csv_dir, args.bsa_csv or None, "BSA")
    iea = load_generic_act_sections(args.csv_dir, args.iea_csv or None, "IEA")

    records = (list(ipc.values()) + list(bns.values())
               + list(bnss.values()) + list(crpc.values())
               + list(bsa.values()) + list(iea.values()))

    if args.dry_run:
        print(f"\n--dry-run set: {len(records)} total sections loaded "
              f"({len(ipc)} IPC, {len(bns)} BNS, {len(bnss)} BNSS, "
              f"{len(crpc)} CRPC, {len(bsa)} BSA, {len(iea)} IEA).")
        sample = next((r for r in records if r["data_complete"] and r["description"]), None)
        if sample:
            print("\nSample embedding text:\n" + "-" * 60)
            print(build_embedding_text(sample))
            print("-" * 60)
            print("\nSample metadata:")
            print(build_metadata(sample))
        return

    run_embedding(records, args.model, args.index_name,
                  args.wipe, args.batch_size, args.include_stubs)

    print("\nDone.")


if __name__ == "__main__":
    main()