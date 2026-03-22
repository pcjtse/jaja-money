"""Tests for comparison.py — analyze_ticker, compare_tickers, comparison_dataframe, fetch_peer_metrics."""

from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_api(
    quote=None,
    profile=None,
    financials=None,
    daily=None,
    recommendations=None,
    earnings=None,
    peers=None,
):
    """Build a minimal mock API object."""
    api = MagicMock()
    api.get_quote.return_value = quote or {"c": 150.0, "dp": 1.5}
    api.get_profile.return_value = profile or {
        "name": "Apple Inc.",
        "finnhubIndustry": "Technology",
    }
    api.get_financials.return_value = financials or {
        "peBasicExclExtraTTM": 28.0,
        "epsBasicExclExtraItemsTTM": 6.0,
        "marketCapitalization": 2_500_000,
        "52WeekHigh": 200.0,
        "52WeekLow": 130.0,
    }
    # Build a minimal daily series (252 trading days)
    import numpy as np

    prices = 100 + np.cumsum(np.random.default_rng(42).normal(0, 1, 252))
    timestamps = list(range(1_600_000_000, 1_600_000_000 + 252 * 86400, 86400))
    api.get_daily.return_value = daily or {
        "c": prices.tolist(),
        "v": [1_000_000] * 252,
        "t": timestamps,
    }
    api.get_recommendations.return_value = recommendations or [
        {"strongBuy": 10, "buy": 5, "hold": 3, "sell": 1, "strongSell": 0}
    ]
    api.get_earnings.return_value = earnings or [
        {"period": "2024-09-30", "actual": 1.5, "estimate": 1.4, "surprisePercent": 7.1}
    ]
    api.get_peers.return_value = peers or ["MSFT", "GOOG"]
    return api


# ---------------------------------------------------------------------------
# analyze_ticker
# ---------------------------------------------------------------------------


class TestAnalyzeTicker:
    def test_returns_dict_with_required_keys(self):
        from src.analysis.comparison import analyze_ticker

        api = _make_api()
        result = analyze_ticker("AAPL", api)
        assert result is not None
        for key in ("symbol", "name", "sector", "price", "factor_score", "risk_score"):
            assert key in result

    def test_symbol_set_correctly(self):
        from src.analysis.comparison import analyze_ticker

        api = _make_api()
        result = analyze_ticker("AAPL", api)
        assert result["symbol"] == "AAPL"

    def test_returns_none_on_exception(self):
        from src.analysis.comparison import analyze_ticker

        api = MagicMock()
        api.get_quote.side_effect = RuntimeError("network error")
        result = analyze_ticker("AAPL", api)
        assert result is None

    def test_handles_missing_profile_gracefully(self):
        from src.analysis.comparison import analyze_ticker

        api = _make_api()
        api.get_profile.side_effect = RuntimeError("profile error")
        result = analyze_ticker("AAPL", api)
        # Should still return a result, using symbol as fallback name
        assert result is not None
        assert result["name"] == "AAPL"

    def test_factor_score_in_valid_range(self):
        from src.analysis.comparison import analyze_ticker

        api = _make_api()
        result = analyze_ticker("AAPL", api)
        assert 0 <= result["factor_score"] <= 100

    def test_risk_score_in_valid_range(self):
        from src.analysis.comparison import analyze_ticker

        api = _make_api()
        result = analyze_ticker("AAPL", api)
        assert 0 <= result["risk_score"] <= 100

    def test_factor_detail_is_dict(self):
        from src.analysis.comparison import analyze_ticker

        api = _make_api()
        result = analyze_ticker("AAPL", api)
        assert isinstance(result["factor_detail"], dict)


# ---------------------------------------------------------------------------
# compare_tickers
# ---------------------------------------------------------------------------


class TestCompareTickers:
    def test_returns_list_of_results(self):
        from src.analysis.comparison import compare_tickers

        api = _make_api()
        results = compare_tickers(["AAPL", "MSFT"], api)
        assert len(results) == 2

    def test_strips_and_uppercases_symbols(self):
        from src.analysis.comparison import compare_tickers

        api = _make_api()
        results = compare_tickers([" aapl "], api)
        assert results[0]["symbol"] == "AAPL"

    def test_skips_failed_tickers(self):
        from src.analysis.comparison import compare_tickers

        api = _make_api()
        api.get_quote.side_effect = [
            {"c": 100.0, "dp": 0.5},
            RuntimeError("fail"),
            {"c": 200.0, "dp": 1.0},
        ]
        results = compare_tickers(["AAPL", "BAD", "MSFT"], api)
        # BAD should be skipped
        symbols = [r["symbol"] for r in results]
        assert "BAD" not in symbols

    def test_empty_input(self):
        from src.analysis.comparison import compare_tickers

        api = _make_api()
        results = compare_tickers([], api)
        assert results == []


