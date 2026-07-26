"""
Answer Generator — Stage 8 of the Text-to-Cypher pipeline.

Uses LLM only AFTER retrieval to generate natural language answers
from the structured Neo4j results.  Never hallucinate.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage

from ..config.settings import get_settings
from ..schemas.models import ExecutionResult, LegalIntent
from .prompts import ANSWER_SYSTEM_PROMPT, ANSWER_USER_TEMPLATE

logger = logging.getLogger(__name__)


def _get_llm() -> ChatGroq:
    cfg = get_settings()
    return ChatGroq(
        model=cfg.groq_model,
        api_key=cfg.groq_api_key,
        temperature=0.1,  # Slightly higher for natural prose
        max_retries=cfg.groq_max_retries,
    )


def _format_records(results: List[ExecutionResult]) -> str:
    """Format execution results into a readable string for the LLM."""
    if not results:
        return "No data was retrieved from the graph."

    sections: List[str] = []
    for i, result in enumerate(results):
        if not result.success:
            sections.append(f"Query {i+1}: FAILED — {result.error}")
            continue

        if not result.records:
            sections.append(f"Query {i+1} ({result.cypher[:80]}...): No results found.")
            continue

        lines: List[str] = [f"Query {i+1} ({len(result.records)} records):"]
        for j, record in enumerate(result.records[:25]):  # Limit to prevent token overflow
            filtered = {
                k: v for k, v in record.items()
                if v is not None and v != "" and v != []
            }
            lines.append(f"  Record {j+1}: {json.dumps(filtered, default=str, ensure_ascii=False)}")

        if len(result.records) > 25:
            lines.append(f"  ... and {len(result.records) - 25} more records")

        sections.append("\n".join(lines))

    return "\n\n".join(sections)


def generate_answer(
    query: str,
    intent: LegalIntent,
    results: List[ExecutionResult],
) -> str:
    """
    Generate a natural language answer from Neo4j query results.

    Uses the LLM only after retrieval — never hallucinate.

    Parameters
    ----------
    query : str
        The original user question.
    intent : LegalIntent
        The classified intent.
    results : List[ExecutionResult]
        Execution results from Neo4j.

    Returns
    -------
    str
        Natural language answer.
    """
    logger.info("Generating answer for intent=%s", intent.value)

    # Check if we have any data
    all_records = []
    for r in results:
        if r.success:
            all_records.extend(r.records)

    if not all_records:
        return (
            "I could not find relevant information in the legal graph to answer "
            "your question. The graph may not contain data about the specific "
            "section, crime, or legal concept you asked about."
        )

    formatted = _format_records(results)
    llm = _get_llm()

    messages = [
        SystemMessage(content=ANSWER_SYSTEM_PROMPT),
        HumanMessage(content=ANSWER_USER_TEMPLATE.format(
            query=query,
            intent=intent.value,
            retrieved_data=formatted,
        )),
    ]

    try:
        response = llm.invoke(messages)
        answer = response.content.strip()
        logger.info("Answer generated (%d chars)", len(answer))
        return answer
    except Exception as exc:
        logger.error("Answer generation failed: %s", exc)
        # Fallback: return raw data summary
        return _fallback_answer(query, intent, all_records)


def _fallback_answer(
    query: str,
    intent: LegalIntent,
    records: List[Dict[str, Any]],
) -> str:
    """Generate a basic fallback answer from raw records when LLM fails."""
    lines = [f"**Query:** {query}", f"**Intent:** {intent.value}", "", "**Retrieved Data:**"]

    for i, record in enumerate(records[:10]):
        filtered = {k: v for k, v in record.items() if v is not None and v != ""}
        if "title" in filtered:
            lines.append(f"\n**{filtered.get('act', '')} Section {filtered.get('section', '')}:** {filtered.get('title', '')}")
        if "description" in filtered:
            lines.append(f"*Description:* {filtered.get('description', '')[:200]}")
        if "punishment_text" in filtered:
            lines.append(f"*Punishment:* {filtered.get('punishment_text', '')}")
        if "crime_name" in filtered:
            lines.append(f"*Crime:* {filtered.get('crime_name', '')}")

    return "\n".join(lines)
