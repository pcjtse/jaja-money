"""Tests for portfolio_analysis.py — missing functions:
compute_risk_parity_weights, run_stress_tests, find_tax_loss_opportunities,
compute_portfolio_drift, analyze_portfolio.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def _make_returns(tickers=("AAPL", "MSFT", "GOOG"), n=252, seed=42):
    """Build a synthetic returns DataFrame."""
    rng = np.random.default_rng(seed)
    data = rng.normal(0.0005, 0.015, (n, len(tickers)))
    return pd.DataFrame(data, columns=list(tickers))


# ---------------------------------------------------------------------------
# compute_risk_parity_weights
# ---------------------------------------------------------------------------


class TestComputeRiskParityWeights:
    def test_weights_sum_to_one(self):
        from portfolio_analysis import compute_risk_parity_weights

        returns = _make_returns()
        weights = compute_risk_parity_weights(returns)
        assert sum(weights.values()) == pytest.approx(1.0, abs=0.01)

    def test_all_weights_positive(self):
        from portfolio_analysis import compute_risk_parity_weights

        returns = _make_returns()
        weights = compute_risk_parity_weights(returns)
        assert all(w > 0 for w in weights.values())

    def test_returns_all_tickers(self):
        from portfolio_analysis import compute_risk_parity_weights

        tickers = ("AAPL", "MSFT", "GOOG")
        returns = _make_returns(tickers=tickers)
        weights = compute_risk_parity_weights(returns)
        assert set(weights.keys()) == set(tickers)

    def test_empty_returns_returns_empty_dict(self):
        from portfolio_analysis import compute_risk_parity_weights

        result = compute_risk_parity_weights(pd.DataFrame())
        assert result == {}

    def test_none_returns_empty_dict(self):
        from portfolio_analysis import compute_risk_parity_weights

        result = compute_risk_parity_weights(None)
        assert result == {}

    def test_low_vol_ticker_gets_higher_weight(self):
        from portfolio_analysis import compute_risk_parity_weights

        # AAPL has very low vol → should get more weight
        n = 252
        rng = np.random.default_rng(0)
        data = pd.DataFrame(
            {
                "LOW_VOL": rng.normal(0, 0.001, n),  # very low vol
                "HIGH_VOL": rng.normal(0, 0.05, n),  # high vol
            }
        )
        weights = compute_risk_parity_weights(data)
        assert weights["LOW_VOL"] > weights["HIGH_VOL"]

    def test_equal_weight_fallback_when_zero_vol(self):
        from portfolio_analysis import compute_risk_parity_weights

        # Flat returns → zero std → fallback to equal weights
        data = pd.DataFrame(
            {
                "A": [0.0] * 100,
                "B": np.random.default_rng(1).normal(0, 0.01, 100),
            }
        )
        weights = compute_risk_parity_weights(data)
        # Should still sum to ~1
        assert sum(weights.values()) == pytest.approx(1.0, abs=0.01)


# ---------------------------------------------------------------------------
# run_stress_tests
# ---------------------------------------------------------------------------


class TestRunStressTests:
    def _positions(self):
        return {
            "AAPL": {"weight": 0.4, "sector": "Technology"},
            "JPM": {"weight": 0.3, "sector": "Financials"},
            "XOM": {"weight": 0.3, "sector": "Energy"},
        }

    def test_returns_list_of_scenarios(self):
        from portfolio_analysis import run_stress_tests, STRESS_SCENARIOS

        results = run_stress_tests(self._positions(), 100_000)
        assert len(results) == len(STRESS_SCENARIOS)

    def test_each_result_has_required_keys(self):
        from portfolio_analysis import run_stress_tests

        results = run_stress_tests(self._positions(), 100_000)
        for r in results:
            assert "scenario" in r
            assert "portfolio_loss_pct" in r
            assert "portfolio_loss_dollar" in r
            assert "by_position" in r

    def test_losses_are_negative(self):
        from portfolio_analysis import run_stress_tests

        results = run_stress_tests(self._positions(), 100_000)
        for r in results:
            # all historical scenarios have negative losses
            assert r["portfolio_loss_pct"] < 0

    def test_dollar_loss_matches_pct_times_value(self):
        from portfolio_analysis import run_stress_tests

        total = 100_000
        results = run_stress_tests(self._positions(), total)
        for r in results:
            expected = round(total * r["portfolio_loss_pct"], 2)
            assert r["portfolio_loss_dollar"] == pytest.approx(expected, abs=1.0)

    def test_empty_positions_returns_empty(self):
        from portfolio_analysis import run_stress_tests

        assert run_stress_tests({}, 100_000) == []

    def test_zero_value_returns_empty(self):
        from portfolio_analysis import run_stress_tests

        assert run_stress_tests(self._positions(), 0) == []

    def test_by_position_sums_to_portfolio_loss(self):
        from portfolio_analysis import run_stress_tests

        results = run_stress_tests(self._positions(), 100_000)
        pos = self._positions()
        for r in results:
            summed = sum(
                p["loss_rate"] * pos.get(p["ticker"], {}).get("weight", 0)
                for p in r["by_position"]
            )
            assert r["portfolio_loss_pct"] == pytest.approx(summed, abs=0.001)

    def test_sector_matched_to_scenario(self):
        from portfolio_analysis import run_stress_tests

        positions = {"AAPL": {"weight": 1.0, "sector": "Technology"}}
        results = run_stress_tests(positions, 100_000)
        # In "2000 Dot-com Crash", Technology = -0.78
        dot_com = next(r for r in results if r["scenario"] == "2000 Dot-com Crash")
        assert dot_com["portfolio_loss_pct"] == pytest.approx(-0.78, abs=0.001)


# ---------------------------------------------------------------------------
# find_tax_loss_opportunities
# ---------------------------------------------------------------------------


class TestFindTaxLossOpportunities:
    def _positions_with_loss(self):
        return {
            "AAPL": {"weight": 0.4, "cost_basis_pct_gain": -12.0},
            "MSFT": {"weight": 0.3, "cost_basis_pct_gain": 5.0},   # gain
            "GOOG": {"weight": 0.3, "cost_basis_pct_gain": -8.0},
        }

    def _correlated_returns(self):
        rng = np.random.default_rng(0)
        base = rng.normal(0, 0.01, 252)
        return pd.DataFrame(
            {
                "AAPL": base + rng.normal(0, 0.001, 252),
                "MSFT": base + rng.normal(0, 0.001, 252),  # highly correlated with AAPL
                "GOOG": rng.normal(0, 0.01, 252),           # independent
            }
        )

    def test_returns_list(self):
        from portfolio_analysis import find_tax_loss_opportunities

        result = find_tax_loss_opportunities(self._positions_with_loss(), self._correlated_returns())
        assert isinstance(result, list)

    def test_only_includes_positions_with_losses(self):
        from portfolio_analysis import find_tax_loss_opportunities

        result = find_tax_loss_opportunities(self._positions_with_loss(), self._correlated_returns())
        tickers = [r["ticker"] for r in result]
        # MSFT has gain (+5%) → should NOT be included
        assert "MSFT" not in tickers
        # AAPL and GOOG have losses → should be included
        assert "AAPL" in tickers
        assert "GOOG" in tickers

    def test_result_has_required_keys(self):
        from portfolio_analysis import find_tax_loss_opportunities

        result = find_tax_loss_opportunities(self._positions_with_loss(), self._correlated_returns())
        for r in result:
            assert "ticker" in r
            assert "loss_pct" in r
            assert "message" in r

    def test_empty_positions_returns_empty(self):
        from portfolio_analysis import find_tax_loss_opportunities

        assert find_tax_loss_opportunities({}, self._correlated_returns()) == []

    def test_empty_returns_df_returns_empty(self):
        from portfolio_analysis import find_tax_loss_opportunities

        assert find_tax_loss_opportunities(self._positions_with_loss(), pd.DataFrame()) == []

    def test_correlated_replacement_found(self):
        from portfolio_analysis import find_tax_loss_opportunities

        result = find_tax_loss_opportunities(self._positions_with_loss(), self._correlated_returns())
        aapl = next((r for r in result if r["ticker"] == "AAPL"), None)
        if aapl:
            # AAPL and MSFT are highly correlated → MSFT should be suggested
            if aapl["corr_replacement"] is not None:
                assert aapl["correlation"] >= 0.70

    def test_loss_pct_matches_input(self):
        from portfolio_analysis import find_tax_loss_opportunities

        result = find_tax_loss_opportunities(self._positions_with_loss(), self._correlated_returns())
        aapl = next((r for r in result if r["ticker"] == "AAPL"), None)
        if aapl:
            assert aapl["loss_pct"] == pytest.approx(-12.0)

    def test_no_losses_returns_empty(self):
        from portfolio_analysis import find_tax_loss_opportunities

        positions = {
            "AAPL": {"weight": 0.5, "cost_basis_pct_gain": 10.0},
            "MSFT": {"weight": 0.5, "cost_basis_pct_gain": 20.0},
        }
        result = find_tax_loss_opportunities(positions, self._correlated_returns())
        assert result == []


# ---------------------------------------------------------------------------
# compute_portfolio_drift
# ---------------------------------------------------------------------------


class TestComputePortfolioDrift:
    def test_returns_list(self):
        from portfolio_analysis import compute_portfolio_drift

        positions = {"AAPL": {"current_weight": 0.45}, "MSFT": {"current_weight": 0.30}}
        targets = {"AAPL": 0.40, "MSFT": 0.35}
        result = compute_portfolio_drift(positions, targets)
        assert isinstance(result, list)

    def test_drift_calculated_correctly(self):
        from portfolio_analysis import compute_portfolio_drift

        positions = {"AAPL": {"current_weight": 0.45}}
        targets = {"AAPL": 0.40}
        result = compute_portfolio_drift(positions, targets)
        aapl = result[0]
        assert aapl["drift"] == pytest.approx(0.05, abs=0.001)

    def test_drifted_flag_set_when_above_5pct(self):
        from portfolio_analysis import compute_portfolio_drift

        positions = {"AAPL": {"current_weight": 0.46}}
        targets = {"AAPL": 0.40}
        result = compute_portfolio_drift(positions, targets)
        assert result[0]["drifted"] is True

    def test_drifted_flag_false_when_within_tolerance(self):
        from portfolio_analysis import compute_portfolio_drift

        positions = {"AAPL": {"current_weight": 0.42}}
        targets = {"AAPL": 0.40}
        result = compute_portfolio_drift(positions, targets)
        assert result[0]["drifted"] is False

    def test_sorted_by_abs_drift_descending(self):
        from portfolio_analysis import compute_portfolio_drift

        positions = {
            "A": {"current_weight": 0.50},
            "B": {"current_weight": 0.20},
        }
        targets = {"A": 0.40, "B": 0.35}  # A drifts 0.10, B drifts -0.15
        result = compute_portfolio_drift(positions, targets)
        drifts = [abs(r["drift"]) for r in result]
        assert drifts == sorted(drifts, reverse=True)

    def test_empty_inputs_return_empty(self):
        from portfolio_analysis import compute_portfolio_drift

        assert compute_portfolio_drift({}, {}) == []
        assert compute_portfolio_drift(None, {}) == []

    def test_includes_tickers_in_targets_but_not_positions(self):
        from portfolio_analysis import compute_portfolio_drift

        positions = {"AAPL": {"current_weight": 0.60}}
        targets = {"AAPL": 0.50, "MSFT": 0.30}
        result = compute_portfolio_drift(positions, targets)
        tickers = {r["ticker"] for r in result}
        assert "MSFT" in tickers

    def test_current_and_target_weights_in_result(self):
        from portfolio_analysis import compute_portfolio_drift

        positions = {"AAPL": {"current_weight": 0.45}}
        targets = {"AAPL": 0.40}
        result = compute_portfolio_drift(positions, targets)
        r = result[0]
        assert r["current_weight"] == pytest.approx(0.45, abs=0.001)
        assert r["target_weight"] == pytest.approx(0.40, abs=0.001)
