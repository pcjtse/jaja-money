"""Pairs Trading / Statistical Arbitrage (21.1).

Tracks the price spread between two correlated stocks and signals when
the z-score of the log-ratio spread diverges beyond ±2σ (mean reversion).

Usage:
    from pairs import compute_spread, compute_zscore, pairs_signal, backtest_pairs
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import pandas as pd

from log_setup import get_logger

log = get_logger(__name__)

# Default thresholds
DEFAULT_ENTRY_ZSCORE = 2.0
DEFAULT_EXIT_ZSCORE = 0.5
DEFAULT_LOOKBACK_WINDOW = 60


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class PairsTrade:
    entry_date: str
    exit_date: str
    direction: str        # "long_A_short_B" | "long_B_short_A"
    entry_zscore: float
    exit_zscore: float
    pnl_pct: float
    is_win: bool


@dataclass
class PairsBacktestResult:
    symbol_a: str
    symbol_b: str
    lookback_window: int
    entry_zscore: float
    exit_zscore: float
    start_date: str
    end_date: str
    total_trades: int
    win_rate_pct: float
    total_return_pct: float
    sharpe_ratio: float | None
    max_drawdown_pct: float
    correlation: float | None
    trades: list[PairsTrade] = field(default_factory=list)
    spread_series: list[float] = field(default_factory=list)
    zscore_series: list[float] = field(default_factory=list)
    dates: list[str] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Core analytics
# ---------------------------------------------------------------------------

def compute_spread(close_a: pd.Series, close_b: pd.Series) -> pd.Series:
    """Compute the log-price-ratio spread between two stocks.

    Uses log(A/B), which is stationary when the pair is cointegrated.
    Both series are aligned by their shared index before computation.
    """
    aligned = pd.DataFrame({"a": close_a, "b": close_b}).dropna()
    if len(aligned) < 2:
        return pd.Series(dtype=float)
    ratio = aligned["a"] / aligned["b"]
    ratio = ratio[ratio > 0]
    return ratio.apply(math.log)


def compute_zscore(spread: pd.Series, window: int = DEFAULT_LOOKBACK_WINDOW) -> pd.Series:
    """Compute rolling z-score of the spread.

    z = (spread - rolling_mean) / rolling_std
    Values within the first `window` bars will be NaN.
    """
    if spread is None or len(spread) < window:
        return pd.Series(dtype=float)
    mean = spread.rolling(window=window).mean()
    std = spread.rolling(window=window).std().replace(0, float("nan"))
    return (spread - mean) / std


def compute_pair_correlation(close_a: pd.Series, close_b: pd.Series) -> float | None:
    """Return Pearson correlation of daily returns between two stocks."""
    aligned = pd.DataFrame({"a": close_a, "b": close_b}).dropna()
    if len(aligned) < 20:
        return None
    ret_a = aligned["a"].pct_change().dropna()
    ret_b = aligned["b"].pct_change().dropna()
    if len(ret_a) < 10 or ret_a.std() == 0 or ret_b.std() == 0:
        return None
    corr = float(ret_a.corr(ret_b))
    return round(corr, 3) if not math.isnan(corr) else None


def pairs_signal(
    zscore: float | None,
    entry_threshold: float = DEFAULT_ENTRY_ZSCORE,
    exit_threshold: float = DEFAULT_EXIT_ZSCORE,
) -> str:
    """Derive a trading signal from the current z-score.

    Returns
    -------
    "long_A_short_B"  : spread unusually low → A cheap relative to B
    "long_B_short_A"  : spread unusually high → A expensive relative to B
    "exit"            : z-score near zero → take profits / close position
    "neutral"         : no actionable signal
    """
    if zscore is None or math.isnan(zscore):
        return "neutral"
    if zscore <= -entry_threshold:
        return "long_A_short_B"
    if zscore >= entry_threshold:
        return "long_B_short_A"
    if abs(zscore) <= exit_threshold:
        return "exit"
    return "neutral"


# ---------------------------------------------------------------------------
# Backtester
# ---------------------------------------------------------------------------

def backtest_pairs(
    df_a: pd.DataFrame,
    df_b: pd.DataFrame,
    symbol_a: str,
    symbol_b: str,
    lookback_window: int = DEFAULT_LOOKBACK_WINDOW,
    entry_zscore: float = DEFAULT_ENTRY_ZSCORE,
    exit_zscore: float = DEFAULT_EXIT_ZSCORE,
    lookback_years: float = 2.0,
) -> PairsBacktestResult:
    """Backtest a pairs trading mean-reversion strategy.

    Parameters
    ----------
    df_a, df_b        : DataFrames with Date and Close columns
    symbol_a, symbol_b: ticker symbols for labelling
    lookback_window   : rolling window for z-score (trading days)
    entry_zscore      : |z| threshold to open a trade (default 2.0)
    exit_zscore       : |z| threshold to close a trade (default 0.5)
    lookback_years    : restrict backtest to the last N years of data

    Returns
    -------
    PairsBacktestResult with full trade log, equity curve, and summary stats.

    Notes
    -----
    P&L is approximated as the z-score mean reversion:
        pnl_pct ≈ (|entry_z| - |exit_z|) × 2.0
    This is a simplified proxy; a full implementation would track the
    individual leg P&Ls explicitly.
    """
    if df_a is None or df_b is None:
        raise ValueError("Both DataFrames are required")
    if len(df_a) < lookback_window + 10 or len(df_b) < lookback_window + 10:
        raise ValueError("Insufficient price history for pairs backtest")

    df_a = df_a.sort_values("Date").reset_index(drop=True)
    df_b = df_b.sort_values("Date").reset_index(drop=True)

    a = df_a.set_index("Date")["Close"]
    b = df_b.set_index("Date")["Close"]
    aligned = pd.DataFrame({"a": a, "b": b}).dropna().sort_index()

    cutoff = aligned.index.max() - pd.Timedelta(days=int(lookback_years * 365))
    aligned = aligned[aligned.index >= cutoff]

    if len(aligned) < lookback_window + 10:
        raise ValueError("Not enough overlapping price data in the lookback window")

    spread = compute_spread(aligned["a"], aligned["b"])
    spread.index = aligned.index
    zscore = compute_zscore(spread, lookback_window)
    correlation = compute_pair_correlation(aligned["a"], aligned["b"])

    dates = [d.strftime("%Y-%m-%d") for d in aligned.index]
    z_vals = zscore.tolist()
    s_vals = spread.tolist()

    # Simulate trades (expanding window — no look-ahead bias)
    in_position = False
    position_dir = ""
    entry_z = 0.0
    entry_date = ""
    trades: list[PairsTrade] = []
    eq_val = 1.0
    equity: list[float] = []

    for i in range(len(dates)):
        z = z_vals[i]
        if i < lookback_window or z is None or (isinstance(z, float) and math.isnan(z)):
            equity.append(eq_val)
            continue

        if not in_position:
            if z <= -entry_zscore:
                in_position = True
                position_dir = "long_A_short_B"
                entry_z = z
                entry_date = dates[i]
            elif z >= entry_zscore:
                in_position = True
                position_dir = "long_B_short_A"
                entry_z = z
                entry_date = dates[i]
        else:
            if abs(z) <= exit_zscore:
                # Approximate P&L: z-score reversal scaled to percent gain
                z_change = abs(entry_z) - abs(z)
                pnl_pct = z_change * 2.0  # simplified proxy
                is_win = pnl_pct > 0
                eq_val *= (1 + pnl_pct / 100)
                trades.append(PairsTrade(
                    entry_date=entry_date,
                    exit_date=dates[i],
                    direction=position_dir,
                    entry_zscore=round(entry_z, 3),
                    exit_zscore=round(z, 3),
                    pnl_pct=round(pnl_pct, 2),
                    is_win=is_win,
                ))
                in_position = False
                position_dir = ""

        equity.append(eq_val)

    # Summary metrics
    total_return_pct = (eq_val - 1) * 100
    win_count = sum(1 for t in trades if t.is_win)
    win_rate = (win_count / len(trades) * 100) if trades else 0.0

    sharpe = None
    if len(equity) > 2:
        eq_s = pd.Series(equity)
        daily_rets = eq_s.pct_change().dropna()
        if len(daily_rets) > 1 and daily_rets.std() > 0:
            sharpe = round(float(daily_rets.mean() / daily_rets.std() * math.sqrt(252)), 2)

    peak = 1.0
    max_dd = 0.0
    for e in equity:
        if e > peak:
            peak = e
        dd = (peak - e) / peak * 100
        if dd > max_dd:
            max_dd = dd

    log.info(
        "Pairs backtest %s/%s: %d trades, return=%.1f%%, sharpe=%s",
        symbol_a, symbol_b, len(trades), total_return_pct,
        f"{sharpe:.2f}" if sharpe else "N/A",
    )

    return PairsBacktestResult(
        symbol_a=symbol_a,
        symbol_b=symbol_b,
        lookback_window=lookback_window,
        entry_zscore=entry_zscore,
        exit_zscore=exit_zscore,
        start_date=dates[0] if dates else "",
        end_date=dates[-1] if dates else "",
        total_trades=len(trades),
        win_rate_pct=round(win_rate, 1),
        total_return_pct=round(total_return_pct, 2),
        sharpe_ratio=sharpe,
        max_drawdown_pct=round(max_dd, 2),
        correlation=correlation,
        trades=trades,
        spread_series=s_vals,
        zscore_series=z_vals,
        dates=dates,
        equity_curve=equity,
    )
