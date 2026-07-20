"""
LexiGraph — Text2Cypher Agent
=============================
NL crime query -> LLM writes a Cypher query against a fixed schema ->
query runs against the full-text index -> results are expanded through
your LegalRule precedence edges -> plain-English answer with IPC + BNS
sections and punishments.

Design choices (read this before treating output as "done"):

1. The LLM does NOT get to invent arbitrary Cypher. It is given the exact
   schema (labels/relationships/properties below) and told to route all
   text matching through `CALL db.index.fulltext.queryNodes(...)` rather
   than `CONTAINS`. This is the single biggest accuracy lever — see
   setup_indexes.py for why.

2. Every generated query is checked with `is_read_only()` before it
   touches the database. This is a legal-facts graph; a Text2Cypher
   agent that can accidentally run a MERGE/DELETE because the LLM
   misunderstood a prompt is a bug you do not want in production.

3. After the initial full-text hits, `expand_with_rules()` walks
   OVERRIDES / ENHANCES / MORE_SPECIFIC_THAN edges one hop out. This is
   what lets "kidnapped a child for ransom" surface IPC 364A as the
   controlling section even if the full-text match alone ranked IPC 363
   higher (your existing seed rule ipc_364a_over_363 already encodes
   this precedence — the agent should actually use it).

4. This is a STRUCTURED/FACTUAL complement to LexiGraph's Pinecone
   semantic search, not a replacement. Full-text search is good at
   surfacing sections whose actual words appear (or stem-match) in the
   query. It will still miss cases where the narrative uses no
   overlapping vocabulary at all (e.g. slang, regional phrasing) — that
   gap is exactly what your semantic pipeline is for. Best setup: run
   both, let Pinecone catch what full-text misses.

Usage:
    python text2cypher_agent.py "a person kidnapped a child for ransom"
    python text2cypher_agent.py   # interactive loop
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    for candidate in [Path(".env"), Path("../.env"), Path("../../.env")]:
        if candidate.exists():
            load_dotenv(candidate)
            break
except ImportError:
    pass

from neo4j import GraphDatabase
from openai import OpenAI  # DeepSeek is OpenAI-compatible, matches your existing stack

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

RESULT_LIMIT = 8

# ----------------------------------------------------------------------
# Schema given to the LLM — keep this in sync with neo4j_v2.py by hand.
# ----------------------------------------------------------------------
SCHEMA_CONTEXT = """
Nodes:
  (:Act {code, name})                       code is 'IPC' or 'BNS'
  (:Chapter {id, act, number, title})
  (:LawSection {id, act, section, title, description, punishment,
                 cognizable, bailable, court,      // IPC-only, may be ""
                 category, keywords,                // BNS-only, may be ""
                 data_complete, mapping_status})     // mapping_status: 'deleted_no_bns_successor' | 'new_no_ipc_predecessor' | absent
  (:Punishment {id, text})
  (:Crime {id, name})
  (:LegalRule {id, relationship, condition, confidence})

Relationships:
  (:Act)-[:HAS_CHAPTER]->(:Chapter)
  (:Act)-[:HAS_SECTION]->(:LawSection)
  (:Chapter)-[:HAS_SECTION]->(:LawSection)
  (:LawSection)-[:HAS_PUNISHMENT]->(:Punishment)
  (:Crime)-[:DEFINED_BY]->(:LawSection)
  (:LawSection {act:'IPC'})-[:REPLACED_BY {status}]->(:LawSection {act:'BNS'})
  (:LawSection {act:'BNS'})-[:REPLACES {status}]->(:LawSection {act:'IPC'})
  (:LawSection)-[:OVERRIDES|MORE_SPECIFIC_THAN|INCLUDES_ELEMENTS_OF|CANNOT_COEXIST_WITH|ENHANCES {condition, confidence}]->(:LawSection)

Full-text indexes (USE THESE for any text matching, never CONTAINS):
  lawSectionText  -> on LawSection(title, description, punishment, keywords)
  crimeName       -> on Crime(name)

Query pattern for full-text search:
  CALL db.index.fulltext.queryNodes('lawSectionText', $searchTerms) YIELD node, score
  RETURN node, score ORDER BY score DESC LIMIT $limit
