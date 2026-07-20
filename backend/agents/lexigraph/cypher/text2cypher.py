"""
LexiGraph — Text2Cypher Agent
=============================
NL crime query -> LangChain GraphCypherQAChain writes a Cypher query
against the Neo4j schema -> query runs against the graph -> results are
expanded through LegalRule precedence edges -> plain-English answer with
IPC + BNS sections and punishments.

Design choices:

1. Query generation and answer synthesis now go through LangChain's
   GraphCypherQAChain, with Groq as the LLM backend.

2. The chain is still constrained with a strict Cypher prompt that only
   allows read-style clauses and routes text matching through
   `db.index.fulltext.queryNodes(...)`.

3. After the initial graph hit list, `expand_with_rules()` walks one hop
   across OVERRIDES / ENHANCES / MORE_SPECIFIC_THAN style edges so legal
   precedence is surfaced alongside the direct matches.

4. This is still a structured graph lookup complement to the broader
   LexiGraph retrieval pipeline, not a semantic-search replacement.

Usage:
    python backend/agents/lexigraph/cypher/text2cypher.py "a person kidnapped a child for ransom"
    python backend/agents/lexigraph/cypher/text2cypher.py
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase

try:
    from dotenv import load_dotenv

    for candidate in [Path(".env"), Path("../.env"), Path("../../.env")]:
        if candidate.exists():
            load_dotenv(candidate)
            break
except ImportError:
    pass

AGENTS_DIR = Path(__file__).resolve().parents[2]
if str(AGENTS_DIR) not in sys.path:
    sys.path.insert(0, str(AGENTS_DIR))

from config.llm_config import get_llm
from langchain_core.prompts import PromptTemplate
from langchain_neo4j import GraphCypherQAChain, Neo4jGraph

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

RESULT_LIMIT = 8

# ----------------------------------------------------------------------
# Schema and examples given to the chain's Cypher generator.
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
        "question": "a person kidnapped a child for ransom",
        "cypher": (
            "CALL db.index.fulltext.queryNodes('lawSectionText', "
            "'kidnap* OR abduct* OR ransom OR minor OR child') "
            "YIELD node AS b, score "
            "WHERE b.act = 'BNS' "
            "OPTIONAL MATCH (i:LawSection {act:'IPC'})-[:REPLACED_BY]->(b) "
            "RETURN b.id AS id, b.act AS act, b.section AS bns_section, "
            "b.title AS bns_title, b.punishment AS bns_punishment, "
            "i.section AS ipc_section, i.title AS ipc_title, "
            "i.punishment AS ipc_punishment, score "
            "ORDER BY score DESC LIMIT 8"
        ),
    },
    {
        "question": "someone stole a car at night by breaking the lock",
        "cypher": (
            "CALL db.index.fulltext.queryNodes('lawSectionText', "
            "'theft OR steal* OR vehicle OR lock OR breaking OR housebreaking') "
            "YIELD node, score "
            "WHERE node.act = 'BNS' OR node.mapping_status = 'deleted_no_bns_successor' "
            "OPTIONAL MATCH (i:LawSection {act:'IPC'})-[:REPLACED_BY]->(node) "
            "RETURN node.id AS id, node.act AS matched_act, "
            "node.section AS matched_section, node.title AS title, "
            "node.punishment AS punishment, i.section AS ipc_section, "
            "i.title AS ipc_title, score "
            "ORDER BY score DESC LIMIT 8"
        ),
    },
    {
        "question": "what BNS section replaced IPC 302",
        "cypher": (
            "MATCH (i:LawSection {act:'IPC', section:'302'})-[r:REPLACED_BY]->(b:LawSection) "
            "RETURN b.id AS id, b.section AS bns_section, "
            "b.title AS bns_title, r.status AS status LIMIT 8"
        ),
    },
    {
        "question": "is theft a bailable offence",
        "cypher": (
            "CALL db.index.fulltext.queryNodes('crimeName', 'theft') YIELD node, score "
            "MATCH (node)-[:DEFINED_BY]->(l:LawSection) "
            "RETURN l.id AS id, l.section AS section, l.act AS act, "
            "l.bailable AS bailable, l.cognizable AS cognizable, score "
            "ORDER BY score DESC LIMIT 8"
        ),
    },
]

def _escape_prompt_literal(text: str) -> str:
    return text.replace("{", "{{").replace("}", "}}")


ESCAPED_SCHEMA_CONTEXT = _escape_prompt_literal(SCHEMA_CONTEXT)
ESCAPED_FEWSHOT = "\n\n".join(
    f"Q: {example['question']}\nCypher: {_escape_prompt_literal(example['cypher'])}"
    for example in FEWSHOT
)

CYPHER_GENERATION_TEMPLATE = f"""Task: Generate a Cypher statement to query an Indian criminal law graph database (IPC + BNS).

