"""
LexiGraph Agent — GraphRAG Legal Retriever (v3, multi-crime aware)
===================================================================
Key upgrade over v2:
- Handles FIRs containing multiple crime events by splitting a long narrative
  into intent-focused subqueries and retrieving per subquery.
- Reduces false positives where one broad section (e.g., "thug") outranks
  specific sections like robbery + murder.

Pipeline
--------
Step A  : Detect/segment incident into crime-intent chunks (multi-intent mode)
Step B  : Pinecone semantic retrieval per chunk (primary signal)
Step C  : Neo4j exact section lookup (if section_hint provided)
Step D  : Neo4j keyword fallback only when semantic is thin per chunk
Step E  : Enrich every candidate from Neo4j
Step F  : Merge with intent-aware scoring + diversity controls
Step G  : Guardrail rewrite retry (only if final is empty)
"""

import os
import re
from pathlib import Path
from typing import Optional, Dict, List, Tuple

from dotenv import load_dotenv

# ── Environment ───────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

NEO4J_URI      = os.getenv("NEO4J_URI", "")
NEO4J_USER     = os.getenv("NEO4J_USER", "")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

PINECONE_API_KEY   = os.getenv("PINECONE_API_KEY", "")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "legal-sections-v2")
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


# ── Keyword extraction ────────────────────────────────────────────────────────
_LEGAL_KEYWORDS = {
    "theft", "robb", "dacoit", "murder", "homicide", "assault", "rape",
    "fraud", "cheat", "forg", "extort", "kidnap", "abduct",
    "trespass", "arson", "brib", "corrupt", "defam", "sedit",
    "riot", "hurt", "grievous", "intimidat", "threat", "stalk",
    "dowry", "cruel", "obscen", "gambl", "smuggl", "traffick",
    "poison", "accident", "neglig", "embezzl", "breach",
    "misappropriat", "imperson", "counterfeit", "mischief",
    "weapon", "gun", "firearm", "shoot",
}

_CONCEPT_EXPANSION = {
    "document": ["forg"],
    "signature": ["forg"],
    "seal": ["forg"],
    "whatsapp": ["threat", "intimidat"],
    "sms": ["threat", "intimidat"],
    "text message": ["threat", "intimidat"],
    "online": ["cyber"],
    "email": ["cyber"],
    "gunpoint": ["weapon", "robb"],
    "shot": ["murder", "homicide", "weapon"],
}


def extract_crime_keywords(query_text: str) -> list[str]:
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
            if token.pos_ in ("NOUN", "PROPN", "VERB") and not token.is_stop:
                _add(token.lemma_)

    return keywords[:10]


# ── Multi-crime intent segmentation (NEW) ─────────────────────────────────────
_CRIME_FAMILIES: Dict[str, set] = {
    "homicide": {"murder", "kill", "killed", "homicide", "culpable", "death", "shot dead", "stabbed"},
    "robbery": {"rob", "robbed", "robbery", "dacoity", "snatch", "loot", "looted", "gunpoint"},
    "theft": {"theft", "stole", "stolen", "steal", "dishonestly take"},
    "assault": {"assault", "hurt", "grievous", "injury", "beaten", "attack"},
    "threat": {"threat", "intimidation", "blackmail", "extort", "menace"},
    "fraud": {"cheat", "cheating", "fraud", "forgery", "forged", "impersonation"},
    "sexual": {"rape", "molest", "sexual assault", "outrage modesty"},
    "abduction": {"kidnap", "abduct", "wrongful confinement", "hostage"},
    "property_damage": {"arson", "mischief", "vandal", "burned", "damage"},
    "weapons": {"gun", "firearm", "pistol", "rifle", "weapon", "shot"},
}

_CONNECTOR_SPLIT_RE = re.compile(
    r"\b(?:and then|then|during|while|before|after|thereafter|subsequently|later)\b|[.;]",
    flags=re.IGNORECASE,
)


