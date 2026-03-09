"""Backtesting Engine (P3.2 + P6.1 + P6.2 + P6.3).

Validates the factor model's predictive power by simulating historical
trades based on price-derived signals (RSI, MACD, SMA trend) against
forward price returns.

Enhancements:
- P6.1: Rolling/expanding window signal (no look-ahead bias), walk-forward validation
- P6.2: Parameter sensitivity sweep with heatmap data
- P6.3: Configurable transaction costs (commission + slippage)

Usage:
    from backtest import run_backtest, BacktestResult, run_parameter_sweep, run_walk_forward
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

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
    # P6.3: Transaction cost breakdown
    gross_return_pct: float = 0.0
    total_cost_pct: float = 0.0
    # P6.1: Walk-forward metadata
    is_insample: bool = True


# ---------------------------------------------------------------------------
# Core backtester
# ---------------------------------------------------------------------------

def run_backtest(
    df: pd.DataFrame,
    symbol: str,
    entry_threshold: int = 65,
    exit_threshold: int = 40,
    lookback_years: float = 2.0,
    commission_pct: float = 0.001,
    slippage_pct: float = 0.0005,
    is_insample: bool = True,
) -> BacktestResult:
    """Run a signal-based backtest.

    Parameters
    ----------
    df               : DataFrame with Date, Close columns (full history)
    symbol           : ticker symbol for labeling
    entry_threshold  : Buy when signal score >= this value
    exit_threshold   : Sell when signal score <= this value
    lookback_years   : Only backtest the last N years of data
    commission_pct   : Round-trip commission per trade (default 0.1%)
    slippage_pct     : One-way slippage per trade (default 0.05%)
    is_insample      : Label this as in-sample or out-of-sample period

    Returns
    -------
    BacktestResult with performance metrics and equity curve.

    Note: Signal computation uses only data available up to each bar
    (expanding window), so there is no look-ahead bias.
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

    # Transaction cost per trade (round-trip = entry + exit slippage + commission)
    round_trip_cost_pct = (commission_pct + 2 * slippage_pct) * 100

    # Simulate trades
    in_position = False
    entry_price = 0.0
    entry_date = ""
    entry_signal = 0
    trades: list[Trade] = []
    equity = [1.0]
    equity_gross = [1.0]  # before transaction costs
    equity_dates = [dates[0]] if dates else []
    position_mult = 1.0
    position_mult_gross = 1.0
    total_cost_pct = 0.0

    for i in range(1, n):
        s = signals[i]
        p = prices[i]
        d = dates[i]

        if not in_position:
            if s >= entry_threshold:
                in_position = True
                # Apply entry slippage (effective entry price is slightly higher)
                entry_price = p * (1 + slippage_pct)
                entry_date = d
                entry_signal = s
        else:
            if s <= exit_threshold:
                # Apply exit slippage (effective exit price is slightly lower)
                exit_price = p * (1 - slippage_pct)
                pnl_gross = (p - entry_price / (1 + slippage_pct)) / (entry_price / (1 + slippage_pct)) * 100
                pnl_pct = pnl_gross - round_trip_cost_pct
                trade = Trade(
                    entry_date=entry_date,
                    exit_date=d,
                    entry_price=round(entry_price, 2),
                    exit_price=round(exit_price, 2),
                    pnl_pct=round(pnl_pct, 2),
                    signal_at_entry=entry_signal,
                    is_win=pnl_pct > 0,
                )
                trades.append(trade)
                position_mult_gross *= (1 + pnl_gross / 100)
                position_mult *= (1 + pnl_pct / 100)
                total_cost_pct += round_trip_cost_pct
                in_position = False

        equity.append(position_mult)
        equity_gross.append(position_mult_gross)
        equity_dates.append(d)

    # Close open position at last price
    if in_position and n > 0:
        exit_price = prices[-1] * (1 - slippage_pct)
        pnl_gross = (prices[-1] - entry_price / (1 + slippage_pct)) / (entry_price / (1 + slippage_pct)) * 100
        pnl_pct = pnl_gross - round_trip_cost_pct
        trades.append(Trade(
            entry_date=entry_date,
            exit_date=dates[-1],
            entry_price=round(entry_price, 2),
            exit_price=round(exit_price, 2),
            pnl_pct=round(pnl_pct, 2),
            signal_at_entry=entry_signal,
            is_win=pnl_pct > 0,
        ))
        position_mult_gross *= (1 + pnl_gross / 100)
        position_mult *= (1 + pnl_pct / 100)
        total_cost_pct += round_trip_cost_pct
        equity[-1] = position_mult
        equity_gross[-1] = position_mult_gross

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

    gross_return_pct = (position_mult_gross - 1) * 100

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
        gross_return_pct=round(gross_return_pct, 2),
        total_cost_pct=round(total_cost_pct, 2),
        is_insample=is_insample,
    )


# ---------------------------------------------------------------------------
# P6.1: Walk-forward validation
# ---------------------------------------------------------------------------

