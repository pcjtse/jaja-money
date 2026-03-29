"""Dark Pool / ATS Volume Signal.

Tracks off-exchange (dark pool) volume using FINRA ATS Transparency data.
High and rising dark pool volume with flat price can indicate institutional
accumulation before a price move.

Data source: FINRA ATS weekly aggregate CSV
  https://otctransparency.finra.org/otctransparency/AtsIssueData
Note: data is delayed ~2 weeks; use as a medium-term signal.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from src.core.log_setup import get_logger

log = get_logger(__name__)

_DATA_DIR = Path.home() / ".jaja-money"
_DB_FILE = _DATA_DIR / "history.db"

_FINRA_ATS_URL = "https://otctransparency.finra.org/otctransparency/AtsIssueData"

# ATS spike threshold: ratio of recent vs 4-week avg
_ATS_SPIKE_THRESHOLD = 1.5


def _connect() -> sqlite3.Connection:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_FILE))
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_dark_pool_table() -> None:
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS dark_pool_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol      TEXT NOT NULL,
                week_date   TEXT NOT NULL,
                ats_volume  INTEGER,
                total_volume INTEGER,
                ats_pct     REAL,
                fetched_at  INTEGER,
                UNIQUE(symbol, week_date)
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_dp_symbol "
            "ON dark_pool_history (symbol, week_date)"
        )


_ensure_dark_pool_table()


def fetch_dark_pool_signal(symbol: str) -> dict:
    """Fetch dark pool volume signal for a symbol.

    Returns
    -------
    dict with keys:
        available (bool)
        ats_pct_latest (float | None): Most recent ATS volume as % of total.
        ats_pct_4w_avg (float | None): 4-week average ATS %.
        trend (str): "increasing" | "decreasing" | "flat" | "unknown"
        spike (bool): True if latest week >> 4w average.
        score (int): 0-100 signal score.
        detail (str)
    """
    symbol = symbol.upper()

    # Try FINRA ATS data
    ats_data = _fetch_finra_ats(symbol)
    if not ats_data:
        # Fall back to yfinance total volume proxy
        ats_data = _estimate_from_yfinance(symbol)

    if not ats_data:
        return {
            "available": False,
            "ats_pct_latest": None,
            "ats_pct_4w_avg": None,
            "trend": "unknown",
            "spike": False,
            "score": 50,
            "detail": "Dark pool data unavailable",
        }

    _save_history(symbol, ats_data)

    history = _load_history(symbol, weeks=8)
    return _compute_signal(history)


def _fetch_finra_ats(symbol: str) -> list[dict]:
    """Fetch FINRA ATS weekly data for a symbol."""
    try:
        import requests

        resp = requests.get(
            _FINRA_ATS_URL,
            params={"symbol": symbol},
            timeout=12,
            headers={"User-Agent": "jaja-money/1.0"},
        )
        if resp.status_code != 200:
            return []

        ct = resp.headers.get("Content-Type", "")
        if "json" in ct:
            data = resp.json()
            items = data if isinstance(data, list) else data.get("data", [])
            result = []
            for item in items:
                result.append({
                    "week_date": str(item.get("weeklyEndingDate", item.get("date", "")))[:10],
                    "ats_volume": int(item.get("totalWeeklyShareQuantity", item.get("volume", 0)) or 0),
                    "total_volume": int(item.get("totalWeeklyShareQuantity", 0) or 0),
                })
            return result
        return []
    except Exception as exc:
        log.debug("FINRA ATS fetch failed for %s: %s", symbol, exc)
        return []


def _estimate_from_yfinance(symbol: str) -> list[dict]:
    """Estimate ATS signal from volume patterns (heuristic proxy)."""
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="60d")
        if hist.empty or "Volume" not in hist.columns:
            return []

        result = []
        hist = hist.reset_index()
        # Group into weekly buckets
        hist["week"] = hist["Date"].dt.to_period("W")
        for week, group in hist.groupby("week"):
            avg_vol = float(group["Volume"].mean())
            # Heuristic: dark pool is roughly 30-45% of total in normal markets
            ats_est_pct = 0.38  # baseline estimate
            result.append({
                "week_date": str(week.end_time)[:10],
                "ats_volume": int(avg_vol * ats_est_pct),
                "total_volume": int(avg_vol),
            })
        return result[-8:]
    except Exception as exc:
        log.debug("yfinance dark pool estimation failed for %s: %s", symbol, exc)
        return []


def _save_history(symbol: str, data: list[dict]) -> None:
    if not data:
        return
    now = int(time.time())
    try:
        with _connect() as conn:
            for item in data:
                total = item.get("total_volume") or 1
                ats = item.get("ats_volume") or 0
                ats_pct = round(ats / total * 100, 2) if total > 0 else None
                conn.execute(
                    """INSERT OR REPLACE INTO dark_pool_history
                       (symbol, week_date, ats_volume, total_volume, ats_pct, fetched_at)
                       VALUES (?,?,?,?,?,?)""",
                    (symbol, item["week_date"], ats, total, ats_pct, now),
                )
    except Exception as exc:
        log.debug("Dark pool history save failed: %s", exc)


def _load_history(symbol: str, weeks: int = 8) -> list[dict]:
    try:
        with _connect() as conn:
            rows = conn.execute(
                """SELECT * FROM dark_pool_history
                   WHERE symbol=? ORDER BY week_date DESC LIMIT ?""",
                (symbol, weeks),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


def _compute_signal(history: list[dict]) -> dict:
    if not history:
        return {
            "available": False,
            "ats_pct_latest": None,
            "ats_pct_4w_avg": None,
            "trend": "unknown",
            "spike": False,
            "score": 50,
            "detail": "No dark pool history",
        }

    pcts = [r["ats_pct"] for r in history if r.get("ats_pct") is not None]
    if not pcts:
        return {
            "available": False,
            "ats_pct_latest": None,
            "ats_pct_4w_avg": None,
            "trend": "unknown",
            "spike": False,
            "score": 50,
            "detail": "No ATS percentage data",
        }

    latest = pcts[0]
    prior = pcts[1:]  # exclude current week for baseline average
    avg_4w = sum(prior[:4]) / min(4, len(prior)) if prior else latest
    spike = latest > avg_4w * _ATS_SPIKE_THRESHOLD

    if len(pcts) >= 3:
        if pcts[0] > pcts[1] > pcts[2]:
            trend = "increasing"
        elif pcts[0] < pcts[1] < pcts[2]:
            trend = "decreasing"
        else:
            trend = "flat"
    else:
        trend = "flat"

    # Score: rising ATS with flat/down price = accumulation = bullish
    if spike and trend == "increasing":
        score = 72
    elif trend == "increasing":
        score = 63
    elif spike:
        score = 60
    elif trend == "decreasing":
        score = 40
    else:
        score = 50

    detail = (
        f"ATS vol (latest): {latest:.1f}% | "
        f"4w avg: {avg_4w:.1f}% | "
        f"Trend: {trend}"
    )
    if spike:
        detail += " | Spike detected"

    return {
        "available": True,
        "ats_pct_latest": round(latest, 2),
        "ats_pct_4w_avg": round(avg_4w, 2),
        "trend": trend,
        "spike": spike,
        "score": score,
        "detail": detail,
    }
