"""
LexiGraph — Text2Cypher Agent (schema-aligned)
==============================================
Natural-language crime query -> LangChain GraphCypherQAChain generates
read-only Cypher -> query runs on Neo4j -> rows are expanded with legal
rule edges -> reranked -> concise legal answer.

This version is aligned with the updated ingestion graph:
- :LawSection unified label
- mapping_status values:
    - deleted_no_bns_successor
    - new_no_ipc_predecessor
- fulltext indexes expected:
    - lawSectionText on LawSection(title, description, punishment, keywords)
    - crimeName on Crime(name)
- mapping edge status expected:
    - (:IPC)-[:REPLACED_BY {status}]->(:BNS)
    - (:BNS)-[:REPLACES {status}]->(:IPC)
"""
from __future__ import annotations

import json
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

STATUS_DELETED_NO_BNS = "deleted_no_bns_successor"
STATUS_NEW_NO_IPC = "new_no_ipc_predecessor"

_RERANKER = None
_RERANKER_ERROR: str | None = None

# ----------------------------------------------------------------------
# Schema context given to Cypher generator.
# ----------------------------------------------------------------------
SCHEMA_CONTEXT = f"""
Nodes:
  (:Act {{code, name}})                       code is 'IPC' or 'BNS'
  (:Chapter {{id, act, number, title}})
  (:LawSection {{
      id, act, section, title, description, punishment,
      cognizable, bailable, court,      // IPC-only may be empty
      category, keywords,                // BNS-only may be empty
      data_complete,
      mapping_status                     // '{STATUS_DELETED_NO_BNS}' | '{STATUS_NEW_NO_IPC}' | absent
  }})
  (:Punishment {{id, text}})
  (:Crime {{id, name}})
  (:Keyword {{id, name}})
  (:LegalRule {{id, relationship, condition, confidence}})

Relationships:
  (:Act)-[:HAS_CHAPTER]->(:Chapter)
  (:Act)-[:HAS_SECTION]->(:LawSection)
  (:Chapter)-[:HAS_SECTION]->(:LawSection)
  (:LawSection)-[:HAS_PUNISHMENT]->(:Punishment)
  (:LawSection)-[:HAS_KEYWORD]->(:Keyword)
  (:Crime)-[:DEFINED_BY]->(:LawSection)

  (:LawSection {{act:'IPC'}})-[:REPLACED_BY {{status, note, raw_mapping}}]->(:LawSection {{act:'BNS'}})
  (:LawSection {{act:'BNS'}})-[:REPLACES {{status, note, raw_mapping}}]->(:LawSection {{act:'IPC'}})

  (:LawSection)-[:OVERRIDES|MORE_SPECIFIC_THAN|ENHANCES|INCLUDES_ELEMENTS_OF|CANNOT_COEXIST_WITH {{condition, confidence}}]->(:LawSection)

Full-text indexes (USE THESE for text matching, never CONTAINS):
  lawSectionText  -> on LawSection(title, description, punishment, keywords)
  crimeName       -> on Crime(name)

Pattern:
  CALL db.index.fulltext.queryNodes('lawSectionText', $searchTerms) YIELD node, score
  RETURN node, score ORDER BY score DESC LIMIT $limit
"""