def _detect_families(text: str) -> List[str]:
    t = text.lower()
    found = []
    for fam, terms in _CRIME_FAMILIES.items():
        if any(term in t for term in terms):
            found.append(fam)
    return found


def _segment_incident(query_text: str, max_segments: int = 4) -> List[dict]:
    """
    Returns list of intent chunks:
      [{ "text": "...", "families": [...], "weight": 1.0 }, ...]
    """
    q = " ".join(query_text.split()).strip()
    if not q:
        return []

    parts = [p.strip(" ,") for p in _CONNECTOR_SPLIT_RE.split(q) if p.strip(" ,")]
    if not parts:
        parts = [q]

    # Merge tiny fragments into previous
    merged = []
    for p in parts:
        if merged and len(p.split()) <= 4:
            merged[-1] = f"{merged[-1]} {p}".strip()
        else:
            merged.append(p)

    # Build chunks with family tags
    chunks = []
    for p in merged[:max_segments]:
        fams = _detect_families(p)
        chunks.append({
            "text": p,
            "families": fams,
            "weight": 1.0 + (0.15 * min(len(fams), 3)),  # slight boost for clearer legal intent
        })

    # If segmentation failed to discover variety, add full query as fallback chunk
    union_fams = set(f for c in chunks for f in c["families"])
    if len(union_fams) >= 2 and len(chunks) >= 2:
        return chunks

    return [{
        "text": q,
        "families": _detect_families(q),
        "weight": 1.0
    }]


def _law_text_for_family_probe(rec: dict) -> str:
    return " ".join([
        str(rec.get("title", "")),
        str(rec.get("offense", "")),
        str(rec.get("description", "")),
        str(rec.get("chapter", "")),
        str(rec.get("category", "")),
    ]).lower()


def _candidate_family_votes(rec: dict) -> set:
    text = _law_text_for_family_probe(rec)
    votes = set()
    for fam, terms in _CRIME_FAMILIES.items():
        if any(t in text for t in terms):
            votes.add(fam)
    return votes


# ── Retrieval steps ───────────────────────────────────────────────────────────
def _query_pinecone(query_text: str, top_k: int = 7, act_filter: Optional[str] = None) -> list[dict]:
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
            "offense":            meta.get("title", ""),
            "description":        "",
            "punishment":         meta.get("punishment", ""),
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


def _candidate_ids_for_hint(section_hint: str) -> list[str]:
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


def _query_neo4j_keyword(keywords: list[str]) -> list[dict]:
    results, seen = [], set()
    if not keywords:
        return results

    for kw in keywords[:6]:
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

    if len(results) < 4:
        for kw in keywords[:5]:
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


def _cosine_sim(a: list[float], b: list[float]) -> float:
    dot    = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _enrich_from_neo4j(law_id: str) -> dict:
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


# ── Scoring controls ──────────────────────────────────────────────────────────
MIN_CONFIDENCE = 0.32
_EXACT_HINT_SCORE = 0.97
_SOURCE_AGREEMENT_BOOST = 0.04
MIN_SEMANTIC_HITS = 3

# Multi-intent controls
MULTI_INTENT_BONUS_PER_CLUSTER = 0.05
MAX_MULTI_INTENT_BONUS = 0.12
UMBRELLA_PENALTY = 0.08   # penalize laws that match too many families weakly
SINGLE_CLUSTER_DOMINANCE_CAP = 2  # max final results from same top family before diversity penalty