Schema:
{{schema}}

Additional graph context:
{ESCAPED_SCHEMA_CONTEXT}

Rules:
- Output ONLY the Cypher query. No explanation, no markdown fences.
- The query MUST be read-only. Only use MATCH, OPTIONAL MATCH, WITH, WHERE, RETURN, ORDER BY, LIMIT, UNWIND,
  and CALL db.index.fulltext.queryNodes.
- NEVER use CREATE, MERGE, SET, DELETE, DETACH, REMOVE, DROP, CALL apoc.*, or any procedure other than db.index.fulltext.queryNodes.
- For any narrative crime description, extract the 3-6 core legal-concept keywords and search them with Lucene OR syntax.
  Example: 'kidnap* OR ransom OR minor'. Do not pass the raw sentence directly as the search string.
- Prefer searching BNS sections first, then map to IPC through REPLACED_BY where applicable.
- Always include the section `id` column whenever returning a LawSection so downstream rule expansion can work.
- Keep result counts small and never exceed {RESULT_LIMIT} rows.

Examples:
""" + ESCAPED_FEWSHOT + """

Question:
{question}
"""

QA_TEMPLATE = """You are a legal graph assistant for Indian criminal law.

Answer the user's question using only the graph context below.
- If the context is empty, say that no matching section was found.
- Prefer section numbers, titles, and punishments when available.
- Do not invent facts that are not present in the context.

Question:
{question}

