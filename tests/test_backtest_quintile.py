"""Tests for backtest.py quintile analysis extension."""

from __future__ import annotations

import pytest
import pandas as pd


def _make_close(n: int = 200, start: float = 100.0) -> list[float]:
    """Generate a simple trending close series of length n."""
    return [start + i * 0.1 for i in range(n)]


# ---------------------------------------------------------------------------
# SP500_TOP50 list
# ---------------------------------------------------------------------------


def test_sp500_top50_has_50_tickers():
    from src.analysis.backtest import SP500_TOP50

    assert len(SP500_TOP50) == 50
    assert all(isinstance(t, str) for t in SP500_TOP50)


# ---------------------------------------------------------------------------
# run_quintile_backtest — mocked price fetches
# ---------------------------------------------------------------------------


def test_quintile_backtest_empty_universe():
    from src.analysis.backtest import run_quintile_backtest

    result = run_quintile_backtest(universe=[])
    assert result["quintile_df"].empty
    assert result["n_tickers"] == 0
    assert result["q1_avg"] is None


def test_quintile_backtest_with_mocked_data(monkeypatch):
    """Mock _fetch_close_series to avoid real API calls."""
    import src.analysis.backtest as B

    close_data = _make_close(200)

    def _mock_fetch(ticker):
        return pd.Series(close_data, dtype=float)

    monkeypatch.setattr(B, "_fetch_close_series", _mock_fetch)

    universe = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]
    result = B.run_quintile_backtest(universe=universe, forward_days=30)

    assert result["n_tickers"] == len(universe)
    assert not result["quintile_df"].empty
    assert "score" in result["quintile_df"].columns
    assert "fwd_return" in result["quintile_df"].columns
    assert "quintile" in result["quintile_df"].columns
    assert result["q1_avg"] is not None
    assert result["q5_avg"] is not None
    assert "survivorship_bias_disclaimer" in result


def test_quintile_skips_short_series(monkeypatch):
    """Tickers with < 60 bars should be excluded."""
    import src.analysis.backtest as B

    short_close = pd.Series(_make_close(40), dtype=float)
    long_close = pd.Series(_make_close(200), dtype=float)

    def _mock_fetch(ticker):
        return short_close if ticker == "AAPL" else long_close

    monkeypatch.setattr(B, "_fetch_close_series", _mock_fetch)

    universe = ["AAPL", "MSFT"]
    result = B.run_quintile_backtest(universe=universe, forward_days=30)
    tickers_scored = result["quintile_df"]["ticker"].tolist()
    assert "AAPL" not in tickers_scored
    assert "MSFT" in tickers_scored


def test_survivorship_bias_disclaimer_present():
    from src.analysis.backtest import _SURVIVORSHIP_DISCLAIMER

    assert "Survivorship bias" in _SURVIVORSHIP_DISCLAIMER
    assert "3 of 23" in _SURVIVORSHIP_DISCLAIMER
