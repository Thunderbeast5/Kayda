"""
LexiGraph Agent — GraphRAG Legal Retriever (v2, semantic-first)
=================================================================
Retrieves IPC/BNS law sections for the Prosecutor/Defense/Judge agents,
BEFORE any LLM reasoning call.

Why this file changed
----------------------
The graph and vector store were rebuilt (neo4j_v2.py / pinecone_v2.py) and
the old retrieval logic no longer matches the new schema:

  - Neo4j label changed  :IPC  ->  :LawSection {act:'IPC'|'BNS', id:'IPC_302'}
    A single graph now holds BOTH IPC and BNS sections, linked by
    (:LawSection)-[:REPLACED_BY]->(:LawSection) crosswalk edges. Bare
    section *numbers* can collide across acts (e.g. IPC 103 and BNS 103
    are different sections) — every candidate is now keyed by its full
    "ACT_SECTION" id, never by the bare number.

  - Pinecone index changed to "legal-sections-v2", vectors now cover BOTH
    acts with a richer embedding text (chapter/category/crosswalk baked
    in). Its metadata carries "title" (not "offense") and NO "description"
    field at all — the old code was silently pulling empty descriptions
    straight from Pinecone. Full description/punishment text now has to
    be enriched from Neo4j after retrieval.

  - Retrieval used to be Neo4j-CONTAINS-keyword-first, with a flat
    0.85 / 1.0 score handed out purely based on *which step* found a
    section, regardless of whether it was actually the best match.
    This rewrite makes Pinecone's cosine similarity the primary score for
    every candidate (it's the same embedding model/metric used to build
    the index, so it's a genuine semantic search, not a keyword match).
    Neo4j keyword search becomes a recall safety net used only when
    semantic search alone comes back thin.

Pipeline for every query
-------------------------
Step A — Pinecone semantic search: embed query_text, search across IPC+BNS.
Step B — Neo4j exact-section lookup (only if section_hint is given).
Step C — Neo4j keyword fallback (only if Step A returns < MIN_SEMANTIC_HITS).
Step D — Enrich every candidate with full description/punishment/crosswalk
          from Neo4j, then merge + rank on one shared semantic scale.
Step E — Guardrail: if 0 results survive, LLM rewrites the query and retries.
"""

import os
import re
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# ── Environment ───────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

NEO4J_URI      = os.getenv("NEO4J_URI", "")
NEO4J_USER     = os.getenv("NEO4J_USER", "")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

PINECONE_API_KEY   = os.getenv("PINECONE_API_KEY", "")
# Matches the index built by pinecone_v2.py (DEFAULT_INDEX_NAME). Override
# via .env if you embedded into a differently-named index.
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "legal-sections-v2")
# Must match the model pinecone_v2.py was run with (its DEFAULT_MODEL).
EMBEDDING_MODEL = os.getenv("LEXIGRAPH_EMBEDDING_MODEL", "all-MiniLM-L6-v2")

# ── Lazy singletons ───────────────────────────────────────────────────────────
_spacy_nlp      = None
_embedder       = None
_pinecone_index = None
_neo4j_driver   = None


def _nlp():
    global _spacy_nlp
    if _spacy_nlp is None:
        import spacy
        try:
            _spacy_nlp = spacy.load("en_core_web_sm")
        except OSError:
            raise RuntimeError(
                "spaCy model not found. Run:\n"
                "  venv\\Scripts\\python -m spacy download en_core_web_sm"
            )
    return _spacy_nlp


def _embed(texts: list[str]) -> list[list[float]]:
    """Embed a list of strings using sentence-transformers (must match the
    model used to build the Pinecone index — see EMBEDDING_MODEL above)."""
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer
        _embedder = SentenceTransformer(EMBEDDING_MODEL)
    return _embedder.encode(texts, convert_to_numpy=True).tolist()


def _pinecone():
    global _pinecone_index
    if _pinecone_index is None:
        if not PINECONE_API_KEY:
            raise RuntimeError("PINECONE_API_KEY not set in backend/.env")
        from pinecone import Pinecone
        pc = Pinecone(api_key=PINECONE_API_KEY)
        # Name-based lookup, same convention pinecone_v2.py's ensure_index() uses.
        _pinecone_index = pc.Index(PINECONE_INDEX_NAME)
    return _pinecone_index


