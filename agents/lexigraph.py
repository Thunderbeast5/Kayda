"""
LexiGraph Agent — Neo4j Legal Retriever
========================================
Queries Neo4j (444 IPC sections) BEFORE every LLM call so agents reason
over real database data, not hallucinated IPC numbers.

Query strategy (in order):
  1. Exact section fetch   — if a specific IPC number is known (e.g. IPC_381)
  2. Offense keyword search — CONTAINS match on IPC.offense field
  3. Description keyword search — CONTAINS match on IPC.description field

No external embedding service required.
"""

import re
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from neo4j_connection import execute_query


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clean_section_id(raw: str) -> str:
    """Normalise 'IPC 381' / 'ipc_381' / '381' → 'IPC_381'."""
    if not raw:
        return ""
    raw = raw.strip().upper().replace(" ", "_")
    if not raw.startswith("IPC_"):
        digits = re.sub(r"[^0-9]", "", raw)
        if digits:
            return f"IPC_{digits}"
    return raw


def _extract_keywords(text: str) -> list[str]:
    """
    Pulls meaningful keywords from a free-text query.
    Strips stop-words and short tokens.
    """
    stop = {
        "the","a","an","of","in","on","at","to","for","and","or","is","was",
        "are","were","by","with","from","that","this","it","be","as","not",
        "have","has","had","he","she","they","we","i","my","his","her","their",
        "accused","crime","when","where","unknown","ipc","section","india",
        "indian","court","case","act","under","whose","which","what","how",
    }
    words = re.sub(r"[^a-zA-Z0-9 ]", " ", text.lower()).split()
    return [w for w in words if len(w) > 3 and w not in stop]


# ── Neo4j queries ─────────────────────────────────────────────────────────────

def _fetch_exact(section_id: str) -> list[dict]:
    if not section_id:
        return []
    recs, _, _ = execute_query(
        """
        MATCH (l:IPC {section: $sec})
        RETURN l.section AS section, l.offense AS offense,
               l.description AS description, l.punishment AS punishment
        """,
        {"sec": section_id},
    )
    return [dict(r) | {"source": "neo4j:exact"} for r in recs]


def _search_offense(keywords: list[str], limit: int = 8) -> list[dict]:
    if not keywords:
        return []
    # Build WHERE clause: offense CONTAINS kw1 OR offense CONTAINS kw2 ...
    conditions = " OR ".join(
        f"toLower(l.offense) CONTAINS toLower($kw{i})"
        for i in range(len(keywords))
    )
    params = {f"kw{i}": kw for i, kw in enumerate(keywords)}
    params["limit"] = limit
    recs, _, _ = execute_query(
        f"""
        MATCH (l:IPC)
        WHERE {conditions}
        RETURN l.section AS section, l.offense AS offense,
               l.description AS description, l.punishment AS punishment
        LIMIT $limit
        """,
        params,
    )
    return [dict(r) | {"source": "neo4j:offense"} for r in recs]


def _search_description(keywords: list[str], limit: int = 5) -> list[dict]:
    if not keywords:
        return []
    conditions = " OR ".join(
        f"toLower(l.description) CONTAINS toLower($kw{i})"
        for i in range(len(keywords))
    )
    params = {f"kw{i}": kw for i, kw in enumerate(keywords)}
    params["limit"] = limit
    recs, _, _ = execute_query(
        f"""
        MATCH (l:IPC)
        WHERE {conditions}
        RETURN l.section AS section, l.offense AS offense,
               l.description AS description, l.punishment AS punishment
        LIMIT $limit
        """,
        params,
    )
    return [dict(r) | {"source": "neo4j:description"} for r in recs]


# ── Merge helpers ─────────────────────────────────────────────────────────────

def _merge(lists: list[list[dict]]) -> list[dict]:
    seen, out = set(), []
    for lst in lists:
        for r in lst:
            sec = r.get("section", "")
            if sec and sec not in seen:
                seen.add(sec)
                out.append(r)
    return out


# ── Public API ────────────────────────────────────────────────────────────────

def retrieve(
    query_text: str,
    crime_type: str = "",
    section_hint: str = None,
) -> dict:
    """
    Query Neo4j for relevant IPC sections BEFORE calling the LLM.

    Args:
        query_text:   Free-text description (used for keyword extraction).
        crime_type:   Crime category from structured facts (e.g. "Theft").
        section_hint: Specific IPC section if already known (e.g. "IPC_381").

    Returns:
        {
          "ipc_sections": [ {section, offense, description, punishment, source} ],
          "neo4j_count":  int,
          "query_text":   str,
        }
    """
    print(f"[LexiGraph] Querying Neo4j for: '{query_text[:70]}'")

    results = []

    # 1. Exact section lookup
    if section_hint:
        sec_id = _clean_section_id(section_hint)
        results += _fetch_exact(sec_id)

    # 2. Keyword search — combine crime_type + query_text keywords
    combined_text = f"{crime_type} {query_text}"
    keywords = _extract_keywords(combined_text)[:6]   # cap at 6 keywords

    if keywords:
        results = _merge([results, _search_offense(keywords)])

    # 3. Description fallback if still thin
    if len(results) < 3 and keywords:
        results = _merge([results, _search_description(keywords[:3])])

    print(f"[LexiGraph] Neo4j → {len(results)} IPC sections found")

    return {
        "ipc_sections": results[:10],
        "neo4j_count":  len(results),
        "query_text":   query_text,
    }


def format_for_prompt(retrieval: dict) -> str:
    """Formats retrieval result for injection into LLM prompts."""
    sections = retrieval.get("ipc_sections", [])
    if not sections:
        return "DATABASE: No matching IPC sections found in Neo4j."

    lines = [
        f"RETRIEVED IPC SECTIONS FROM NEO4J DATABASE ({retrieval['neo4j_count']} found):",
        "-" * 60,
    ]
    for i, s in enumerate(sections, 1):
        lines.append(
            f"{i}. {s.get('section','?')}  [{s.get('source','')}]\n"
            f"   Offense   : {s.get('offense','N/A')}\n"
            f"   Punishment: {s.get('punishment','N/A')}\n"
        )
    return "\n".join(lines)


# ── Smoke test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    tests = [
        ("theft of electronics from employer", "Theft",  "IPC_381"),
        ("threatening messages via WhatsApp",   "Criminal Intimidation", None),
        ("murder culpable homicide",            "Homicide", "IPC_302"),
    ]
    for qt, ct, sh in tests:
        print(f"\n{'='*55}")
        r = retrieve(qt, ct, sh)
        print(format_for_prompt(r))
