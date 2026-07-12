"""
Sprint 4: LexiGraph Agent — GraphRAG Legal Retriever
======================================================
Connects Neo4j (graph) + Pinecone (vector) to retrieve real IPC sections
BEFORE any LLM reasoning call. This is the retrieval backbone for
Prosecutor, Defense, and Judge agents.

Pipeline for every query
------------------------
Step A  — spaCy NER: extract crime keywords from query_text
Step B  — Neo4j graph query: CONTAINS match on Crime.name and IPC.description
Step C  — Pinecone vector query: 384-dim semantic similarity search
Step D  — Merge + deduplicate + rank: Neo4j hits first (exact), then Pinecone
Step E  — Guardrail: if 0 results, LLM rewrites the query and retries once

Key facts about the database (verified before writing):
  Neo4j  : IPC nodes have {section, description, punishment}
           Crime nodes store FULL offense text (e.g. "Theft by clerk…")
           Relationship: (:Crime)-[:DEFINED_BY]->(:IPC)
  Pinecone: 448 vectors, dim=384 (all-MiniLM-L6-v2)
            IDs like "IPC_302", metadata={section, offense, punishment}
"""

import os
import json
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
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
PINECONE_HOST    = os.getenv(
    "PINECONE_HOST",
    "legal-embeddings-ce6891u.svc.aped-4627-b74a.pinecone.io",
)

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
    """Embed a list of strings using sentence-transformers (384-dim)."""
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer
        _embedder = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedder.encode(texts, convert_to_numpy=True).tolist()


def _pinecone():
    global _pinecone_index
    if _pinecone_index is None:
        if not PINECONE_API_KEY:
            raise RuntimeError("PINECONE_API_KEY not set in backend/.env")
        from pinecone import Pinecone
        pc = Pinecone(api_key=PINECONE_API_KEY)
        _pinecone_index = pc.Index(host=PINECONE_HOST)
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


# ── Step A: spaCy keyword extraction ─────────────────────────────────────────

# Legal crime keywords that spaCy may not label as NER entities but are
# critical for IPC matching.
_LEGAL_KEYWORDS = {
    "theft", "robbery", "dacoity", "murder", "homicide", "assault", "rape",
    "fraud", "cheating", "forgery", "extortion", "kidnap", "abduction",
    "trespass", "arson", "bribery", "corruption", "defamation", "sedition",
    "rioting", "hurt", "grievous", "intimidation", "threatening", "stalking",
    "dowry", "cruelty", "obscenity", "gambling", "smuggling", "trafficking",
    "poisoning", "accident", "negligence", "embezzlement", "breach",
    "misappropriation", "impersonation", "counterfeiting", "mischief",
}


def extract_crime_keywords(query_text: str) -> list[str]:
    """
    Step A — Use spaCy NER + legal keyword matching to extract crime terms.

    Returns a deduplicated list of keywords in order of confidence:
      1. spaCy EVENT entities (highest — explicit event labels)
      2. spaCy ORG/NORP entities that overlap legal terms
      3. Pattern-matched legal keywords from the text
      4. Significant nouns/noun-chunks as fallback
    """
    nlp  = _nlp()
    doc  = nlp(query_text)
    seen = set()
    keywords: list[str] = []

    def _add(word: str):
        w = word.strip().lower()
        if w and w not in seen and len(w) > 2:
            seen.add(w)
            keywords.append(w)

    # 1. spaCy named entities
    for ent in doc.ents:
        if ent.label_ in ("EVENT", "ORG", "NORP", "LAW", "GPE"):
            _add(ent.text)

    # 2. Legal keywords present in text (case-insensitive)
    text_lower = query_text.lower()
    for kw in _LEGAL_KEYWORDS:
        if kw in text_lower:
            _add(kw)

    # 3. Noun chunks as fallback (take first 4 words max per chunk)
    if len(keywords) < 2:
        for chunk in doc.noun_chunks:
            # Skip very short or stopword-only chunks
            if any(t.is_alpha and not t.is_stop for t in chunk):
                _add(" ".join(t.text for t in chunk if t.is_alpha)[:40])

    # 4. Individual non-stop nouns as final fallback
    if len(keywords) < 2:
        for token in doc:
            if token.pos_ in ("NOUN", "PROPN") and not token.is_stop:
                _add(token.lemma_)

    return keywords[:8]   # cap: 8 keywords is enough, more causes noise