def _neo4j():
    global _neo4j_driver
    if _neo4j_driver is None:
        if not NEO4J_URI:
            raise RuntimeError("NEO4J_URI not set in backend/.env")
        from neo4j import GraphDatabase
        _neo4j_driver = GraphDatabase.driver(
            NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
        )
    return _neo4j_driver


def _neo4j_run(cypher: str, params: dict) -> list[dict]:
    driver = _neo4j()
    with driver.session(database=NEO4J_DATABASE) as session:
        result = session.run(cypher, params)
        return [dict(record) for record in result]


# ── Keyword extraction (used only for the Step C fallback + Step E rewrite) ───

# Short ROOT/STEM forms so substring matching catches every inflected form
# ("threat" matches "threatens", "threatening", "threatened").
_LEGAL_KEYWORDS = {
    "theft", "robb", "dacoit", "murder", "homicide", "assault", "rape",
    "fraud", "cheat", "forg", "extort", "kidnap", "abduct",
    "trespass", "arson", "brib", "corrupt", "defam", "sedit",
    "riot", "hurt", "grievous", "intimidat", "threat", "stalk",
    "dowry", "cruel", "obscen", "gambl", "smuggl", "traffick",
    "poison", "accident", "neglig", "embezzl", "breach",
    "misappropriat", "imperson", "counterfeit", "mischief",
}

# Concepts implied without the literal legal term appearing in the query.
_CONCEPT_EXPANSION = {
    "document": ["forg"],
    "signature": ["forg"],
    "seal": ["forg"],
    "whatsapp": ["threat", "intimidat"],
    "sms": ["threat", "intimidat"],
    "text message": ["threat", "intimidat"],
    "online": ["cyber"],
    "email": ["cyber"],
}


def extract_crime_keywords(query_text: str) -> list[str]:
    """spaCy NER + legal keyword matching. Only used to feed the Neo4j
    fallback search (Step C) and the guardrail rewrite (Step E) — the
    primary retrieval path (Step A) never touches this."""
    nlp  = _nlp()
    doc  = nlp(query_text)
    seen = set()
    keywords: list[str] = []

    def _add(word: str):
        w = word.strip().lower()
        if w and w not in seen and len(w) > 2:
            seen.add(w)
            keywords.append(w)

    for ent in doc.ents:
        if ent.label_ in ("EVENT", "ORG", "NORP", "LAW", "GPE"):
            _add(ent.text)

    text_lower = query_text.lower()
    for kw in _LEGAL_KEYWORDS:
        if kw in text_lower:
            _add(kw)

    for trigger, extra_kws in _CONCEPT_EXPANSION.items():
        if trigger in text_lower:
            for ekw in extra_kws:
                _add(ekw)

    if len(keywords) < 2:
        for chunk in doc.noun_chunks:
            if any(t.is_alpha and not t.is_stop for t in chunk):
                _add(" ".join(t.text for t in chunk if t.is_alpha)[:40])

    if len(keywords) < 2:
        for token in doc:
            if token.pos_ in ("NOUN", "PROPN") and not token.is_stop:
                _add(token.lemma_)

    return keywords[:8]


# ── Step A: Pinecone semantic search (PRIMARY retrieval path) ─────────────────

def _query_pinecone(query_text: str, top_k: int = 7, act_filter: Optional[str] = None) -> list[dict]:
    """
    Step A — Embed query_text and search Pinecone for semantically similar
    IPC/BNS sections. This is the primary signal: the returned `score` is
    Pinecone's own cosine similarity (the index metric is 'cosine'), so it
    means the same thing for every candidate regardless of how it was found.
    """
    index  = _pinecone()
    vector = _embed([query_text])[0]

    query_kwargs = dict(vector=vector, top_k=top_k, include_metadata=True)
    if act_filter:
        query_kwargs["filter"] = {"act": {"$eq": act_filter}}

    response = index.query(**query_kwargs)

    results = []
    for match in response.get("matches", []):
        meta    = match.get("metadata", {}) or {}
        act     = meta.get("act", "")
        section = str(meta.get("section", ""))
        law_id  = match.get("id", "") or f"{act}_{section}"

        results.append({
            "law_id":             law_id,
            "act":                act,
            "section":            section,
            "title":              meta.get("title", ""),
            "offense":            meta.get("title", ""),   # alias for downstream/format compat
            "description":        "",                       # not in Pinecone metadata — enriched later
            "punishment":         meta.get("punishment", ""),  # truncated to 500 chars — enriched later
            "chapter":            meta.get("chapter", ""),
            "category":           meta.get("category", ""),
            "cognizable":         meta.get("cognizable", ""),
            "bailable":           meta.get("bailable", ""),
            "court":              meta.get("court", ""),
            "equivalent_act":     meta.get("equivalent_act", ""),
            "equivalent_section": meta.get("equivalent_section", ""),
            "mapping_status":     meta.get("mapping_status", ""),
            "data_complete":      meta.get("data_complete", True),
            "source":             "pinecone:semantic",
            "score":              round(float(match.get("score", 0.0)), 4),
        })
    return results


