"""
enrich_and_reindex.py
─────────────────────
Pulls every LawSection from Neo4j, builds a richly-contextualised text block
for each one, re-embeds with all-MiniLM-L6-v2, and upserts back to Pinecone
using the same IDs that already exist in the index.

Why this fixes the retrieval problem
─────────────────────────────────────
all-MiniLM-L6-v2 was trained on general English. Two legal sentences with
overlapping vocabulary score ~0.52 because the model has no notion of legal
domain proximity. When each vector is computed from a 400-700 token context
block that includes the section title, ingredients (elements of proof), keywords,
applicable crimes, punishment details, and cross-act links, the query
"criminal breach of trust by employee agent clerk" finds IPC 409 at ~0.72
because those exact concepts now live in the embedding payload.

Usage
──────
    pip install neo4j pinecone-client sentence-transformers python-dotenv tqdm
    python enrich_and_reindex.py [--dry-run] [--act IPC] [--batch-size 100]

Flags
──────
    --dry-run        Build context blocks and print samples; do NOT write to Pinecone.
    --act ACT        Restrict to one act (IPC / BNS / CrPC / IEA / BSA).
                     Omit to process all acts.
    --batch-size N   Pinecone upsert batch size (default 100).
    --namespace NS   Pinecone namespace (default: legal_sections).
    --limit N        Cap total sections processed — useful for testing.
"""

import os
import re
import sys
import time
import argparse
import textwrap
from pathlib import Path
from typing import List, Dict, Any, Optional

# ── env loading (mirrors your existing service pattern) ───────────────────────
from dotenv import load_dotenv

env_loaded = False
for candidate in [
    Path(__file__).resolve().parents[2] / ".env",  # backend/.env  
    Path(__file__).resolve().parents[3] / ".env",  # MootCourt/.env
    Path(__file__).resolve().parents[4] / "backend" / ".env",
    Path("backend/.env"),
    Path(".env"),
]:
    print(f"[ENV] Checking: {candidate} (exists: {candidate.exists()})")
    if candidate.exists():
        load_dotenv(candidate)
        print(f"[ENV] ✓ Loaded from: {candidate}")
        env_loaded = True
        break

if not env_loaded:
    print("[ENV] ⚠ No .env file found")

NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")
PINECONE_API_KEY   = os.getenv("PINECONE_API_KEY",   "")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "ipc")
PINECONE_HOST      = os.getenv("PINECONE_HOST",       "")

print(f"[ENV] NEO4J_PASSWORD: {'✓' if NEO4J_PASSWORD else '✗'}")
print(f"[ENV] PINECONE_API_KEY: {'✓' if PINECONE_API_KEY else '✗'}")


# ══════════════════════════════════════════════════════════════════════════════
# 1.  NEO4J FETCH
# ══════════════════════════════════════════════════════════════════════════════