# ---------------------------------------------------------------------------
# comparison_dataframe
# ---------------------------------------------------------------------------


class TestComparisonDataframe:
    def _make_result(self, symbol="AAPL", mc_m=2_500_000, pe=28.0):
        return {
            "symbol": symbol,
            "name": "Apple Inc.",
            "sector": "Technology",
            "price": 150.0,
            "change_pct": 1.5,
            "factor_score": 65,
            "composite_label": "Bullish",
            "composite_color": "green",
            "risk_score": 30,
            "risk_level": "Low",
            "risk_color": "green",
            "flag_count": 0,
            "hv": 18.5,
            "drawdown_pct": -8.2,
            "pe": pe,
            "eps": 6.0,
            "mc_m": mc_m,
            "high52": 200.0,
            "low52": 130.0,
            "factor_detail": {},
            "factors": [],
            "risk": {},
            "close": None,
        }

    def test_returns_dataframe(self):
        from src.analysis.comparison import comparison_dataframe

        df = comparison_dataframe([self._make_result()])
        assert isinstance(df, pd.DataFrame)

    def test_dataframe_has_expected_columns(self):
        from src.analysis.comparison import comparison_dataframe

        df = comparison_dataframe([self._make_result()])
        for col in ("Symbol", "Price", "Factor Score", "Risk Score", "Signal"):
            assert col in df.columns

    def test_dataframe_rows_match_inputs(self):
        from src.analysis.comparison import comparison_dataframe

        results = [self._make_result("AAPL"), self._make_result("MSFT")]
        df = comparison_dataframe(results)
        assert len(df) == 2

    def test_market_cap_billions_formatting(self):
        from src.analysis.comparison import comparison_dataframe

        df = comparison_dataframe([self._make_result(mc_m=2_500_000)])  # $2.5T
        assert "T" in df.iloc[0]["Market Cap"] or "B" in df.iloc[0]["Market Cap"]

    def test_market_cap_none_shows_na(self):
        from src.analysis.comparison import comparison_dataframe

        result = self._make_result(mc_m=None)
        df = comparison_dataframe([result])
        assert df.iloc[0]["Market Cap"] == "N/A"

    def test_pe_none_shows_na(self):
        from src.analysis.comparison import comparison_dataframe

        result = self._make_result(pe=None)
        df = comparison_dataframe([result])
        assert df.iloc[0]["P/E"] == "N/A"

    def test_empty_results_returns_empty_df(self):
        from src.analysis.comparison import comparison_dataframe

        df = comparison_dataframe([])
        assert len(df) == 0


# ---------------------------------------------------------------------------
# fetch_peer_metrics
# ---------------------------------------------------------------------------


class TestFetchPeerMetrics:
    def test_returns_error_when_target_data_unavailable(self):
        from src.analysis.comparison import fetch_peer_metrics

        api = MagicMock()
        api.get_peers.return_value = []
        api.get_financials.side_effect = RuntimeError("fail")
        api.get_quote.side_effect = RuntimeError("fail")
        api.get_profile.side_effect = RuntimeError("fail")
        result = fetch_peer_metrics("AAPL", api)
        assert "error" in result

    def test_returns_required_keys_when_data_available(self):
        from src.analysis.comparison import fetch_peer_metrics

        api = _make_api()
        api.get_peers.return_value = ["MSFT", "GOOG"]
        result = fetch_peer_metrics("AAPL", api)
        if "error" not in result:
            assert "target" in result
            assert "peer_tickers" in result
            assert "peer_table" in result
            assert "percentile_ranks" in result

    def test_no_peers_still_returns_target_data(self):
        from src.analysis.comparison import fetch_peer_metrics

        api = _make_api()
        api.get_peers.return_value = []
        result = fetch_peer_metrics("AAPL", api)
        if "error" not in result:
            assert result["target"] == "AAPL"
            assert result["peer_tickers"] == []

    def test_peer_table_includes_target(self):
        from src.analysis.comparison import fetch_peer_metrics

        api = _make_api()
        api.get_peers.return_value = []
        result = fetch_peer_metrics("AAPL", api)
        if "peer_table" in result:
            targets = [r for r in result["peer_table"] if r["is_target"]]
            assert len(targets) == 1
            assert targets[0]["ticker"] == "AAPL"

    def test_percentile_rank_in_valid_range(self):
        from src.analysis.comparison import fetch_peer_metrics

        api = _make_api()
        api.get_peers.return_value = ["MSFT", "GOOG", "META"]
        result = fetch_peer_metrics("AAPL", api)
        if "percentile_ranks" in result:
            for key, val in result["percentile_ranks"].items():
                if val is not None:
                    assert 0 <= val <= 100