# ── Step B: Neo4j exact-section lookup ─────────────────────────────────────────

def _candidate_ids_for_hint(section_hint: str) -> list[str]:
    """'302' -> ['IPC_302','BNS_302']; 'BNS_103' / 'BNS 103' -> ['BNS_103']."""
    raw = section_hint.strip().upper()

    act_prefix = None
    if raw.startswith("IPC"):
        act_prefix = "IPC"
        raw = raw[3:]
    elif raw.startswith("BNS"):
        act_prefix = "BNS"
        raw = raw[3:]

    number = re.sub(r"[^0-9A-Za-z]", "", raw)

    if act_prefix:
        return [f"{act_prefix}_{number}"]
    return [f"IPC_{number}", f"BNS_{number}"]


def _neo4j_exact(section_hint: str) -> list[dict]:
    """Step B — direct id/section lookup for an already-known section number."""
    if not section_hint:
        return []
    ids  = _candidate_ids_for_hint(section_hint)
    bare = re.sub(r"[^0-9A-Za-z]", "", section_hint)

    rows = _neo4j_run(
        """
        MATCH (l:LawSection)
        WHERE l.id IN $ids OR l.section = $bare
        RETURN l.id AS law_id, l.act AS act, l.section AS section, l.title AS title,
               l.description AS description, l.punishment AS punishment
        LIMIT 5
        """,
        {"ids": ids, "bare": bare},
    )
    return [
        {
            "law_id": r["law_id"], "act": r["act"], "section": r["section"],
            "title": r.get("title", ""), "offense": r.get("title", ""),
            "description": r.get("description", ""), "punishment": r.get("punishment", ""),
            "source": "neo4j:exact", "score": 1.0,
        }
        for r in rows
    ]


# ── Step C: Neo4j keyword fallback (recall safety net, NOT primary) ───────────

def _query_neo4j_keyword(keywords: list[str]) -> list[dict]:
    """
    Step C — only called when Pinecone alone returns fewer than
    MIN_SEMANTIC_HITS candidates. CONTAINS-matches Crime.name and
    LawSection.title/description across BOTH acts.
    """
    results, seen = [], set()
    if not keywords:
        return results

    for kw in keywords[:5]:
        rows = _neo4j_run(
            """
            MATCH (c:Crime)-[:DEFINED_BY]->(l:LawSection)
            WHERE toLower(c.name) CONTAINS toLower($kw)
            RETURN l.id AS law_id, l.act AS act, l.section AS section, l.title AS title,
                   l.description AS description, l.punishment AS punishment, c.name AS crime_name
            LIMIT 5
            """,
            {"kw": kw},
        )
        for r in rows:
            lid = r["law_id"]
            if lid in seen:
                continue
            seen.add(lid)
            results.append({
                "law_id": lid, "act": r["act"], "section": r["section"],
                "title": r.get("title", ""), "offense": r.get("crime_name") or r.get("title", ""),
                "description": r.get("description", ""), "punishment": r.get("punishment", ""),
                "source": "neo4j:keyword_fallback", "score": 0.0,
            })

    if len(results) < 3:
        for kw in keywords[:4]:
            rows = _neo4j_run(
                """
                MATCH (l:LawSection)
                WHERE toLower(l.title) CONTAINS toLower($kw)
                   OR toLower(l.description) CONTAINS toLower($kw)
                RETURN l.id AS law_id, l.act AS act, l.section AS section, l.title AS title,
                       l.description AS description, l.punishment AS punishment
                LIMIT 5
                """,
                {"kw": kw},
            )
            for r in rows:
                lid = r["law_id"]
                if lid in seen:
                    continue
                seen.add(lid)
                results.append({
                    "law_id": lid, "act": r["act"], "section": r["section"],
                    "title": r.get("title", ""), "offense": r.get("title", ""),
                    "description": r.get("description", ""), "punishment": r.get("punishment", ""),
                    "source": "neo4j:keyword_fallback", "score": 0.0,
                })
    return results


