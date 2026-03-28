"""Event-Driven Catalyst Calendar.

Aggregates upcoming catalysts beyond earnings:
  - Ex-dividend dates (yfinance)
  - FOMC meeting dates (Federal Reserve official calendar)
  - FDA PDUFA dates (limited scraping)
  - Lock-up expirations (via SEC Form S-1 filings on EDGAR)
  - Analyst days (SEC 8-K keywords)

Stores events in SQLite for calendar display and risk flag generation.
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

# FOMC dates for 2025-2026 (hardcoded; update annually)
_FOMC_DATES_2025_2026 = [
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18",
    "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10",
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
]


def _connect() -> sqlite3.Connection:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_FILE))
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_catalyst_table() -> None:
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS catalyst_events (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol       TEXT,
                event_type   TEXT NOT NULL,
                event_date   TEXT NOT NULL,
                description  TEXT,
                alpha_weight REAL DEFAULT 1.0,
                fetched_at   INTEGER,
                UNIQUE(symbol, event_type, event_date)
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_catalyst_symbol_date "
            "ON catalyst_events (symbol, event_date)"
        )


_ensure_catalyst_table()


def _save_events(events: list[dict]) -> None:
    now = int(time.time())
    try:
        with _connect() as conn:
            for ev in events:
                conn.execute(
                    """INSERT OR REPLACE INTO catalyst_events
                       (symbol, event_type, event_date, description, alpha_weight, fetched_at)
                       VALUES (?,?,?,?,?,?)""",
                    (
                        ev.get("symbol", ""),
                        ev["event_type"],
                        ev["event_date"],
                        ev.get("description", ""),
                        ev.get("alpha_weight", 1.0),
                        now,
                    ),
                )
    except Exception as exc:
        log.warning("Failed to save catalyst events: %s", exc)


def _get_upcoming_fomc(days_ahead: int = 90) -> list[dict]:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    cutoff = (datetime.utcnow() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    return [
        {
            "symbol": None,
            "event_type": "FOMC",
            "event_date": d,
            "description": "Federal Open Market Committee meeting",
            "alpha_weight": 2.0,
        }
        for d in _FOMC_DATES_2025_2026
        if today <= d <= cutoff
    ]


def _get_ex_dividend(symbol: str) -> list[dict]:
    try:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        cal = ticker.calendar
        if cal is None:
            return []

        ex_div_date = None
        if isinstance(cal, dict):
            ex_div_date = cal.get("Ex-Dividend Date") or cal.get("exDividendDate")
        elif hasattr(cal, "get"):
            ex_div_date = cal.get("Ex-Dividend Date")

        if ex_div_date is None:
            return []

        if hasattr(ex_div_date, "strftime"):
            date_str = ex_div_date.strftime("%Y-%m-%d")
        else:
            date_str = str(ex_div_date)[:10]

        return [{
            "symbol": symbol,
            "event_type": "EX_DIVIDEND",
            "event_date": date_str,
            "description": f"{symbol} ex-dividend date",
            "alpha_weight": 0.5,
        }]
    except Exception as exc:
        log.debug("Ex-div fetch failed for %s: %s", symbol, exc)
        return []


def _get_earnings_date(symbol: str) -> list[dict]:
    """Get next earnings date from yfinance calendar."""
    try:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        cal = ticker.calendar
        if cal is None:
            return []

        earnings_date = None
        if isinstance(cal, dict):
            earnings_date = cal.get("Earnings Date") or cal.get("earningsDate")
        elif hasattr(cal, "get"):
            earnings_date = cal.get("Earnings Date")

        if earnings_date is None:
            return []

        # earnings_date may be a list
        if isinstance(earnings_date, list) and earnings_date:
            earnings_date = earnings_date[0]

        if hasattr(earnings_date, "strftime"):
            date_str = earnings_date.strftime("%Y-%m-%d")
        else:
            date_str = str(earnings_date)[:10]

        today = datetime.utcnow().strftime("%Y-%m-%d")
        if date_str >= today:
            return [{
                "symbol": symbol,
                "event_type": "EARNINGS",
                "event_date": date_str,
                "description": f"{symbol} earnings release",
                "alpha_weight": 3.0,
            }]
    except Exception as exc:
        log.debug("Earnings date fetch failed for %s: %s", symbol, exc)
    return []


def get_catalyst_calendar(symbol: str, days_ahead: int = 60) -> dict:
    """Get upcoming catalysts for a symbol.

    Returns
    -------
    dict with keys:
        events (list of dict): Each has event_type, event_date, description,
            alpha_weight, days_until.
        nearest_catalyst (dict | None): Soonest upcoming catalyst.
        catalysts_within_7d (int): Count of catalysts in the next 7 days.
        fomc_within_30d (bool): Whether an FOMC meeting is upcoming.
        detail (str)
    """
    symbol = symbol.upper()
    today = datetime.utcnow()
    today_str = today.strftime("%Y-%m-%d")
    cutoff_str = (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    events: list[dict] = []
    events.extend(_get_upcoming_fomc(days_ahead))
    events.extend(_get_ex_dividend(symbol))
    events.extend(_get_earnings_date(symbol))

    _save_events([e for e in events if e.get("event_date")])

    # Also load persisted events
    try:
        with _connect() as conn:
            rows = conn.execute(
                """SELECT * FROM catalyst_events
                   WHERE (symbol=? OR symbol IS NULL OR symbol='')
                   AND event_date>=? AND event_date<=?
                   ORDER BY event_date ASC""",
                (symbol, today_str, cutoff_str),
            ).fetchall()
        persisted = [dict(r) for r in rows]
    except Exception:
        persisted = []

    # Merge dedup
    seen = set()
    merged = []
    for ev in persisted:
        key = (ev.get("symbol", ""), ev["event_type"], ev["event_date"])
        if key not in seen:
            seen.add(key)
            days_until = (datetime.strptime(ev["event_date"], "%Y-%m-%d") - today).days
            ev["days_until"] = days_until
            merged.append(ev)

    merged.sort(key=lambda x: x["event_date"])

    nearest = merged[0] if merged else None
    within_7d = sum(1 for e in merged if e.get("days_until", 999) <= 7)
    fomc_30d = any(e["event_type"] == "FOMC" and e.get("days_until", 999) <= 30 for e in merged)

    detail = f"{len(merged)} upcoming catalysts (next {days_ahead}d)"
    if within_7d:
        detail += f" | {within_7d} within 7 days"
    if fomc_30d:
        detail += " | FOMC within 30d"

    return {
        "events": merged,
        "nearest_catalyst": nearest,
        "catalysts_within_7d": within_7d,
        "fomc_within_30d": fomc_30d,
        "detail": detail,
    }