# ── Step B: Neo4j graph queries ───────────────────────────────────────────────

def _neo4j_run(cypher: str, params: dict) -> list[dict]:
    driver = _neo4j()
    with driver.session(database=NEO4J_DATABASE) as session:
        result = session.run(cypher, params)
        return [dict(record) for record in result]


def _query_neo4j(keywords: list[str], section_hint: str = None) -> list[dict]:
    """
    Step B — Query Neo4j using the extracted keywords.

    Three strategies (run all, merge results):
      B1. Exact section fetch if a specific IPC number is known.
      B2. Crime node CONTAINS match on full offense text.
      B3. IPC description CONTAINS match (broader fallback).
    """
    results   = []
    seen_secs = set()

    def _add_rows(rows: list[dict], source: str):
        for r in rows:
            sec = str(r.get("section", "")).strip()
            if sec and sec not in seen_secs:
                seen_secs.add(sec)
                results.append({
                    "section":     sec,
                    "description": r.get("description", ""),
                    "punishment":  r.get("punishment", ""),
                    "offense":     r.get("offense", r.get("crime_name", "")),
                    "source":      source,
                    "score":       1.0 if source == "neo4j:exact" else 0.85,
                })

    # B1 — exact section
    if section_hint:
        clean = re.sub(r"[^0-9A-Za-z]", "", section_hint)
        rows = _neo4j_run(
            """
            MATCH (l:IPC)
            WHERE l.section = $sec OR l.section = $sec_upper
            RETURN l.section AS section, l.description AS description,
                   l.punishment AS punishment, '' AS offense
            LIMIT 3
            """,
            {"sec": clean, "sec_upper": clean.upper()},
        )
        _add_rows(rows, "neo4j:exact")

    if not keywords:
        return results

    # B2 — Crime node offense text CONTAINS keyword
    # Build WHERE clause dynamically for each keyword
    for kw in keywords[:5]:
        rows = _neo4j_run(
            """
            MATCH (c:Crime)-[:DEFINED_BY]->(l:IPC)
            WHERE toLower(c.name) CONTAINS toLower($kw)
            RETURN l.section AS section, l.description AS description,
                   l.punishment AS punishment, c.name AS offense
            LIMIT 5
            """,
            {"kw": kw},
        )
        _add_rows(rows, "neo4j:crime_node")

    # B3 — IPC description CONTAINS keyword (broader)
    if len(results) < 3:
        for kw in keywords[:4]:
            rows = _neo4j_run(
                """
                MATCH (l:IPC)
                WHERE toLower(l.description) CONTAINS toLower($kw)
                RETURN l.section AS section, l.description AS description,
                       l.punishment AS punishment, '' AS offense
                LIMIT 5
                """,
                {"kw": kw},
            )
            _add_rows(rows, "neo4j:description")

    return results


# ── Step C: Pinecone vector search ────────────────────────────────────────────

# IPC law vectors were ingested with IDs like "IPC_379", "IPC_302A" etc.
# FIR/case-summary vectors stored by evidence_analyzer use "CASE_..." IDs.
_IPC_ID_RE      = re.compile(r"^IPC_\d+[A-Za-z]*$")
_IPC_SECTION_RE = re.compile(r"^\d+[A-Za-z]*$")


def _is_ipc_hit(match_id: str, meta: dict) -> bool:
    """Return True only for IPC law vectors; skip FIR session embeddings."""
    if _IPC_ID_RE.match(match_id):
        return True
    sec = str(meta.get("section", ""))
    return bool(sec and _IPC_SECTION_RE.match(sec))


