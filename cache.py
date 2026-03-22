"""Persistent disk cache with TTL.

Stores pickled values in ~/.jaja-money/cache/.  Falls back gracefully
to no-op if the cache directory can't be created or a read/write fails.

Uses a sentinel value to distinguish "not in cache" from "cached None".

Usage:
    from cache import DiskCache, CACHE_MISS
    dc = DiskCache()
    dc.set("quote:AAPL", data, ttl=300)
    val = dc.get("quote:AAPL")   # CACHE_MISS if expired / missing
"""

from __future__ import annotations

import hashlib
import pickle
import time
from pathlib import Path
from typing import Any

from config import cfg
from log_setup import get_logger

log = get_logger(__name__)

# Sentinel to distinguish "key not found / expired" from a cached None value
_CACHE_MISS = object()
CACHE_MISS = _CACHE_MISS


class DiskCache:
    """Simple TTL-based disk cache backed by pickle files."""

    def __init__(self, cache_dir: Path | None = None) -> None:
        self._dir = Path(cache_dir or cfg.cache_dir)
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            self._enabled = True
        except OSError as exc:
            log.warning("Disk cache disabled – could not create dir: %s", exc)
            self._enabled = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _key_to_path(self, key: str) -> Path:
        h = hashlib.sha256(key.encode()).hexdigest()
        return self._dir / f"{h}.pkl"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, key: str) -> Any:
        """Return cached value or CACHE_MISS sentinel if missing / expired."""
        if not self._enabled:
            return _CACHE_MISS
        path = self._key_to_path(key)
        try:
            if not path.exists():
                return _CACHE_MISS
            with open(path, "rb") as f:
                expires_at, value = pickle.load(f)
            if time.time() > expires_at:
                path.unlink(missing_ok=True)
                return _CACHE_MISS
            log.debug("Cache hit: %s", key)
            return value
        except Exception as exc:
            log.debug("Cache read error for %s: %s", key, exc)
            return _CACHE_MISS

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Store value with TTL (seconds).  Default TTL from config."""
        if not self._enabled:
            return
        ttl = ttl if ttl is not None else cfg.cache_ttl
        path = self._key_to_path(key)
        try:
            expires_at = time.time() + ttl
            with open(path, "wb") as f:
                pickle.dump((expires_at, value), f, protocol=4)
            log.debug("Cache set: %s (ttl=%ds)", key, ttl)
        except Exception as exc:
            log.debug("Cache write error for %s: %s", key, exc)

    def delete(self, key: str) -> None:
        if not self._enabled:
            return
        path = self._key_to_path(key)
        path.unlink(missing_ok=True)

    def clear(self) -> int:
        """Delete all cached files.  Returns count of deleted entries."""
        if not self._enabled:
            return 0
        count = 0
        for p in self._dir.glob("*.pkl"):
            try:
                p.unlink()
                count += 1
            except OSError:
                pass
        log.info("Cache cleared: %d entries removed", count)
        return count

    def stats(self) -> dict:
        """Return simple cache stats."""
        if not self._enabled:
            return {"enabled": False, "entries": 0, "size_mb": 0.0}
        files = list(self._dir.glob("*.pkl"))
        size = sum(f.stat().st_size for f in files if f.exists())
        return {
            "enabled": True,
            "entries": len(files),
            "size_mb": round(size / 1_048_576, 2),
        }


# ---------------------------------------------------------------------------
# P14.2: Redis Cache Backend Option
# ---------------------------------------------------------------------------


class RedisCacheBackend:
    """Redis-backed cache implementing the same interface as DiskCache.

    Requires redis-py: pip install redis

    Configure via environment variables:
        CACHE_BACKEND=redis
        REDIS_URL=redis://localhost:6379/0   (default)
    """

    def __init__(self, redis_url: str = "redis://localhost:6379/0") -> None:
        self._url = redis_url
        self._client = None
        self._enabled = False
        self._connect()

    def _connect(self) -> None:
        try:
            import redis

            self._client = redis.Redis.from_url(self._url, decode_responses=False)
            self._client.ping()
            self._enabled = True
            log.info("Redis cache connected: %s", self._url)
        except ImportError:
            log.warning("redis-py not installed; RedisCacheBackend disabled")
        except Exception as exc:
            log.warning("Redis connection failed (%s): %s", self._url, exc)

    def get(self, key: str) -> Any:
        """Return cached value or CACHE_MISS sentinel."""
        if not self._enabled:
            return _CACHE_MISS
        try:
            data = self._client.get(key)
            if data is None:
                return _CACHE_MISS
            log.debug("Redis cache hit: %s", key)
            return pickle.loads(data)
        except Exception as exc:
            log.debug("Redis get error for %s: %s", key, exc)
            return _CACHE_MISS

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Store value with TTL."""
        if not self._enabled:
            return
        try:
            ttl = ttl if ttl is not None else cfg.cache_ttl
            data = pickle.dumps(value, protocol=4)
            self._client.setex(key, ttl, data)
            log.debug("Redis cache set: %s (ttl=%ds)", key, ttl)
        except Exception as exc:
            log.debug("Redis set error for %s: %s", key, exc)

    def delete(self, key: str) -> None:
        if not self._enabled:
            return
        try:
            self._client.delete(key)
        except Exception:
            pass

    def clear(self) -> int:
        """Delete all keys. Returns count."""
        if not self._enabled:
            return 0
        try:
            keys = self._client.keys("*")
            if keys:
                return self._client.delete(*keys)
            return 0
        except Exception:
            return 0

    def stats(self) -> dict:
        if not self._enabled:
            return {"enabled": False, "backend": "redis", "entries": 0}
        try:
            info = self._client.info("keyspace")
            db_info = list(info.values())[0] if info else {}
            return {
                "enabled": True,
                "backend": "redis",
                "url": self._url,
                "entries": db_info.get("keys", 0),
            }
        except Exception:
            return {"enabled": self._enabled, "backend": "redis"}


# ---------------------------------------------------------------------------
# Cache factory — selects backend based on CACHE_BACKEND env variable
# ---------------------------------------------------------------------------


def _create_cache():
    """Create the appropriate cache backend based on CACHE_BACKEND env var."""
    import os

    backend = os.getenv("CACHE_BACKEND", "disk").lower()
    if backend == "redis":
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        log.info("Using Redis cache backend: %s", redis_url)
        return RedisCacheBackend(redis_url=redis_url)
    return DiskCache()


# Module-level singleton
_cache = _create_cache()


def get_cache():
    """Return the active cache backend (DiskCache or RedisCacheBackend)."""
    return _cache