# ── Step D: Enrich, merge, rank on one shared semantic scale ──────────────────

def _cosine_sim(a: list[float], b: list[float]) -> float:
    dot    = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _enrich_from_neo4j(law_id: str) -> dict:
    """Pinecone metadata has no `description` and a truncated `punishment` —
    pull the full text plus crosswalk/chapter/crime-name context from Neo4j."""
    rows = _neo4j_run(
        """
        MATCH (l:LawSection {id: $id})
        OPTIONAL MATCH (l)<-[:DEFINED_BY]-(c:Crime)
        OPTIONAL MATCH (l)-[:REPLACED_BY|REPLACES]->(other:LawSection)
        OPTIONAL MATCH (ch:Chapter)-[:HAS_SECTION]->(l)
        RETURN l.description AS description, l.punishment AS punishment, l.title AS title,
               l.mapping_status AS mapping_status,
               collect(DISTINCT c.name)[0] AS crime_name,
               other.act AS equivalent_act, other.section AS equivalent_section,
               ch.title AS chapter_title
        LIMIT 1
        """,
        {"id": law_id},
    )
    return rows[0] if rows else {}


# Below this score, a candidate is noise and gets dropped rather than
# surfaced as a "relevant law". Tune against a gold-set eval.
MIN_CONFIDENCE = 0.32
# An explicitly requested section_hint should basically always rank first.
_EXACT_HINT_SCORE = 0.97
# Small nudge when independent sources (vector + graph) agree on a section.
_SOURCE_AGREEMENT_BOOST = 0.04
# If Pinecone alone returns fewer candidates than this, run the Neo4j
# keyword fallback too, purely for extra recall.
MIN_SEMANTIC_HITS = 3


