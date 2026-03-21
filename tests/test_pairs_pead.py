"""Tests for pairs.py and pead.py — spread, z-score, pairs signal, backtest, PEAD drift."""

from __future__ import annotations

import math
from unittest.mock import MagicMock

import pandas as pd
import numpy as np
import pytest


# ===========================================================================
# pairs.py
# ===========================================================================


def _make_price_series(n=300, seed=42, trend=0.0):
    rng = np.random.default_rng(seed)
    prices = 100 + np.cumsum(rng.normal(trend, 1.0, n))
    prices = np.maximum(prices, 1.0)  # keep positive
    idx = pd.date_range("2022-01-01", periods=n, freq="B")
    return pd.Series(prices, index=idx)


def _make_df(series: pd.Series) -> pd.DataFrame:
    return pd.DataFrame({"Date": series.index, "Close": series.values})


class TestComputeSpread:
    def test_returns_series(self):
        from pairs import compute_spread

        a = _make_price_series(100)
        b = _make_price_series(100, seed=7)
        result = compute_spread(a, b)
        assert isinstance(result, pd.Series)

    def test_length_matches_aligned(self):
        from pairs import compute_spread

        a = _make_price_series(100)
        b = _make_price_series(100, seed=7)
        result = compute_spread(a, b)
        assert len(result) == 100

    def test_empty_input_returns_empty_series(self):
        from pairs import compute_spread

        a = pd.Series(dtype=float)
        b = pd.Series(dtype=float)
        result = compute_spread(a, b)
        assert len(result) == 0

    def test_identical_series_gives_zero_spread(self):
        from pairs import compute_spread

        a = _make_price_series(50)
        result = compute_spread(a, a)
        # log(a/a) = log(1) = 0
        assert all(abs(v) < 1e-10 for v in result)

    def test_spread_is_log_ratio(self):
        from pairs import compute_spread

        a = pd.Series([100.0, 110.0, 120.0])
        b = pd.Series([50.0, 55.0, 60.0])
        result = compute_spread(a, b)
        expected = [math.log(100 / 50), math.log(110 / 55), math.log(120 / 60)]
        for got, exp in zip(result, expected):
            assert abs(got - exp) < 1e-10


class TestComputeZscore:
    def test_returns_series(self):
        from pairs import compute_zscore, compute_spread

        a = _make_price_series(200)
        b = _make_price_series(200, seed=7)
        spread = compute_spread(a, b)
        result = compute_zscore(spread, window=60)
        assert isinstance(result, pd.Series)

    def test_first_window_bars_are_nan(self):
        from pairs import compute_zscore, compute_spread

        a = _make_price_series(200)
        b = _make_price_series(200, seed=7)
        spread = compute_spread(a, b)
        window = 60
        result = compute_zscore(spread, window=window)
        # First window-1 values should be NaN
        assert all(math.isnan(v) for v in result.iloc[: window - 1])

    def test_returns_empty_on_insufficient_data(self):
        from pairs import compute_zscore

        short = pd.Series([1.0, 2.0, 3.0])
        result = compute_zscore(short, window=60)
        assert len(result) == 0

    def test_zscore_mean_near_zero(self):
        from pairs import compute_zscore, compute_spread

        # Cointegrated pair should have mean-reverting spread → z-score near 0 on avg
        a = _make_price_series(500)
        b = _make_price_series(500, seed=99)
        spread = compute_spread(a, b)
        z = compute_zscore(spread, window=60).dropna()
        assert abs(float(z.mean())) < 2.0  # loose bound


class TestComputePairCorrelation:
    def test_highly_correlated_pair(self):
        from pairs import compute_pair_correlation

        a = _make_price_series(200)
        # b is nearly identical to a
        b = a + pd.Series(np.random.default_rng(5).normal(0, 0.01, 200), index=a.index)
        corr = compute_pair_correlation(a, b)
        assert corr is not None
        assert corr > 0.9

    def test_returns_none_for_short_series(self):
        from pairs import compute_pair_correlation

        a = pd.Series([1.0, 2.0, 3.0])
        b = pd.Series([1.0, 2.0, 3.0])
        assert compute_pair_correlation(a, b) is None

    def test_correlation_in_range(self):
        from pairs import compute_pair_correlation

        a = _make_price_series(200)
        b = _make_price_series(200, seed=33)
        corr = compute_pair_correlation(a, b)
        if corr is not None:
            assert -1.0 <= corr <= 1.0