"""

FEWSHOT = [
    {
        # Preferred pattern for narrative crime queries: BNS has curated
        # `keywords` on every section (IPC has none), so search BNS first
        # and hop back to the IPC section via REPLACED_BY. One query gives
        # both acts instead of guessing on IPC's bare description text.
        "question": "a person kidnapped a child for ransom",
        "cypher": (
            "CALL db.index.fulltext.queryNodes('lawSectionText', "
            "'kidnap* OR abduct* OR ransom OR minor OR child') "
            "YIELD node AS b, score "
            "WHERE b.act = 'BNS' "
            "OPTIONAL MATCH (i:LawSection {act:'IPC'})-[:REPLACED_BY]->(b) "
            "RETURN b.section AS bns_section, b.title AS bns_title, "
            "b.punishment AS bns_punishment, i.section AS ipc_section, "
            "i.title AS ipc_title, i.punishment AS ipc_punishment, score "
            "ORDER BY score DESC LIMIT $limit"
        ),
    },
    {
        # Fallback pattern: some IPC sections were dropped entirely under
        # BNS (mapping_status = 'deleted_no_bns_successor'), so they have
        # no BNS node to search via keywords. Search IPC text directly for
        # those. Combine with the BNS-first query above when the topic is
        # broad enough that either could apply.
        "question": "someone stole a car at night by breaking the lock",
        "cypher": (
            "CALL db.index.fulltext.queryNodes('lawSectionText', "
            "'theft OR steal* OR vehicle OR lock OR breaking OR housebreaking') "
            "YIELD node, score "
            "WHERE node.act = 'BNS' OR node.mapping_status = 'deleted_no_bns_successor' "
            "OPTIONAL MATCH (i:LawSection {act:'IPC'})-[:REPLACED_BY]->(node) "
            "RETURN node.act AS matched_act, node.section AS matched_section, "
            "node.title AS title, node.punishment AS punishment, "
            "i.section AS ipc_section, i.title AS ipc_title, score "
            "ORDER BY score DESC LIMIT $limit"
        ),
    },
    {
        "question": "what BNS section replaced IPC 302",
        "cypher": (
            "MATCH (i:LawSection {act:'IPC', section:'302'})-[r:REPLACED_BY]->(b:LawSection) "
            "RETURN b.section AS bns_section, b.title AS bns_title, r.status AS status"
        ),
    },
    {
        "question": "is theft a bailable offence",
        "cypher": (
            "CALL db.index.fulltext.queryNodes('crimeName', 'theft') YIELD node, score "
            "MATCH (node)-[:DEFINED_BY]->(l:LawSection) "
            "RETURN l.section AS section, l.act AS act, l.bailable AS bailable, "
            "l.cognizable AS cognizable ORDER BY score DESC LIMIT $limit"
        ),
    },
]

SYSTEM_PROMPT = f"""You are a Cypher query generator for an Indian criminal law graph (IPC + BNS) in Neo4j.

SCHEMA:
{SCHEMA_CONTEXT}

RULES:
- Output ONLY the Cypher query. No explanation, no markdown fences.
- The query MUST be read-only: only MATCH / CALL db.index.fulltext.queryNodes / WHERE / RETURN / ORDER BY / LIMIT / WITH / UNWIND / OPTIONAL MATCH.
  NEVER use CREATE, MERGE, SET, DELETE, DETACH, REMOVE, CALL apoc.*, or any procedure other than db.index.fulltext.queryNodes.
- For any narrative crime description, extract the 3-6 core legal-concept
  keywords (crime acts, victim type, weapon, aggravating circumstance,
  intent) and search them via db.index.fulltext.queryNodes('lawSectionText', ...).
  Use Lucene OR syntax and wildcard * for word-stem variants, e.g.
  'kidnap* OR ransom OR minor'. Do NOT pass the raw sentence as the search string.
- PREFER SEARCHING BNS FIRST, THEN MAP TO IPC: BNS LawSection nodes have a
  curated `keywords` property; IPC LawSection nodes do not (IPC only has
  title/description/punishment text). So for narrative queries, filter
  full-text hits to `node.act = 'BNS'` and OPTIONAL MATCH the IPC section
  via `(i:LawSection {act:'IPC'})-[:REPLACED_BY]->(b)` to get both acts in
  one query (see example 1). Only fall back to matching IPC nodes directly
  when the query is clearly about an old, since-deleted IPC offence with
  no BNS successor (`node.mapping_status = 'deleted_no_bns_successor'`,
  see example 2) — those have no BNS node to search keywords on at all.
- Always use the query parameter $limit for LIMIT (never hardcode a number).
- Prefer returning node.id, node.act, node.section, node.title, node.description, node.punishment, and score when searching LawSection.

