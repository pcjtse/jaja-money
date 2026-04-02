"""Signal Decay Analysis — per-factor win rate at T+5/T+10/T+30.

Reads closed positions from data/ledger.json and computes, for each factor
group, the win rate (exit_price > price_at_signal) using the pre-stored
calendar-day prices (price_t5, price_t10, price_t30).

The "leading factor" for a position is the factor with the highest score
above 50 (argmax of max(score - 50, 0)). This is computed at analysis time
and NOT stored in the ledger — the ledger stores raw factor scores only.

Usage:
    from src.analysis.signal_decay import get_signal_decay_table

    df = get_signal_decay_table(min_n=5)
    # Columns: factor, n, win_t5, win_t10, win_t30, sufficient
    # win_tX is None when n < min_n
"""

from __future__ import annotations

import pandas as pd

from src.core.log_setup import get_logger

log = get_logger(__name__)

# Factor display names (subset of ALL_FACTOR_NAMES — only scores stored in ledger)
# The ledger stores factor_scores as {display_name: score}
_CORE_FACTOR_DISPLAY = [
    "Valuation (P/E)",
    "Trend (SMA)",
    "Momentum (RSI)",
    "MACD Signal",
    "News Sentiment",
    "Earnings Quality",
    "Analyst Consensus",
    "52-Wk Strength",
]

_ALPHA_FACTOR_DISPLAY = [
    "Dividend Yield",
    "Estimate Revisions",
    "Alt Data Signal",
    "Congress Signal",
    "Institutional Flow",
    "Estimate Velocity",
    "Buyback Effectiveness",
    "Guidance Quality",
    "Options Flow",
    "Dark Pool Signal",
    "Supply Chain Risk",
    "Special Situation",
    "Cross-Asset Signal",
    "Geo Revenue Macro",
    "Market Regime",
]

ALL_FACTOR_DISPLAY = _CORE_FACTOR_DISPLAY + _ALPHA_FACTOR_DISPLAY


# ---------------------------------------------------------------------------
# Leading factor computation
# ---------------------------------------------------------------------------


def get_leading_factor(factor_scores: dict[str, float]) -> str:
    """Return the display name of the factor with the highest score above 50.

    Uses argmax(max(score - 50, 0)) across all factor_scores.
    Returns "none" if all scores are <= 50.
    """
    best_name = "none"
    best_val = 0.0
    for name, score in factor_scores.items():
        above = max(float(score) - 50.0, 0.0)
        if above > best_val:
            best_val = above
            best_name = name
    return best_name


# ---------------------------------------------------------------------------
# Win rate computation
# ---------------------------------------------------------------------------


def get_signal_decay_table(min_n: int = 5) -> pd.DataFrame:
    """Compute per-factor win rate at T+5/T+10/T+30 from closed positions.

    Win = exit_price > price_at_signal (simple price-based win, not P&L%).
    T+5/T+10/T+30 prices come from price_t5/price_t10/price_t30 stored in
    the ledger JSON at close time.

    Returns a DataFrame with columns:
        factor     — display name
        n          — number of closed positions where this was the leading factor
        win_t5     — win rate (0-1) at T+5, or None if n < min_n
        win_t10    — win rate (0-1) at T+10, or None if n < min_n
        win_t30    — win rate (0-1) at T+30, or None if n < min_n
        sufficient — True if n >= min_n
    """
    from src.analysis.ledger import get_closed_positions

    closed = get_closed_positions()
    if not closed:
        return _empty_table()

    # Group by leading factor
    factor_data: dict[str, list[dict]] = {f: [] for f in ALL_FACTOR_DISPLAY}
    factor_data["none"] = []

    for pos in closed:
        factor_scores = pos.get("factor_scores") or {}
        if not factor_scores:
            continue
        leading = get_leading_factor(factor_scores)
        entry_price = float(pos.get("price_at_signal") or 0)
        if entry_price <= 0:
            continue

        record = {
            "entry": entry_price,
            "t5": pos.get("price_t5"),
            "t10": pos.get("price_t10"),
            "t30": pos.get("price_t30"),
        }

        if leading in factor_data:
            factor_data[leading].append(record)
        else:
            factor_data.setdefault(leading, []).append(record)

    rows = []
    for factor in ALL_FACTOR_DISPLAY:
        positions = factor_data.get(factor, [])
        n = len(positions)
        sufficient = n >= min_n

        def _win_rate(price_key: str) -> float | None:
            if not sufficient:
                return None
            valid = [
                p for p in positions if p[price_key] is not None and p["entry"] > 0
            ]
            if not valid:
                return None
            wins = sum(1 for p in valid if float(p[price_key]) > p["entry"])
            return wins / len(valid)

        rows.append(
            {
                "factor": factor,
                "n": n,
                "win_t5": _win_rate("t5"),
                "win_t10": _win_rate("t10"),
                "win_t30": _win_rate("t30"),
                "sufficient": sufficient,
            }
        )

    return pd.DataFrame(rows)


def _empty_table() -> pd.DataFrame:
    rows = [
        {
            "factor": f,
            "n": 0,
            "win_t5": None,
            "win_t10": None,
            "win_t30": None,
            "sufficient": False,
        }
        for f in ALL_FACTOR_DISPLAY
    ]
    return pd.DataFrame(rows)
