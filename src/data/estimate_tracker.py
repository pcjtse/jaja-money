"""Earnings Estimate Revision Velocity Tracker.

Stores EPS estimate snapshots in SQLite on each analysis run and
computes velocity (rate of change) and acceleration of analyst revisions.

Revision momentum is one of the strongest documented alpha factors:
stocks with accelerating upward revisions consistently outperform.
"""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path

from src.core.log_setup import get_logger

log = get_logger(__name__)

_DATA_DIR = Path.home() / ".jaja-money"
_DB_FILE = _DATA_DIR / "history.db"


def _connect() -> sqlite3.Connection:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_FILE))
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_estimate_table() -> None:
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS estimate_history (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol              TEXT NOT NULL,
                snapshot_date       TEXT NOT NULL,
                forward_eps         REAL,
                analyst_count       INTEGER,
                revision_direction  TEXT,
                fetched_at          INTEGER,
                UNIQUE(symbol, snapshot_date)
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_estimate_symbol "
            "ON estimate_history (symbol, snapshot_date)"
        )


_ensure_estimate_table()


def save_estimate_snapshot(
    symbol: str,
    forward_eps: float | None,
    analyst_count: int | None,
    revision_direction: str,
) -> None:
    """Persist today's EPS estimate snapshot for velocity tracking."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    symbol = symbol.upper()
    try:
        with _connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO estimate_history
                   (symbol, snapshot_date, forward_eps, analyst_count,
                    revision_direction, fetched_at)
                   VALUES (?,?,?,?,?,?)""",
                (
                    symbol,
                    today,
                    forward_eps,
                    analyst_count,
                    revision_direction,
                    int(time.time()),
                ),
            )
    except Exception as exc:
        log.warning("Failed to save estimate snapshot for %s: %s", symbol, exc)


def get_estimate_history(symbol: str, days: int = 90) -> list[dict]:
    """Return stored estimate snapshots for the last `days` days."""
    symbol = symbol.upper()
    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    try:
        with _connect() as conn:
            rows = conn.execute(
                """SELECT * FROM estimate_history
                   WHERE symbol=? AND snapshot_date>=?
                   ORDER BY snapshot_date ASC""",
                (symbol, cutoff),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


def compute_revision_velocity(symbol: str, window_days: int = 60) -> dict:
    """Compute EPS revision velocity and acceleration from stored history.

    Returns
    -------
    dict with keys:
        revision_count_30d (int): Number of snapshots stored in last 30 days.
        revision_count_60d (int): Number of snapshots stored in last 60 days.
        consecutive_up (int): Longest streak of consecutive "up" directions.
        consecutive_down (int): Longest streak of consecutive "down" directions.
        eps_change_pct (float | None): % change in fwd EPS over window.
        velocity_score (int): 0-100 velocity signal score.
        detail (str)
    """
    history = get_estimate_history(symbol, days=window_days)

    if not history:
        return {
            "revision_count_30d": 0,
            "revision_count_60d": 0,
            "consecutive_up": 0,
            "consecutive_down": 0,
            "eps_change_pct": None,
            "velocity_score": 50,
            "detail": "Insufficient estimate history for velocity calculation",
        }

    cutoff_30d = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")
    count_30d = sum(1 for r in history if r["snapshot_date"] >= cutoff_30d)
    count_60d = len(history)

    directions = [r["revision_direction"] for r in history]
    max_up_streak = _max_streak(directions, "up")
    max_down_streak = _max_streak(directions, "down")

    eps_values = [r["forward_eps"] for r in history if r["forward_eps"] is not None]
    eps_change_pct = None
    if len(eps_values) >= 2:
        start_eps = eps_values[0]
        end_eps = eps_values[-1]
        if start_eps and start_eps != 0:
            eps_change_pct = round((end_eps - start_eps) / abs(start_eps) * 100, 2)

    # Score based on streak and EPS change
    if max_up_streak >= 3:
        score = 90
    elif max_up_streak == 2:
        score = 78
    elif max_down_streak >= 3:
        score = 12
    elif max_down_streak == 2:
        score = 25
    elif eps_change_pct is not None and eps_change_pct > 5:
        score = 72
    elif eps_change_pct is not None and eps_change_pct < -5:
        score = 30
    else:
        score = 50

    detail_parts = [f"Up streak: {max_up_streak}", f"Down streak: {max_down_streak}"]
    if eps_change_pct is not None:
        detail_parts.append(f"EPS change {window_days}d: {eps_change_pct:+.1f}%")

    return {
        "revision_count_30d": count_30d,
        "revision_count_60d": count_60d,
        "consecutive_up": max_up_streak,
        "consecutive_down": max_down_streak,
        "eps_change_pct": eps_change_pct,
        "velocity_score": score,
        "detail": " | ".join(detail_parts),
    }


def _max_streak(directions: list[str], target: str) -> int:
    """Return the maximum consecutive run of `target` in `directions`."""
    max_run = current_run = 0
    for d in directions:
        if d == target:
            current_run += 1
            max_run = max(max_run, current_run)
        else:
            current_run = 0
    return max_run