def _merge_and_rank_multi(
    query_text: str,
    chunk_results: List[dict],
    neo4j_exact_hits: List[dict],
    top_n: int = 5,
) -> Tuple[List[dict], List[dict]]:
    """
    Returns:
      final_ranked, cluster_debug
    chunk_results: list of {
      "chunk_text": str,
      "families": [...],
      "weight": float,
      "pinecone_hits": [...],
      "fallback_hits": [...],
      "keywords": [...]
    }
    """
    merged: Dict[str, dict] = {}

    def _upsert(r: dict, cluster_idx: int, cluster_weight: float, cluster_families: List[str]):
        lid = r["law_id"]
        if lid not in merged:
            rec = dict(r)
            rec["_sources"] = {r["source"]}
            rec["_cluster_hits"] = {cluster_idx}
            rec["_cluster_weight_sum"] = cluster_weight
            rec["_cluster_families"] = set(cluster_families)
            if r["source"] == "pinecone:semantic":
                rec["_native_scores"] = [r["score"]]
            else:
                rec["_native_scores"] = []
            merged[lid] = rec
        else:
            rec = merged[lid]
            rec["_sources"].add(r["source"])
            rec["_cluster_hits"].add(cluster_idx)
            rec["_cluster_weight_sum"] += cluster_weight
            rec["_cluster_families"].update(cluster_families)
            if r["source"] == "pinecone:semantic":
                rec["_native_scores"].append(r["score"])
            for f in ("description", "title", "offense", "punishment"):
                if not rec.get(f) and r.get(f):
                    rec[f] = r[f]

    # Add per-cluster hits
    for i, cr in enumerate(chunk_results):
        for r in cr["pinecone_hits"]:
            _upsert(r, i, cr["weight"], cr["families"])
        for r in cr["fallback_hits"]:
            _upsert(r, i, cr["weight"] * 0.6, cr["families"])

    # Add explicit section hits globally
    for r in neo4j_exact_hits:
        lid = r["law_id"]
        if lid not in merged:
            rec = dict(r)
            rec["_sources"] = {"neo4j:exact"}
            rec["_cluster_hits"] = set()
            rec["_cluster_weight_sum"] = 0.0
            rec["_cluster_families"] = set()
            rec["_native_scores"] = []
            merged[lid] = rec
        else:
            merged[lid]["_sources"].add("neo4j:exact")

    if not merged:
        return [], []

    # Enrich
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

    # Local semantic score if no pinecone score exists
    need_local = [lid for lid, rec in merged.items() if len(rec["_native_scores"]) == 0]
    if need_local:
        cand_texts = [
            (f"{merged[lid].get('act','')} {merged[lid].get('title','')} {merged[lid].get('description','')}").strip() or lid
            for lid in need_local
        ]
        try:
            vectors = _embed([query_text] + cand_texts)
            qv, cvs = vectors[0], vectors[1:]
            for lid, v in zip(need_local, cvs):
                merged[lid]["_native_scores"] = [_cosine_sim(qv, v)]
        except Exception:
            for lid in need_local:
                merged[lid]["_native_scores"] = [0.5]

    # Score assembly
    for lid, rec in merged.items():
        base = max(rec["_native_scores"]) if rec["_native_scores"] else 0.0
        score = base

        # Explicit section hint should dominate
        if "neo4j:exact" in rec["_sources"]:
            score = max(score, _EXACT_HINT_SCORE)
        else:
            # Source agreement boost
            if len(rec["_sources"]) > 1:
                score = min(1.0, score + _SOURCE_AGREEMENT_BOOST)

            # Multi-cluster bonus (law matched multiple incident chunks)
            multi_bonus = min(
                MAX_MULTI_INTENT_BONUS,
                MULTI_INTENT_BONUS_PER_CLUSTER * max(0, len(rec["_cluster_hits"]) - 1)
            )
            score = min(1.0, score + multi_bonus)

        # Penalize "umbrella-only" broad matches
        family_votes = _candidate_family_votes(rec)
        if len(family_votes) >= 3 and len(rec["_cluster_hits"]) <= 1:
            score = max(0.0, score - UMBRELLA_PENALTY)

        rec["score"] = round(score, 4)
        rec["source"] = "+".join(sorted(rec["_sources"]))
        rec["_family_votes"] = sorted(list(family_votes))

    # First sort by score
    ranked = sorted(merged.values(), key=lambda x: x["score"], reverse=True)
    ranked = [r for r in ranked if r["score"] >= MIN_CONFIDENCE]

    # Diversity pass: avoid all top results from same family bucket
    family_counts: Dict[str, int] = {}
    diversified = []

    for rec in ranked:
        votes = rec.get("_family_votes", [])
        primary = votes[0] if votes else "unknown"
        cnt = family_counts.get(primary, 0)

        if cnt >= SINGLE_CLUSTER_DOMINANCE_CAP:
            rec_adj = dict(rec)
            rec_adj["score"] = round(max(0.0, rec["score"] - 0.05), 4)
            diversified.append(rec_adj)
        else:
            diversified.append(rec)

        family_counts[primary] = cnt + 1

    diversified = sorted(diversified, key=lambda x: x["score"], reverse=True)[:top_n]

    # Clean internals
    for rec in diversified:
        for k in ("_sources", "_cluster_hits", "_cluster_weight_sum", "_cluster_families", "_native_scores"):
            rec.pop(k, None)

    cluster_debug = []
    for i, cr in enumerate(chunk_results):
        cluster_debug.append({
            "cluster_index": i,
            "query": cr["chunk_text"],
            "families": cr["families"],
            "keywords": cr["keywords"],
            "pinecone_count": len(cr["pinecone_hits"]),
            "fallback_count": len(cr["fallback_hits"]),
        })

    return diversified, cluster_debug