def _merge_and_rank(
    pinecone_hits: list[dict],
    neo4j_exact_hits: list[dict],
    neo4j_fallback_hits: list[dict],
    query_text: str,
    top_n: int = 5,
) -> list[dict]:
    """
    Every candidate is keyed by its full `law_id` ("IPC_302"/"BNS_103") —
    NOT the bare section number, since IPC and BNS numbering can collide.

    Every candidate is scored on ONE shared scale: Pinecone's native cosine
    similarity where available (pinecone:semantic hits), falling back to a
    locally-computed cosine similarity only for candidates that came from
    Neo4j alone (exact hint / keyword fallback) and therefore never got a
    vector score. Source agreement gives a small boost; an explicit
    section_hint still wins outright. Nothing keyword-matched can outrank
    a genuinely better semantic match purely because of which step found it.
    """
    merged: dict[str, dict] = {}

    def _upsert(r: dict) -> None:
        lid = r["law_id"]
        if lid not in merged:
            rec = dict(r)
            rec["_sources"] = {r["source"]}
            if r["source"] == "pinecone:semantic":
                rec["_native_score"] = r["score"]
            merged[lid] = rec
        else:
            existing = merged[lid]
            existing["_sources"].add(r["source"])
            if r["source"] == "pinecone:semantic":
                existing["_native_score"] = r["score"]
            for field in ("description", "title", "offense", "punishment"):
                if not existing.get(field) and r.get(field):
                    existing[field] = r[field]

    for r in pinecone_hits:
        _upsert(r)
    for r in neo4j_exact_hits:
        _upsert(r)
    for r in neo4j_fallback_hits:
        _upsert(r)

    if not merged:
        return []

    # Enrich every surviving candidate with full text + crosswalk context.
    for lid, rec in merged.items():
        enriched = _enrich_from_neo4j(lid)
        if enriched:
            rec["description"]        = rec.get("description") or enriched.get("description", "")
            rec["punishment"]         = rec.get("punishment") or enriched.get("punishment", "")
            rec["title"]              = rec.get("title") or enriched.get("title", "")
            rec["offense"]            = rec.get("offense") or enriched.get("crime_name") or rec.get("title", "")
            rec["chapter"]            = rec.get("chapter") or enriched.get("chapter_title", "")
            rec["equivalent_act"]     = rec.get("equivalent_act") or enriched.get("equivalent_act", "") or ""
            rec["equivalent_section"] = rec.get("equivalent_section") or enriched.get("equivalent_section", "") or ""
            rec["mapping_status"]     = rec.get("mapping_status") or enriched.get("mapping_status", "") or ""

    # Candidates without a native Pinecone score (pure Neo4j hits) get a
    # local semantic score so they're comparable on the same scale.
    need_local = [lid for lid, rec in merged.items() if "_native_score" not in rec]
    if need_local:
        cand_texts = [
            (f"{merged[lid].get('act','')} {merged[lid].get('title','')} "
             f"{merged[lid].get('description','')}").strip() or lid
            for lid in need_local
        ]
        try:
            vectors = _embed([query_text] + cand_texts)
            query_vec, cand_vecs = vectors[0], vectors[1:]
            for lid, v in zip(need_local, cand_vecs):
                merged[lid]["_native_score"] = _cosine_sim(query_vec, v)
        except Exception as e:
            print(f"[LexiGraph] Local semantic scoring unavailable ({e}); using 0.5 fallback")
            for lid in need_local:
                merged[lid]["_native_score"] = 0.5

    for lid, rec in merged.items():
        score = rec["_native_score"]
        if "neo4j:exact" in rec["_sources"]:
            score = max(score, _EXACT_HINT_SCORE)
        elif len(rec["_sources"]) > 1:
            score = min(1.0, score + _SOURCE_AGREEMENT_BOOST)
        rec["score"]  = round(score, 4)
        rec["source"] = "+".join(sorted(rec["_sources"]))
        del rec["_sources"]
        del rec["_native_score"]

    ranked = sorted(merged.values(), key=lambda x: x["score"], reverse=True)
    ranked = [r for r in ranked if r["score"] >= MIN_CONFIDENCE]
    return ranked[:top_n]


# ── Step E: Guardrail — LLM query rewrite ─────────────────────────────────────

def _rewrite_query(original_query: str) -> str:
    """If retrieval returns 0 results, ask the LLM to rephrase the query
    using precise IPC/BNS terminology and retry once."""
    from config.llm_config import get_llm
    llm    = get_llm(temperature=0.3)
    prompt = (
        f"You are an Indian criminal law expert. The following query returned no "
        f"results from an IPC/BNS (Indian Penal Code / Bharatiya Nyaya Sanhita) "
        f"database:\n\n\"{original_query}\"\n\n"
        f"Rewrite this query using precise Indian criminal law terminology "
        f"(e.g. 'theft', 'culpable homicide', 'criminal intimidation', 'cheating'). "
        f"Return ONLY the rewritten query — no explanation, no punctuation."
    )
    response  = llm.invoke(prompt)
    rewritten = response.content.strip().strip('"').strip("'")
    print(f"[LexiGraph] Query rewritten: '{original_query}' -> '{rewritten}'")
    return rewritten


# ── Public API ──────────────────────────────────────────────────────────────