def _query_pinecone(query_text: str, top_k: int = 5) -> list[dict]:
    """
    Step C — Embed query_text and search Pinecone for semantically
    similar IPC sections. Filters out FIR/case-summary embeddings.
    """
    index  = _pinecone()
    vector = _embed([query_text])[0]

    # Request extra candidates so we still get top_k after filtering FIR noise
    response = index.query(
        vector=vector,
        top_k=top_k * 3,
        include_metadata=True,
    )

    results = []
    for match in response.get("matches", []):
        mid  = match.get("id", "")
        meta = match.get("metadata", {})

        # Skip FIR / case-summary embeddings
        if not _is_ipc_hit(mid, meta):
            continue

        section = meta.get("section", mid.replace("IPC_", ""))
        results.append({
            "section":     section,
            "description": meta.get("description", ""),
            "punishment":  meta.get("punishment", ""),
            "offense":     meta.get("offense", ""),
            "source":      "pinecone:vector",
            "score":       round(float(match.get("score", 0.0)), 4),
        })

        if len(results) >= top_k:
            break

    return results


# ── Step D: Merge, enrich from Neo4j, rank ────────────────────────────────────

def _enrich_from_neo4j(section: str) -> dict:
    """
    For a Pinecone hit that has a section number but no description,
    fetch the full node from Neo4j.
    """
    rows = _neo4j_run(
        """
        MATCH (l:IPC)
        WHERE l.section = $sec
        RETURN l.section AS section, l.description AS description,
               l.punishment AS punishment
        LIMIT 1
        """,
        {"sec": section},
    )
    if rows:
        return rows[0]
    return {}


def _merge_and_rank(
    neo4j_hits: list[dict],
    pinecone_hits: list[dict],
    top_n: int = 5,
) -> list[dict]:
    """
    Step D — Deduplicate and rank results.

    Scoring logic:
      - Neo4j exact match:       score = 1.0
      - Neo4j crime/desc match:  score = 0.85
      - Pinecone only:           score = cosine similarity (0–1)
      - Both Neo4j + Pinecone:   score = max(neo4j_score, pinecone_score) + 0.1 boost
    """
    merged: dict[str, dict] = {}   # section -> best record

    # Add Neo4j hits first
    for r in neo4j_hits:
        sec = r["section"]
        merged[sec] = dict(r)

    # Merge Pinecone hits
    for r in pinecone_hits:
        sec = r["section"]
        if sec in merged:
            # Section already found by Neo4j — boost score
            existing       = merged[sec]
            boosted_score  = max(existing["score"], r["score"]) + 0.10
            existing["score"]  = round(min(boosted_score, 1.0), 4)
            existing["source"] = existing["source"] + "+pinecone"
            # Fill in missing description from Pinecone metadata if Neo4j had none
            if not existing.get("description") and r.get("description"):
                existing["description"] = r["description"]
            if not existing.get("offense") and r.get("offense"):
                existing["offense"] = r["offense"]
        else:
            # New section from Pinecone — enrich with Neo4j description
            record = dict(r)
            if not record.get("description") or not record.get("punishment"):
                enriched = _enrich_from_neo4j(sec)
                if enriched:
                    record["description"] = record.get("description") or enriched.get("description", "")
                    record["punishment"]  = record.get("punishment")  or enriched.get("punishment", "")
            merged[sec] = record

    # Sort by score descending, return top_n
    ranked = sorted(merged.values(), key=lambda x: x["score"], reverse=True)
    return ranked[:top_n]


# ── Step E: Guardrail — LLM query rewrite ────────────────────────────────────