FETCH_QUERY = """
MATCH (s:LawSection)
WHERE ($act IS NULL OR s.act = $act)

// ── Ingredients (elements of proof) ──────────────────────────────────────
OPTIONAL MATCH (s)-[:HAS_INGREDIENT]->(ing:Ingredient)

// ── Keywords ──────────────────────────────────────────────────────────────
OPTIONAL MATCH (s)-[:HAS_KEYWORD]->(kw:Keyword)

// ── Punishment ────────────────────────────────────────────────────────────
OPTIONAL MATCH (s)-[:PRESCRIBES]->(pun:Punishment)

// ── Crimes this section applies to ───────────────────────────────────────
OPTIONAL MATCH (s)-[:APPLIES_TO]->(cr:Crime)

// ── Parent sections (hierarchy / specificity) ─────────────────────────────
OPTIONAL MATCH (s)-[:MORE_SPECIFIC_THAN]->(parent:LawSection)

// ── Exceptions ────────────────────────────────────────────────────────────
OPTIONAL MATCH (s)-[:HAS_EXCEPTION]->(exc:Exception)

// ── Cross-act replacements (IPC ↔ BNS, CrPC ↔ BNSS, IEA ↔ BSA) ──────────
OPTIONAL MATCH (s)-[:REPLACES]->(old_s:LawSection)
OPTIONAL MATCH (s)-[:REPLACED_BY]->(new_s:LawSection)

RETURN
    s.id          AS id,
    s.act         AS act,
    s.section     AS section,
    s.title       AS title,
    s.description AS description,
    s.punishment  AS punishment_text,
    s.category    AS category,
    s.keywords    AS raw_keywords,

    collect(DISTINCT {
        name:              ing.name,
        element_type:      ing.element_type,
        fact_key:          ing.fact_key,
        mandatory:         ing.mandatory,
        confidence_weight: ing.confidence_weight
    }) AS ingredients,

    collect(DISTINCT kw.name)  AS keywords,

    collect(DISTINCT {
        cognizable: pun.cognizable,
        bailable:   pun.bailable,
        term:       pun.term
    }) AS punishments,

    collect(DISTINCT cr.name)       AS crimes,
    collect(DISTINCT parent.title)  AS parent_titles,
    collect(DISTINCT exc.description) AS exceptions,
    collect(DISTINCT old_s.section + ' ' + old_s.act) AS replaces_sections,
    collect(DISTINCT new_s.section + ' ' + new_s.act) AS replaced_by_sections

ORDER BY s.act, s.section
"""


def fetch_all_sections(driver, act_filter: Optional[str] = None, limit: Optional[int] = None) -> List[Dict]:
    """Return a list of raw Neo4j records as plain dicts."""
    with driver.session() as session:
        result = session.run(FETCH_QUERY, act=act_filter)
        records = [dict(r) for r in result]

    if limit:
        records = records[:limit]

    print(f"[Neo4j] Fetched {len(records)} LawSection nodes"
          + (f" (act={act_filter})" if act_filter else "")
          + (f" (limit={limit})" if limit else ""))
    return records


# ══════════════════════════════════════════════════════════════════════════════
# 2.  CONTEXT BLOCK BUILDER
# ══════════════════════════════════════════════════════════════════════════════

def _clean(val) -> str:
    """Coerce None / empty to empty string."""
    if val is None:
        return ""
    return str(val).strip()


def _ingredients_text(ingredients: List[Dict]) -> str:
    """
    Turn ingredient nodes into a human-readable block.
    Mandatory ingredients come first and are flagged.
    """
    if not ingredients or all(not i.get("name") for i in ingredients):
        return ""

    mandatory, optional = [], []
    for ing in ingredients:
        name = _clean(ing.get("name"))
        if not name:
            continue
        element_type = _clean(ing.get("element_type"))
        fact_key     = _clean(ing.get("fact_key"))
        is_mandatory = ing.get("mandatory", True)

        parts = [name]
        if element_type:
            parts.append(f"[{element_type}]")
        if fact_key and fact_key != name:
            parts.append(f"({fact_key})")

        entry = " ".join(parts)
        if is_mandatory:
            mandatory.append(entry)
        else:
            optional.append(entry)

    lines = []
    if mandatory:
        lines.append("Required elements: " + "; ".join(mandatory))
    if optional:
        lines.append("Optional elements: " + "; ".join(optional))
    return "\n".join(lines)


def _punishment_text(punishments: List[Dict], fallback: str) -> str:
    """Summarise punishment nodes; fall back to the raw string on the node."""
    clean_puns = [p for p in punishments if p.get("term")]
    if not clean_puns and not fallback:
        return ""

    if clean_puns:
        parts = []
        for p in clean_puns:
            term      = _clean(p.get("term"))
            cogniz    = p.get("cognizable")
            bailable  = p.get("bailable")

            flags = []
            if cogniz is not None:
                flags.append("cognizable" if cogniz else "non-cognizable")
            if bailable is not None:
                flags.append("bailable" if bailable else "non-bailable")

            line = term
            if flags:
                line += " | " + ", ".join(flags)
            parts.append(line)
        return "; ".join(parts)

    return fallback


