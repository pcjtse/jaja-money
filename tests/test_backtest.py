"""Tests for backtest.py (P3.2)."""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


def _make_df(n=300, trend="up"):
    """Generate synthetic price data."""
    dates = [datetime(2022, 1, 1) + timedelta(days=i) for i in range(n)]
    if trend == "up":
        prices = [100 + i * 0.2 + np.random.normal(0, 0.5) for i in range(n)]
    elif trend == "down":
        prices = [200 - i * 0.2 + np.random.normal(0, 0.5) for i in range(n)]
    else:
        prices = [100 + np.random.normal(0, 2) for _ in range(n)]
    return pd.DataFrame({
        "Date": dates,
        "Open": prices,
        "High": [p * 1.01 for p in prices],
        "Low": [p * 0.99 for p in prices],
        "Close": prices,
        "Volume": [1_000_000] * n,
    })


def test_basic_backtest_runs():
    from backtest import run_backtest
    df = _make_df(300, "up")
    result = run_backtest(df, "TEST", entry_threshold=60, exit_threshold=40, lookback_years=1)
    assert result is not None
    assert result.symbol == "TEST"


def test_backtest_returns_result_structure():
    from backtest import run_backtest, BacktestResult
    df = _make_df(300)
    result = run_backtest(df, "TEST", lookback_years=1)
    assert isinstance(result, BacktestResult)
    assert isinstance(result.total_return_pct, float)
    assert isinstance(result.max_drawdown_pct, float)
    assert 0 <= result.win_rate_pct <= 100
    assert len(result.equity_curve) > 0
    assert len(result.equity_dates) > 0


def test_backtest_requires_minimum_data():
    from backtest import run_backtest
    df = _make_df(30)  # Too little data
    with pytest.raises(ValueError, match="Insufficient"):
        run_backtest(df, "TEST")


def test_equity_curve_starts_at_one():
    from backtest import run_backtest
    df = _make_df(300)
    result = run_backtest(df, "TEST", lookback_years=1)
    assert result.equity_curve[0] == pytest.approx(1.0)


def test_trades_are_coherent():
    from backtest import run_backtest
    df = _make_df(400, "up")
    result = run_backtest(df, "TEST", entry_threshold=55, exit_threshold=45, lookback_years=1)
    for trade in result.trades:
        assert trade.entry_price > 0
        assert trade.exit_price > 0
        assert isinstance(trade.is_win, bool)
        pnl_check = (trade.exit_price - trade.entry_price) / trade.entry_price * 100
        assert abs(pnl_check - trade.pnl_pct) < 0.01


def test_win_rate_matches_trades():
    from backtest import run_backtest
    df = _make_df(400)
    result = run_backtest(df, "TEST", lookback_years=1)
    if result.total_trades > 0:
        wins = sum(1 for t in result.trades if t.is_win)
        expected_rate = wins / result.total_trades * 100
        assert abs(result.win_rate_pct - expected_rate) < 0.1


def test_sharpe_is_numeric_or_none():
    from backtest import run_backtest
    df = _make_df(300)
    result = run_backtest(df, "TEST", lookback_years=1)
    assert result.sharpe_ratio is None or isinstance(result.sharpe_ratio, float)
