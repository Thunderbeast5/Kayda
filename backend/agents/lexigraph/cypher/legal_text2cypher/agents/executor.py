"""
Cypher Executor — Stage 7 of the Text-to-Cypher pipeline.

Executes validated Cypher queries against Neo4j with retry logic
and structured result parsing.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from ..config.settings import get_settings
from ..schemas.models import CypherQuery, ExecutionResult
from ..utils.neo4j_utils import run_cypher

logger = logging.getLogger(__name__)


def execute_query(query: CypherQuery) -> ExecutionResult:
    """
    Execute a single CypherQuery against Neo4j.

    Parameters
    ----------
    query : CypherQuery
        A validated, parameterised Cypher query.

    Returns
    -------
    ExecutionResult
        Structured result with records, timing, and error info.
    """
    logger.info("Executing: %s", query.description or query.cypher[:100])

    t0 = time.perf_counter()
    retries = 0

    try:
        records = run_cypher(query.cypher, query.parameters)
        elapsed = (time.perf_counter() - t0) * 1000

        result = ExecutionResult(
            success=True,
            records=records,
            cypher=query.cypher,
            parameters=query.parameters,
            execution_time_ms=round(elapsed, 2),
            retries=retries,
        )

        logger.info(
            "Execution OK: %d records in %.1fms (%s)",
            len(records), elapsed, query.description,
        )
        return result

    except Exception as exc:
        elapsed = (time.perf_counter() - t0) * 1000
        logger.error("Execution FAILED: %s — %s", query.description, exc)

        return ExecutionResult(
            success=False,
            records=[],
            cypher=query.cypher,
            parameters=query.parameters,
            execution_time_ms=round(elapsed, 2),
            error=str(exc),
        )


def execute_all(queries: List[CypherQuery]) -> List[ExecutionResult]:
    """
    Execute multiple CypherQuery objects sequentially.

    Parameters
    ----------
    queries : List[CypherQuery]
        Validated queries to execute.

    Returns
    -------
    List[ExecutionResult]
        Results for each query (order preserved).
    """
    logger.info("Executing %d queries...", len(queries))
    results: List[ExecutionResult] = []

    for i, q in enumerate(queries):
        logger.info("Query %d/%d: %s", i + 1, len(queries), q.description)
        result = execute_query(q)
        results.append(result)

        if not result.success:
            logger.warning(
                "Query %d failed: %s (continuing with remaining queries)",
                i + 1, result.error,
            )

    successful = sum(1 for r in results if r.success)
    total_records = sum(len(r.records) for r in results)
    total_time = sum(r.execution_time_ms for r in results)

    logger.info(
        "Execution complete: %d/%d succeeded, %d total records, %.1fms total",
        successful, len(results), total_records, total_time,
    )
    return results