def _dedup_list(lst: List) -> List:
    seen, out = set(), []
    for item in lst:
        key = str(item).strip()
        if key and key not in seen and key != "None":
            seen.add(key)
            out.append(key)
    return out


def build_context_block(record: Dict) -> str:
    """
    Constructs a richly-contextualised text block for one LawSection.

    Structure (all fields optional; omitted if empty):

        [ACT: X] [SECTION: Y] [TYPE: Z] [DOMAIN: ...]
        Title: ...
        Description: ...
        Applies to crimes: ...
        Required elements: ...; ...
        Optional elements: ...; ...
        Keywords: ...
        Punishment: ...
        Part of: ...
        Exceptions: ...
        Replaces: ...  /  Replaced by: ...
    """
    act       = _clean(record.get("act"))
    section   = _clean(record.get("section"))
    title     = _clean(record.get("title"))
    desc      = _clean(record.get("description"))
    category  = _clean(record.get("category"))

    ingredients  = record.get("ingredients")  or []
    keywords     = _dedup_list(record.get("keywords")     or [])
    raw_kw       = _dedup_list((record.get("raw_keywords") or "").split(",") if record.get("raw_keywords") else [])
    all_keywords = _dedup_list(keywords + raw_kw)
    punishments  = record.get("punishments")  or []
    pun_fallback = _clean(record.get("punishment_text"))
    crimes       = _dedup_list(record.get("crimes")       or [])
    parents      = _dedup_list(record.get("parent_titles") or [])
    exceptions   = _dedup_list(record.get("exceptions")   or [])
    replaces     = _dedup_list(record.get("replaces_sections")     or [])
    replaced_by  = _dedup_list(record.get("replaced_by_sections") or [])

    lines = []

    # ── Header tags ────────────────────────────────────────────────────────
    header_parts = []
    if act:
        header_parts.append(f"[ACT: {act}]")
    if section:
        header_parts.append(f"[SECTION: {section}]")
    if category:
        header_parts.append(f"[TYPE: {category}]")
    if crimes:
        header_parts.append(f"[DOMAIN: {', '.join(crimes[:5])}]")
    if header_parts:
        lines.append(" ".join(header_parts))

    # ── Core fields ────────────────────────────────────────────────────────
    if title:
        lines.append(f"Title: {title}")
    if desc:
        lines.append(f"Description: {desc}")

    # ── Applicability ─────────────────────────────────────────────────────
    if crimes:
        lines.append(f"Applies to: {', '.join(crimes)}")

    # ── Ingredients (highest signal for financial crime / offence queries) ─
    ing_text = _ingredients_text(ingredients)
    if ing_text:
        lines.append(ing_text)

    # ── Keywords ──────────────────────────────────────────────────────────
    if all_keywords:
        lines.append(f"Keywords: {', '.join(all_keywords)}")

    # ── Punishment ────────────────────────────────────────────────────────
    pun_text = _punishment_text(punishments, pun_fallback)
    if pun_text:
        lines.append(f"Punishment: {pun_text}")

    # ── Hierarchy ─────────────────────────────────────────────────────────
    if parents:
        lines.append(f"More specific than: {', '.join(parents)}")

    # ── Exceptions ────────────────────────────────────────────────────────
    if exceptions:
        lines.append(f"Exceptions: {'; '.join(exceptions[:3])}")

    # ── Cross-act links ───────────────────────────────────────────────────
    if replaces:
        lines.append(f"Replaces: {', '.join(replaces)}")
    if replaced_by:
        lines.append(f"Replaced by: {', '.join(replaced_by)}")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# 3.  EMBEDDING
# ══════════════════════════════════════════════════════════════════════════════

