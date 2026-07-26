"""
Unit tests for the query cache.
"""

import time
import pytest

from backend.agents.lexigraph.cypher.legal_text2cypher.utils.query_cache import TTLCache


class TestTTLCache:
    def test_put_and_get(self):
        cache = TTLCache(max_size=10, ttl_seconds=60)
        cache.put("value1", "ns", "key1")
        assert cache.get("ns", "key1") == "value1"

    def test_miss(self):
        cache = TTLCache(max_size=10, ttl_seconds=60)
        assert cache.get("ns", "missing") is None

    def test_ttl_expiry(self):
        cache = TTLCache(max_size=10, ttl_seconds=1)
        cache.put("value1", "ns", "key1")
        assert cache.get("ns", "key1") == "value1"
        time.sleep(1.1)
        assert cache.get("ns", "key1") is None

    def test_max_size_eviction(self):
        cache = TTLCache(max_size=3, ttl_seconds=60)
        cache.put("v1", "ns", "k1")
        cache.put("v2", "ns", "k2")
        cache.put("v3", "ns", "k3")
        cache.put("v4", "ns", "k4")  # Should evict k1
        assert cache.size == 3
        assert cache.get("ns", "k1") is None  # evicted
        assert cache.get("ns", "k4") == "v4"

    def test_clear(self):
        cache = TTLCache(max_size=10, ttl_seconds=60)
        cache.put("v1", "ns", "k1")
        cache.put("v2", "ns", "k2")
        cache.clear()
        assert cache.size == 0
        assert cache.get("ns", "k1") is None

    def test_overwrite_key(self):
        cache = TTLCache(max_size=10, ttl_seconds=60)
        cache.put("old", "ns", "key")
        cache.put("new", "ns", "key")
        assert cache.get("ns", "key") == "new"
        assert cache.size == 1