def _rewrite_query(original_query: str) -> str:
    from config.llm_config import get_llm
    llm    = get_llm(temperature=0.3)
    prompt = (
        f"You are an Indian criminal law expert. The following query returned no "
        f"results from an IPC/BNS database:\n\n\"{original_query}\"\n\n"
        f"Rewrite this query using precise Indian criminal law terminology. "
        f"If multiple crimes happened, keep each act explicitly in the rewrite. "
        f"Return ONLY the rewritten query."
    )
    response  = llm.invoke(prompt)
    rewritten = response.content.strip().strip('"').strip("'")
    print(f"[LexiGraph] Query rewritten: '{original_query}' -> '{rewritten}'")
    return rewritten


# ── Public API ────────────────────────────────────────────────────────────────
def retrieve(
    query_text: str,
    section_hint: str = None,
    act_filter: Optional[str] = None,
    top_n: int = 5,
    pinecone_top_k: int = 7,
) -> dict:
    """
    Multi-intent retrieval:
    - Split FIR into chunks
    - Retrieve per chunk
    - Merge with intent-aware ranking
    """
    print(f"\n[LexiGraph] -- Retrieving for: '{query_text[:120]}'")

    # Step A: segment incident
    chunks = _segment_incident(query_text)
    print(f"[LexiGraph] Step A — Segmentation: {len(chunks)} chunk(s)")
    for i, c in enumerate(chunks, 1):
        print(f"  [{i}] {c['text']} | families={c['families']}")

    # Step C (global exact section)
    neo4j_exact_hits = []
    if section_hint:
        try:
            neo4j_exact_hits = _neo4j_exact(section_hint)
            print(f"[LexiGraph] Step C — Neo4j exact: {len(neo4j_exact_hits)} hits")
        except Exception as e:
            print(f"[LexiGraph] Neo4j exact-lookup error: {e}")

    # Step B + D per chunk
    chunk_results = []
    total_pinecone = 0
    total_fallback = 0
    all_keywords = []

    for idx, ch in enumerate(chunks):
        pinecone_hits = []
        fallback_hits = []
        keywords = []

        try:
            pinecone_hits = _query_pinecone(ch["text"], top_k=pinecone_top_k, act_filter=act_filter)
        except Exception as e:
            print(f"[LexiGraph] Pinecone error (chunk {idx}): {e}")

        if len(pinecone_hits) < MIN_SEMANTIC_HITS:
            keywords = extract_crime_keywords(ch["text"])
            try:
                fallback_hits = _query_neo4j_keyword(keywords)
            except Exception as e:
                print(f"[LexiGraph] Neo4j fallback error (chunk {idx}): {e}")

        total_pinecone += len(pinecone_hits)
        total_fallback += len(fallback_hits)
        all_keywords.extend(keywords)

        chunk_results.append({
            "chunk_text": ch["text"],
            "families": ch["families"],
            "weight": ch["weight"],
            "pinecone_hits": pinecone_hits,
            "fallback_hits": fallback_hits,
            "keywords": keywords,
        })

        print(
            f"[LexiGraph] Chunk {idx+1}: Pinecone={len(pinecone_hits)} "
            f"Fallback={len(fallback_hits)}"
        )

    # Step F merge/rank
    ranked, cluster_debug = _merge_and_rank_multi(
        query_text=query_text,
        chunk_results=chunk_results,
        neo4j_exact_hits=neo4j_exact_hits,
        top_n=top_n,
    )
    print(f"[LexiGraph] Step F — Final ranked: {len(ranked)}")

    rewritten = False
    query_used = query_text

    # Step G guardrail retry
    if len(ranked) == 0:
        print("[LexiGraph] Step G — 0 results, rewriting query...")
        rewritten_query = _rewrite_query(query_text)
        rewritten = True
        query_used = rewritten_query

        chunks2 = _segment_incident(rewritten_query)
        chunk_results2 = []
        total_pinecone = 0
        total_fallback = 0
        all_keywords = []

        for idx, ch in enumerate(chunks2):
            p2, f2, kws2 = [], [], []
            try:
                p2 = _query_pinecone(ch["text"], top_k=pinecone_top_k, act_filter=act_filter)
            except Exception as e:
                print(f"[LexiGraph] Pinecone retry error (chunk {idx}): {e}")

            if len(p2) < MIN_SEMANTIC_HITS:
                kws2 = extract_crime_keywords(ch["text"])
                try:
                    f2 = _query_neo4j_keyword(kws2)
                except Exception as e:
                    print(f"[LexiGraph] Neo4j retry error (chunk {idx}): {e}")

            total_pinecone += len(p2)
            total_fallback += len(f2)
            all_keywords.extend(kws2)

            chunk_results2.append({
                "chunk_text": ch["text"],
                "families": ch["families"],
                "weight": ch["weight"],
                "pinecone_hits": p2,
                "fallback_hits": f2,
                "keywords": kws2,
            })

        ranked, cluster_debug = _merge_and_rank_multi(
            query_text=rewritten_query,
            chunk_results=chunk_results2,
            neo4j_exact_hits=neo4j_exact_hits,
            top_n=top_n,
        )
        print(f"[LexiGraph] Step G retry — Final ranked: {len(ranked)}")

    dedup_keywords = []
    seen_kw = set()
    for k in all_keywords:
        lk = k.lower()
        if lk not in seen_kw:
            seen_kw.add(lk)
            dedup_keywords.append(k)

    return {
        "ipc_sections": ranked,
        "incident_clusters": cluster_debug,
        "keywords": dedup_keywords[:20],
        "neo4j_count": len(neo4j_exact_hits) + total_fallback,
        "pinecone_count": total_pinecone,
        "query_used": query_used,
        "rewritten": rewritten,
        "multi_intent": len(cluster_debug) > 1,
    }