FEWSHOT = [
    {
        "question": "a person kidnapped a child for ransom",
        "cypher": (
            "CALL db.index.fulltext.queryNodes('lawSectionText', "
            "'kidnap* OR abduct* OR ransom OR hostage') "
            "YIELD node AS b, score "
            "WHERE b.act = 'BNS' AND score > 1.5 "
            "OPTIONAL MATCH (i:LawSection {act:'IPC'})-[r:REPLACED_BY]->(b) "
            "RETURN b.id AS id, b.act AS act, b.section AS bns_section, "
            "b.title AS bns_title, b.punishment AS bns_punishment, "
            "i.section AS ipc_section, i.title AS ipc_title, "
            "i.punishment AS ipc_punishment, r.status AS mapping_status, score "
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
            "OPTIONAL MATCH (i:LawSection {act:'IPC'})-[r:REPLACED_BY]->(node) "
            "RETURN node.id AS id, node.act AS matched_act, "
            "node.section AS matched_section, node.title AS title, "
            "node.punishment AS punishment, i.section AS ipc_section, "
            "i.title AS ipc_title, r.status AS mapping_status, score "
            "ORDER BY score DESC LIMIT 12"
        ),
    },
    {
        "question": "what BNS section replaced IPC 302",
        "cypher": (
            "MATCH (i:LawSection {act:'IPC', section:'302'})-[r:REPLACED_BY]->(b:LawSection {act:'BNS'}) "
            "RETURN b.id AS id, b.section AS bns_section, b.title AS bns_title, "
            "r.status AS status LIMIT 12"
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

CYPHER_GENERATION_TEMPLATE = f"""Task: Generate a Cypher statement for an Indian criminal law graph (IPC + BNS).

Schema:
{{schema}}

Additional graph context:
{ESCAPED_SCHEMA_CONTEXT}

Rules:
- Output ONLY Cypher. No explanation, no markdown fences.
- Query MUST be read-only. Allowed clauses:
  MATCH, OPTIONAL MATCH, WITH, WHERE, RETURN, ORDER BY, LIMIT, UNWIND,
  CALL db.index.fulltext.queryNodes.
- NEVER use CREATE, MERGE, SET, DELETE, DETACH, REMOVE, DROP, CALL apoc.*, or procedures other than db.index.fulltext.queryNodes.
- For narrative incidents, extract 3-6 legal keywords and use Lucene OR syntax.
  Example: 'kidnap* OR ransom OR hostage'. Do not pass raw sentence as search string.
- For full-text queries, enforce: WHERE score > {FULLTEXT_SCORE_THRESHOLD}
  except direct exact section lookups.
- Prefer BNS-first retrieval and map to IPC via REPLACES/REPLACED_BY as needed.
- mapping_status values are exact strings:
  '{STATUS_DELETED_NO_BNS}', '{STATUS_NEW_NO_IPC}'.
- Do not retrieve on victim-type words alone (minor/woman/child) without offense words.
- Always include id when returning LawSection rows.
- Keep retrieval <= {INITIAL_RETRIEVAL_LIMIT} rows.

Examples:
""" + ESCAPED_FEWSHOT + """

Question:
{question}
"""

QA_TEMPLATE = """You are a legal graph assistant for Indian criminal law.

Answer the user using only the context below.
- If context is empty, say no matching section was found.
- Prefer section numbers, titles, punishments, and mapping counterpart where present.
- Do not invent facts.

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

DECOMPOSE_SYSTEM_PROMPT = """You are a legal-analysis assistant for Indian criminal law (IPC/BNS).
Given an incident description, identify each DISTINCT criminal act.

For each act output:
  - "label"
  - "query_text"
  - "raw_span"

Respond ONLY valid JSON:
{"acts":[{"label":"...","query_text":"...","raw_span":"..."}]}
"""

WRITE_KEYWORDS = re.compile(
    r"\b(CREATE|MERGE|SET|DELETE|DETACH|REMOVE|DROP|CALL\s+apoc\.)\b",
    re.IGNORECASE,
)
MULTI_CRIME_CONNECTOR_RE = re.compile(
    r"\b(?:and then|then|thereafter|subsequently|later|after that|afterwards|while|during)\b|[.;]",
    re.IGNORECASE,
)
CRIME_FAMILY_PATTERNS = {
    "kidnapping": ("kidnap", "abduct", "hostage", "ransom"),
    "theft": ("steal", "stole", "stolen", "theft", "snatch"),
    "robbery": ("robbery", "robbed", "loot", "looted", "gunpoint"),
    "murder": ("murder", "killed", "shot", "stabbed", "death", "died"),
    "hurt": ("hurt", "injury", "injured", "assault", "beat", "beaten"),
    "rape": ("rape", "sexual assault", "molest"),
    "cheating": ("cheat", "cheated", "fraud"),
    "forgery": ("forged", "forgery", "fake document"),
    "intimidation": ("threat", "threatened", "intimidation", "blackmail"),
    "extortion": ("extort", "extortion"),
    "trespass": ("trespass", "housebreaking", "broke into", "entered unlawfully"),
}


def is_read_only(cypher: str) -> bool:
    return not WRITE_KEYWORDS.search(cypher)


def _detect_crime_families(text: str) -> set[str]:
    lowered = text.lower()
    found = set()
    for family, patterns in CRIME_FAMILY_PATTERNS.items():
        if any(pattern in lowered for pattern in patterns):
            found.add(family)
    return found


def _looks_multi_crime(question: str) -> bool:
    connectors = len(re.findall(MULTI_CRIME_CONNECTOR_RE, question))
    families = _detect_crime_families(question)
    return len(families) >= 2 or connectors >= 2


def _decompose_incident(question: str) -> list[dict[str, str]]:
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        response = get_llm(temperature=0.0).invoke(
            [SystemMessage(content=DECOMPOSE_SYSTEM_PROMPT), HumanMessage(content=question)]
        )
        raw = response.content.strip()
        raw = re.sub(r"^```(json)?|```$", "", raw, flags=re.MULTILINE).strip()
        data = json.loads(raw)
    except Exception:
        return [{"label": "Reported incident", "query_text": question, "raw_span": question}]

    acts = []
    for act in data.get("acts", []):
        label = str(act.get("label") or "").strip()
        query_text = str(act.get("query_text") or "").strip() or label
        raw_span = str(act.get("raw_span") or "").strip() or query_text
        if not query_text:
            continue
        acts.append({"label": label or query_text, "query_text": query_text, "raw_span": raw_span})

    if not acts:
        return [{"label": "Reported incident", "query_text": question, "raw_span": question}]
    return acts


def verify_runtime_schema(driver) -> None:
    """
    Fail fast with actionable error if fulltext indexes are missing.
    """
    with driver.session() as session:
        # Neo4j 5: SHOW FULLTEXT INDEXES
        rows = list(session.run("SHOW FULLTEXT INDEXES YIELD name, state RETURN name, state"))
        names = {row["name"] for row in rows}
        missing = [idx for idx in ("lawSectionText", "crimeName") if idx not in names]
        if missing:
            raise RuntimeError(
                "Missing required full-text indexes: "
                + ", ".join(missing)
                + ". Run neo4j_v3.py ingest (which creates fulltext indexes)."
            )


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
    section_ids = [sid for sid in section_ids if sid]
    if not section_ids:
        return []
    result = session.run(
        """
        UNWIND $ids AS sid
        MATCH (l:LawSection {id: sid})-[r:OVERRIDES|MORE_SPECIFIC_THAN|ENHANCES|INCLUDES_ELEMENTS_OF|CANNOT_COEXIST_WITH]-(other:LawSection)
        RETURN DISTINCT
               other.id AS id, other.act AS act, other.section AS section,
               other.title AS title, other.description AS description,
               other.punishment AS punishment, other.bailable AS bailable, other.cognizable AS cognizable,
               other.keywords AS keywords,
               type(r) AS relationship, r.condition AS condition, r.confidence AS confidence
        """
        ,
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
        OPTIONAL MATCH (l)-[l2b:REPLACED_BY]->(b:LawSection {act:'BNS'})
        OPTIONAL MATCH (i:LawSection {act:'IPC'})-[i2l:REPLACED_BY]->(l)

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
               l.mapping_status AS mapping_status,

               CASE WHEN l.act = 'IPC' THEN b.section ELSE i.section END AS counterpart_section,
               CASE WHEN l.act = 'IPC' THEN b.title ELSE i.title END AS counterpart_title,
               CASE
                   WHEN l.act = 'IPC' AND b IS NOT NULL THEN 'BNS'
                   WHEN l.act = 'BNS' AND i IS NOT NULL THEN 'IPC'
                   ELSE NULL
               END AS counterpart_act,

               CASE
                   WHEN l.act = 'IPC' THEN l2b.status
                   WHEN l.act = 'BNS' THEN i2l.status
                   ELSE NULL
               END AS counterpart_mapping_status
        """
        ,
        ids=section_ids,
    )
    return [dict(record) for record in result]


def _row_section_ids(row: dict[str, Any]) -> list[str]:
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
            line += f"\n      Punishment: {str(row['punishment'])[:220]}"
        if row.get("bailable"):
            line += f"\n      Bailable: {row['bailable']}"
        if row.get("cognizable"):
            line += f"\n      Cognizable: {row['cognizable']}"
        if row.get("mapping_status"):
            line += f"\n      Mapping status: {row['mapping_status']}"
        return line

    if "bns_section" in row or "ipc_section" in row:
        parts = []
        if row.get("bns_section"):
            parts.append(f"BNS {row['bns_section']}: {row.get('bns_title', '')}")
        if row.get("ipc_section"):
            parts.append(f"IPC {row['ipc_section']}: {row.get('ipc_title', row.get('title', ''))}")
        elif row.get("bns_section"):
            parts.append("IPC: no equivalent")
        line = "  " + " | ".join(parts)
        punishment = row.get("bns_punishment") or row.get("punishment") or row.get("ipc_punishment")
        if punishment:
            line += f"\n      Punishment: {str(punishment)[:220]}"
        if row.get("mapping_status"):
            line += f"\n      Mapping edge status: {row['mapping_status']}"
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
        "",
        "Mapping status:",
        candidate.get("mapping_status", "") or "",
    ]
    if candidate.get("counterpart_act") and candidate.get("counterpart_section"):
        parts.extend(
            [
                "",
                "Mapped counterpart:",
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
    query_terms = {term.lower() for term in re.findall(r"[A-Za-z]+", question) if len(term) > 3}
    doc_terms = {term.lower() for term in re.findall(r"[A-Za-z]+", _candidate_text(candidate)) if len(term) > 3}
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
    return [(v - lo) / (hi - lo) for v in values]


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
    for c in candidates:
        print(
            c.get("section", ""),
            "|",
            c.get("title", ""),
            "| raw=",
            f"{c.get('raw_score', 0.0):.4f}",
            "| rerank=",
            f"{c.get('rerank_score', 0.0):.4f}",
            "| raw_norm=",
            f"{c.get('raw_score_norm', 0.0):.4f}",
            "| final=",
            f"{c.get('final_score', 0.0):.4f}",
        )


def rerank_candidates(question: str, candidates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
    model = _load_reranker()
    reranker_name = f"CrossEncoder({RERANKER_MODEL})"

    if model is not None:
        pairs = [(question, _candidate_text(c)) for c in candidates]
        scores = model.predict(pairs)
        for c, score in zip(candidates, scores):
            c["rerank_score"] = float(score)
    else:
        reranker_name = f"fallback lexical reranker ({_RERANKER_ERROR})"
        for c in candidates:
            c["rerank_score"] = _lexical_fallback_score(question, c)

    rerank_values = [float(c.get("rerank_score", 0.0)) for c in candidates]
    raw_values = [float(c.get("raw_score", 0.0)) for c in candidates]
    rerank_norm = _normalize_score_map(rerank_values)
    raw_norm = _normalize_score_map(raw_values)

    for c, rrn, rn in zip(candidates, rerank_norm, raw_norm):
        c["rerank_score_norm"] = rrn
        c["raw_score_norm"] = rn
        c["final_score"] = RERANKER_WEIGHT * rrn + (1.0 - RERANKER_WEIGHT) * rn

    ranked = sorted(
        candidates,
        key=lambda c: (c.get("final_score", 0.0), c.get("rerank_score", 0.0), c.get("raw_score", 0.0)),
        reverse=True,
    )
    return ranked, reranker_name


def _build_direct_candidates(direct_rows: list[dict[str, Any]], section_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: dict[str, dict[str, Any]] = {}
    raw_scores: dict[str, float] = {}

    for row in direct_rows:
        score = row.get("score")
        try:
            score_value = float(score) if score is not None else 0.0
        except (TypeError, ValueError):
            score_value = 0.0
        for sid in _row_section_ids(row):
            raw_scores[sid] = max(score_value, raw_scores.get(sid, float("-inf")))

    for row in section_rows:
        sid = row["id"]
        candidate = dict(row)
        candidate["raw_score"] = raw_scores.get(sid, 0.0)
        candidate["source"] = "full_text_or_exact_match"
        candidates[sid] = candidate

    return list(candidates.values())


def _build_related_candidates(related_rows: list[dict[str, Any]], section_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    related_by_id = {r["id"]: r for r in related_rows if r.get("id")}
    out = []
    for row in section_rows:
        sid = row["id"]
        related = related_by_id.get(sid)
        if not related:
            continue
        candidate = dict(row)
        candidate["source"] = "rule_expansion"
        candidate["relationship"] = related.get("relationship")
        candidate["condition"] = related.get("condition")
        candidate["confidence"] = related.get("confidence")
        out.append(candidate)
    return out


def _format_candidate_context(c: dict[str, Any]) -> str:
    lines = [f"[{c.get('act', '')} {c.get('section', '')}] {c.get('title', '')}".strip()]
    if c.get("description"):
        lines.append(f"Description: {c['description']}")
    if c.get("punishment"):
        lines.append(f"Punishment: {c['punishment']}")
    if c.get("bailable"):
        lines.append(f"Bailable: {c['bailable']}")
    if c.get("cognizable"):
        lines.append(f"Cognizable: {c['cognizable']}")
    if c.get("mapping_status"):
        lines.append(f"Mapping status: {c['mapping_status']}")
    if c.get("counterpart_act") and c.get("counterpart_section"):
        lines.append(
            f"Mapped counterpart: {c['counterpart_act']} {c['counterpart_section']} - {c.get('counterpart_title', '')}"
        )
    if c.get("counterpart_mapping_status"):
        lines.append(f"Mapping edge status: {c['counterpart_mapping_status']}")
    if c.get("relationship"):
        cond = c.get("condition") or "no explicit condition recorded"
        lines.append(f"Rule relation: {c['relationship']} ({cond})")
    if "final_score" in c:
        lines.append(f"Final score: {c.get('final_score', 0.0):.4f}")
    return "\n".join(lines)


def answer_with_llm(question: str, primary_candidates: list[dict[str, Any]], related_candidates: list[dict[str, Any]]) -> str:
    if not primary_candidates:
        return "No matching section passed the retrieval threshold."

    primary_context = "\n\n".join(_format_candidate_context(c) for c in primary_candidates)
    related_context = "\n\n".join(_format_candidate_context(c) for c in related_candidates)

    prompt = (
        "You are a legal graph assistant for Indian criminal law.\n"
        "Answer ONLY from retrieved graph context.\n"
        "- Prioritize higher-ranked direct matches.\n"
        "- Mention IPC/BNS section numbers and titles explicitly.\n"
        "- If uncertain, say uncertain.\n"
        "- Use rule-expansion as supporting context only; do not override top direct hits unless rule relation clearly indicates precedence.\n"
        "- If a section has mapping_status deleted_no_bns_successor or new_no_ipc_predecessor, mention that implication briefly.\n\n"
        f"Question:\n{question}\n\n"
        f"Top direct matches:\n{primary_context}\n\n"
        f"Related legal-rule sections:\n{related_context or 'None'}\n"
    )
    response = get_llm(temperature=0.1).invoke(prompt)
    return response.content.strip()


def _run_single_query(question: str, chain: GraphCypherQAChain, driver) -> dict[str, Any]:
    try:
        chain_result = chain.invoke({"query": question})
    except Exception as exc:
        return {"error": f"GraphCypherQAChain failed: {exc}", "question": question}

    cypher, rows = _extract_intermediate(chain_result)

    if cypher and not is_read_only(cypher):
        return {
            "error": (
                "Generated query was not read-only.\n\n"
                f"Generated query:\n{cypher}"
            ),
            "question": question,
            "cypher": cypher,
        }

    _debug_print_rows("BEFORE RERANK", rows)

    if not rows:
        return {
            "error": (
                f"No sections matched above score threshold {FULLTEXT_SCORE_THRESHOLD}.\n\nGenerated query:\n{cypher}"
                if cypher
                else "No sections matched."
            ),
            "question": question,
            "cypher": cypher,
        }

    with driver.session() as session:
        direct_ids = [sid for row in rows for sid in _row_section_ids(row)]
        direct_section_rows = fetch_sections(session, direct_ids)

        candidates = _build_direct_candidates(rows, direct_section_rows)
        ranked, reranker_name = rerank_candidates(question, candidates)
        _debug_print_candidates("AFTER RERANK", ranked)
        top_candidates = ranked[:FINAL_TOP_K]

        related_rows = expand_with_rules(session, [c["id"] for c in top_candidates if c.get("id")])
        _debug_print_rows("AFTER RULE EXPANSION", related_rows)

        related_section_rows = fetch_sections(session, [r["id"] for r in related_rows if r.get("id")])

    related_candidates = _build_related_candidates(related_rows, related_section_rows)
    answer = answer_with_llm(question, top_candidates, related_candidates)

    return {
        "question": question,
        "cypher": cypher,
        "answer": answer,
        "reranker_name": reranker_name,
        "top_candidates": top_candidates,
        "related_candidates": related_candidates,
        "rows": rows,
    }


def _format_single_result(result: dict[str, Any]) -> str:
    if result.get("error"):
        return str(result["error"])

    lines = []
    if result.get("answer"):
        lines.extend(["Answer:", f"  {result['answer']}", ""])
    if result.get("cypher"):
        lines.extend([f"Cypher used:\n  {result['cypher']}", ""])
    lines.extend(
        [
            f"Retrieval pipeline: full-text > {FULLTEXT_SCORE_THRESHOLD} -> {result['reranker_name']} -> top {FINAL_TOP_K} -> rule expansion",
            "",
            "Top Matches:",
        ]
    )
    for c in result["top_candidates"]:
        lines.append(_format_row(c))
        lines.append(
            "      Source: "
            f"{c.get('source', 'unknown')} | "
            f"Raw: {c.get('raw_score', 0.0):.4f} | "
            f"Rerank: {c.get('rerank_score', 0.0):.4f} | "
            f"Final: {c.get('final_score', 0.0):.4f}"
        )

    if result["related_candidates"]:
        lines.extend(["", "Related Legal-Rule Sections:"])
        for c in result["related_candidates"]:
            lines.append(_format_row(c))
            cond = c.get("condition") or "no explicit condition recorded"
            lines.append(f"      Rule relation: {c['relationship']} ({cond})")

    return "\n".join(lines)


def _merge_multi_crime_results(question: str, acts: list[dict[str, str]], results: list[dict[str, Any]]) -> str:
    merged_primary: dict[str, dict[str, Any]] = {}
    merged_related: dict[str, dict[str, Any]] = {}

    for act, result in zip(acts, results):
        for c in result.get("top_candidates", []):
            sid = c.get("id")
            if not sid:
                continue
            existing = merged_primary.get(sid)
            cc = dict(c)
            cc.setdefault("supporting_acts", []).append(act["label"])
            if existing is None or cc.get("final_score", 0.0) > existing.get("final_score", 0.0):
                if existing and existing.get("supporting_acts"):
                    cc["supporting_acts"] = sorted(set(existing["supporting_acts"] + cc["supporting_acts"]))
                merged_primary[sid] = cc
            else:
                existing.setdefault("supporting_acts", []).append(act["label"])
                existing["supporting_acts"] = sorted(set(existing["supporting_acts"]))

        for c in result.get("related_candidates", []):
            sid = c.get("id")
            if not sid or sid in merged_primary:
                continue
            existing = merged_related.get(sid)
            cc = dict(c)
            cc.setdefault("supporting_acts", []).append(act["label"])
            if existing is None:
                merged_related[sid] = cc
            else:
                existing.setdefault("supporting_acts", []).append(act["label"])
                existing["supporting_acts"] = sorted(set(existing["supporting_acts"]))

    merged_top = sorted(
        merged_primary.values(),
        key=lambda c: (c.get("final_score", 0.0), c.get("raw_score", 0.0)),
        reverse=True,
    )[: max(FINAL_TOP_K, len(results))]
    merged_related_list = list(merged_related.values())

    merged_answer = answer_with_llm(question, merged_top, merged_related_list)

    lines = ["Overall Answer:", f"  {merged_answer}", "", "Crime Decomposition:"]
    for idx, act in enumerate(acts, start=1):
        lines.append(f"{idx}. {act['label']}: {act['query_text']}")

    lines.extend(["", "Per-Crime Retrieval:"])
    for idx, (act, result) in enumerate(zip(acts, results), start=1):
        lines.extend(["", f"[Crime {idx}] {act['label']}", f"Query: {act['query_text']}"])
        if result.get("error"):
            lines.append(result["error"])
            continue
        if result.get("cypher"):
            lines.append(f"Cypher used:\n  {result['cypher']}")
        lines.append(f"Answer:\n  {result['answer']}")
        lines.append("Top Matches:")
        for c in result.get("top_candidates", []):
            lines.append(_format_row(c))
            lines.append(
                "      Source: "
                f"{c.get('source', 'unknown')} | "
                f"Raw: {c.get('raw_score', 0.0):.4f} | "
                f"Rerank: {c.get('rerank_score', 0.0):.4f} | "
                f"Final: {c.get('final_score', 0.0):.4f}"
            )

    lines.extend(["", "Merged Matches:"])
    for c in merged_top:
        lines.append(_format_row(c))
        lines.append(
            f"      Supporting acts: {', '.join(c.get('supporting_acts', [])) or 'n/a'} | "
            f"Final: {c.get('final_score', 0.0):.4f}"
        )

    if merged_related_list:
        lines.extend(["", "Merged Related Legal-Rule Sections:"])
        for c in merged_related_list:
            lines.append(_format_row(c))
            lines.append(f"      Supporting acts: {', '.join(c.get('supporting_acts', [])) or 'n/a'}")
            cond = c.get("condition") or "no explicit condition recorded"
            lines.append(f"      Rule relation: {c['relationship']} ({cond})")

    return "\n".join(lines)


def run(question: str, chain: GraphCypherQAChain, driver) -> str:
    if not _looks_multi_crime(question):
        return _format_single_result(_run_single_query(question, chain, driver))

    acts = _decompose_incident(question)
    if len(acts) <= 1:
        return _format_single_result(_run_single_query(question, chain, driver))

    results = [_run_single_query(act["query_text"], chain, driver) for act in acts]
    successful = [r for r in results if not r.get("error")]
    if not successful:
        return _format_single_result(_run_single_query(question, chain, driver))

    return _merge_multi_crime_results(question, acts, results)


def main() -> None:
    if not (NEO4J_URI and NEO4J_USER and NEO4J_PASSWORD):
        raise SystemExit("Set NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD (env or .env)")

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        verify_runtime_schema(driver)
        chain = build_chain()

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