Context:
{context}
"""

CYPHER_GENERATION_PROMPT = PromptTemplate(
    input_variables=["schema", "question"],
    template=CYPHER_GENERATION_TEMPLATE,
)

QA_PROMPT = PromptTemplate(
    input_variables=["question", "context"],
    template=QA_TEMPLATE,
)

WRITE_KEYWORDS = re.compile(
    r"\b(CREATE|MERGE|SET|DELETE|DETACH|REMOVE|DROP|CALL\s+apoc\.)\b",
    re.IGNORECASE,
)


def is_read_only(cypher: str) -> bool:
    return not WRITE_KEYWORDS.search(cypher)


def build_chain() -> GraphCypherQAChain:
    graph = Neo4jGraph(
        url=NEO4J_URI,
        username=NEO4J_USER,
        password=NEO4J_PASSWORD,
        enhanced_schema=True,
    )
    return GraphCypherQAChain.from_llm(
        graph=graph,
        cypher_llm=get_llm(temperature=0),
        qa_llm=get_llm(temperature=0.1),
        cypher_prompt=CYPHER_GENERATION_PROMPT,
        qa_prompt=QA_PROMPT,
        top_k=RESULT_LIMIT,
        validate_cypher=True,
        return_intermediate_steps=True,
        allow_dangerous_requests=True,
        verbose=False,
    )


def expand_with_rules(session, section_ids: list[str]) -> list[dict[str, Any]]:
    """One hop out along precedence/enhancement edges, both directions,
    so e.g. a 363 hit also surfaces the 364A rule that overrides it."""
    section_ids = [section_id for section_id in section_ids if section_id]
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
    return [dict(record) for record in result]


def _row_section_ids(row: dict[str, Any]) -> list[str]:
    """Rows can name their columns id/act/section (generic) or
    bns_section/ipc_section (the BNS-first pattern) — pull out whatever
    LawSection.id values are present so rule-expansion still works."""
    ids = []
    if row.get("id"):
        ids.append(row["id"])
    if row.get("bns_section"):
        ids.append(f"BNS_{row['bns_section']}")
    if row.get("ipc_section"):
        ids.append(f"IPC_{row['ipc_section']}")
    if row.get("matched_act") and row.get("matched_section"):
        ids.append(f"{row['matched_act']}_{row['matched_section']}")
    return ids


def _format_row(row: dict[str, Any]) -> str:
    if "id" in row and "act" in row and "section" in row:
        line = f"  [{row['act']} {row['section']}] {row.get('title', '')}"
        if row.get("punishment"):
            line += f"\n      Punishment: {str(row['punishment'])[:150]}"
        if row.get("bailable"):
            line += f"\n      Bailable: {row['bailable']}"
        if row.get("cognizable"):
            line += f"\n      Cognizable: {row['cognizable']}"
        return line

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
            line += f"\n      Punishment: {str(punishment)[:150]}"
        return line

    return f"  {row}"


def _extract_intermediate(result: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    cypher = ""
    rows: list[dict[str, Any]] = []

    for step in result.get("intermediate_steps", []):
        if isinstance(step, dict) and "query" in step:
            cypher = str(step["query"]).strip()
        if isinstance(step, dict) and "context" in step:
            context = step["context"] or []
            rows = [dict(row) if not isinstance(row, dict) else row for row in context]

    return cypher, rows


def run(question: str, chain: GraphCypherQAChain, driver) -> str:
    try:
        chain_result = chain.invoke({"query": question})
    except Exception as exc:
        return f"GraphCypherQAChain failed: {exc}"

    cypher, rows = _extract_intermediate(chain_result)
    answer = str(chain_result.get("result", "")).strip()

    if cypher and not is_read_only(cypher):
        return (
            "Generated query was not read-only. "
            "Use read-only Neo4j credentials with this chain.\n\n"
            f"Generated query was:\n{cypher}"
        )

    if not rows:
        if cypher:
            return f"No sections matched.\n\nGenerated query was:\n{cypher}"
        return "No sections matched."

    with driver.session() as session:
        related = expand_with_rules(
            session,
            [section_id for row in rows for section_id in _row_section_ids(row)],
        )

    lines = []
    if answer:
        lines.extend(["Answer:", f"  {answer}", ""])
    if cypher:
        lines.extend([f"Cypher used:\n  {cypher}", ""])
    lines.append("Matches:")
    for row in rows:
        lines.append(_format_row(row))

    if related:
        lines.append("\nRelated by legal precedence (may override/enhance the above):")
        seen = set()
        for row in related:
            key = (row["act"], row["section"], row["relationship"])
            if key in seen:
                continue
            seen.add(key)
            condition = row.get("condition") or "no explicit condition recorded"
            lines.append(
                f"  [{row['act']} {row['section']}] {row['title']} "
                f"— {row['relationship']} ({condition})"
            )

    return "\n".join(lines)


def main() -> None:
    if not (NEO4J_URI and NEO4J_USER and NEO4J_PASSWORD):
        raise SystemExit("Set NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD (env or .env)")

    chain = build_chain()
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    try:
        if len(sys.argv) > 1:
            print(run(" ".join(sys.argv[1:]), chain, driver))
        else:
            print("LexiGraph Text2Cypher agent. Ctrl+C to exit.")
            while True:
                query = input("\nquery> ").strip()
                if not query:
                    continue
                print(run(query, chain, driver))
    finally:
        driver.close()


if __name__ == "__main__":
    main()
