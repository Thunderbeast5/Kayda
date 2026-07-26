"""
Thread-safe Neo4j driver management with retry logic and full-text search helpers.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Any, Dict, Generator, List, Optional

from neo4j import GraphDatabase, Driver, Session
from neo4j.exceptions import (
    ServiceUnavailable,
    SessionExpired,
    TransientError,
)

from ..config.settings import get_settings

logger = logging.getLogger(__name__)

# ─── Singleton driver ─────────────────────────────────────────────────────

_driver: Optional[Driver] = None


def get_driver() -> Driver:
    """Return a singleton Neo4j driver, creating one if needed."""
    global _driver
    if _driver is None:
        cfg = get_settings()
        logger.info("Creating Neo4j driver → %s", cfg.neo4j_uri)
        _driver = GraphDatabase.driver(
            cfg.neo4j_uri,
            auth=(cfg.neo4j_user, cfg.neo4j_password),
        )
    return _driver


def close_driver() -> None:
    """Explicitly close the driver (call on shutdown)."""
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None
        logger.info("Neo4j driver closed.")


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Yield a Neo4j session scoped to the configured database."""
    cfg = get_settings()
    driver = get_driver()
    session = driver.session(database=cfg.neo4j_database)
    try:
        yield session
    finally:
        session.close()


# ─── Query execution with retry ──────────────────────────────────────────

_TRANSIENT = (ServiceUnavailable, SessionExpired, TransientError)


def run_cypher(
    cypher: str,
    parameters: Optional[Dict[str, Any]] = None,
    max_retries: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Execute a Cypher query with exponential-backoff retry on transient errors.

    Returns a list of record dicts.
    """
    cfg = get_settings()
    retries = max_retries if max_retries is not None else cfg.max_cypher_retries
    params = parameters or {}
    last_exc: Optional[Exception] = None

    for attempt in range(1, retries + 1):
        try:
            t0 = time.perf_counter()
            with get_session() as session:
                result = session.run(cypher, params)
                records = [dict(r) for r in result]
            elapsed = (time.perf_counter() - t0) * 1000
            logger.info(
                "Cypher OK (attempt %d, %.1fms, %d rows): %s",
                attempt, elapsed, len(records), cypher[:120],
            )
            return records
        except _TRANSIENT as exc:
            last_exc = exc
            wait = min(2 ** attempt, 16)
            logger.warning(
                "Transient Neo4j error (attempt %d/%d), retrying in %ds: %s",
                attempt, retries, wait, exc,
            )
            time.sleep(wait)
        except Exception as exc:
            logger.error("Non-transient Neo4j error: %s", exc)
            raise

    raise RuntimeError(
        f"Neo4j query failed after {retries} retries: {last_exc}"
    ) from last_exc


# ─── Full-text search helpers ────────────────────────────────────────────

def fulltext_search_crimes(
    search_term: str,
    limit: Optional[int] = None,
    min_score: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """
    Search the `crimeName` full-text index.

    Returns list of dicts with keys: node_id, name, score, label.
    """
    cfg = get_settings()
    lim = limit or cfg.fulltext_max_results
    threshold = min_score if min_score is not None else cfg.fulltext_score_threshold

    cypher = """
    CALL db.index.fulltext.queryNodes('crimeName', $term)
    YIELD node, score
    WHERE score >= $threshold
    RETURN node.id   AS node_id,
           node.name AS name,
           score,
           'Crime'   AS label
    ORDER BY score DESC
    LIMIT $limit
    """
    return run_cypher(cypher, {"term": search_term, "threshold": threshold, "limit": lim})


def fulltext_search_sections(
    search_term: str,
    limit: Optional[int] = None,
    min_score: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """
    Search the `lawSectionText` full-text index.

    Returns list of dicts with keys: node_id, section, act, title, score, label.
    """
    cfg = get_settings()
    lim = limit or cfg.fulltext_max_results
    threshold = min_score if min_score is not None else cfg.fulltext_score_threshold

    cypher = """
    CALL db.index.fulltext.queryNodes('lawSectionText', $term)
    YIELD node, score
    WHERE score >= $threshold
    RETURN node.id          AS node_id,
           node.section     AS section,
           node.act         AS act,
           node.title       AS title,
           node.description AS description,
           node.punishment  AS punishment,
           score,
           'LawSection'     AS label
    ORDER BY score DESC
    LIMIT $limit
    """
    return run_cypher(cypher, {"term": search_term, "threshold": threshold, "limit": lim})


def find_section_by_id(section_id: str) -> Optional[Dict[str, Any]]:
    """Look up a LawSection by its id property (e.g. 'IPC_302')."""
    cypher = """
    MATCH (l:LawSection {id: $sid})
    RETURN l.id          AS node_id,
           l.section     AS section,
           l.act         AS act,
           l.title       AS title,
           l.description AS description,
           l.punishment  AS punishment,
           l.keywords    AS keywords,
           l.cognizable  AS cognizable,
           l.bailable    AS bailable,
           l.court       AS court,
           l.mapping_status AS mapping_status,
           'LawSection'  AS label
    """
    rows = run_cypher(cypher, {"sid": section_id})
    return rows[0] if rows else None


def find_section_by_number(act: str, section_number: str) -> Optional[Dict[str, Any]]:
    """Look up a LawSection by act code and section number."""
    sid = f"{act.upper()}_{section_number}"
    return find_section_by_id(sid)