def format_for_prompt(result: dict) -> str:
    sections = result.get("ipc_sections", [])
    clusters = result.get("incident_clusters", [])

    if not sections:
        return (
            "DATABASE RETRIEVAL: No relevant law sections found.\n"
            f"Keywords tried: {result.get('keywords', [])}\n"
            "The LLM must reason from general knowledge only."
        )

    lines = [
        f"RETRIEVED LAW SECTIONS  "
        f"[Neo4j:{result['neo4j_count']}  Pinecone:{result['pinecone_count']}  Final:{len(sections)}]",
        "=" * 72,
    ]

    if clusters:
        lines.append("INCIDENT CLUSTERS:")
        for c in clusters:
            lines.append(
                f"- C{c['cluster_index']+1}: {c['query']} "
                f"(families={c['families']}, pinecone={c['pinecone_count']}, fallback={c['fallback_count']})"
            )
        lines.append("-" * 72)

    for i, s in enumerate(sections, 1):
        act    = s.get("act", "")
        sec    = s.get("section", "?")
        off    = s.get("offense", "").strip()
        punish = s.get("punishment", "N/A").strip()
        src    = s.get("source", "")
        score  = s.get("score", 0)
        desc   = s.get("description", "").strip()
        equiv  = s.get("equivalent_act") and s.get("equivalent_section")
        fams   = s.get("_family_votes", [])

        desc_short = (desc[:220] + "…") if len(desc) > 220 else desc

        equiv_line = (
            f"\n   Equivalent: {s['equivalent_act']} {s['equivalent_section']}"
            if equiv else ""
        )

        fam_line = f"\n   Family    : {', '.join(fams)}" if fams else ""

        lines.append(
            f"\n{i}. {act} {sec}  [score={score:.2f} | {src}]"
            f"{fam_line}\n"
            f"   Offense   : {off or 'See description'}\n"
            f"   Punishment: {punish}{equiv_line}\n"
            f"   Summary   : {desc_short}"
        )

    if result.get("rewritten"):
        lines.append("\n[Note: query was rewritten for better matching]")

    return "\n".join(lines)