class TestPairsSignal:
    def test_long_a_short_b_when_zscore_below_negative_threshold(self):
        from pairs import pairs_signal

        assert pairs_signal(-2.5) == "long_A_short_B"

    def test_long_b_short_a_when_zscore_above_positive_threshold(self):
        from pairs import pairs_signal

        assert pairs_signal(2.5) == "long_B_short_A"

    def test_exit_when_zscore_near_zero(self):
        from pairs import pairs_signal

        assert pairs_signal(0.2) == "exit"

    def test_neutral_in_between(self):
        from pairs import pairs_signal

        assert pairs_signal(1.5) == "neutral"

    def test_none_zscore_returns_neutral(self):
        from pairs import pairs_signal

        assert pairs_signal(None) == "neutral"

    def test_nan_zscore_returns_neutral(self):
        from pairs import pairs_signal

        assert pairs_signal(float("nan")) == "neutral"

    def test_custom_thresholds(self):
        from pairs import pairs_signal

        # Using entry=1.0, exit=0.2
        assert (
            pairs_signal(1.5, entry_threshold=1.0, exit_threshold=0.2)
            == "long_B_short_A"
        )
        assert (
            pairs_signal(-1.5, entry_threshold=1.0, exit_threshold=0.2)
            == "long_A_short_B"
        )
        assert pairs_signal(0.1, entry_threshold=1.0, exit_threshold=0.2) == "exit"


class TestBacktestPairs:
    def _make_dfs(self, n=200):
        a = _make_price_series(n, seed=1)
        b = _make_price_series(n, seed=2)
        return _make_df(a), _make_df(b)

    def test_returns_result_object(self):
        from pairs import backtest_pairs, PairsBacktestResult

        df_a, df_b = self._make_dfs(200)
        result = backtest_pairs(df_a, df_b, "A", "B")
        assert isinstance(result, PairsBacktestResult)

    def test_result_has_symbol_names(self):
        from pairs import backtest_pairs

        df_a, df_b = self._make_dfs(200)
        result = backtest_pairs(df_a, df_b, "AAPL", "MSFT")
        assert result.symbol_a == "AAPL"
        assert result.symbol_b == "MSFT"

    def test_equity_curve_starts_at_one(self):
        from pairs import backtest_pairs

        df_a, df_b = self._make_dfs(200)
        result = backtest_pairs(df_a, df_b, "A", "B")
        assert result.equity_curve[0] == pytest.approx(1.0)

    def test_win_rate_in_range(self):
        from pairs import backtest_pairs

        df_a, df_b = self._make_dfs(200)
        result = backtest_pairs(df_a, df_b, "A", "B")
        assert 0.0 <= result.win_rate_pct <= 100.0

    def test_raises_on_insufficient_data(self):
        from pairs import backtest_pairs

        df_a = _make_df(_make_price_series(10))
        df_b = _make_df(_make_price_series(10, seed=2))
        with pytest.raises(ValueError):
            backtest_pairs(df_a, df_b, "A", "B")

    def test_raises_on_none_input(self):
        from pairs import backtest_pairs

        with pytest.raises(ValueError):
            backtest_pairs(None, None, "A", "B")

    def test_dates_are_strings(self):
        from pairs import backtest_pairs

        df_a, df_b = self._make_dfs(200)
        result = backtest_pairs(df_a, df_b, "A", "B")
        assert all(isinstance(d, str) for d in result.dates)

    def test_spread_series_not_empty(self):
        from pairs import backtest_pairs

        df_a, df_b = self._make_dfs(200)
        result = backtest_pairs(df_a, df_b, "A", "B")
        assert len(result.spread_series) > 0


# ===========================================================================
# pead.py
# ===========================================================================


def _make_close_and_dates(n=252, start="2023-01-01"):
    idx = pd.date_range(start, periods=n, freq="B")
    prices = 100 + np.cumsum(np.random.default_rng(10).normal(0, 1, n))
    close = pd.Series(prices, name="Close")
    dates = pd.Series(idx)
    return close, dates