def _rewrite_query(original_query: str) -> str:
    """
    Step E — If retrieval returns 0 results, ask the LLM to rephrase
    the query using Indian Penal Code terminology.
    """
    from config.llm_config import get_llm
    llm    = get_llm(temperature=0.3)
    prompt = (
        f"You are an Indian legal expert. The following query returned no results "
        f"from an IPC (Indian Penal Code) database:\n\n"
        f"\"{original_query}\"\n\n"
        f"Rewrite this query using precise Indian Penal Code legal terminology "
        f"(e.g. 'theft', 'culpable homicide', 'criminal intimidation', 'cheating'). "
        f"Return ONLY the rewritten query — no explanation, no punctuation."
    )
    response  = llm.invoke(prompt)
    rewritten = response.content.strip().strip('"').strip("'")
    print(f"[LexiGraph] Query rewritten: '{original_query}' → '{rewritten}'")
    return rewritten


# ── Public API ────────────────────────────────────────────────────────────────

def retrieve(
    query_text: str,
    section_hint: str = None,
    top_n: int = 5,
    pinecone_top_k: int = 7,
) -> dict:
    """
    Main retrieval function. Call this BEFORE any LLM prompt.

    Parameters
    ----------
    query_text    : Free-text crime description from structured_facts or user query.
    section_hint  : Specific IPC section if already known (e.g. "302" or "IPC_381").
    top_n         : Number of final ranked results to return (default 5).
    pinecone_top_k: How many Pinecone candidates to fetch before ranking (default 7).

    Returns
    -------
    {
        "ipc_sections": [
            {
                "section":     "302",
                "description": "...",
                "punishment":  "Death or Imprisonment for Life + Fine",
                "offense":     "Murder",
                "source":      "neo4j:crime_node+pinecone",
                "score":       0.95
            },
            ...
        ],
        "keywords":       ["murder", "homicide"],
        "neo4j_count":    3,
        "pinecone_count": 5,
        "query_used":     "murder of a person",   # may differ if rewritten
        "rewritten":      False,
    }
    """
    print(f"\n[LexiGraph] ── Retrieving for: '{query_text[:80]}'")

    # ── Step A: extract keywords ──────────────────────────────────────
    keywords = extract_crime_keywords(query_text)
    print(f"[LexiGraph] Step A — keywords: {keywords}")

    # ── Step B: Neo4j ─────────────────────────────────────────────────
    neo4j_hits = []
    try:
        neo4j_hits = _query_neo4j(keywords, section_hint)
        print(f"[LexiGraph] Step B — Neo4j: {len(neo4j_hits)} hits")
    except Exception as e:
        print(f"[LexiGraph] Neo4j error: {e}")

    # ── Step C: Pinecone ──────────────────────────────────────────────
    pinecone_hits = []
    try:
        pinecone_hits = _query_pinecone(query_text, top_k=pinecone_top_k)
        print(f"[LexiGraph] Step C — Pinecone: {len(pinecone_hits)} hits")
    except Exception as e:
        print(f"[LexiGraph] Pinecone error: {e}")

    # ── Step D: merge & rank ──────────────────────────────────────────
    ranked = _merge_and_rank(neo4j_hits, pinecone_hits, top_n=top_n)
    print(f"[LexiGraph] Step D — merged: {len(ranked)} unique sections")

    rewritten = False

    # ── Step E: guardrail — retry with rewritten query ────────────────
    if len(ranked) == 0:
        print("[LexiGraph] Step E — 0 results, rewriting query...")
        rewritten_query = _rewrite_query(query_text)
        rewritten       = True

        # Retry with rewritten query
        keywords_2      = extract_crime_keywords(rewritten_query)
        neo4j_hits_2    = []
        pinecone_hits_2 = []
        try:
            neo4j_hits_2 = _query_neo4j(keywords_2, section_hint)
        except Exception as e:
            print(f"[LexiGraph] Neo4j retry error: {e}")
        try:
            pinecone_hits_2 = _query_pinecone(rewritten_query, top_k=pinecone_top_k)
        except Exception as e:
            print(f"[LexiGraph] Pinecone retry error: {e}")

        ranked     = _merge_and_rank(neo4j_hits_2, pinecone_hits_2, top_n=top_n)
        keywords   = keywords_2
        print(f"[LexiGraph] Step E retry — {len(ranked)} sections after rewrite")
        query_text = rewritten_query

    return {
        "ipc_sections":   ranked,
        "keywords":       keywords,
        "neo4j_count":    len(neo4j_hits),
        "pinecone_count": len(pinecone_hits),
        "query_used":     query_text,
        "rewritten":      rewritten,
    }


