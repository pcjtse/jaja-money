"""Forward testing module for paper portfolio management (P22.1).

Provides SQLite-backed paper portfolios for tracking AI-recommended stocks
without risking real capital.

Usage:
    from src.analysis.forward_test import (
        create_portfolio, add_position, close_position,
        get_portfolio_summary, snapshot_portfolio,
    )
"""

from __future__ import annotations

import math
from datetime import date, datetime

import src.data.history as _h
from src.core.log_setup import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Portfolio CRUD
# ---------------------------------------------------------------------------


def create_portfolio(name: str) -> int:
    """Create a new paper portfolio. Returns the portfolio ID."""
    today = date.today().isoformat()
    try:
        with _h._connect() as conn:
            cur = conn.execute(
                "INSERT INTO paper_portfolio (name, created_date) VALUES (?, ?)",
                (name, today),
            )
            portfolio_id = cur.lastrowid
        log.info("Created paper portfolio %r (id=%d)", name, portfolio_id)
        return portfolio_id
    except Exception as exc:
        log.error("Failed to create portfolio %r: %s", name, exc)
        raise


def list_portfolios() -> list[dict]:
    """Return all paper portfolios ordered by id."""
    try:
        with _h._connect() as conn:
            rows = conn.execute(
                "SELECT id, name, created_date FROM paper_portfolio ORDER BY id"
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as exc:
        log.warning("Failed to list portfolios: %s", exc)
        return []


def rename_portfolio(portfolio_id: int, new_name: str) -> bool:
    """Rename a portfolio. Returns True on success."""
    try:
        with _h._connect() as conn:
            conn.execute(
                "UPDATE paper_portfolio SET name=? WHERE id=?",
                (new_name, portfolio_id),
            )
        return True
    except Exception as exc:
        log.warning("Failed to rename portfolio %d: %s", portfolio_id, exc)
        return False


def delete_portfolio(portfolio_id: int) -> bool:
    """Delete a portfolio and all its trades and history. Returns True on success."""
    try:
        with _h._connect() as conn:
            conn.execute(
                "DELETE FROM paper_portfolio_history WHERE portfolio_id=?",
                (portfolio_id,),
            )
            conn.execute(
                "DELETE FROM paper_trades WHERE portfolio_id=?", (portfolio_id,)
            )
            conn.execute("DELETE FROM paper_portfolio WHERE id=?", (portfolio_id,))
        log.info("Deleted paper portfolio %d", portfolio_id)
        return True
    except Exception as exc:
        log.warning("Failed to delete portfolio %d: %s", portfolio_id, exc)
        return False


# ---------------------------------------------------------------------------
# Position management
# ---------------------------------------------------------------------------


def add_position(
    portfolio_id: int,
    symbol: str,
    entry_price: float,
    factor_score: int | None = None,
    risk_score: int | None = None,
    shares: float = 1.0,
) -> int:
    """Add a new open position to a portfolio. Returns the trade ID."""
    today = date.today().isoformat()
    symbol = symbol.upper()
    try:
        with _h._connect() as conn:
            cur = conn.execute(
                """INSERT INTO paper_trades
                   (portfolio_id, symbol, entry_price, entry_date,
                    factor_score_entry, risk_score_entry, shares)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    portfolio_id,
                    symbol,
                    entry_price,
                    today,
                    factor_score,
                    risk_score,
                    shares,
                ),
            )
            trade_id = cur.lastrowid
        log.info(
            "Added position %s @ %.2f to portfolio %d (trade_id=%d)",
            symbol,
            entry_price,
            portfolio_id,
            trade_id,
        )
        return trade_id
    except Exception as exc:
        log.error(
            "Failed to add position %s to portfolio %d: %s",
            symbol,
            portfolio_id,
            exc,
        )
        raise


def close_position(trade_id: int, exit_price: float) -> bool:
    """Close an open position at the given exit price. Returns True on success."""
    today = date.today().isoformat()
    try:
        with _h._connect() as conn:
            conn.execute(
                """UPDATE paper_trades
                   SET exit_price=?, exit_date=?
                   WHERE id=? AND exit_date IS NULL""",
                (exit_price, today, trade_id),
            )
        log.info("Closed trade %d at %.2f", trade_id, exit_price)
        return True
    except Exception as exc:
        log.warning("Failed to close trade %d: %s", trade_id, exc)
        return False


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------


def get_open_positions(portfolio_id: int) -> list[dict]:
    """Return all open (not yet closed) positions for a portfolio."""
    try:
        with _h._connect() as conn:
            rows = conn.execute(
                """SELECT id, symbol, entry_price, entry_date,
                          factor_score_entry, risk_score_entry, shares
                   FROM paper_trades
                   WHERE portfolio_id=? AND exit_date IS NULL
                   ORDER BY entry_date ASC""",
                (portfolio_id,),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as exc:
        log.warning(
            "Failed to get open positions for portfolio %d: %s", portfolio_id, exc
        )
        return []


def get_closed_trades(portfolio_id: int) -> list[dict]:
    """Return all closed trades for a portfolio, newest first.

    Each row includes a ``pnl_pct`` key with the realised P&L percentage.
    """
    try:
        with _h._connect() as conn:
            rows = conn.execute(
                """SELECT id, symbol, entry_price, entry_date,
                          exit_price, exit_date,
                          factor_score_entry, risk_score_entry, shares
                   FROM paper_trades
                   WHERE portfolio_id=? AND exit_date IS NOT NULL
                   ORDER BY exit_date DESC""",
                (portfolio_id,),
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            if d["entry_price"] and d["exit_price"] and d["entry_price"] != 0:
                d["pnl_pct"] = (
                    (d["exit_price"] - d["entry_price"]) / d["entry_price"] * 100
                )
            else:
                d["pnl_pct"] = 0.0
            result.append(d)
        return result
    except Exception as exc:
        log.warning(
            "Failed to get closed trades for portfolio %d: %s", portfolio_id, exc
        )
        return []


# ---------------------------------------------------------------------------
# Equity curve / snapshots
# ---------------------------------------------------------------------------


def snapshot_portfolio(
    portfolio_id: int,
    current_prices: dict[str, float],
) -> None:
    """Record today's portfolio valuation to the history table.

    Parameters
    ----------
    portfolio_id:
        The portfolio to snapshot.
    current_prices:
        Mapping of ticker symbol → current market price.  Positions whose
        symbol is missing from the map fall back to entry price.
    """
    today = date.today().isoformat()
    positions = get_open_positions(portfolio_id)
    total_value = sum(
        current_prices.get(p["symbol"], p["entry_price"]) * p["shares"]
        for p in positions
    )
    try:
        with _h._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO paper_portfolio_history
                   (portfolio_id, date, total_value) VALUES (?, ?, ?)""",
                (portfolio_id, today, total_value),
            )
        log.info(
            "Snapshotted portfolio %d on %s: total_value=%.2f",
            portfolio_id,
            today,
            total_value,
        )
    except Exception as exc:
        log.warning("Failed to snapshot portfolio %d: %s", portfolio_id, exc)


def get_equity_curve(portfolio_id: int) -> list[dict]:
    """Return the daily equity curve for a portfolio, oldest first.

    Each entry has keys ``date`` (ISO string) and ``total_value`` (float).
    """
    try:
        with _h._connect() as conn:
            rows = conn.execute(
                """SELECT date, total_value FROM paper_portfolio_history
                   WHERE portfolio_id=? ORDER BY date ASC""",
                (portfolio_id,),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as exc:
        log.warning(
            "Failed to get equity curve for portfolio %d: %s", portfolio_id, exc
        )
        return []


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


def _calc_stats(
    equity_curve: list[dict],
    closed_trades: list[dict],
) -> dict:
    """Compute summary statistics for a paper portfolio.

    Parameters
    ----------
    equity_curve:
        List of ``{date, total_value}`` dicts ordered oldest first.
    closed_trades:
        List of closed trade dicts each containing ``pnl_pct``.

    Returns
    -------
    dict with keys: total_return_pct, annualized_return_pct, sharpe_ratio,
    max_drawdown_pct, win_rate_pct, trade_count.
    """
    stats: dict = {
        "total_return_pct": 0.0,
        "annualized_return_pct": 0.0,
        "sharpe_ratio": None,
        "max_drawdown_pct": 0.0,
        "win_rate_pct": None,
        "trade_count": len(closed_trades),
    }

    if not equity_curve or len(equity_curve) < 2:
        return stats

    values = [r["total_value"] for r in equity_curve]
    if values[0] == 0:
        return stats

    # Total return
    stats["total_return_pct"] = round((values[-1] - values[0]) / values[0] * 100, 2)

    # Annualised return
    n_days = max(
        (
            datetime.fromisoformat(equity_curve[-1]["date"])
            - datetime.fromisoformat(equity_curve[0]["date"])
        ).days,
        1,
    )
    ann_return = (((values[-1] / values[0]) ** (365 / n_days)) - 1) * 100
    stats["annualized_return_pct"] = round(ann_return, 2)

    # Daily returns for Sharpe ratio
    daily_returns = [
        (values[i] - values[i - 1]) / values[i - 1]
        for i in range(1, len(values))
        if values[i - 1] != 0
    ]
    if len(daily_returns) >= 2:
        mean_ret = sum(daily_returns) / len(daily_returns)
        variance = sum((r - mean_ret) ** 2 for r in daily_returns) / (
            len(daily_returns) - 1
        )
        std_ret = math.sqrt(variance) if variance > 0 else 0
        if std_ret > 0:
            stats["sharpe_ratio"] = round((mean_ret / std_ret) * math.sqrt(252), 2)

    # Max drawdown
    peak = values[0]
    max_dd = 0.0
    for v in values:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (peak - v) / peak * 100
            if dd > max_dd:
                max_dd = dd
    stats["max_drawdown_pct"] = round(max_dd, 2)

    # Win rate
    if closed_trades:
        wins = sum(1 for t in closed_trades if t.get("pnl_pct", 0) > 0)
        stats["win_rate_pct"] = round(wins / len(closed_trades) * 100, 1)

    return stats


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


def get_portfolio_summary(portfolio_id: int) -> dict:
    """Return a complete portfolio summary.

    Returns
    -------
    dict with keys: portfolio_id, name, open_positions, closed_trades,
    equity_curve, stats.
    """
    portfolios = list_portfolios()
    name = next((p["name"] for p in portfolios if p["id"] == portfolio_id), "Unknown")
    open_positions = get_open_positions(portfolio_id)
    closed_trades = get_closed_trades(portfolio_id)
    equity_curve = get_equity_curve(portfolio_id)
    stats = _calc_stats(equity_curve, closed_trades)

    return {
        "portfolio_id": portfolio_id,
        "name": name,
        "open_positions": open_positions,
        "closed_trades": closed_trades,
        "equity_curve": equity_curve,
        "stats": stats,
    }