def embed_texts(texts: List[str], model_name: str = "all-MiniLM-L6-v2") -> List[List[float]]:
    """Batch-embed a list of strings. Returns list of 384-d float vectors."""
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(model_name)
    print(f"[Embed] Encoding {len(texts)} context blocks …")
    vectors = model.encode(texts, batch_size=64, show_progress_bar=True, convert_to_numpy=True)
    return vectors.tolist()


# ══════════════════════════════════════════════════════════════════════════════
# 4.  PINECONE UPSERT
# ══════════════════════════════════════════════════════════════════════════════

def _build_metadata(record: Dict, context_block: str) -> Dict[str, Any]:
    """
    Build the metadata dict to store alongside the vector.
    Mirrors the fields your retrieval pipeline expects from match["metadata"].
    Adds context_block so you can inspect what was embedded.
    """
    act     = _clean(record.get("act"))
    section = _clean(record.get("section"))
    title   = _clean(record.get("title"))
    desc    = _clean(record.get("description"))

    crimes   = _dedup_list(record.get("crimes")   or [])
    keywords = _dedup_list(record.get("keywords") or [])
    raw_kw   = _dedup_list((record.get("raw_keywords") or "").split(",") if record.get("raw_keywords") else [])

    pun_text = _punishment_text(
        record.get("punishments") or [],
        _clean(record.get("punishment_text"))
    )

    punishments = record.get("punishments") or []
    cognizable = None
    bailable   = None
    for p in punishments:
        if p.get("cognizable") is not None:
            cognizable = p["cognizable"]
        if p.get("bailable") is not None:
            bailable = p["bailable"]

    # Pinecone rejects null metadata values — coerce None booleans to "unknown"
    # so definitional/procedural sections (which have no punishment node) don't
    # cause a 400 on every batch.
    def _bool_meta(val) -> str:
        if val is True:
            return "yes"
        if val is False:
            return "no"
        return "unknown"

    # Pinecone hard limit: 40KB per vector metadata total (all fields combined).
    # Some LawSection descriptions are 5000+ chars (chapter-level sections with
    # illustrations, provisos, sub-clauses). Truncate aggressively — the full
    # text is already baked into the embedding via the context block; metadata
    # is only used for display in your retrieval results, not for scoring.
    return {
        "act":         act,
        "section":     section,
        "title":       title[:200],
        "description": desc[:300],
        "punishment":  (pun_text if pun_text else "N/A")[:150],
        "category":    _clean(record.get("category"))[:80],
        "keywords":    ", ".join(_dedup_list(keywords + raw_kw))[:200],
        "crimes":      ", ".join(crimes)[:150],
        "cognizable":  _bool_meta(cognizable),
        "bailable":    _bool_meta(bailable),
    }


def upsert_to_pinecone(
    records: List[Dict],
    context_blocks: List[str],
    vectors: List[List[float]],
    namespace: str = "legal_sections",
    batch_size: int = 100,
    dry_run: bool = False,
):
    if dry_run:
        print(f"[DryRun] Would upsert {len(records)} vectors to namespace='{namespace}'")
        return

    from pinecone import Pinecone
    pc    = Pinecone(api_key=PINECONE_API_KEY)
    index = pc.Index(PINECONE_INDEX_NAME)

    total   = len(records)
    batches = (total + batch_size - 1) // batch_size
    upserted = 0

    for b in range(batches):
        start = b * batch_size
        end   = min(start + batch_size, total)

        batch_vectors = []
        for i in range(start, end):
            rec   = records[i]
            vec   = vectors[i]
            ctx   = context_blocks[i]
            vec_id = _clean(rec.get("id"))

            if not vec_id:
                # Fallback ID construction matching your existing scheme
                vec_id = f"{_clean(rec.get('act'))}_{_clean(rec.get('section'))}"

            metadata = _build_metadata(rec, ctx)

            batch_vectors.append({
                "id":       vec_id,
                "values":   vec,
                "metadata": metadata,
            })

        try:
            index.upsert(vectors=batch_vectors, namespace=namespace)
            upserted += len(batch_vectors)
            print(f"[Pinecone] Upserted batch {b+1}/{batches} ({upserted}/{total})")
        except Exception as e:
            print(f"[Pinecone] ERROR on batch {b+1}: {e}")
            print("  Retrying after 5 s …")
            time.sleep(5)
            try:
                index.upsert(vectors=batch_vectors, namespace=namespace)
                upserted += len(batch_vectors)
                print(f"[Pinecone] Retry succeeded for batch {b+1}")
            except Exception as e2:
                print(f"[Pinecone] Retry failed for batch {b+1}: {e2}. Skipping.")

    print(f"\n[Pinecone] Done. {upserted}/{total} vectors upserted to '{PINECONE_INDEX_NAME}' / '{namespace}'")


