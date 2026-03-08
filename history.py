"""Historical factor score tracking using SQLite.

Stores analysis snapshots (factor score, risk score, price, flags) keyed
by (symbol, date) in ~/.jaja-money/history.db.

Usage:
    from history import save_analysis, get_history, get_score_trend
"""
from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from log_setup import get_logger

log = get_logger(__name__)

_DATA_DIR = Path.home() / ".jaja-money"
_DB_FILE = _DATA_DIR / "history.db"


def _connect() -> sqlite3.Connection:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_FILE))
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_table() -> None:
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS analysis_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol      TEXT NOT NULL,
                date        TEXT NOT NULL,
                timestamp   INTEGER NOT NULL,
                price       REAL,
                factor_score INTEGER,
                risk_score   INTEGER,
                composite_label TEXT,
                risk_level   TEXT,
                factors_json TEXT,
                flags_json   TEXT
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_symbol_date "
            "ON analysis_history (symbol, date)"
        )


_ensure_table()


def save_analysis(
    symbol: str,
    price: float | None,
    factor_score: int,
    risk_score: int,
    composite_label: str = "",
    risk_level: str = "",
    factors: list | None = None,
    flags: list | None = None,
) -> None:
    """Upsert today's analysis snapshot for a symbol."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    symbol = symbol.upper()
    try:
        with _connect() as conn:
            # Remove existing entry for today
            conn.execute(
                "DELETE FROM analysis_history WHERE symbol=? AND date=?",
                (symbol, today),
            )
            conn.execute(
                """INSERT INTO analysis_history
                   (symbol, date, timestamp, price, factor_score, risk_score,
                    composite_label, risk_level, factors_json, flags_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    symbol,
                    today,
                    int(time.time()),
                    price,
                    factor_score,
                    risk_score,
                    composite_label,
                    risk_level,
                    json.dumps(factors or []),
                    json.dumps(flags or []),
                ),
            )
        log.info("Saved analysis snapshot for %s on %s", symbol, today)
    except Exception as exc:
        log.warning("Failed to save analysis history for %s: %s", symbol, exc)


def get_history(symbol: str, limit: int = 90) -> list[dict]:
    """Return chronological analysis history for a symbol (up to `limit` days)."""
    symbol = symbol.upper()
    try:
        with _connect() as conn:
            rows = conn.execute(
                """SELECT * FROM analysis_history
                   WHERE symbol=?
                   ORDER BY date ASC
                   LIMIT ?""",
                (symbol, limit),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as exc:
        log.warning("Failed to fetch history for %s: %s", symbol, exc)
        return []


def get_score_trend(symbol: str, limit: int = 30) -> dict:
    """Return date/factor_score/risk_score arrays for charting."""
    rows = get_history(symbol, limit=limit)
    return {
        "dates": [r["date"] for r in rows],
        "factor_scores": [r["factor_score"] for r in rows],
        "risk_scores": [r["risk_score"] for r in rows],
        "prices": [r["price"] for r in rows],
    }


def get_latest_two_snapshots(symbol: str) -> list[dict]:
    """Return the two most recent distinct-date analysis snapshots for a symbol.

    Returns a list of 0–2 dicts, sorted oldest-first, so index 0 is the
    previous snapshot and index 1 is the most recent one.
    """
    symbol = symbol.upper()
    try:
        with _connect() as conn:
            rows = conn.execute(
                """SELECT * FROM analysis_history
                   WHERE symbol=?
                   ORDER BY date DESC
                   LIMIT 2""",
                (symbol,),
            ).fetchall()
        result = [dict(r) for r in rows]
        result.reverse()
        return result
    except Exception as exc:
        log.warning("Failed to fetch latest snapshots for %s: %s", symbol, exc)
        return []


def get_tracked_symbols() -> list[str]:
    """Return all symbols that have at least one history entry."""
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT symbol FROM analysis_history ORDER BY symbol"
            ).fetchall()
        return [r["symbol"] for r in rows]
    except Exception:
        return []
