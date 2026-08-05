"""
Pipeline Orchestrator — ties all stages together.

User Query → Intent → Entity Extraction → Entity Linking →
Graph Expansion → Planner → Cypher Builder → Validator →
Executor → Answer Generator → Final Answer
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from ..config.settings import get_settings
from ..schemas.models import (
    FinalAnswer,
    LegalIntent,
    PipelineState,
)
from .intent_classifier import classify_intent
from .entity_extractor import extract_entities
from .entity_linker import link_entities
from .graph_expander import expand_graph
from .planner import create_query_plan
from .cypher_builder import build_cypher
from .cypher_validator import validate_all, CypherValidationError
from .executor import execute_all
from .answer_generator import generate_answer
from ..utils.neo4j_utils import close_driver

logger = logging.getLogger(__name__)


def _time_stage(name: str, state: PipelineState):
    """Context-manager-style timing helper."""
    class _Timer:
        def __init__(self):
            self.start = 0.0
        def __enter__(self):
            self.start = time.perf_counter()
            logger.info("▶ Stage: %s", name)
            return self
        def __exit__(self, *args):
            elapsed = (time.perf_counter() - self.start) * 1000
            state.stages_log[name] = round(elapsed, 2)
            logger.info("◀ Stage: %s completed in %.1fms", name, elapsed)
    return _Timer()


def run_pipeline(query: str) -> FinalAnswer:
    """
    Execute the full Text-to-Cypher pipeline.

    Parameters
    ----------
    query : str
        The user's natural-language legal question.

    Returns
    -------
    FinalAnswer
        Complete response with answer, execution data, and timing info.
    """
    t_total = time.perf_counter()
    state = PipelineState(query=query)

    logger.info("=" * 60)
    logger.info("PIPELINE START: %s", query[:100])
    logger.info("=" * 60)

    # ── Stage 1: Intent Classification ────────────────────────────────
    with _time_stage("intent_classification", state):
        try:
            state.intent_result = classify_intent(query)
        except Exception as exc:
            logger.error("Intent classification failed: %s", exc)
            state.errors.append(f"Intent classification: {exc}")
            state.intent_result = None

    if state.intent_result is None:
        from ..schemas.models import IntentResult
        state.intent_result = IntentResult(
            intent=LegalIntent.UNKNOWN,
            confidence=0.0,
            reasoning="Classification failed",
        )

    # ── Stage 2: Entity Extraction ────────────────────────────────────
    with _time_stage("entity_extraction", state):
        try:
            state.extracted_entities = extract_entities(query)
        except Exception as exc:
            logger.error("Entity extraction failed: %s", exc)
            state.errors.append(f"Entity extraction: {exc}")
            from ..schemas.models import ExtractedEntities
            state.extracted_entities = ExtractedEntities()

    # ── Stage 3: Entity Linking ───────────────────────────────────────
    with _time_stage("entity_linking", state):
        try:
            state.linked_entities = link_entities(state.extracted_entities)
        except Exception as exc:
            logger.error("Entity linking failed: %s", exc)
            state.errors.append(f"Entity linking: {exc}")
            from ..schemas.models import LinkedEntities
            state.linked_entities = LinkedEntities()

    # ── Stage 4: Graph Expansion ──────────────────────────────────────
    with _time_stage("graph_expansion", state):
        try:
            cfg = get_settings()
            state.expanded_context = expand_graph(
                state.linked_entities,
                max_depth=cfg.graph_expansion_depth,
            )
        except Exception as exc:
            logger.error("Graph expansion failed: %s", exc)
            state.errors.append(f"Graph expansion: {exc}")
            from ..schemas.models import ExpandedContext
            state.expanded_context = ExpandedContext(linked=state.linked_entities)

    # ── Stage 5: Query Planning ───────────────────────────────────────
    with _time_stage("query_planning", state):
        try:
            state.query_plan = create_query_plan(
                query,
                state.intent_result,
                state.extracted_entities,
                state.linked_entities,
                state.expanded_context,
            )
        except Exception as exc:
            logger.error("Query planning failed: %s", exc)
            state.errors.append(f"Query planning: {exc}")
            from ..schemas.models import QueryPlan
            state.query_plan = QueryPlan(intent=state.intent_result.intent)

    # ── Stage 6: Cypher Building ──────────────────────────────────────
    with _time_stage("cypher_building", state):
        try:
            state.cypher_queries = build_cypher(state.query_plan)
        except Exception as exc:
            logger.error("Cypher building failed: %s", exc)
            state.errors.append(f"Cypher building: {exc}")

    # ── Stage 6b: Cypher Validation ───────────────────────────────────
    with _time_stage("cypher_validation", state):
        try:
            state.cypher_queries = validate_all(state.cypher_queries)
        except Exception as exc:
            logger.error("Cypher validation failed: %s", exc)
            state.errors.append(f"Cypher validation: {exc}")

    # ── Stage 7: Execution ────────────────────────────────────────────
    with _time_stage("execution", state):
        if state.cypher_queries:
            try:
                state.execution_results = execute_all(state.cypher_queries)
            except Exception as exc:
                logger.error("Execution failed: %s", exc)
                state.errors.append(f"Execution: {exc}")
        else:
            logger.warning("No valid Cypher queries to execute")
            state.errors.append("No valid Cypher queries generated")

    # ── Stage 8: Answer Generation ────────────────────────────────────
    with _time_stage("answer_generation", state):
        try:
            state.answer = generate_answer(
                query,
                state.intent_result.intent,
                state.execution_results,
            )
        except Exception as exc:
            logger.error("Answer generation failed: %s", exc)
            state.errors.append(f"Answer generation: {exc}")
            state.answer = "An error occurred while generating the answer."

    # ── Build Final Answer ────────────────────────────────────────────
    total_time = (time.perf_counter() - t_total) * 1000

    final = FinalAnswer(
        query=query,
        intent=state.intent_result.intent,
        extracted_entities=state.extracted_entities,
        linked_entities=state.linked_entities,
        query_plan=state.query_plan,
        cypher_queries=state.cypher_queries,
        execution_results=state.execution_results,
        answer=state.answer,
        total_time_ms=round(total_time, 2),
        stages_log=state.stages_log,
    )

    logger.info("=" * 60)
    logger.info("PIPELINE COMPLETE in %.1fms", total_time)
    logger.info("  Intent: %s", final.intent.value)
    logger.info("  Queries executed: %d", len(final.execution_results))
    logger.info("  Total records: %d", sum(len(r.records) for r in final.execution_results))
    logger.info("  Errors: %s", state.errors if state.errors else "None")
    logger.info("=" * 60)

    return final


def shutdown() -> None:
    """Gracefully shut down the pipeline (close connections)."""
    close_driver()
    logger.info("Pipeline shut down.")
