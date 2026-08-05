"""
Query Planner — Stage 5 of the Text-to-Cypher pipeline.

Receives intent, entities, and expanded graph context.
Returns a JSON QueryPlan that the deterministic CypherBuilder reads.

Never generates Cypher.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage

from ..config.settings import get_settings
from ..schemas.models import (
    ExpandedContext,
    ExtractedEntities,
    IntentResult,
    LegalIntent,
    LinkedEntities,
    QueryPlan,
)
from .prompts import get_planner_system_prompt, PLANNER_USER_TEMPLATE
from ..utils.query_cache import cache_planner_output, get_cached_planner_output

logger = logging.getLogger(__name__)


def _get_llm() -> ChatGroq:
    cfg = get_settings()
    return ChatGroq(
        model=cfg.groq_model,
        api_key=cfg.groq_api_key,
        temperature=0.0,
        max_retries=cfg.groq_max_retries,
    )


# ─── Deterministic planner (no LLM needed for common intents) ────────────

def _deterministic_plan(
    intent: LegalIntent,
    entities: ExtractedEntities,
    linked: LinkedEntities,
    expanded: ExpandedContext,
) -> Optional[QueryPlan]:
    """
    For common, well-structured intents, generate the plan deterministically
    without any LLM call.  Returns None if the intent requires LLM reasoning.
    """
    node_ids = [n.node_id for n in linked.section_nodes]
    entity_names = entities.crimes + entities.ipc_sections + entities.bns_sections

    base = dict(
        intent=intent,
        entities=entity_names,
        linked_node_ids=node_ids,
        need_punishment=False,
        need_replacement=False,
        need_keywords=False,
        need_description=False,
        need_chapter=False,
        need_related=False,
        need_hierarchy=False,
        target_act=None,
        multi_crime=len(entities.crimes) > 1,
        comparison_pairs=[],
    )

    if intent == LegalIntent.PUNISHMENT:
        return QueryPlan(**{**base, "need_punishment": True, "need_description": True})

    if intent == LegalIntent.IPC_TO_BNS:
        return QueryPlan(**{
            **base,
            "need_replacement": True,
            "need_punishment": True,
            "need_description": True,
            "target_act": "IPC",
        })

    if intent == LegalIntent.BNS_TO_IPC:
        return QueryPlan(**{
            **base,
            "need_replacement": True,
            "need_punishment": True,
            "need_description": True,
            "target_act": "BNS",
        })

    if intent == LegalIntent.SECTION_LOOKUP:
        return QueryPlan(**{
            **base,
            "need_punishment": True,
            "need_keywords": True,
            "need_description": True,
            "need_chapter": True,
        })

    if intent == LegalIntent.CRIME_LOOKUP:
        return QueryPlan(**{
            **base,
            "need_punishment": True,
            "need_replacement": True,
            "need_description": True,
        })

    if intent == LegalIntent.KEYWORD_LOOKUP:
        return QueryPlan(**{**base, "need_keywords": True, "need_description": True})

    if intent == LegalIntent.RELATED_OFFENCES:
        return QueryPlan(**{
            **base,
            "need_related": True,
            "need_description": True,
            "need_punishment": True,
        })

    if intent == LegalIntent.HIERARCHY:
        return QueryPlan(**{
            **base,
            "need_hierarchy": True,
            "need_description": True,
        })

    if intent == LegalIntent.PUNISHMENT_COMPARISON:
        # Build comparison pairs from linked sections
        pairs = []
        if len(node_ids) >= 2:
            for i in range(len(node_ids)):
                for j in range(i + 1, len(node_ids)):
                    pairs.append([node_ids[i], node_ids[j]])
        return QueryPlan(**{
            **base,
            "need_punishment": True,
            "need_description": True,
            "comparison_pairs": pairs,
        })

    if intent == LegalIntent.COMPARISON:
        pairs = []
        if len(node_ids) >= 2:
            for i in range(len(node_ids)):
                for j in range(i + 1, len(node_ids)):
                    pairs.append([node_ids[i], node_ids[j]])
        return QueryPlan(**{
            **base,
            "need_punishment": True,
            "need_description": True,
            "need_keywords": True,
            "comparison_pairs": pairs,
        })

    if intent == LegalIntent.MULTIPLE_CRIMES:
        return QueryPlan(**{
            **base,
            "need_punishment": True,
            "need_replacement": True,
            "need_description": True,
            "need_related": True,
            "multi_crime": True,
        })

    if intent == LegalIntent.LEGAL_EXPLANATION:
        return QueryPlan(**{
            **base,
            "need_description": True,
            "need_keywords": True,
            "need_punishment": True,
            "need_replacement": True,
        })

    # If we get here, fall through to LLM planner
    return None


# ─── LLM-assisted planner (fallback) ─────────────────────────────────────

def _parse_plan_json(raw: str, intent: LegalIntent) -> QueryPlan:
    """Parse LLM planner response into a QueryPlan."""
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`")

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("Failed to parse planner JSON: %s", raw[:300])
        return QueryPlan(intent=intent)

    # Coerce intent
    intent_str = data.get("intent", intent.value)
    try:
        parsed_intent = LegalIntent(intent_str)
    except ValueError:
        parsed_intent = intent

    return QueryPlan(
        intent=parsed_intent,
        entities=data.get("entities", []),
        linked_node_ids=data.get("linked_node_ids", []),
        need_punishment=bool(data.get("need_punishment", False)),
        need_replacement=bool(data.get("need_replacement", False)),
        need_keywords=bool(data.get("need_keywords", False)),
        need_description=bool(data.get("need_description", False)),
        need_chapter=bool(data.get("need_chapter", False)),
        need_related=bool(data.get("need_related", False)),
        need_hierarchy=bool(data.get("need_hierarchy", False)),
        target_act=data.get("target_act"),
        multi_crime=bool(data.get("multi_crime", False)),
        comparison_pairs=data.get("comparison_pairs", []),
    )


def _llm_plan(
    query: str,
    intent: IntentResult,
    entities: ExtractedEntities,
    linked: LinkedEntities,
    expanded: ExpandedContext,
) -> QueryPlan:
    """Use LLM to generate a query plan for complex / ambiguous intents."""
    llm = _get_llm()

    linked_summary = [
        {"id": n.node_id, "label": n.label, "name": n.name}
        for n in linked.section_nodes + linked.crime_nodes
    ]
    expanded_summary = [
        {"source": r.source_id, "target": r.target_id, "rel": r.relationship}
        for r in expanded.relations[:20]  # limit to avoid token overflow
    ]

    messages = [
        SystemMessage(content=get_planner_system_prompt()),
        HumanMessage(content=PLANNER_USER_TEMPLATE.format(
            query=query,
            intent=intent.intent.value,
            entities=json.dumps(entities.model_dump(), default=str),
            linked_nodes=json.dumps(linked_summary, default=str),
            expanded_context=json.dumps(expanded_summary, default=str),
        )),
    ]

    try:
        response = llm.invoke(messages)
        raw = response.content.strip()
        logger.debug("Planner LLM raw: %s", raw[:500])
        return _parse_plan_json(raw, intent.intent)
    except Exception as exc:
        logger.error("LLM planner failed: %s", exc)
        return QueryPlan(intent=intent.intent)


# ─── Public API ──────────────────────────────────────────────────────────

def create_query_plan(
    query: str,
    intent: IntentResult,
    entities: ExtractedEntities,
    linked: LinkedEntities,
    expanded: ExpandedContext,
) -> QueryPlan:
    """
    Create a query plan from classified intent, extracted entities,
    linked graph nodes, and expanded context.

    Tries deterministic planning first; falls back to LLM for
    ambiguous or complex intents.

    Parameters
    ----------
    query : str
        Original user question.
    intent : IntentResult
        Classified intent.
    entities : ExtractedEntities
        Extracted entities.
    linked : LinkedEntities
        Graph-linked entities.
    expanded : ExpandedContext
        Expanded graph context.

    Returns
    -------
    QueryPlan
        JSON query specification for the CypherBuilder.
    """
    logger.info("Creating query plan for intent=%s", intent.intent.value)

    # Check cache
    entities_key = json.dumps(sorted(entities.crimes + entities.ipc_sections + entities.bns_sections))
    cached = get_cached_planner_output(intent.intent.value, entities_key)
    if cached is not None:
        logger.info("Using cached query plan")
        return cached

    # Try deterministic plan first
    plan = _deterministic_plan(intent.intent, entities, linked, expanded)
    if plan is not None:
        logger.info("Deterministic plan generated for intent=%s", intent.intent.value)
    else:
        logger.info("Falling back to LLM planner for intent=%s", intent.intent.value)
        plan = _llm_plan(query, intent, entities, linked, expanded)

    # Cache the result
    cache_planner_output(intent.intent.value, entities_key, plan)

    logger.info("Query plan: %s", plan.model_dump_json(indent=2)[:500])
    return plan
