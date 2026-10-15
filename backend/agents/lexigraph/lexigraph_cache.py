"""
lexigraph_cache.py
──────────────────
Thin, synchronous cache layer for LexiGraphAgent.process_query() results.

Cache key  : lexigraph:v1:<sha256(query)[:32]>
Backend    : Redis (primary) → disk JSON (fallback) → none
Config     : all via environment variables (no code changes needed)

  LEXIGRAPH_CACHE_BACKEND  redis | disk | none   (default: redis)
  LEXIGRAPH_CACHE_TTL      seconds                (default: 259200 = 72 h)
  LEXIGRAPH_CACHE_DIR      path on disk           (default: data/lexigraph_cache)

The module never raises — every public function swallows exceptions and
returns None / False so the live pipeline is never blocked by cache errors.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import pathlib
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

_BACKEND: str = os.getenv("LEXIGRAPH_CACHE_BACKEND", "redis").lower().strip()
_TTL: int = int(os.getenv("LEXIGRAPH_CACHE_TTL", "259200"))  # 72 hours
_CACHE_DIR: pathlib.Path = pathlib.Path(
    os.getenv("LEXIGRAPH_CACHE_DIR", "data/lexigraph_cache")
)
_KEY_PREFIX = "lexigraph:v1:"
_HASH_LEN = 32  # first 32 hex chars of sha256 (128-bit collision safety)


_PROMPT_VERSION: str = os.getenv("PROMPT_VERSION", "v1.0")


def is_cache_enabled() -> bool:
    """Return True if caching is enabled via environment variables."""
    if os.getenv("OPT_LEXIGRAPH_CACHE", "true").lower() in ("false", "0", "no"):
        return False
    return _BACKEND != "none"


# ── Key generation ────────────────────────────────────────────────────────────

def make_key(query: str, model_name: Optional[str] = None, namespace: Optional[str] = None) -> str:
    """
    Return the full cache key for *query*, qualified by prompt version and model name.
    """
    ns = namespace or os.getenv("CACHE_NAMESPACE", "prod")
    model = model_name or os.getenv("OPENAI_MODEL", os.getenv("OLLAMA_MODEL", "default"))
    payload = f"{query}:{_PROMPT_VERSION}:{model}:{ns}"
    digest = hashlib.sha256(payload.encode("utf-8", errors="replace")).hexdigest()
    return f"{_KEY_PREFIX}{ns}:{digest[:_HASH_LEN]}"


def make_doc_key(document_text: str, model_name: Optional[str] = None, namespace: Optional[str] = None) -> str:
    """
    Return cache key strictly keyed on hashlib.sha256(document_text),
    qualified with prompt version, model tier, and namespace to prevent
    stale cache hits across model or prompt updates.
    """
    ns = namespace or os.getenv("CACHE_NAMESPACE", "prod")
    model = model_name or os.getenv("OPENAI_MODEL", os.getenv("OLLAMA_MODEL", "default"))
    payload = f"{document_text}:{_PROMPT_VERSION}:{model}:{ns}"
    digest = hashlib.sha256(payload.encode("utf-8", errors="replace")).hexdigest()
    return f"lexigraph:doc:{ns}:{digest}"


def make_stage0_key(document_text: str, model_name: Optional[str] = None, namespace: Optional[str] = None) -> str:
    """
    Return Stage 0 cache key qualified with prompt version, model, and namespace.
    """
    ns = namespace or os.getenv("CACHE_NAMESPACE", "prod")
    model = model_name or os.getenv("MODEL_STAGE0", "default")
    payload = f"{document_text}:{_PROMPT_VERSION}:{model}:{ns}"
    digest = hashlib.sha256(payload.encode("utf-8", errors="replace")).hexdigest()
    return f"stage0:doc:{ns}:{digest}"


# ── Redis backend ─────────────────────────────────────────────────────────────

def _redis_client():
    """
    Return a *synchronous* redis.Redis instance, or None if unavailable.

    We use the sync client intentionally: LexiGraphAgent.process_query() is
    called inside asyncio.to_thread() so blocking IO is fine here, and it
    avoids a second async client that would need its own event-loop context.
    """
    try:
        import redis  # type: ignore
        r = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        r.ping()
        return r
    except Exception as exc:
        logger.debug("[LexiGraphCache] Redis unavailable: %s", exc)
        return None


def _redis_get(key: str) -> Optional[Dict[str, Any]]:
    r = _redis_client()
    if r is None:
        return None
    try:
        raw = r.get(key)
        if raw:
            return json.loads(raw)
    except Exception as exc:
        logger.warning("[LexiGraphCache] Redis GET error: %s", exc)
    return None


def _redis_set(key: str, value: Dict[str, Any], ttl: int) -> bool:
    r = _redis_client()
    if r is None:
        return False
    try:
        r.setex(key, ttl, json.dumps(value, ensure_ascii=False))
        return True
    except Exception as exc:
        logger.warning("[LexiGraphCache] Redis SET error: %s", exc)
    return False


# ── Disk backend ──────────────────────────────────────────────────────────────

def _disk_path(key: str) -> pathlib.Path:
    # strip prefix so the filename is just the hex digest
    slug = key.replace(_KEY_PREFIX, "").replace(":", "_")
    return _CACHE_DIR / f"{slug}.json"


def _disk_get(key: str) -> Optional[Dict[str, Any]]:
    path = _disk_path(key)
    try:
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as fh:
            envelope = json.load(fh)
        # Honour TTL on disk too
        stored_at = envelope.get("_cached_at", 0)
        if _TTL > 0 and (time.time() - stored_at) > _TTL:
            path.unlink(missing_ok=True)
            return None
        return envelope.get("payload")
    except Exception as exc:
        logger.warning("[LexiGraphCache] Disk GET error: %s", exc)
    return None


def _disk_set(key: str, value: Dict[str, Any]) -> bool:
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        envelope = {"_cached_at": time.time(), "payload": value}
        path = _disk_path(key)
        with path.open("w", encoding="utf-8") as fh:
            json.dump(envelope, fh, ensure_ascii=False)
        return True
    except Exception as exc:
        logger.warning("[LexiGraphCache] Disk SET error: %s", exc)
    return False


# ── Public API ────────────────────────────────────────────────────────────────

def get(key: str) -> Optional[Dict[str, Any]]:
    """
    Look up *key* in the configured cache backend.

    Returns the stored dict on a hit, or ``None`` on a miss / disabled cache.
    Never raises.
    """
    if not is_cache_enabled():
        return None
    try:
        if _BACKEND == "redis":
            result = _redis_get(key)
            if result is not None:
                return result
            # Transparent fallback to disk when Redis is up but key missing
            # (no fallback needed — just return None)
            return None
        if _BACKEND == "disk":
            return _disk_get(key)
    except Exception as exc:
        logger.warning("[LexiGraphCache] get() unexpected error: %s", exc)
    return None


def set(key: str, value: Dict[str, Any]) -> bool:  # noqa: A001
    """
    Store *value* under *key* in the configured cache backend.

    Returns ``True`` on success, ``False`` on failure / disabled.
    Never raises.
    """
    if not is_cache_enabled():
        return False
    try:
        if _BACKEND == "redis":
            stored = _redis_set(key, value, _TTL)
            if not stored:
                # Redis failed → silently fall through to disk
                return _disk_set(key, value)
            return True
        if _BACKEND == "disk":
            return _disk_set(key, value)
    except Exception as exc:
        logger.warning("[LexiGraphCache] set() unexpected error: %s", exc)
    return False


def invalidate(key: str) -> None:
    """
    Remove *key* from all backends.  Useful for forced re-runs.
    Never raises.
    """
    try:
        if _BACKEND in ("redis", "none"):
            r = _redis_client()
            if r:
                r.delete(key)
        if _BACKEND in ("disk", "none"):
            _disk_path(key).unlink(missing_ok=True)
    except Exception as exc:
        logger.debug("[LexiGraphCache] invalidate() error: %s", exc)


def invalidate_query(query: str) -> None:
    """Convenience wrapper: invalidate the cache entry for a raw query string."""
    invalidate(make_key(query))


def flush_cache() -> None:
    """Flush all cache entries across Redis and disk storage."""
    try:
        if _BACKEND in ("redis", "none"):
            r = _redis_client()
            if r:
                for pattern in ("lexigraph:*", "stage0:*"):
                    keys = r.keys(pattern)
                    if keys:
                        r.delete(*keys)
        if _CACHE_DIR.exists():
            for f in _CACHE_DIR.glob("*.json"):
                f.unlink(missing_ok=True)
    except Exception as exc:
        logger.debug("[LexiGraphCache] flush_cache() error: %s", exc)