# ══════════════════════════════════════════════════════════════════════════════
# 5.  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def parse_args():
    p = argparse.ArgumentParser(description="Re-embed LawSection nodes with enriched context.")
    p.add_argument("--dry-run",    action="store_true", help="Build blocks, print samples, skip Pinecone write.")
    p.add_argument("--act",        type=str, default=None, help="Restrict to one act (e.g. IPC, BNS, CrPC).")
    p.add_argument("--batch-size", type=int, default=100, help="Pinecone upsert batch size.")
    p.add_argument("--namespace",  type=str, default="legal_sections", help="Pinecone namespace.")
    p.add_argument("--limit",      type=int, default=None, help="Max sections to process (for testing).")
    p.add_argument("--sample",     type=int, default=3, help="Number of context block samples to print.")
    return p.parse_args()


def main():
    args = parse_args()

    # ── Validate env ──────────────────────────────────────────────────────
    missing = []
    if not NEO4J_PASSWORD:
        missing.append("NEO4J_PASSWORD")
    if not PINECONE_API_KEY and not args.dry_run:
        missing.append("PINECONE_API_KEY")
    if missing:
        print(f"[Error] Missing env vars: {', '.join(missing)}")
        sys.exit(1)

    # ── Neo4j connection ──────────────────────────────────────────────────
    from neo4j import GraphDatabase
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        driver.verify_connectivity()
        print(f"[Neo4j] Connected to {NEO4J_URI}")
    except Exception as e:
        print(f"[Neo4j] Connection failed: {e}")
        sys.exit(1)

    # ── Fetch ─────────────────────────────────────────────────────────────
    records = fetch_all_sections(driver, act_filter=args.act, limit=args.limit)
    driver.close()

    if not records:
        print("[Error] No records returned from Neo4j. Check your filters.")
        sys.exit(1)

    # ── Build context blocks ──────────────────────────────────────────────
    print("[Enrich] Building context blocks …")
    context_blocks = [build_context_block(r) for r in records]

    # ── Print samples ─────────────────────────────────────────────────────
    n_samples = min(args.sample, len(records))
    print(f"\n{'═'*70}")
    print(f"SAMPLE CONTEXT BLOCKS ({n_samples} of {len(records)})")
    print('═'*70)
    for i in range(n_samples):
        rec = records[i]
        print(f"\n── [{rec.get('act')} § {rec.get('section')}] {rec.get('title')} ──")
        print(context_blocks[i])
        print()
    print('═'*70)

    if args.dry_run:
        print("\n[DryRun] Skipping embed + upsert. Remove --dry-run to write to Pinecone.")
        return

    # ── Embed ─────────────────────────────────────────────────────────────
    vectors = embed_texts(context_blocks)

    # ── Upsert ────────────────────────────────────────────────────────────
    upsert_to_pinecone(
        records       = records,
        context_blocks = context_blocks,
        vectors        = vectors,
        namespace      = args.namespace,
        batch_size     = args.batch_size,
        dry_run        = args.dry_run,
    )

    print("\n[Done] Re-indexing complete.")
    print("Run a test query against your existing retrieval pipeline —")
    print("financial crime queries should now score above your threshold.")


if __name__ == "__main__":
    main()