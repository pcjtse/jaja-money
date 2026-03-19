"""Tests for alerts.py — check_signal_changes, check_drift_alerts, _get_severity."""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Snapshot history helpers (replacing lambdas for ruff E731 compliance)
# ---------------------------------------------------------------------------


def _one_snapshot(_sym):
    return [{"factor_score": 60, "risk_level": "Moderate"}]


def _no_snapshots(_sym):
    return []


def _factor_increase(_sym):
    return [
        {"factor_score": 65, "risk_level": "Moderate"},
        {"factor_score": 50, "risk_level": "Moderate"},
    ]


def _factor_decrease(_sym):
    return [
        {"factor_score": 45, "risk_level": "Moderate"},
        {"factor_score": 60, "risk_level": "Moderate"},
    ]


def _small_delta(_sym):
    return [
        {"factor_score": 65, "risk_level": "Moderate"},
        {"factor_score": 60, "risk_level": "Moderate"},
    ]


def _risk_upgrade(_sym):
    return [
        {"factor_score": 60, "risk_level": "Low"},
        {"factor_score": 60, "risk_level": "High"},
    ]


def _risk_deterioration(_sym):
    return [
        {"factor_score": 50, "risk_level": "High"},
        {"factor_score": 50, "risk_level": "Low"},
    ]


def _same_risk(_sym):
    return [
        {"factor_score": 60, "risk_level": "Moderate"},
        {"factor_score": 60, "risk_level": "Moderate"},
    ]


def _big_factor(_sym):
    return [
        {"factor_score": 80, "risk_level": "Moderate"},
        {"factor_score": 60, "risk_level": "Moderate"},
    ]


def _symbol_check(_sym):
    return [
        {"factor_score": 75, "risk_level": "Moderate"},
        {"factor_score": 60, "risk_level": "Moderate"},
    ]


def _both_changes(_sym):
    return [
        {"factor_score": 75, "risk_level": "High"},
        {"factor_score": 60, "risk_level": "Moderate"},
    ]


# ---------------------------------------------------------------------------
# check_signal_changes
# ---------------------------------------------------------------------------


class TestCheckSignalChanges:
    def test_returns_empty_when_fewer_than_two_snapshots(self):
        from alerts import check_signal_changes

        result = check_signal_changes("AAPL", 65, "Moderate", history_fn=_one_snapshot)
        assert result == []

    def test_returns_empty_when_no_snapshots(self):
        from alerts import check_signal_changes

        result = check_signal_changes("AAPL", 65, "Moderate", history_fn=_no_snapshots)
        assert result == []

    def test_detects_large_factor_score_increase(self):
        from alerts import check_signal_changes

        # Old factor = 50, new = 65 → delta = +15 > 10
        result = check_signal_changes("AAPL", 65, "Moderate", history_fn=_factor_increase)
        factor_changes = [r for r in result if r["change_type"] == "factor_score"]
        assert len(factor_changes) == 1
        assert factor_changes[0]["delta"] == 15

    def test_detects_large_factor_score_decrease(self):
        from alerts import check_signal_changes

        result = check_signal_changes("AAPL", 45, "Moderate", history_fn=_factor_decrease)
        factor_changes = [r for r in result if r["change_type"] == "factor_score"]
        assert len(factor_changes) == 1
        assert factor_changes[0]["delta"] == -15

    def test_no_change_when_delta_within_10(self):
        from alerts import check_signal_changes

        result = check_signal_changes("AAPL", 65, "Moderate", history_fn=_small_delta)
        factor_changes = [r for r in result if r["change_type"] == "factor_score"]
        assert len(factor_changes) == 0

    def test_detects_risk_level_upgrade(self):
        from alerts import check_signal_changes

        # Risk went from High (4) → Low (1) → improvement
        result = check_signal_changes("AAPL", 60, "Low", history_fn=_risk_upgrade)
        risk_changes = [r for r in result if r["change_type"] == "risk_level"]
        assert len(risk_changes) == 1
        assert risk_changes[0]["delta"] < 0  # negative = improvement

    def test_detects_risk_level_deterioration(self):
        from alerts import check_signal_changes

        result = check_signal_changes("AAPL", 50, "High", history_fn=_risk_deterioration)
        risk_changes = [r for r in result if r["change_type"] == "risk_level"]
        assert len(risk_changes) == 1
        assert risk_changes[0]["delta"] > 0  # positive = elevated

    def test_no_risk_change_when_same_level(self):
        from alerts import check_signal_changes

        result = check_signal_changes("AAPL", 60, "Moderate", history_fn=_same_risk)
        risk_changes = [r for r in result if r["change_type"] == "risk_level"]
        assert len(risk_changes) == 0

    def test_change_dict_has_required_keys(self):
        from alerts import check_signal_changes

        result = check_signal_changes("AAPL", 80, "Moderate", history_fn=_big_factor)
        for change in result:
            for key in ("symbol", "change_type", "old_value", "new_value", "delta", "message"):
                assert key in change

    def test_handles_history_fn_exception_gracefully(self):
        from alerts import check_signal_changes

        def bad_fn(sym):
            raise RuntimeError("DB error")

        result = check_signal_changes("AAPL", 60, "Moderate", history_fn=bad_fn)
        assert result == []

    def test_symbol_set_in_change_events(self):
        from alerts import check_signal_changes

        result = check_signal_changes("AAPL", 75, "Moderate", history_fn=_symbol_check)
        for change in result:
            assert change["symbol"] == "AAPL"

    def test_both_factor_and_risk_change_detected(self):
        from alerts import check_signal_changes

        result = check_signal_changes("AAPL", 75, "High", history_fn=_both_changes)
        change_types = {r["change_type"] for r in result}
        assert "factor_score" in change_types
        assert "risk_level" in change_types