def retrieve(
    query_text: str,
    section_hint: str = None,
    act_filter: Optional[str] = None,
    top_n: int = 5,
    pinecone_top_k: int = 7,
) -> dict:
    """
    Main retrieval function. Call this BEFORE any LLM prompt.

    Parameters
    ----------
    query_text     : Free-text crime description from structured_facts or user query.
    section_hint   : Specific section if already known ("302", "IPC 302", "BNS_103").
    act_filter     : Restrict Pinecone search to "IPC" or "BNS" only. None = search both.
    top_n          : Number of final ranked results to return (default 5).
    pinecone_top_k : How many Pinecone candidates to fetch before ranking (default 7).

    Returns
    -------
    {
        "ipc_sections": [   # kept as the historical key name; entries may be
                            # IPC or BNS — check each entry's "act" field
            {
                "law_id": "IPC_302", "act": "IPC", "section": "302",
                "title": "Murder", "offense": "Murder",
                "description": "...", "punishment": "Death or life imprisonment + fine",
                "equivalent_act": "BNS", "equivalent_section": "103",
                "source": "pinecone:semantic", "score": 0.87,
            },
            ...
        ],
        "keywords":       [...],   # only populated if the fallback/rewrite path ran
        "neo4j_count":    2,
        "pinecone_count": 6,
        "query_used":     "murder of a person",
        "rewritten":      False,
    }
    """
    print(f"\n[LexiGraph] -- Retrieving for: '{query_text[:80]}'")

    # ── Step A: Pinecone semantic search (primary) ─────────────────────
    pinecone_hits = []
    try:
        pinecone_hits = _query_pinecone(query_text, top_k=pinecone_top_k, act_filter=act_filter)
        print(f"[LexiGraph] Step A — Pinecone semantic: {len(pinecone_hits)} hits")
    except Exception as e:
        print(f"[LexiGraph] Pinecone error: {e}")

    # ── Step B: Neo4j exact-section lookup ──────────────────────────────
    neo4j_exact_hits = []
    if section_hint:
        try:
            neo4j_exact_hits = _neo4j_exact(section_hint)
            print(f"[LexiGraph] Step B — Neo4j exact: {len(neo4j_exact_hits)} hits")
        except Exception as e:
            print(f"[LexiGraph] Neo4j exact-lookup error: {e}")

    # ── Step C: Neo4j keyword fallback (only if semantic search is thin) ─
    keywords = []
    neo4j_fallback_hits = []
    if len(pinecone_hits) < MIN_SEMANTIC_HITS:
        keywords = extract_crime_keywords(query_text)
        try:
            neo4j_fallback_hits = _query_neo4j_keyword(keywords)
            print(f"[LexiGraph] Step C — Neo4j fallback (semantic hits < {MIN_SEMANTIC_HITS}): "
                  f"{len(neo4j_fallback_hits)} hits")
        except Exception as e:
            print(f"[LexiGraph] Neo4j fallback error: {e}")

    # ── Step D: enrich, merge, rank ──────────────────────────────────────
    ranked = _merge_and_rank(pinecone_hits, neo4j_exact_hits, neo4j_fallback_hits, query_text, top_n=top_n)
    print(f"[LexiGraph] Step D — merged: {len(ranked)} unique sections above confidence floor")

    rewritten = False

    # ── Step E: guardrail — retry with rewritten query ───────────────────
    if len(ranked) == 0:
        print("[LexiGraph] Step E — 0 results, rewriting query...")
        rewritten_query = _rewrite_query(query_text)
        rewritten        = True

        pinecone_hits_2 = []
        try:
            pinecone_hits_2 = _query_pinecone(rewritten_query, top_k=pinecone_top_k, act_filter=act_filter)
        except Exception as e:
            print(f"[LexiGraph] Pinecone retry error: {e}")

        keywords = extract_crime_keywords(rewritten_query)
        neo4j_fallback_2 = []
        try:
            neo4j_fallback_2 = _query_neo4j_keyword(keywords)
        except Exception as e:
            print(f"[LexiGraph] Neo4j retry error: {e}")

        ranked = _merge_and_rank(pinecone_hits_2, neo4j_exact_hits, neo4j_fallback_2, rewritten_query, top_n=top_n)
        pinecone_hits = pinecone_hits_2
        print(f"[LexiGraph] Step E retry — {len(ranked)} sections after rewrite")
        query_text = rewritten_query

    return {
        "ipc_sections":   ranked,
        "keywords":       keywords,
        "neo4j_count":    len(neo4j_exact_hits) + len(neo4j_fallback_hits),
        "pinecone_count": len(pinecone_hits),
        "query_used":     query_text,
        "rewritten":      rewritten,
    }