EXAMPLES:
""" + "\n\n".join(
    f"Q: {ex['question']}\nCypher: {ex['cypher']}" for ex in FEWSHOT
)

WRITE_KEYWORDS = re.compile(
    r"\b(CREATE|MERGE|SET|DELETE|DETACH|REMOVE|DROP|CALL\s+apoc\.)\b", re.IGNORECASE
)


def is_read_only(cypher: str) -> bool:
    return not WRITE_KEYWORDS.search(cypher)


def generate_cypher(client: OpenAI, question: str) -> str:
    resp = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Q: {question}\nCypher:"},
        ],
        temperature=0,
        max_tokens=400,
    )
    cypher = resp.choices[0].message.content.strip()
    cypher = re.sub(r"^```(cypher)?|```$", "", cypher, flags=re.MULTILINE).strip()
    return cypher


def expand_with_rules(session, section_ids: list[str]) -> list[dict]:
    """One hop out along precedence/enhancement edges, both directions,
    so e.g. a 363 hit also surfaces the 364A rule that overrides it."""
    section_ids = [s for s in section_ids if s]
    if not section_ids:
        return []
    result = session.run(
        """
        UNWIND $ids AS sid
        MATCH (l:LawSection {id: sid})-[r:OVERRIDES|MORE_SPECIFIC_THAN|ENHANCES|INCLUDES_ELEMENTS_OF|CANNOT_COEXIST_WITH]-(other:LawSection)
        RETURN DISTINCT other.id AS id, other.act AS act, other.section AS section,
               other.title AS title, other.punishment AS punishment,
               type(r) AS relationship, r.condition AS condition
        """,
        ids=section_ids,
    )
    return [dict(r) for r in result]


def _row_section_ids(row: dict) -> list[str]:
    """Rows can name their columns id/act/section (generic) or
    bns_section/ipc_section (the BNS-first pattern) — pull out whatever
    LawSection.id values are present so rule-expansion still works."""
    ids = []
    if row.get("id") and row.get("act") and row.get("section"):
        ids.append(row["id"])
    if row.get("bns_section"):
        ids.append(f"BNS_{row['bns_section']}")
    if row.get("ipc_section"):
        ids.append(f"IPC_{row['ipc_section']}")
    if row.get("matched_act") and row.get("matched_section"):
        ids.append(f"{row['matched_act']}_{row['matched_section']}")
    return ids


def _format_row(row: dict) -> str:
    # Generic single-node shape
    if "id" in row and "act" in row and "section" in row:
        line = f"  [{row['act']} {row['section']}] {row.get('title', '')}"
        if row.get("punishment"):
            line += f"\n      Punishment: {row['punishment'][:150]}"
        return line

    # BNS-first-mapped-to-IPC shape
    if "bns_section" in row or "ipc_section" in row:
        parts = []
        if row.get("bns_section"):
            parts.append(f"BNS {row['bns_section']}: {row.get('bns_title', '')}")
        if row.get("ipc_section"):
            parts.append(f"IPC {row['ipc_section']}: {row.get('ipc_title', row.get('title', ''))}")
        elif row.get("bns_section"):
            parts.append("IPC: no equivalent (new offence under BNS)")
        line = "  " + " | ".join(parts)
        punishment = row.get("bns_punishment") or row.get("punishment") or row.get("ipc_punishment")
        if punishment:
            line += f"\n      Punishment: {punishment[:150]}"
        return line

    # Fallback: dump whatever came back
    return f"  {row}"


def run(question: str, client: OpenAI, driver) -> str:
    cypher = generate_cypher(client, question)

    if not is_read_only(cypher):
        return (
            f"Blocked a non-read-only query the model generated:\n{cypher}\n"
            "This should not happen with the schema constraints given — treat it as a bug."
        )

    with driver.session() as session:
        try:
            result = session.run(cypher, limit=RESULT_LIMIT)
            rows = [dict(r) for r in result]
        except Exception as e:
            return f"Cypher failed: {e}\n\nGenerated query was:\n{cypher}"

        if not rows:
            return f"No sections matched.\n\nGenerated query was:\n{cypher}"

        section_ids = [sid for r in rows for sid in _row_section_ids(r)]
        related = expand_with_rules(session, section_ids)

    lines = [f"Cypher used:\n  {cypher}\n", "Matches:"]
    for r in rows:
        lines.append(_format_row(r))

    if related:
        lines.append("\nRelated by legal precedence (may override/enhance the above):")
        seen = set()
        for r in related:
            key = (r["act"], r["section"], r["relationship"])
            if key in seen:
                continue
            seen.add(key)
            lines.append(
                f"  [{r['act']} {r['section']}] {r['title']} "
                f"— {r['relationship']} ({r['condition']})"
            )

    return "\n".join(lines)


def main():
    if not (NEO4J_URI and NEO4J_USER and NEO4J_PASSWORD):
        raise SystemExit("Set NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD (env or .env)")
    if not DEEPSEEK_API_KEY:
        raise SystemExit("Set DEEPSEEK_API_KEY (env or .env)")

    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    try:
        if len(sys.argv) > 1:
            print(run(" ".join(sys.argv[1:]), client, driver))
        else:
            print("LexiGraph Text2Cypher agent. Ctrl+C to exit.")
            while True:
                q = input("\nquery> ").strip()
                if not q:
                    continue
                print(run(q, client, driver))
    finally:
        driver.close()


if __name__ == "__main__":
    main()