# ---------------------------------------------------------------------------
# check_drift_alerts
# ---------------------------------------------------------------------------


class TestCheckDriftAlerts:
    def test_returns_none_when_within_threshold(self):
        from alerts import check_drift_alerts

        result = check_drift_alerts("AAPL", 0.42, 0.40, threshold=0.05)
        assert result is None

    def test_returns_dict_when_over_threshold(self):
        from alerts import check_drift_alerts

        result = check_drift_alerts("AAPL", 0.50, 0.40, threshold=0.05)
        assert result is not None
        assert result["symbol"] == "AAPL"

    def test_drift_value_correct(self):
        from alerts import check_drift_alerts

        result = check_drift_alerts("AAPL", 0.50, 0.40)
        assert result["drift"] == pytest.approx(0.10, abs=0.001)

    def test_overweight_message(self):
        from alerts import check_drift_alerts

        result = check_drift_alerts("AAPL", 0.50, 0.40)
        assert "overweight" in result["message"].lower()

    def test_underweight_message(self):
        from alerts import check_drift_alerts

        result = check_drift_alerts("AAPL", 0.30, 0.40)
        assert "underweight" in result["message"].lower()

    def test_exact_threshold_returns_none(self):
        from alerts import check_drift_alerts

        # drift = 0.05, threshold = 0.05 → NOT over threshold (strict >)
        result = check_drift_alerts("AAPL", 0.45, 0.40, threshold=0.05)
        assert result is None

    def test_just_over_threshold_returns_dict(self):
        from alerts import check_drift_alerts

        result = check_drift_alerts("AAPL", 0.451, 0.40, threshold=0.05)
        assert result is not None

    def test_result_has_all_required_keys(self):
        from alerts import check_drift_alerts

        result = check_drift_alerts("AAPL", 0.50, 0.40)
        assert result is not None
        for key in ("symbol", "current_weight", "target_weight", "drift", "message"):
            assert key in result

    def test_current_and_target_in_result(self):
        from alerts import check_drift_alerts

        result = check_drift_alerts("MSFT", 0.50, 0.35)
        assert result["current_weight"] == pytest.approx(0.50)
        assert result["target_weight"] == pytest.approx(0.35)

    def test_custom_threshold(self):
        from alerts import check_drift_alerts

        # With threshold=0.02, drift of 0.03 should trigger
        result = check_drift_alerts("AAPL", 0.43, 0.40, threshold=0.02)
        assert result is not None


# ---------------------------------------------------------------------------
# _get_severity
# ---------------------------------------------------------------------------


class TestGetSeverity:
    def test_risk_condition_high_value_is_critical(self):
        from alerts import _get_severity

        result = _get_severity("Risk Score", 50, 80)
        assert result == "critical"

    def test_risk_condition_low_value_is_warning(self):
        from alerts import _get_severity

        result = _get_severity("Risk Score", 50, 60)
        assert result == "warning"

    def test_non_risk_condition_is_warning(self):
        from alerts import _get_severity

        result = _get_severity("Price Above", 150.0, 155.0)
        assert result == "warning"