def format_for_prompt(result: dict) -> str:
    """
    Formats the retrieval result into a clean, numbered string
    ready to be injected into any LLM system/user prompt.
    """
    sections = result.get("ipc_sections", [])
    if not sections:
        return (
            "DATABASE RETRIEVAL: No relevant IPC sections found.\n"
            f"Keywords tried: {result.get('keywords', [])}\n"
            "The LLM must reason from general knowledge only."
        )

    lines = [
        f"RETRIEVED IPC SECTIONS  "
        f"[Neo4j:{result['neo4j_count']}  Pinecone:{result['pinecone_count']}  "
        f"Final:{len(sections)}]",
        "=" * 65,
    ]
    for i, s in enumerate(sections, 1):
        sec    = s.get("section", "?")
        off    = s.get("offense", "").strip()
        punish = s.get("punishment", "N/A").strip()
        src    = s.get("source", "")
        score  = s.get("score", 0)
        desc   = s.get("description", "").strip()

        # Show first 200 chars of description only — keeps prompt lean
        desc_short = (desc[:200] + "…") if len(desc) > 200 else desc

        lines.append(
            f"\n{i}. IPC {sec}  [score={score:.2f} | {src}]\n"
            f"   Offense   : {off or 'See description'}\n"
            f"   Punishment: {punish}\n"
            f"   Summary   : {desc_short}"
        )

    if result.get("rewritten"):
        lines.append(f"\n[Note: query was rewritten for better matching]")

    return "\n".join(lines)


# ── LangGraph node wrapper ────────────────────────────────────────────────────

def lexigraph_node(state: dict) -> dict:
    """
    LangGraph-compatible node. Reads structured_facts (or user_query as fallback)
    and stores retrieved laws into state['relevant_laws'].

    Wire into orchestrator_graph.py:
        graph.add_node("lexigraph", lexigraph_node)
        graph.add_edge("evidence_analyzer", "lexigraph")
    """
    facts   = state.get("structured_facts") or {}
    incident = facts.get("incident", {})
    sections = facts.get("sections", [])

    query_parts: list[str] = []
    if incident.get("summary"):
        query_parts.append(incident["summary"])
    if sections:
        # Use the first known section as a hint
        section_hint = sections[0].replace("IPC ", "").replace("IPC_", "").strip()
    else:
        section_hint = None

    if not query_parts:
        query_parts.append(state.get("user_query", ""))

    query_text = ". ".join(filter(None, query_parts))
    result     = retrieve(query_text, section_hint=section_hint)

    state["relevant_laws"]      = result["ipc_sections"]
    state["lexigraph_result"]   = result          # full result for downstream agents
    print(f"[LexiGraph] Retrieved {len(result['ipc_sections'])} law(s).")
    return state


# ── CLI / standalone runner ───────────────────────────────────────────────────

def _print_results(query: str, result: dict) -> None:
    """Pretty-print retrieve() output in a readable bordered format."""
    import textwrap
    sections = result["ipc_sections"]
    W = 70   # display width

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
        sec   = law.get("section", "?")
        desc  = law.get("description", "") or "(no description stored)"
        pun   = law.get("punishment", "") or "(no punishment stored)"

        # Normalise "nan" that comes from the CSV
        if str(pun).strip().lower() == "nan":
            pun = "(not specified)"

        print("─" * W)
        print(f"  #{i}  IPC Section {sec}   [{src} | score {score:.3f}]")
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

    # Single-query mode: python lexigraph.py "Theft of a bicycle …"
    if len(sys.argv) > 1:
        q = " ".join(sys.argv[1:])
        r = retrieve(q)
        _print_results(q, r)

    # Smoke-test mode: python lexigraph.py
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