def lexigraph_node(state: dict) -> dict:
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


def _print_results(query: str, result: dict) -> None:
    import textwrap
    sections = result["ipc_sections"]
    clusters = result.get("incident_clusters", [])
    W = 78

    print(f"\n🔍 Query: {query}\n")
    print("─" * W)

    if clusters:
        print("🧩 Incident clusters:")
        for c in clusters:
            print(
                f"  C{c['cluster_index']+1}: {c['query']} "
                f"| families={c['families']} "
                f"| pinecone={c['pinecone_count']} fallback={c['fallback_count']}"
            )
        print("─" * W)

    if not sections:
        print("❌ No results found even after guardrail rewrite.")
        print("─" * W)
        return

    print(f"✅ Found {len(sections)} relevant law(s):\n")

    for i, law in enumerate(sections, 1):
        src   = law.get("source", "").upper()
        score = law.get("score", 0.0)
        act   = law.get("act", "")
        sec   = law.get("section", "?")
        desc  = law.get("description", "") or "(no description stored)"
        pun   = law.get("punishment", "") or "(no punishment stored)"
        fams  = law.get("_family_votes", [])

        if str(pun).strip().lower() == "nan":
            pun = "(not specified)"

        print("─" * W)
        fam_txt = f" | families: {', '.join(fams)}" if fams else ""
        print(f"  #{i}  {act} Section {sec}   [{src} | score {score:.3f}{fam_txt}]")
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
        print("  ℹ️ Query was rewritten by the guardrail LLM for better matching.")
        print("─" * W)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        q = " ".join(sys.argv[1:])
        r = retrieve(q)
        _print_results(q, r)
    else:
        test_cases = [
            ("A man robbed a jewellery shop at gunpoint. During the robbery, he shot and killed the shop owner before escaping with the cash.", None),
            ("Theft of electronics from employer's store caught on CCTV", "381"),
            ("Sending threatening WhatsApp messages to a person", None),
            ("Murder of a person with premeditation", "302"),
            ("Cheating someone of money through fraudulent documents", None),
            ("xyzabc completely unknown crime type", None),
        ]
        for q, hint in test_cases:
            r = retrieve(q, section_hint=hint)
            _print_results(q, r)