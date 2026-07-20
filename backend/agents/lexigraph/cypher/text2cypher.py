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

FULLTEXT_SCORE_THRESHOLD = float(os.getenv("LEXIGRAPH_FULLTEXT_SCORE_THRESHOLD", "1.5"))
INITIAL_RETRIEVAL_LIMIT = int(os.getenv("LEXIGRAPH_INITIAL_TOP_K", "12"))
FINAL_TOP_K = int(os.getenv("LEXIGRAPH_FINAL_TOP_K", "3"))
RERANKER_MODEL = os.getenv("LEXIGRAPH_RERANKER_MODEL", "BAAI/bge-reranker-large")
RERANKER_WEIGHT = float(os.getenv("LEXIGRAPH_RERANKER_WEIGHT", "0.7"))
DEBUG_RANKING = os.getenv("LEXIGRAPH_DEBUG_RANKING", "").strip().lower() in {"1", "true", "yes", "on"}

_RERANKER = None
_RERANKER_ERROR: str | None = None

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
            "AND score > 1.5 "
            "OPTIONAL MATCH (i:LawSection {act:'IPC'})-[:REPLACED_BY]->(b) "
            "RETURN b.id AS id, b.act AS act, b.section AS bns_section, "
            "b.title AS bns_title, b.punishment AS bns_punishment, "
            "i.section AS ipc_section, i.title AS ipc_title, "
            "i.punishment AS ipc_punishment, score "
            "ORDER BY score DESC LIMIT 12"
        ),
    },
    {
        "question": "someone stole a car at night by breaking the lock",
        "cypher": (
            "CALL db.index.fulltext.queryNodes('lawSectionText', "
            "'theft OR steal* OR vehicle OR lock OR breaking OR housebreaking') "
            "YIELD node, score "
            "WHERE score > 1.5 "
            "AND (node.act = 'BNS' OR node.mapping_status = 'deleted_no_bns_successor') "
            "OPTIONAL MATCH (i:LawSection {act:'IPC'})-[:REPLACED_BY]->(node) "
            "RETURN node.id AS id, node.act AS matched_act, "
            "node.section AS matched_section, node.title AS title, "
            "node.punishment AS punishment, i.section AS ipc_section, "
            "i.title AS ipc_title, score "
            "ORDER BY score DESC LIMIT 12"
        ),
    },
    {
        "question": "what BNS section replaced IPC 302",
        "cypher": (
            "MATCH (i:LawSection {act:'IPC', section:'302'})-[r:REPLACED_BY]->(b:LawSection) "
            "RETURN b.id AS id, b.section AS bns_section, "
            "b.title AS bns_title, r.status AS status LIMIT 12"
        ),
    },
    {
        "question": "is theft a bailable offence",
        "cypher": (
            "CALL db.index.fulltext.queryNodes('crimeName', 'theft') YIELD node, score "
            "WHERE score > 1.5 "
            "MATCH (node)-[:DEFINED_BY]->(l:LawSection) "
            "RETURN l.id AS id, l.section AS section, l.act AS act, "
            "l.bailable AS bailable, l.cognizable AS cognizable, score "
            "ORDER BY score DESC LIMIT 12"
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
- For full-text queries, require a score floor using `WHERE score > {FULLTEXT_SCORE_THRESHOLD}` unless the query is a direct section lookup.
- Prefer searching BNS sections first, then map to IPC through REPLACED_BY where applicable.
- Do not retrieve on victim-type words like `minor`, `child`, or `woman` alone; combine them with offense words like kidnapping, sale, trafficking, pornography, ransom, assault, or rape.
- Always include the section `id` column whenever returning a LawSection so downstream rule expansion can work.
- Keep initial retrieval counts small and never exceed {INITIAL_RETRIEVAL_LIMIT} rows.

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
        top_k=INITIAL_RETRIEVAL_LIMIT,
        validate_cypher=True,
        return_direct=True,
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
               other.title AS title, other.description AS description,
               other.punishment AS punishment,
               type(r) AS relationship, r.condition AS condition
        """,
        ids=section_ids,
    )
    return [dict(record) for record in result]


def fetch_sections(session, section_ids: list[str]) -> list[dict[str, Any]]:
    section_ids = list(dict.fromkeys(section_ids))
    if not section_ids:
        return []
    result = session.run(
        """
        UNWIND $ids AS sid
        MATCH (l:LawSection {id: sid})
        OPTIONAL MATCH (l)-[:REPLACED_BY]->(b:LawSection {act:'BNS'})
        OPTIONAL MATCH (i:LawSection {act:'IPC'})-[:REPLACED_BY]->(l)
        RETURN DISTINCT
               l.id AS id,
               l.act AS act,
               l.section AS section,
               l.title AS title,
               l.description AS description,
               l.punishment AS punishment,
               l.bailable AS bailable,
               l.cognizable AS cognizable,
               l.keywords AS keywords,
               CASE
                   WHEN l.act = 'IPC' THEN b.section
                   ELSE i.section
               END AS counterpart_section,
               CASE
                   WHEN l.act = 'IPC' THEN b.title
                   ELSE i.title
               END AS counterpart_title,
               CASE
                   WHEN l.act = 'IPC' AND b IS NOT NULL THEN 'BNS'
                   WHEN l.act = 'BNS' AND i IS NOT NULL THEN 'IPC'
                   ELSE NULL
               END AS counterpart_act
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


def _normalize_rows(payload: Any) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, dict):
        return [payload]
    if isinstance(payload, (list, tuple)):
        rows: list[dict[str, Any]] = []
        for item in payload:
            if isinstance(item, dict):
                rows.append(item)
            else:
                try:
                    rows.append(dict(item))
                except Exception:
                    continue
        return rows
    return []


def _extract_intermediate(result: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    cypher = ""
    rows: list[dict[str, Any]] = []

    for step in result.get("intermediate_steps", []):
        if isinstance(step, dict) and "query" in step:
            cypher = str(step["query"]).strip()
        if isinstance(step, dict) and "context" in step:
            rows = _normalize_rows(step.get("context"))
            if rows:
                break

    if not rows:
        rows = _normalize_rows(result.get("result"))

    return cypher, rows


def _load_reranker():
    global _RERANKER, _RERANKER_ERROR
    if _RERANKER is not None or _RERANKER_ERROR is not None:
        return _RERANKER
    try:
        from sentence_transformers import CrossEncoder

        _RERANKER = CrossEncoder(RERANKER_MODEL)
    except Exception as exc:
        _RERANKER_ERROR = f"{type(exc).__name__}: {exc}"
    return _RERANKER


def _candidate_text(candidate: dict[str, Any]) -> str:
    parts = [
        f"Act: {candidate.get('act', '')}",
        f"Section: {candidate.get('section', '')}",
        "",
        "Title:",
        candidate.get("title", "") or "",
        "",
        "Description:",
        candidate.get("description", "") or "",
        "",
        "Keywords:",
        candidate.get("keywords", "") or "",
        "",
        "Punishment:",
        candidate.get("punishment", "") or "",
    ]
    if candidate.get("counterpart_act") and candidate.get("counterpart_section"):
        parts.extend(
            [
                "",
                f"Mapped {candidate['counterpart_act']}:",
                f"{candidate['counterpart_act']} {candidate['counterpart_section']} {candidate.get('counterpart_title', '')}".strip(),
            ]
        )
    if candidate.get("relationship"):
        parts.extend(
            [
                "",
                "Rule relation:",
                f"{candidate['relationship']} {candidate.get('condition', '') or ''}".strip(),
            ]
        )
    return "\n".join(part for part in parts if part is not None)


def _lexical_fallback_score(question: str, candidate: dict[str, Any]) -> float:
    query_terms = {
        term.lower()
        for term in re.findall(r"[A-Za-z]+", question)
        if len(term) > 3
    }
    doc_terms = {
        term.lower()
        for term in re.findall(r"[A-Za-z]+", _candidate_text(candidate))
        if len(term) > 3
    }
    overlap = len(query_terms & doc_terms)
    raw_score = float(candidate.get("raw_score") or 0.0)
    rule_bonus = 0.2 if candidate.get("relationship") else 0.0
    return overlap + raw_score + rule_bonus


def _normalize_score_map(values: list[float]) -> list[float]:
    if not values:
        return []
    lo = min(values)
    hi = max(values)
    if hi == lo:
        return [1.0 for _ in values]
    return [(value - lo) / (hi - lo) for value in values]


def _debug_print_rows(label: str, rows: list[dict[str, Any]]) -> None:
    if not DEBUG_RANKING:
        return
    print(f"\n===== {label} =====")
    for row in rows:
        print(row)


def _debug_print_candidates(label: str, candidates: list[dict[str, Any]]) -> None:
    if not DEBUG_RANKING:
        return
    print(f"\n===== {label} =====")
    for candidate in candidates:
        print(
            candidate.get("section", ""),
            "|",
            candidate.get("title", ""),
            "| raw=",
            f"{candidate.get('raw_score', 0.0):.4f}",
            "| rerank=",
            f"{candidate.get('rerank_score', 0.0):.4f}",
            "| raw_norm=",
            f"{candidate.get('raw_score_norm', 0.0):.4f}",
            "| final=",
            f"{candidate.get('final_score', 0.0):.4f}",
        )


def rerank_candidates(question: str, candidates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
    model = _load_reranker()
    reranker_name = f"CrossEncoder({RERANKER_MODEL})"

    if model is not None:
        pairs = [(question, _candidate_text(candidate)) for candidate in candidates]
        scores = model.predict(pairs)
        for candidate, score in zip(candidates, scores):
            candidate["rerank_score"] = float(score)
    else:
        reranker_name = f"fallback lexical reranker ({_RERANKER_ERROR})"
        for candidate in candidates:
            candidate["rerank_score"] = _lexical_fallback_score(question, candidate)

    rerank_values = [float(candidate.get("rerank_score", 0.0)) for candidate in candidates]
    raw_values = [float(candidate.get("raw_score", 0.0)) for candidate in candidates]
    rerank_norm = _normalize_score_map(rerank_values)
    raw_norm = _normalize_score_map(raw_values)

    for candidate, rerank_score_norm, raw_score_norm in zip(candidates, rerank_norm, raw_norm):
        candidate["rerank_score_norm"] = rerank_score_norm
        candidate["raw_score_norm"] = raw_score_norm
        candidate["final_score"] = (
            RERANKER_WEIGHT * rerank_score_norm
            + (1.0 - RERANKER_WEIGHT) * raw_score_norm
        )

    ranked = sorted(
        candidates,
        key=lambda candidate: (
            candidate.get("final_score", 0.0),
            candidate.get("rerank_score", 0.0),
            candidate.get("raw_score", 0.0),
        ),
        reverse=True,
    )
    return ranked, reranker_name


def _build_direct_candidates(
    direct_rows: list[dict[str, Any]],
    section_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates: dict[str, dict[str, Any]] = {}
    raw_scores: dict[str, float] = {}

    for row in direct_rows:
        score = row.get("score")
        try:
            score_value = float(score) if score is not None else 0.0
        except (TypeError, ValueError):
            score_value = 0.0
        for section_id in _row_section_ids(row):
            raw_scores[section_id] = max(score_value, raw_scores.get(section_id, float("-inf")))

    for row in section_rows:
        section_id = row["id"]
        candidate = dict(row)
        candidate["raw_score"] = raw_scores.get(section_id, 0.0)
        candidate["source"] = "full_text"
        candidates[section_id] = candidate

    return list(candidates.values())


def _build_related_candidates(
    related_rows: list[dict[str, Any]],
    section_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    related_by_id = {row["id"]: row for row in related_rows if row.get("id")}
    candidates = []
    for row in section_rows:
        section_id = row["id"]
        related = related_by_id.get(section_id)
        if not related:
            continue
        candidate = dict(row)
        candidate["source"] = "rule_expansion"
        candidate["relationship"] = related.get("relationship")
        candidate["condition"] = related.get("condition")
        candidates.append(candidate)
    return candidates


def _format_candidate_context(candidate: dict[str, Any]) -> str:
    lines = [
        f"[{candidate.get('act', '')} {candidate.get('section', '')}] {candidate.get('title', '')}".strip(),
    ]
    if candidate.get("description"):
        lines.append(f"Description: {candidate['description']}")
    if candidate.get("punishment"):
        lines.append(f"Punishment: {candidate['punishment']}")
    if candidate.get("bailable"):
        lines.append(f"Bailable: {candidate['bailable']}")
    if candidate.get("cognizable"):
        lines.append(f"Cognizable: {candidate['cognizable']}")
    if candidate.get("counterpart_act") and candidate.get("counterpart_section"):
        lines.append(
            f"Mapped counterpart: {candidate['counterpart_act']} {candidate['counterpart_section']} - "
            f"{candidate.get('counterpart_title', '')}"
        )
    if candidate.get("relationship"):
        condition = candidate.get("condition") or "no explicit condition recorded"
        lines.append(f"Rule relation: {candidate['relationship']} ({condition})")
    if "final_score" in candidate:
        lines.append(f"Final score: {candidate.get('final_score', 0.0):.4f}")
    return "\n".join(lines)


def answer_with_llm(
    question: str,
    primary_candidates: list[dict[str, Any]],
    related_candidates: list[dict[str, Any]],
) -> str:
    if not primary_candidates:
        return "No matching section passed the retrieval threshold."
    primary_context = "\n\n".join(_format_candidate_context(candidate) for candidate in primary_candidates)
    related_context = "\n\n".join(_format_candidate_context(candidate) for candidate in related_candidates)
    prompt = (
        "You are a legal graph assistant for Indian criminal law.\n"
        "Answer the user's question using only the retrieved graph sections below.\n"
        "- Prioritize the highest-ranked sections.\n"
        "- Mention IPC/BNS section numbers and titles explicitly.\n"
        "- If the facts are ambiguous, say so rather than inventing certainty.\n"
        "- Use rule-expansion sections only as supporting context. Do not let them override the top-ranked direct hits unless the rule relation explicitly says so.\n"
        "- If rule relations show one section overrides or is more specific than another, say that plainly.\n\n"
        f"Question:\n{question}\n\n"
        f"Top direct matches:\n{primary_context}\n\n"
        f"Related legal-rule sections:\n{related_context or 'None'}\n"
    )
    response = get_llm(temperature=0.1).invoke(prompt)
    return response.content.strip()


def run(question: str, chain: GraphCypherQAChain, driver) -> str:
    try:
        chain_result = chain.invoke({"query": question})
    except Exception as exc:
        return f"GraphCypherQAChain failed: {exc}"

    cypher, rows = _extract_intermediate(chain_result)

    if cypher and not is_read_only(cypher):
        return (
            "Generated query was not read-only. "
            "Use read-only Neo4j credentials with this chain.\n\n"
            f"Generated query was:\n{cypher}"
        )

    _debug_print_rows("BEFORE RERANK", rows)

    if not rows:
        if cypher:
            return (
                f"No sections matched above score threshold {FULLTEXT_SCORE_THRESHOLD}.\n\n"
                f"Generated query was:\n{cypher}"
            )
        return "No sections matched."

    with driver.session() as session:
        direct_section_ids = [section_id for row in rows for section_id in _row_section_ids(row)]
        direct_section_rows = fetch_sections(session, direct_section_ids)
        candidates = _build_direct_candidates(rows, direct_section_rows)
        ranked_candidates, reranker_name = rerank_candidates(question, candidates)
        _debug_print_candidates("AFTER RERANK", ranked_candidates)
        top_candidates = ranked_candidates[:FINAL_TOP_K]

        related = expand_with_rules(
            session,
            [candidate["id"] for candidate in top_candidates if candidate.get("id")],
        )
        _debug_print_rows("AFTER RULE EXPANSION", related)
        related_section_rows = fetch_sections(
            session,
            [row["id"] for row in related if row.get("id")],
        )

    related_candidates = _build_related_candidates(related, related_section_rows)
    answer = answer_with_llm(question, top_candidates, related_candidates)

    lines = []
    if answer:
        lines.extend(["Answer:", f"  {answer}", ""])
    if cypher:
        lines.extend([f"Cypher used:\n  {cypher}", ""])
    lines.extend(
        [
            (
                f"Retrieval pipeline: full-text > {FULLTEXT_SCORE_THRESHOLD} -> "
                f"{reranker_name} -> top {FINAL_TOP_K} -> rule expansion"
            ),
            "",
            "Top Matches:",
        ]
    )
    for candidate in top_candidates:
        lines.append(_format_row(candidate))
        lines.append(
            "      Source: "
            f"{candidate.get('source', 'unknown')} | "
            f"Raw: {candidate.get('raw_score', 0.0):.4f} | "
            f"Rerank: {candidate.get('rerank_score', 0.0):.4f} | "
            f"Final: {candidate.get('final_score', 0.0):.4f}"
        )

    if related_candidates:
        lines.extend(["", "Related Legal-Rule Sections:"])
        for candidate in related_candidates:
            lines.append(_format_row(candidate))
            condition = candidate.get("condition") or "no explicit condition recorded"
            lines.append(f"      Rule relation: {candidate['relationship']} ({condition})")

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
