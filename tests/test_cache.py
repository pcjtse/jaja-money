"""Tests for cache.py (P1.5)."""

import time
import pytest


@pytest.fixture
def dc(tmp_path):
    from cache import DiskCache

    return DiskCache(cache_dir=tmp_path)


def test_set_and_get(dc):
    dc.set("key1", {"data": 42}, ttl=60)
    val = dc.get("key1")
    assert val == {"data": 42}


def test_miss_returns_sentinel(dc):
    from cache import CACHE_MISS

    assert dc.get("nonexistent") is CACHE_MISS


def test_ttl_expiry(dc):
    from cache import CACHE_MISS

    dc.set("key_expire", "hello", ttl=0)
    time.sleep(0.05)
    assert dc.get("key_expire") is CACHE_MISS


def test_delete(dc):
    from cache import CACHE_MISS

    dc.set("key_del", "value", ttl=60)
    dc.delete("key_del")
    assert dc.get("key_del") is CACHE_MISS


def test_clear(dc):
    from cache import CACHE_MISS

    dc.set("a", 1, ttl=60)
    dc.set("b", 2, ttl=60)
    count = dc.clear()
    assert count == 2
    assert dc.get("a") is CACHE_MISS
    assert dc.get("b") is CACHE_MISS


def test_stats(dc):
    dc.set("x", [1, 2, 3], ttl=60)
    s = dc.stats()
    assert s["enabled"] is True
    assert s["entries"] == 1
    assert s["size_mb"] >= 0


def test_overwrite(dc):
    dc.set("key", "old", ttl=60)
    dc.set("key", "new", ttl=60)
    assert dc.get("key") == "new"


def test_various_value_types(dc):
    from cache import CACHE_MISS

    dc.set("int", 42, ttl=60)
    dc.set("list", [1, 2, 3], ttl=60)
    dc.set("dict", {"a": 1}, ttl=60)
    dc.set("none_val", None, ttl=60)
    assert dc.get("int") == 42
    assert dc.get("list") == [1, 2, 3]
    assert dc.get("dict") == {"a": 1}
    # With sentinel, cached None is now distinguishable from a miss
    assert dc.get("none_val") is None
    assert dc.get("truly_missing") is CACHE_MISS
