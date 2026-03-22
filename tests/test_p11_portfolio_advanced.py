"""Tests for P11.x: Portfolio Intelligence — Monte Carlo, Kelly, Factor Attribution, Peer Comparison."""

from __future__ import annotations

import pandas as pd
import numpy as np
import pytest
from unittest.mock import MagicMock

from src.analysis.portfolio_analysis import (
    factor_attribution,
    kelly_sizing,
    monte_carlo_simulation,
    FACTOR_DIMENSIONS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_returns():
    """Create deterministic daily returns for 3 tickers."""
    dates = pd.date_range("2023-01-01", periods=300)
    np.random.seed(42)
    data = {
        "AAPL": np.random.normal(0.001, 0.02, 300),
        "MSFT": np.random.normal(0.0008, 0.018, 300),
        "GOOGL": np.random.normal(0.0012, 0.022, 300),
    }
    return pd.DataFrame(data, index=dates)


@pytest.fixture
def equal_weights():
    return {"AAPL": 1 / 3, "MSFT": 1 / 3, "GOOGL": 1 / 3}


# ---------------------------------------------------------------------------
# Monte Carlo tests
# ---------------------------------------------------------------------------


class TestMonteCarlo:
    def test_basic_simulation(self, sample_returns, equal_weights):
        result = monte_carlo_simulation(
            sample_returns, equal_weights, n_simulations=1000, seed=42
        )
        assert "simulated_final_returns" in result
        assert len(result["simulated_final_returns"]) == 1000
        assert "percentiles" in result
        assert "prob_ruin" in result

    def test_percentiles_ordered(self, sample_returns, equal_weights):
        result = monte_carlo_simulation(
            sample_returns, equal_weights, n_simulations=1000, seed=42
        )
        pcts = result["percentiles"]
        assert pcts["p5"] <= pcts["p25"]
        assert pcts["p25"] <= pcts["p50"]
        assert pcts["p50"] <= pcts["p75"]
        assert pcts["p75"] <= pcts["p95"]

    def test_prob_target_sum(self, sample_returns, equal_weights):
        result = monte_carlo_simulation(
            sample_returns, equal_weights, n_simulations=1000, seed=42
        )
        # Probabilities should be between 0 and 100
        for target, prob in result["prob_target"].items():
            assert 0 <= prob <= 100

    def test_prob_ruin_range(self, sample_returns, equal_weights):
        result = monte_carlo_simulation(
            sample_returns, equal_weights, n_simulations=500, seed=42
        )
        assert 0 <= result["prob_ruin"] <= 100

    def test_empty_returns(self):
        result = monte_carlo_simulation(pd.DataFrame(), {}, n_simulations=100)
        assert result == {}

    def test_reproducible_with_seed(self, sample_returns, equal_weights):
        result1 = monte_carlo_simulation(
            sample_returns, equal_weights, n_simulations=500, seed=99
        )
        result2 = monte_carlo_simulation(
            sample_returns, equal_weights, n_simulations=500, seed=99
        )
        assert result1["median_return_pct"] == result2["median_return_pct"]

    def test_n_simulations(self, sample_returns, equal_weights):
        for n in [100, 500, 1000]:
            result = monte_carlo_simulation(
                sample_returns, equal_weights, n_simulations=n, seed=42
            )
            assert result["n_simulations"] == n
            assert len(result["simulated_final_returns"]) == n

    def test_missing_ticker_in_weights(self, sample_returns):
        weights = {"AAPL": 0.5, "NONEXISTENT": 0.5}
        result = monte_carlo_simulation(sample_returns, weights, n_simulations=100)
        # Should only use AAPL
        assert len(result.get("simulated_final_returns", [])) == 100


# ---------------------------------------------------------------------------
# Kelly Criterion tests
# ---------------------------------------------------------------------------


class TestKellySizing:
    def test_basic_kelly(self, sample_returns):
        factor_scores = {"AAPL": 70.0, "MSFT": 60.0, "GOOGL": 55.0}
        result = kelly_sizing(factor_scores, sample_returns, account_size=100_000)

        assert "AAPL" in result
        assert "MSFT" in result
        assert "GOOGL" in result

    def test_kelly_fields(self, sample_returns):
        factor_scores = {"AAPL": 70.0}
        result = kelly_sizing(factor_scores, sample_returns)

        aapl = result["AAPL"]
        assert "full_kelly_pct" in aapl
        assert "win_rate" in aapl
        assert "win_loss_ratio" in aapl
        assert "100%_kelly" in aapl
        assert "50%_kelly" in aapl
        assert "25%_kelly" in aapl
        assert "equal_weight" in aapl

    def test_kelly_respects_max_position(self, sample_returns):
        factor_scores = {"AAPL": 99.0}
        result = kelly_sizing(factor_scores, sample_returns, max_position_pct=10.0)
        # Full Kelly should be capped at 10%
        assert result["AAPL"]["full_kelly_pct"] <= 10.0

    def test_kelly_dollar_amounts(self, sample_returns):
        factor_scores = {"AAPL": 70.0}
        result = kelly_sizing(factor_scores, sample_returns, account_size=200_000)
        # Dollar amounts should be proportional to account size
        kelly_100 = result["AAPL"]["100%_kelly"]
        # Dollar amounts should be approximately proportional to account size
        # Allow small rounding differences (rounded to nearest dollar)
        assert kelly_100["dollars"] == pytest.approx(
            200_000 * kelly_100["pct"] / 100, rel=0.01
        )

    def test_empty_factor_scores(self, sample_returns):
        result = kelly_sizing({}, sample_returns)
        assert result == {}

    def test_custom_fractions(self, sample_returns):
        factor_scores = {"AAPL": 65.0}
        result = kelly_sizing(
            factor_scores, sample_returns, kelly_fractions=[1.0, 0.33]
        )
        aapl = result["AAPL"]
        assert "100%_kelly" in aapl
        assert "33%_kelly" in aapl
        assert "50%_kelly" not in aapl


# ---------------------------------------------------------------------------
# Factor Attribution tests
# ---------------------------------------------------------------------------


class TestFactorAttribution:
    def test_basic_attribution(self):
        factor_details = {
            "AAPL": {f: 70 for f in FACTOR_DIMENSIONS},
            "MSFT": {f: 60 for f in FACTOR_DIMENSIONS},
        }
        weights = {"AAPL": 0.6, "MSFT": 0.4}

        result = factor_attribution(factor_details, weights)

        assert "factor_contributions" in result
        assert "factor_shares" in result
        assert "total_weighted_score" in result

    def test_factor_shares_sum_100(self):
        factor_details = {
            "AAPL": {
                "valuation": 80,
                "trend": 70,
                "rsi": 60,
                "macd": 50,
                "sentiment": 65,
                "earnings": 75,
                "analyst": 55,
                "range": 60,
            },
            "MSFT": {
                "valuation": 60,
                "trend": 65,
                "rsi": 70,
                "macd": 55,
                "sentiment": 70,
                "earnings": 65,
                "analyst": 60,
                "range": 50,
            },
        }
        weights = {"AAPL": 0.5, "MSFT": 0.5}

        result = factor_attribution(factor_details, weights)
        total_share = sum(result["factor_shares"].values())
        assert total_share == pytest.approx(100.0, abs=1.0)

    def test_concentration_warning(self):
        # All weight on one factor
        factor_details = {
            "AAPL": {
                "valuation": 0,
                "trend": 100,
                "rsi": 0,
                "macd": 0,
                "sentiment": 0,
                "earnings": 0,
                "analyst": 0,
                "range": 0,
            },
        }
        weights = {"AAPL": 1.0}

        result = factor_attribution(factor_details, weights)
        assert result["top_factor"] == "trend"
        assert result["concentration_warning"] is not None

    def test_empty_inputs(self):
        result = factor_attribution({}, {})
        assert result == {}

    def test_missing_ticker_in_weights(self):
        factor_details = {"AAPL": {f: 50 for f in FACTOR_DIMENSIONS}}
        weights = {"AAPL": 0.5, "MISSING": 0.5}

        result = factor_attribution(factor_details, weights)
        # Should only process AAPL
        assert "AAPL" in result.get("ticker_contributions", {})

    def test_ticker_contributions_sum(self):
        factor_details = {
            "AAPL": {f: 80 for f in FACTOR_DIMENSIONS},
            "MSFT": {f: 60 for f in FACTOR_DIMENSIONS},
        }
        weights = {"AAPL": 0.4, "MSFT": 0.6}

        result = factor_attribution(factor_details, weights)

        # For each factor, ticker contributions should sum to factor_contributions
        for factor in FACTOR_DIMENSIONS:
            ticker_sum = sum(
                result["ticker_contributions"][t].get(factor, 0)
                for t in result["ticker_contributions"]
            )
            assert ticker_sum == pytest.approx(
                result["factor_contributions"][factor], abs=0.01
            )


# ---------------------------------------------------------------------------
# Peer comparison tests (via comparison module)
# ---------------------------------------------------------------------------


class TestPeerComparison:
    def test_fetch_peer_metrics_no_peers(self):
        from src.analysis.comparison import fetch_peer_metrics

        mock_api = MagicMock()
        mock_api.get_peers.return_value = []
        mock_api.get_financials.return_value = {
            "peBasicExclExtraTTM": 25.0,
            "roeTTM": 15.0,
            "revenueGrowthTTMYoy": 8.0,
            "grossMarginTTM": 40.0,
        }
        mock_api.get_quote.return_value = {"c": 150.0}
        mock_api.get_profile.return_value = {
            "name": "Apple Inc.",
            "finnhubIndustry": "Technology",
        }

        result = fetch_peer_metrics("AAPL", mock_api)

        assert result["target"] == "AAPL"
        assert result["peer_tickers"] == []

    def test_fetch_peer_metrics_with_peers(self):
        from src.analysis.comparison import fetch_peer_metrics

        mock_api = MagicMock()
        mock_api.get_peers.return_value = ["MSFT", "GOOGL"]
        mock_api.get_financials.return_value = {
            "peBasicExclExtraTTM": 25.0,
            "roeTTM": 15.0,
            "revenueGrowthTTMYoy": 8.0,
            "grossMarginTTM": 40.0,
        }
        mock_api.get_quote.return_value = {"c": 150.0}
        mock_api.get_profile.return_value = {
            "name": "Apple Inc.",
            "finnhubIndustry": "Technology",
        }

        result = fetch_peer_metrics("AAPL", mock_api)

        assert result["target"] == "AAPL"
        assert "MSFT" in result["peer_tickers"]
        assert "percentile_ranks" in result
        assert "peer_table" in result

    def test_percentile_ranks_range(self):
        from src.analysis.comparison import fetch_peer_metrics

        mock_api = MagicMock()
        mock_api.get_peers.return_value = ["MSFT", "GOOGL", "META"]

        def get_fin(sym):
            data = {
                "AAPL": {
                    "peBasicExclExtraTTM": 25.0,
                    "roeTTM": 15.0,
                    "revenueGrowthTTMYoy": 8.0,
                    "grossMarginTTM": 40.0,
                },
                "MSFT": {
                    "peBasicExclExtraTTM": 30.0,
                    "roeTTM": 40.0,
                    "revenueGrowthTTMYoy": 12.0,
                    "grossMarginTTM": 70.0,
                },
                "GOOGL": {
                    "peBasicExclExtraTTM": 20.0,
                    "roeTTM": 20.0,
                    "revenueGrowthTTMYoy": 5.0,
                    "grossMarginTTM": 55.0,
                },
                "META": {
                    "peBasicExclExtraTTM": 22.0,
                    "roeTTM": 25.0,
                    "revenueGrowthTTMYoy": 15.0,
                    "grossMarginTTM": 80.0,
                },
            }
            return data.get(sym, {})

        mock_api.get_financials.side_effect = get_fin
        mock_api.get_quote.return_value = {"c": 150.0}
        mock_api.get_profile.return_value = {
            "name": "Apple",
            "finnhubIndustry": "Technology",
        }

        result = fetch_peer_metrics("AAPL", mock_api)

        for key, pct in result["percentile_ranks"].items():
            if pct is not None:
                assert 0 <= pct <= 100
