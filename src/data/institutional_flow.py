"""13F Institutional Holdings QoQ Change Tracker.

Extends basic institutional ownership to track quarter-over-quarter
changes in holdings — which institutions are entering, exiting, and
the net change in total institutional ownership percentage.
"""

from __future__ import annotations

import sqlite3
import time
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


def _ensure_institutional_table() -> None:
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS institutional_snapshots (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol              TEXT NOT NULL,
                snapshot_date       TEXT NOT NULL,
                holder              TEXT NOT NULL,
                shares              INTEGER,
                pct_held            REAL,
                fetched_at          INTEGER,
                UNIQUE(symbol, snapshot_date, holder)
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_inst_symbol_date "
            "ON institutional_snapshots (symbol, snapshot_date)"
        )


_ensure_institutional_table()


def _save_snapshot(symbol: str, holders: list[dict]) -> None:
    if not holders:
        return
    from datetime import datetime

    today = datetime.utcnow().strftime("%Y-%m-%d")
    now = int(time.time())
    symbol = symbol.upper()
    try:
        with _connect() as conn:
            for h in holders:
                conn.execute(
                    """INSERT OR REPLACE INTO institutional_snapshots
                       (symbol, snapshot_date, holder, shares, pct_held, fetched_at)
                       VALUES (?,?,?,?,?,?)""",
                    (
                        symbol,
                        today,
                        h.get("holder", ""),
                        int(h.get("shares", 0) or 0),
                        float(h.get("pct_held", 0) or 0),
                        now,
                    ),
                )
    except Exception as exc:
        log.warning("Failed to save institutional snapshot for %s: %s", symbol, exc)


def _load_snapshots(symbol: str, limit_dates: int = 2) -> dict[str, list[dict]]:
    """Return latest `limit_dates` distinct snapshot dates with their holders."""
    symbol = symbol.upper()
    try:
        with _connect() as conn:
            dates = conn.execute(
                """SELECT DISTINCT snapshot_date FROM institutional_snapshots
                   WHERE symbol=? ORDER BY snapshot_date DESC LIMIT ?""",
                (symbol, limit_dates),
            ).fetchall()
            result = {}
            for row in dates:
                date = row["snapshot_date"]
                rows = conn.execute(
                    "SELECT * FROM institutional_snapshots WHERE symbol=? AND snapshot_date=?",
                    (symbol, date),
                ).fetchall()
                result[date] = [dict(r) for r in rows]
        return result
    except Exception:
        return {}


def fetch_13f_changes(symbol: str) -> dict:
    """Fetch 13F institutional holding changes for a symbol.

    Compares current holdings against the most recent stored snapshot
    to compute QoQ changes.

    Returns
    -------
    dict with keys:
        available (bool)
        current_holders (list of dict)
        entering (list of str): New institutions not in prior snapshot.
        exiting (list of str): Institutions gone from prior snapshot.
        net_change_pct (float): Change in total institutional pct.
        top_movers (list of dict): Largest share-count changes.
        score (int): 0-100 smart-money flow signal.
        detail (str)
    """
    symbol = symbol.upper()

    current_holders = []
    try:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        df = ticker.institutional_holders
        if df is not None and not df.empty:
            for _, row in df.iterrows():
                holder_name = str(row.get("Holder", row.get("holder", "")))
                shares = int(row.get("Shares", row.get("shares", 0)) or 0)
                pct_raw = row.get("% Out", row.get("pctHeld", row.get("pct_held", None)))
                pct = 0.0
                if pct_raw is not None:
                    try:
                        pct_val = float(pct_raw)
                        pct = pct_val * 100 if pct_val < 1.0 else pct_val
                    except (TypeError, ValueError):
                        pct = 0.0
                current_holders.append({"holder": holder_name, "shares": shares, "pct_held": round(pct, 4)})
    except Exception as exc:
        log.warning("13F yfinance fetch failed for %s: %s", symbol, exc)

    if not current_holders:
        return {
            "available": False,
            "current_holders": [],
            "entering": [],
            "exiting": [],
            "net_change_pct": 0.0,
            "top_movers": [],
            "score": 50,
            "detail": "Institutional holdings data unavailable",
        }

    _save_snapshot(symbol, current_holders)

    snapshots = _load_snapshots(symbol, limit_dates=2)
    dates = sorted(snapshots.keys(), reverse=True)

    entering: list[str] = []
    exiting: list[str] = []
    top_movers: list[dict] = []
    net_change_pct = 0.0

    if len(dates) >= 2:
        current_date, prev_date = dates[0], dates[1]
        current_map = {r["holder"]: r for r in snapshots[current_date]}
        prev_map = {r["holder"]: r for r in snapshots[prev_date]}

        entering = [h for h in current_map if h not in prev_map]
        exiting = [h for h in prev_map if h not in current_map]

        current_total = sum(r["pct_held"] for r in snapshots[current_date])
        prev_total = sum(r["pct_held"] for r in snapshots[prev_date])
        net_change_pct = round(current_total - prev_total, 4)

        movers = []
        for holder, curr in current_map.items():
            if holder in prev_map:
                delta = curr["shares"] - prev_map[holder]["shares"]
                if delta != 0:
                    movers.append({"holder": holder, "share_delta": delta})
        movers.sort(key=lambda x: abs(x["share_delta"]), reverse=True)
        top_movers = movers[:10]

    # Score: positive net_change and new entrants = bullish
    if len(entering) >= 2 or net_change_pct > 1.0:
        score = 78
    elif len(entering) >= 1 or net_change_pct > 0:
        score = 65
    elif len(exiting) >= 2 or net_change_pct < -1.0:
        score = 28
    elif len(exiting) >= 1 or net_change_pct < 0:
        score = 38
    else:
        score = 52

    detail = (
        f"Institutional flow: {len(entering)} new entrants, {len(exiting)} exits | "
        f"Net ownership change: {net_change_pct:+.2f}%"
    )

    return {
        "available": True,
        "current_holders": current_holders,
        "entering": entering,
        "exiting": exiting,
        "net_change_pct": net_change_pct,
        "top_movers": top_movers,
        "score": score,
        "detail": detail,
    }