class TestComputePeadDrift:
    def test_empty_earnings_returns_neutral(self):
        from pead import compute_pead_drift

        close, dates = _make_close_and_dates()
        result = compute_pead_drift("AAPL", [], close, dates)
        assert result.signal == "Neutral"
        assert result.latest_surprise_pct is None

    def test_returns_pead_result_object(self):
        from pead import compute_pead_drift, PEADResult

        close, dates = _make_close_and_dates(252, "2023-01-01")
        earnings = [
            {"period": "2023-06-30", "surprisePercent": 8.0},
            {"period": "2023-03-31", "surprisePercent": -3.0},
        ]
        result = compute_pead_drift("AAPL", earnings, close, dates)
        assert isinstance(result, PEADResult)

    def test_big_beat_gives_long_signal(self):
        from pead import compute_pead_drift

        close, dates = _make_close_and_dates()
        earnings = [{"period": "2023-06-30", "surprisePercent": 10.0}]
        result = compute_pead_drift(
            "AAPL", earnings, close, dates, min_surprise_pct=5.0
        )
        assert result.signal == "Long (PEAD Beat)"

    def test_big_miss_gives_short_signal(self):
        from pead import compute_pead_drift

        close, dates = _make_close_and_dates()
        earnings = [{"period": "2023-06-30", "surprisePercent": -10.0}]
        result = compute_pead_drift(
            "AAPL", earnings, close, dates, min_surprise_pct=5.0
        )
        assert result.signal == "Short Signal (PEAD Miss)"

    def test_inline_gives_neutral(self):
        from pead import compute_pead_drift

        close, dates = _make_close_and_dates()
        earnings = [{"period": "2023-06-30", "surprisePercent": 2.0}]
        result = compute_pead_drift(
            "AAPL", earnings, close, dates, min_surprise_pct=5.0
        )
        assert result.signal == "Neutral"

    def test_drift_direction_classification(self):
        from pead import compute_pead_drift

        close, dates = _make_close_and_dates()
        earnings = [
            {"period": "2023-01-10", "surprisePercent": 8.0},
            {"period": "2023-04-10", "surprisePercent": -7.0},
        ]
        result = compute_pead_drift("AAPL", earnings, close, dates)
        directions = {d.direction for d in result.drifts}
        assert "beat" in directions or "miss" in directions

    def test_returns_neutral_with_none_close(self):
        from pead import compute_pead_drift

        earnings = [{"period": "2023-06-30", "surprisePercent": 8.0}]
        result = compute_pead_drift("AAPL", earnings, None, None)
        assert result.signal == "Neutral"

    def test_latest_surprise_pct_matches_first_entry(self):
        from pead import compute_pead_drift

        close, dates = _make_close_and_dates()
        earnings = [{"period": "2023-09-30", "surprisePercent": 6.5}]
        result = compute_pead_drift("AAPL", earnings, close, dates)
        assert result.latest_surprise_pct == pytest.approx(6.5)


class TestScreenPeadCandidates:
    def test_returns_list(self):
        from pead import screen_pead_candidates

        api = MagicMock()
        api.get_earnings.return_value = [
            {"period": "2024-09-30", "surprisePercent": 12.0}
        ]
        import numpy as np

        prices = (100 + np.cumsum(np.random.default_rng(1).normal(0, 1, 252))).tolist()
        timestamps = list(range(1_600_000_000, 1_600_000_000 + 252 * 86400, 86400))
        api.get_daily.return_value = {"c": prices, "t": timestamps}
        results = screen_pead_candidates(["AAPL"], api)
        assert isinstance(results, list)

    def test_filters_below_threshold(self):
        from pead import screen_pead_candidates

        api = MagicMock()
        api.get_earnings.return_value = [
            {"period": "2024-09-30", "surprisePercent": 1.0}
        ]  # below 5%
        results = screen_pead_candidates(["AAPL"], api, min_surprise_pct=5.0)
        assert results == []

    def test_result_has_required_keys(self):
        from pead import screen_pead_candidates

        api = MagicMock()
        api.get_earnings.return_value = [
            {"period": "2024-09-30", "surprisePercent": 15.0}
        ]
        import numpy as np

        prices = (100 + np.cumsum(np.random.default_rng(1).normal(0, 1, 252))).tolist()
        timestamps = list(range(1_600_000_000, 1_600_000_000 + 252 * 86400, 86400))
        api.get_daily.return_value = {"c": prices, "t": timestamps}
        results = screen_pead_candidates(["AAPL"], api)
        if results:
            for key in ("symbol", "surprise_pct", "signal"):
                assert key in results[0]
