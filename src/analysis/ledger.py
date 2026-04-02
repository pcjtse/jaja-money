"""Signal Ledger — tamper-evident JSON trade record.

A live, committed JSON file (data/ledger.json) that accumulates buy signals
and their outcomes. Committed to GitHub — the commit history provides a
timestamped audit trail that cannot be retroactively modified.

T+5/T+10/T+30 are calendar-day prices stored in the ledger JSON at close time.
These are intentionally SEPARATE from signal_returns (T+21/T+63/T+126 trading days).
Do NOT merge these two systems: ledger tracks trade P&L; signal_returns tracks factor IC.

Usage:
    from src.analysis.ledger import add_signal, close_position, get_open_positions
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.core.log_setup import get_logger

log = get_logger(__name__)

_LEDGER_PATH = Path("data/ledger.json")
_TMP_PATH = Path("data/ledger.json.tmp")


# ---------------------------------------------------------------------------
# Internal I/O helpers
# ---------------------------------------------------------------------------


def _load() -> list[dict]:
    """Load ledger JSON from disk. Returns [] if file does not exist."""
    if not _LEDGER_PATH.exists():
        return []
    try:
        return json.loads(_LEDGER_PATH.read_text())
    except Exception as exc:
        log.error("Failed to load ledger.json: %s", exc)
        return []


def _save(signals: list[dict]) -> None:
    """Atomically write signals list to data/ledger.json via tmp → rename."""
    _LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    _TMP_PATH.write_text(json.dumps(signals, indent=2))
    _TMP_PATH.rename(_LEDGER_PATH)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def add_signal(
    ticker: str,
    composite_score: float,
    factor_scores: dict[str, float],
    price: float,
    spy_price: float,
    direction: str = "long",
) -> str:
    """Append a new open signal to the ledger. Returns the new signal_id.

    Raises ValueError if ticker already has an open position (duplicate guard).
    """
    signals = _load()

    # Duplicate guard — one open position per ticker
    for s in signals:
        if s["ticker"] == ticker and s["status"] == "open":
            raise ValueError(
                f"Duplicate signal: {ticker} already has an open position "
                f"(signal_id={s['signal_id']})"
            )

    signal_id = str(uuid.uuid4())
    entry: dict = {
        "signal_id": signal_id,
        "ticker": ticker,
        "fired_at": datetime.now(timezone.utc).isoformat(),
        "composite_score": float(composite_score),
        "factor_scores": {k: float(v) for k, v in factor_scores.items()},
        "price_at_signal": float(price),
        "spy_entry_price": float(spy_price),
        "direction": direction,
        "status": "open",
        "exit_price": None,
        "exit_at": None,
        "pnl_pct": None,
        "spy_pnl_pct": None,
        "price_t5": None,
        "price_t10": None,
        "price_t30": None,
    }
    signals.append(entry)
    _save(signals)
    log.info("Signal added: %s %s composite=%.1f", ticker, signal_id[:8], composite_score)
    return signal_id


def close_position(
    signal_id: str,
    exit_price: float,
    spy_exit_price: float,
    price_t5: float | None,
    price_t10: float | None,
    price_t30: float | None,
) -> None:
    """Close an open position and record exit prices and P&L.

    price_t5/t10/t30 may be None if the Finnhub lookup failed — that's OK.
    Never block a close on API failure.

    Raises ValueError if signal_id is not found or is already closed.
    """
    signals = _load()

    for s in signals:
        if s["signal_id"] == signal_id:
            if s["status"] == "closed":
                raise ValueError(f"Position {signal_id[:8]} is already closed")
            entry_price = float(s["price_at_signal"])
            spy_entry = float(s["spy_entry_price"])

            pnl_pct = (
                ((float(exit_price) - entry_price) / entry_price * 100)
                if entry_price > 0
                else None
            )
            spy_pnl_pct = (
                ((float(spy_exit_price) - spy_entry) / spy_entry * 100)
                if spy_entry > 0
                else None
            )

            s["status"] = "closed"
            s["exit_price"] = float(exit_price)
            s["exit_at"] = datetime.now(timezone.utc).isoformat()
            s["pnl_pct"] = round(pnl_pct, 4) if pnl_pct is not None else None
            s["spy_pnl_pct"] = round(spy_pnl_pct, 4) if spy_pnl_pct is not None else None
            s["price_t5"] = float(price_t5) if price_t5 is not None else None
            s["price_t10"] = float(price_t10) if price_t10 is not None else None
            s["price_t30"] = float(price_t30) if price_t30 is not None else None

            _save(signals)
            log.info(
                "Position closed: %s pnl=%.2f%% vs SPY=%.2f%%",
                signal_id[:8],
                pnl_pct or 0.0,
                spy_pnl_pct or 0.0,
            )
            return

    raise ValueError(f"Signal {signal_id} not found in ledger")


def get_open_positions() -> list[dict]:
    """Return all signals with status='open'."""
    return [s for s in _load() if s["status"] == "open"]


def get_closed_positions() -> list[dict]:
    """Return all signals with status='closed'."""
    return [s for s in _load() if s["status"] == "closed"]


def get_all_signals() -> list[dict]:
    """Return all signals (open and closed)."""
    return _load()
