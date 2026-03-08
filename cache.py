"""Persistent disk cache with TTL.

Stores pickled values in ~/.jaja-money/cache/.  Falls back gracefully
to no-op if the cache directory can't be created or a read/write fails.

Usage:
    from cache import DiskCache
    dc = DiskCache()
    dc.set("quote:AAPL", data, ttl=300)
    val = dc.get("quote:AAPL")   # None if expired / missing
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
        """Return cached value or None if missing / expired."""
        if not self._enabled:
            return None
        path = self._key_to_path(key)
        try:
            if not path.exists():
                return None
            with open(path, "rb") as f:
                expires_at, value = pickle.load(f)
            if time.time() > expires_at:
                path.unlink(missing_ok=True)
                return None
            log.debug("Cache hit: %s", key)
            return value
        except Exception as exc:
            log.debug("Cache read error for %s: %s", key, exc)
            return None

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


# Module-level singleton
_cache = DiskCache()


def get_cache() -> DiskCache:
    return _cache
