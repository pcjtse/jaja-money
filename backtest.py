"""Backtesting Engine (P3.2).

Validates the factor model's predictive power by simulating historical
trades based on price-derived signals (RSI, MACD, SMA trend) against
forward price returns.

Usage:
    from backtest import run_backtest, BacktestResult
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

from log_setup import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Signal computation (price-based only — no fundamental data for history)
# ---------------------------------------------------------------------------

def _compute_signal(close: pd.Series, index: int) -> int:
    """Compute a simplified signal score (0-100) at a given price history index.

    Uses: SMA trend (40%), RSI (30%), MACD (30%)
    Returns an integer 0-100.
    """
    if index < 35:
        return 50  # Not enough history

    slice_ = close.iloc[:index + 1]
    n = len(slice_)

    # SMA trend
    sma_score = 50
    if n >= 50:
        sma50 = float(slice_.rolling(50).mean().iloc[-1])
        sma200 = float(slice_.rolling(200).mean().iloc[-1]) if n >= 200 else None
        price = float(slice_.iloc[-1])
        if sma200 is not None:
            if price > sma50 > sma200:
                sma_score = 90
            elif price < sma50 < sma200:
                sma_score = 10
            else:
                sma_score = 50
        else:
            sma_score = 70 if price > sma50 else 30

    # RSI
    rsi_score = 50
    if n >= 15:
        delta = slice_.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1/14, min_periods=14).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=14).mean()
        rs = avg_gain / avg_loss
        rsi = float((100 - 100/(1+rs)).iloc[-1])
        if not math.isnan(rsi):
            rsi_score = int(max(0, min(100, 100 - abs(rsi - 50) * 0.5)))

    # MACD
    macd_score = 50
    if n >= 36:
        ema12 = slice_.ewm(span=12, adjust=False).mean()
        ema26 = slice_.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        sig = macd_line.ewm(span=9, adjust=False).mean()
        hist = macd_line - sig
        h_now = float(hist.iloc[-1])
        h_prev = float(hist.iloc[-2])
        if h_now > 0 and h_now > h_prev:
            macd_score = 85
        elif h_now > 0:
            macd_score = 65
        elif h_now <= 0 and h_now > h_prev:
            macd_score = 40
        else:
            macd_score = 15

    return int(0.40 * sma_score + 0.30 * rsi_score + 0.30 * macd_score)


# ---------------------------------------------------------------------------
# Trade record
# ---------------------------------------------------------------------------

@dataclass
class Trade:
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    pnl_pct: float
    signal_at_entry: int
    is_win: bool


# ---------------------------------------------------------------------------
# Backtest result
# ---------------------------------------------------------------------------

@dataclass
class BacktestResult:
    symbol: str
    start_date: str
    end_date: str
    entry_threshold: int
    exit_threshold: int
    total_return_pct: float
    benchmark_return_pct: float
    cagr_pct: float
    sharpe_ratio: float | None
    max_drawdown_pct: float
    win_rate_pct: float
    total_trades: int
    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)
    equity_dates: list[str] = field(default_factory=list)
    benchmark_curve: list[float] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Core backtester
# ---------------------------------------------------------------------------

def run_backtest(
    df: pd.DataFrame,
    symbol: str,
    entry_threshold: int = 65,
    exit_threshold: int = 40,
    lookback_years: float = 2.0,
) -> BacktestResult:
    """Run a signal-based backtest.

    Parameters
    ----------
    df               : DataFrame with Date, Close columns (full history)
    symbol           : ticker symbol for labeling
    entry_threshold  : Buy when signal score >= this value
    exit_threshold   : Sell when signal score <= this value
    lookback_years   : Only backtest the last N years of data

    Returns
    -------
    BacktestResult with performance metrics and equity curve.
    """
    if df is None or len(df) < 60:
        raise ValueError("Insufficient price history for backtesting (need 60+ days)")

    df = df.sort_values("Date").reset_index(drop=True).copy()

    # Restrict to lookback window
    cutoff = df["Date"].max() - pd.Timedelta(days=int(lookback_years * 365))
    df_back = df[df["Date"] >= cutoff].reset_index(drop=True)

    if len(df_back) < 40:
        raise ValueError("Not enough data in the requested lookback window")

    close = df_back["Close"]
    dates = df_back["Date"].dt.strftime("%Y-%m-%d").tolist()
    prices = close.tolist()
    n = len(prices)

    # Build signal series
    signals = []
    for i in range(n):
        # Use the full history up to this point for signal computation
        # Find the index in the full df
        row_date = df_back["Date"].iloc[i]
        full_idx = df[df["Date"] <= row_date].index[-1]
        sig = _compute_signal(df["Close"], full_idx)
        signals.append(sig)

    # Simulate trades
    in_position = False
    entry_price = 0.0
    entry_date = ""
    entry_signal = 0
    trades: list[Trade] = []
    equity = [1.0]
    equity_dates = [dates[0]] if dates else []
    position_mult = 1.0

    for i in range(1, n):
        s = signals[i]
        p = prices[i]
        d = dates[i]

        if not in_position:
            if s >= entry_threshold:
                in_position = True
                entry_price = p
                entry_date = d
                entry_signal = s
        else:
            if s <= exit_threshold:
                pnl_pct = (p - entry_price) / entry_price * 100
                trade = Trade(
                    entry_date=entry_date,
                    exit_date=d,
                    entry_price=round(entry_price, 2),
                    exit_price=round(p, 2),
                    pnl_pct=round(pnl_pct, 2),
                    signal_at_entry=entry_signal,
                    is_win=pnl_pct > 0,
                )
                trades.append(trade)
                position_mult *= (1 + pnl_pct / 100)
                in_position = False

        equity.append(position_mult)
        equity_dates.append(d)

    # Close open position at last price
    if in_position and n > 0:
        pnl_pct = (prices[-1] - entry_price) / entry_price * 100
        trades.append(Trade(
            entry_date=entry_date,
            exit_date=dates[-1],
            entry_price=round(entry_price, 2),
            exit_price=round(prices[-1], 2),
            pnl_pct=round(pnl_pct, 2),
            signal_at_entry=entry_signal,
            is_win=pnl_pct > 0,
        ))
        position_mult *= (1 + pnl_pct / 100)
        equity[-1] = position_mult

    # Metrics
    total_return_pct = (position_mult - 1) * 100
    benchmark_return_pct = ((prices[-1] / prices[0]) - 1) * 100 if prices[0] > 0 else 0
    benchmark_curve = [prices[i] / prices[0] for i in range(n)]

    days = n
    years = days / 252
    cagr_pct = ((position_mult ** (1 / years)) - 1) * 100 if years > 0 and position_mult > 0 else 0

    # Sharpe (simplified: daily returns)
    sharpe = None
    if len(equity) > 2:
        eq_series = pd.Series(equity)
        daily_rets = eq_series.pct_change().dropna()
        if len(daily_rets) > 1 and daily_rets.std() > 0:
            sharpe = round(float(daily_rets.mean() / daily_rets.std() * math.sqrt(252)), 2)

    # Max drawdown
    peak = 1.0
    max_dd = 0.0
    for e in equity:
        if e > peak:
            peak = e
        dd = (peak - e) / peak * 100
        if dd > max_dd:
            max_dd = dd

    win_count = sum(1 for t in trades if t.is_win)
    win_rate = (win_count / len(trades) * 100) if trades else 0

    return BacktestResult(
        symbol=symbol,
        start_date=dates[0] if dates else "",
        end_date=dates[-1] if dates else "",
        entry_threshold=entry_threshold,
        exit_threshold=exit_threshold,
        total_return_pct=round(total_return_pct, 2),
        benchmark_return_pct=round(benchmark_return_pct, 2),
        cagr_pct=round(cagr_pct, 2),
        sharpe_ratio=sharpe,
        max_drawdown_pct=round(max_dd, 2),
        win_rate_pct=round(win_rate, 1),
        total_trades=len(trades),
        trades=trades,
        equity_curve=equity,
        equity_dates=equity_dates,
        benchmark_curve=benchmark_curve,
    )
