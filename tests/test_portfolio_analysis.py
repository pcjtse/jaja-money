"""Tests for portfolio_analysis.py (P2.4)."""
import pytest
import pandas as pd
import numpy as np


def _make_returns(tickers, n=252, seed=42):
    rng = np.random.default_rng(seed)
    data = {}
    for t in tickers:
        data[t] = rng.normal(0.0005, 0.015, n)
    return pd.DataFrame(data)


def test_correlation_matrix_shape():
    from portfolio_analysis import correlation_matrix
    returns = _make_returns(["AAPL", "MSFT", "GOOG"])
    corr = correlation_matrix(returns)
    assert corr.shape == (3, 3)
    # Diagonal should be 1.0
    for t in ["AAPL", "MSFT", "GOOG"]:
        assert corr.loc[t, t] == pytest.approx(1.0)


def test_correlation_matrix_symmetric():
    from portfolio_analysis import correlation_matrix
    returns = _make_returns(["A", "B", "C"])
    corr = correlation_matrix(returns)
    for i in corr.index:
        for j in corr.columns:
            assert corr.loc[i, j] == pytest.approx(corr.loc[j, i], abs=1e-10)


def test_correlation_range():
    from portfolio_analysis import correlation_matrix
    returns = _make_returns(["X", "Y"])
    corr = correlation_matrix(returns)
    for i in corr.index:
        for j in corr.columns:
            assert -1.0 <= corr.loc[i, j] <= 1.0


def test_portfolio_stats_keys():
    from portfolio_analysis import portfolio_stats
    returns = _make_returns(["AAPL", "MSFT"])
    weights = {"AAPL": 0.6, "MSFT": 0.4}
    stats = portfolio_stats(returns, weights)
    for key in ["portfolio_return_pct", "portfolio_vol_pct", "sharpe",
                "diversification_ratio", "effective_n"]:
        assert key in stats


def test_portfolio_stats_vol_positive():
    from portfolio_analysis import portfolio_stats
    returns = _make_returns(["A", "B"])
    stats = portfolio_stats(returns, {"A": 0.5, "B": 0.5})
    assert stats["portfolio_vol_pct"] > 0


def test_portfolio_stats_equal_weights():
    from portfolio_analysis import portfolio_stats
    returns = _make_returns(["A", "B"])
    stats = portfolio_stats(returns, {"A": 0.5, "B": 0.5})
    assert stats["weights"]["A"] == pytest.approx(0.5)
    assert stats["weights"]["B"] == pytest.approx(0.5)


def test_portfolio_stats_normalized_weights():
    """Weights that don't sum to 1 should be normalized."""
    from portfolio_analysis import portfolio_stats
    returns = _make_returns(["A", "B"])
    stats = portfolio_stats(returns, {"A": 50, "B": 50})  # sums to 100, not 1
    total = sum(stats["weights"].values())
    assert total == pytest.approx(1.0)


def test_portfolio_beta():
    from portfolio_analysis import portfolio_beta
    returns = _make_returns(["A", "B", "SPY"])
    weights = {"A": 0.5, "B": 0.5}
    market = returns["SPY"]
    beta = portfolio_beta(returns[["A", "B"]], weights, market)
    assert beta is not None
    assert -5.0 < beta < 5.0  # reasonable beta range


def test_build_returns_matrix():
    from portfolio_analysis import build_returns_matrix
    import pandas as pd
    s1 = pd.Series([100, 102, 101, 103], name="A")
    s2 = pd.Series([200, 198, 202, 204], name="B")
    closes = {"A": s1, "B": s2}
    ret = build_returns_matrix(closes)
    assert "A" in ret.columns
    assert "B" in ret.columns
    assert len(ret) == 3  # pct_change drops first row