def run_walk_forward(
    df: pd.DataFrame,
    symbol: str,
    entry_threshold: int = 65,
    exit_threshold: int = 40,
    insample_pct: float = 0.70,
    commission_pct: float = 0.001,
    slippage_pct: float = 0.0005,
) -> tuple[BacktestResult, BacktestResult]:
    """Run walk-forward validation by splitting history into in-sample and out-of-sample.

    Parameters
    ----------
    df               : Full price history DataFrame
    symbol           : Ticker symbol
    entry_threshold  : Entry signal threshold
    exit_threshold   : Exit signal threshold
    insample_pct     : Fraction of history for in-sample (default 70%)
    commission_pct   : Commission per trade
    slippage_pct     : Slippage per trade

    Returns
    -------
    (in_sample_result, out_of_sample_result) tuple of BacktestResult
    """
    if df is None or len(df) < 100:
        raise ValueError("Insufficient data for walk-forward validation (need 100+ days)")

    df = df.sort_values("Date").reset_index(drop=True)
    split_idx = int(len(df) * insample_pct)
    df_in = df.iloc[:split_idx].copy()
    # For out-of-sample, we pass the full df so signals use full history up to each bar
    df_out_slice = df.iloc[split_idx:].copy()

    in_result = run_backtest(
        df=df_in,
        symbol=symbol,
        entry_threshold=entry_threshold,
        exit_threshold=exit_threshold,
        lookback_years=50,  # use all available in-sample data
        commission_pct=commission_pct,
        slippage_pct=slippage_pct,
        is_insample=True,
    )

    # For out-of-sample, pass full df for signal computation but only trade in the OOS period
    # We need at least some rows in OOS
    if len(df_out_slice) < 30:
        raise ValueError("Not enough out-of-sample data (need 30+ days)")

    out_result = run_backtest(
        df=df,  # pass full df for proper signal computation (uses expanding window)
        symbol=symbol,
        entry_threshold=entry_threshold,
        exit_threshold=exit_threshold,
        lookback_years=round(len(df_out_slice) / 252, 2),  # OOS period only
        commission_pct=commission_pct,
        slippage_pct=slippage_pct,
        is_insample=False,
    )

    return in_result, out_result


# ---------------------------------------------------------------------------
# P6.2: Parameter sensitivity sweep
# ---------------------------------------------------------------------------

def run_parameter_sweep(
    df: pd.DataFrame,
    symbol: str,
    entry_values: list[int] | None = None,
    exit_values: list[int] | None = None,
    commission_pct: float = 0.001,
    slippage_pct: float = 0.0005,
    lookback_years: float = 2.0,
) -> dict:
    """Test all combinations of entry/exit thresholds.

    Returns dict with:
        grid: DataFrame (entry as rows, exit as cols) of Sharpe ratios
        grid_return: DataFrame of total returns
        best_params: {entry, exit, sharpe, total_return}
        boundary_warning: bool (True if optimal params are at boundary)
    """
    if entry_values is None:
        entry_values = [55, 60, 65, 70]
    if exit_values is None:
        exit_values = [30, 35, 40, 45]

    sharpe_grid = {}
    return_grid = {}
    best_sharpe = -999.0
    best_params = {"entry": entry_values[0], "exit": exit_values[0], "sharpe": None, "total_return": None}

    for entry in entry_values:
        sharpe_grid[entry] = {}
        return_grid[entry] = {}
        for exit_ in exit_values:
            if exit_ >= entry:
                sharpe_grid[entry][exit_] = None
                return_grid[entry][exit_] = None
                continue
            try:
                result = run_backtest(
                    df=df,
                    symbol=symbol,
                    entry_threshold=entry,
                    exit_threshold=exit_,
                    lookback_years=lookback_years,
                    commission_pct=commission_pct,
                    slippage_pct=slippage_pct,
                )
                sharpe = result.sharpe_ratio
                ret = result.total_return_pct
                sharpe_grid[entry][exit_] = sharpe
                return_grid[entry][exit_] = ret
                if sharpe is not None and sharpe > best_sharpe:
                    best_sharpe = sharpe
                    best_params = {
                        "entry": entry,
                        "exit": exit_,
                        "sharpe": sharpe,
                        "total_return": ret,
                    }
            except Exception:
                sharpe_grid[entry][exit_] = None
                return_grid[entry][exit_] = None

    import pandas as pd
    sharpe_df = pd.DataFrame(sharpe_grid).T  # entry as rows, exit as cols
    return_df = pd.DataFrame(return_grid).T

    # Boundary warning: optimal params are at min/max of the tested range
    boundary_warning = (
        best_params["entry"] in [min(entry_values), max(entry_values)]
        or best_params["exit"] in [min(exit_values), max(exit_values)]
    )

    return {
        "grid_sharpe": sharpe_df,
        "grid_return": return_df,
        "best_params": best_params,
        "boundary_warning": boundary_warning,
    }
