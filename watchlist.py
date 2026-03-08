"""Watchlist management.

Persists a JSON file at ~/.jaja-money/watchlist.json.
Each entry stores ticker, name, last price, factor score, and timestamp.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from log_setup import get_logger

log = get_logger(__name__)

_DATA_DIR = Path.home() / ".jaja-money"
_WATCHLIST_FILE = _DATA_DIR / "watchlist.json"


def _load() -> list[dict]:
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not _WATCHLIST_FILE.exists():
            return []
        with open(_WATCHLIST_FILE, "r") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception as exc:
        log.warning("Failed to load watchlist: %s", exc)
        return []


def _save(items: list[dict]) -> None:
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(_WATCHLIST_FILE, "w") as f:
            json.dump(items, f, indent=2)
    except Exception as exc:
        log.warning("Failed to save watchlist: %s", exc)


def get_watchlist() -> list[dict]:
    """Return all watchlist entries."""
    return _load()


def is_in_watchlist(symbol: str) -> bool:
    return any(e["symbol"] == symbol.upper() for e in _load())


def add_to_watchlist(
    symbol: str,
    name: str = "",
    price: float | None = None,
    factor_score: int | None = None,
    risk_score: int | None = None,
) -> None:
    """Add or update a symbol in the watchlist."""
    items = _load()
    symbol = symbol.upper()
    # Remove existing entry for this symbol
    items = [e for e in items if e["symbol"] != symbol]
    items.append({
        "symbol": symbol,
        "name": name,
        "price": price,
        "factor_score": factor_score,
        "risk_score": risk_score,
        "added_at": int(time.time()),
    })
    _save(items)
    log.info("Added %s to watchlist", symbol)


def remove_from_watchlist(symbol: str) -> None:
    """Remove a symbol from the watchlist."""
    items = _load()
    items = [e for e in items if e["symbol"] != symbol.upper()]
    _save(items)
    log.info("Removed %s from watchlist", symbol)


def update_watchlist_entry(symbol: str, **kwargs: Any) -> None:
    """Update specific fields for an existing watchlist entry."""
    items = _load()
    symbol = symbol.upper()
    for entry in items:
        if entry["symbol"] == symbol:
            entry.update(kwargs)
            break
    _save(items)
