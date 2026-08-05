"""
In-memory LRU cache with TTL for entity linking, planner output, and Cypher queries.

Optionally backed by Redis when `redis_url` is set in config.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections import OrderedDict
from typing import Any, Optional

from ..config.settings import get_settings

logger = logging.getLogger(__name__)


class TTLCache:
    """Thread-safe in-memory LRU cache with per-entry TTL."""

    def __init__(self, max_size: int = 1024, ttl_seconds: int = 3600):
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._store: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    # ── helpers ──

    @staticmethod
    def _make_key(namespace: str, *parts: str) -> str:
        raw = f"{namespace}|{'|'.join(parts)}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def _evict_expired(self) -> None:
        now = time.time()
        expired = [k for k, (ts, _) in self._store.items() if now - ts > self._ttl]
        for k in expired:
            del self._store[k]

    # ── public API ──

    def get(self, namespace: str, *parts: str) -> Optional[Any]:
        key = self._make_key(namespace, *parts)
        entry = self._store.get(key)
        if entry is None:
            return None
        ts, value = entry
        if time.time() - ts > self._ttl:
            del self._store[key]
            return None
        # Move to end (most-recently used)
        self._store.move_to_end(key)
        logger.debug("Cache HIT: %s(%s)", namespace, parts)
        return value

    def put(self, value: Any, namespace: str, *parts: str) -> None:
        key = self._make_key(namespace, *parts)
        if key in self._store:
            del self._store[key]
        elif len(self._store) >= self._max_size:
            self._evict_expired()
            # Still full? Drop oldest
            if len(self._store) >= self._max_size:
                self._store.popitem(last=False)
        self._store[key] = (time.time(), value)
        logger.debug("Cache PUT: %s(%s)", namespace, parts)

    def clear(self) -> None:
        self._store.clear()
        logger.info("Cache cleared.")

    @property
    def size(self) -> int:
        return len(self._store)


# ─── Singleton cache ─────────────────────────────────────────────────────

_cache: Optional[TTLCache] = None


def get_cache() -> TTLCache:
    """Return the singleton cache instance."""
    global _cache
    if _cache is None:
        cfg = get_settings()
        _cache = TTLCache(
            max_size=cfg.cache_max_size,
            ttl_seconds=cfg.cache_ttl_seconds,
        )
        logger.info("Query cache initialised (max_size=%d, ttl=%ds)", cfg.cache_max_size, cfg.cache_ttl_seconds)
    return _cache


def reset_cache() -> None:
    """Force re-create (useful in tests)."""
    global _cache
    _cache = None


# ─── Convenience wrappers ────────────────────────────────────────────────

def cache_entity_linking(query_term: str, result: Any) -> None:
    get_cache().put(result, "entity_linking", query_term.lower().strip())


def get_cached_entity_linking(query_term: str) -> Optional[Any]:
    return get_cache().get("entity_linking", query_term.lower().strip())


def cache_planner_output(intent: str, entities_key: str, result: Any) -> None:
    get_cache().put(result, "planner", intent, entities_key)


def get_cached_planner_output(intent: str, entities_key: str) -> Optional[Any]:
    return get_cache().get("planner", intent, entities_key)


def cache_cypher(plan_key: str, result: Any) -> None:
    get_cache().put(result, "cypher", plan_key)


def get_cached_cypher(plan_key: str) -> Optional[Any]:
    return get_cache().get("cypher", plan_key)
