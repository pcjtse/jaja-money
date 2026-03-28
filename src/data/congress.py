"""Congressional / STOCK Act trade tracker.

Fetches politician trade disclosures from the Capitol Trades public API
(https://www.capitoltrades.com) with a Quiver Quantitative fallback.

Returns a signal dict and stores trades in SQLite for historical analysis.
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

_CAPITOL_TRADES_URL = "https://www.capitoltrades.com/api/trades"
_QUIVER_URL = "https://api.quiverquant.com/beta/live/congresstrading"


def _connect() -> sqlite3.Connection:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_FILE))
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_congress_table() -> None:
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS congress_trades (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol           TEXT NOT NULL,
                politician       TEXT,
                trade_date       TEXT,
                transaction_type TEXT,
                amount_range     TEXT,
                party            TEXT,
                chamber          TEXT,
                fetched_at       INTEGER
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_congress_symbol "
            "ON congress_trades (symbol, trade_date)"
        )


_ensure_congress_table()


def _fetch_capitol_trades(symbol: str, days: int = 90) -> list[dict]:
    """Fetch trades from Capitol Trades API."""
    try:
        import requests

        since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        resp = requests.get(
            _CAPITOL_TRADES_URL,
            params={"ticker": symbol, "from": since},
            timeout=10,
            headers={"User-Agent": "jaja-money/1.0"},
        )
        resp.raise_for_status()
        data = resp.json()

        trades = []
        items = data if isinstance(data, list) else data.get("trades", data.get("data", []))
        for item in items:
            ticker = (
                item.get("ticker")
                or item.get("symbol")
                or item.get("asset", {}).get("ticker", "")
            )
            if str(ticker).upper() != symbol.upper():
                continue
            trades.append({
                "politician": item.get("politician", {}).get("name", item.get("politician", "")),
                "trade_date": item.get("traded", item.get("tradeDate", item.get("date", ""))),
                "transaction_type": item.get("txType", item.get("type", "purchase")),
                "amount_range": str(item.get("size", item.get("amount", ""))),
                "party": item.get("politician", {}).get("party", item.get("party", "")),
                "chamber": item.get("politician", {}).get("chamber", item.get("chamber", "")),
            })
        return trades
    except Exception as exc:
        log.debug("Capitol Trades fetch failed for %s: %s", symbol, exc)
        return []


def _fetch_quiver_quant(symbol: str) -> list[dict]:
    """Fallback: fetch from Quiver Quantitative free tier."""
    try:
        import requests

        resp = requests.get(
            f"{_QUIVER_URL}/{symbol}",
            timeout=10,
            headers={"User-Agent": "jaja-money/1.0"},
        )
        resp.raise_for_status()
        items = resp.json()
        if not isinstance(items, list):
            return []

        trades = []
        for item in items:
            tx = str(item.get("Transaction", "")).lower()
            trades.append({
                "politician": item.get("Representative", ""),
                "trade_date": item.get("Date", ""),
                "transaction_type": "purchase" if "purchase" in tx or "buy" in tx else "sale",
                "amount_range": str(item.get("Range", item.get("Amount", ""))),
                "party": item.get("Party", ""),
                "chamber": item.get("Chamber", ""),
            })
        return trades
    except Exception as exc:
        log.debug("Quiver Quant fallback failed for %s: %s", symbol, exc)
        return []


def _save_trades(symbol: str, trades: list[dict]) -> None:
    if not trades:
        return
    now = int(time.time())
    symbol = symbol.upper()
    try:
        with _connect() as conn:
            cutoff = int((datetime.utcnow() - timedelta(days=1)).timestamp())
            conn.execute(
                "DELETE FROM congress_trades WHERE symbol=? AND fetched_at>?",
                (symbol, cutoff),
            )
            for t in trades:
                conn.execute(
                    """INSERT INTO congress_trades
                       (symbol, politician, trade_date, transaction_type,
                        amount_range, party, chamber, fetched_at)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (
                        symbol,
                        t.get("politician", ""),
                        t.get("trade_date", ""),
                        t.get("transaction_type", ""),
                        t.get("amount_range", ""),
                        t.get("party", ""),
                        t.get("chamber", ""),
                        now,
                    ),
                )
    except Exception as exc:
        log.warning("Failed to save congress trades for %s: %s", symbol, exc)


def _load_cached(symbol: str, max_age_seconds: int = 43200) -> list[dict] | None:
    symbol = symbol.upper()
    try:
        cutoff = int(time.time()) - max_age_seconds
        with _connect() as conn:
            rows = conn.execute(
                "SELECT * FROM congress_trades WHERE symbol=? AND fetched_at>? ORDER BY trade_date DESC",
                (symbol, cutoff),
            ).fetchall()
        if rows:
            return [dict(r) for r in rows]
    except Exception:
        pass
    return None


def fetch_congress_trades(symbol: str, lookback_days: int = 90) -> dict:
    """Fetch congressional trading data for a symbol.

    Returns
    -------
    dict with keys:
        available (bool)
        trades (list of dict): Each has politician, trade_date,
            transaction_type, amount_range, party, chamber.
        buys (int): Purchase count in lookback window.
        sells (int): Sale count in lookback window.
        net_signal (str): "Buying" | "Selling" | "Mixed" | "No activity"
        score (int): 0-100 alpha signal score.
        detail (str): Human-readable summary.
    """
    symbol = symbol.upper()

    cached = _load_cached(symbol)
    if cached is not None:
        trades = cached
    else:
        trades = _fetch_capitol_trades(symbol, days=lookback_days)
        if not trades:
            trades = _fetch_quiver_quant(symbol)
        _save_trades(symbol, trades)

    if not trades:
        return {
            "available": False,
            "trades": [],
            "buys": 0,
            "sells": 0,
            "net_signal": "No activity",
            "score": 50,
            "detail": "No congressional trading data found",
        }

    # Score based on recent 30-day activity
    cutoff_30d = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")
    recent = [t for t in trades if (t.get("trade_date") or "") >= cutoff_30d]

    all_buys = sum(1 for t in trades if "purchase" in str(t.get("transaction_type", "")).lower())
    all_sells = sum(1 for t in trades if "sale" in str(t.get("transaction_type", "")).lower())
    recent_buys = sum(1 for t in recent if "purchase" in str(t.get("transaction_type", "")).lower())
    recent_sells = sum(1 for t in recent if "sale" in str(t.get("transaction_type", "")).lower())

    if recent_buys > 0 and recent_sells == 0:
        score, net_signal = 80, "Buying"
    elif recent_buys > recent_sells and recent_buys > 0:
        score, net_signal = 70, "Buying"
    elif recent_sells > 0 and recent_buys == 0:
        score, net_signal = 22, "Selling"
    elif recent_sells > recent_buys and recent_sells > 0:
        score, net_signal = 30, "Selling"
    elif all_buys > all_sells:
        score, net_signal = 62, "Buying"
    elif all_sells > all_buys:
        score, net_signal = 38, "Selling"
    elif all_buys == 0 and all_sells == 0:
        score, net_signal = 50, "No activity"
    else:
        score, net_signal = 50, "Mixed"

    detail = (
        f"Congress activity (last {lookback_days}d): "
        f"{all_buys} buys, {all_sells} sells | "
        f"Last 30d: {recent_buys} buys, {recent_sells} sells"
    )

    return {
        "available": True,
        "trades": trades[:50],
        "buys": all_buys,
        "sells": all_sells,
        "net_signal": net_signal,
        "score": score,
        "detail": detail,
    }