def format_for_prompt(result: dict) -> str:
    """Formats the retrieval result into a clean, numbered string ready
    to be injected into any LLM system/user prompt."""
    sections = result.get("ipc_sections", [])
    if not sections:
        return (
            "DATABASE RETRIEVAL: No relevant law sections found.\n"
            f"Keywords tried: {result.get('keywords', [])}\n"
            "The LLM must reason from general knowledge only."
        )

    lines = [
        f"RETRIEVED LAW SECTIONS  "
        f"[Neo4j:{result['neo4j_count']}  Pinecone:{result['pinecone_count']}  "
        f"Final:{len(sections)}]",
        "=" * 65,
    ]
    for i, s in enumerate(sections, 1):
        act    = s.get("act", "")
        sec    = s.get("section", "?")
        off    = s.get("offense", "").strip()
        punish = s.get("punishment", "N/A").strip()
        src    = s.get("source", "")
        score  = s.get("score", 0)
        desc   = s.get("description", "").strip()
        equiv  = s.get("equivalent_act") and s.get("equivalent_section")

        desc_short = (desc[:200] + "…") if len(desc) > 200 else desc

        equiv_line = (
            f"\n   Equivalent: {s['equivalent_act']} {s['equivalent_section']}"
            if equiv else ""
        )

        lines.append(
            f"\n{i}. {act} {sec}  [score={score:.2f} | {src}]\n"
            f"   Offense   : {off or 'See description'}\n"
            f"   Punishment: {punish}{equiv_line}\n"
            f"   Summary   : {desc_short}"
        )

    if result.get("rewritten"):
        lines.append(f"\n[Note: query was rewritten for better matching]")

    return "\n".join(lines)


# ── LangGraph node wrapper ────────────────────────────────────────────────────

def lexigraph_node(state: dict) -> dict:
    """
    LangGraph-compatible node. Reads structured_facts (or user_query as
    fallback) and stores retrieved laws into state['relevant_laws'].

    Wire into orchestrator_graph.py:
        graph.add_node("lexigraph", lexigraph_node)
        graph.add_edge("evidence_analyzer", "lexigraph")
    """
    facts    = state.get("structured_facts") or {}
    incident = facts.get("incident", {})
    sections = facts.get("sections", [])

    query_parts: list[str] = []
    if incident.get("summary"):
        query_parts.append(incident["summary"])
    if sections:
        section_hint = sections[0].replace("IPC ", "").replace("IPC_", "").replace("BNS ", "").replace("BNS_", "").strip()
    else:
        section_hint = None

    if not query_parts:
        query_parts.append(state.get("user_query", ""))

    query_text = ". ".join(filter(None, query_parts))
    result     = retrieve(query_text, section_hint=section_hint)

    state["relevant_laws"]    = result["ipc_sections"]
    state["lexigraph_result"] = result
    print(f"[LexiGraph] Retrieved {len(result['ipc_sections'])} law(s).")
    return state


# ── CLI / standalone runner ───────────────────────────────────────────────────

def _print_results(query: str, result: dict) -> None:
    import textwrap
    sections = result["ipc_sections"]
    W = 70

    print(f"\n🔍 Query: {query}\n")
    print("─" * W)

    if not sections:
        print("❌  No results found even after guardrail rewrite.")
        print("─" * W)
        return

    print(f"✅  Found {len(sections)} relevant law(s):\n")

    for i, law in enumerate(sections, 1):
        src   = law.get("source", "").upper()
        score = law.get("score", 0.0)
        act   = law.get("act", "")
        sec   = law.get("section", "?")
        desc  = law.get("description", "") or "(no description stored)"
        pun   = law.get("punishment", "") or "(no punishment stored)"

        if str(pun).strip().lower() == "nan":
            pun = "(not specified)"

        print("─" * W)
        print(f"  #{i}  {act} Section {sec}   [{src} | score {score:.3f}]")
        if law.get("equivalent_act") and law.get("equivalent_section"):
            print(f"      Equivalent: {law['equivalent_act']} {law['equivalent_section']}")
        print()
        print("  DESCRIPTION:")
        for line in textwrap.wrap(desc, width=W - 4):
            print(f"    {line}")
        print()
        print(f"  PUNISHMENT:  {pun}")
        print()

    print("─" * W)
    if result.get("rewritten"):
        print("  ℹ️  Query was rewritten by the guardrail LLM for better matching.")
        print("─" * W)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        q = " ".join(sys.argv[1:])
        r = retrieve(q)
        _print_results(q, r)
    else:
        test_cases = [
            ("Theft of electronics from employer's store caught on CCTV", "381"),
            ("Sending threatening WhatsApp messages to a person",          None),
            ("Murder of a person with premeditation",                      "302"),
            ("Cheating someone of money through fraudulent documents",     None),
            ("xyzabc completely unknown crime type",                       None),
        ]
        for q, hint in test_cases:
            r = retrieve(q, section_hint=hint)
            _print_results(q, r)