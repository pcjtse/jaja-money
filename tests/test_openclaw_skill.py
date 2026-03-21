"""Tests for openclaw_skill.py — OpenClaw Skill Package."""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch
import time

import pytest


# ---------------------------------------------------------------------------
# Module-level stubs for pandas-dependent modules
# ---------------------------------------------------------------------------


def _stub_factors_and_guardrails():
    """Install lightweight stubs for factors / guardrails / screener so that
    tests work even when pandas/numpy are absent."""
    for mod_name in ("factors", "guardrails", "screener"):
        if mod_name not in sys.modules:
            sys.modules[mod_name] = types.ModuleType(mod_name)

    factors_mod = sys.modules["factors"]
    if not hasattr(factors_mod, "compute_factors"):
        factors_mod.compute_factors = MagicMock(
            return_value={
                "composite_score": 70,
                "composite_label": "Buy",
                "factors": [],
            }
        )

    guardrails_mod = sys.modules["guardrails"]
    if not hasattr(guardrails_mod, "compute_risk"):
        guardrails_mod.compute_risk = MagicMock(
            return_value={
                "risk_score": 40,
                "risk_level": "Low",
                "flags": [],
            }
        )

    screener_mod = sys.modules["screener"]
    if not hasattr(screener_mod, "run_screener"):
        screener_mod.run_screener = MagicMock(return_value=[])


_stub_factors_and_guardrails()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_api():
    """Minimal mock FinnhubAPI."""
    api = MagicMock()
    api.get_quote.return_value = {"c": 150.0, "dp": 1.2}
    api.get_financials.return_value = {
        "peBasicExclExtraTTM": 28.0,
        "marketCapitalization": 2_500_000,
    }
    api.get_daily.return_value = {"c": [100.0] * 60, "t": list(range(60))}
    api.get_news.return_value = []
    api.get_profile.return_value = {
        "name": "Apple Inc.",
        "finnhubIndustry": "Technology",
    }
    api.fetch_all_parallel.return_value = {
        "quote": {"c": 150.0, "dp": 1.2},
        "profile": {"name": "Apple Inc.", "finnhubIndustry": "Technology"},
        "financials": {"peBasicExclExtraTTM": 28.0},
        "daily": {"c": [100.0] * 60, "t": list(range(60))},
        "news": [],
    }
    return api


# ---------------------------------------------------------------------------
# Skill manifest tests
# ---------------------------------------------------------------------------


def test_skill_manifest_has_required_fields():
    from openclaw_skill import SKILL_MANIFEST

    assert SKILL_MANIFEST["name"] == "jaja-money"
    assert "version" in SKILL_MANIFEST
    assert "description" in SKILL_MANIFEST
    assert "functions" in SKILL_MANIFEST
    assert "endpoints" in SKILL_MANIFEST


def test_skill_manifest_functions():
    from openclaw_skill import SKILL_MANIFEST

    expected = {"analyze", "screen", "score", "get_alerts", "research"}
    assert set(SKILL_MANIFEST["functions"].keys()) == expected


def test_get_skill_manifest_returns_manifest():
    from openclaw_skill import get_skill_manifest, SKILL_MANIFEST

    result = get_skill_manifest()
    assert result is SKILL_MANIFEST


# ---------------------------------------------------------------------------
# derive_signal tests
# ---------------------------------------------------------------------------


def test_derive_signal_buy():
    from openclaw_skill import derive_signal

    result = derive_signal(factor_score=70, risk_score=40)
    assert result["signal"] == "BUY"
    assert result["confidence"] > 50


def test_derive_signal_sell_low_factor():
    from openclaw_skill import derive_signal

    result = derive_signal(factor_score=30, risk_score=40)
    assert result["signal"] == "SELL"


def test_derive_signal_sell_high_risk():
    from openclaw_skill import derive_signal

    result = derive_signal(factor_score=60, risk_score=80)
    assert result["signal"] == "SELL"


def test_derive_signal_hold():
    from openclaw_skill import derive_signal

    result = derive_signal(factor_score=55, risk_score=55)
    assert result["signal"] == "HOLD"
    assert result["confidence"] == 50


def test_derive_signal_confidence_capped_at_100():
    from openclaw_skill import derive_signal

    result = derive_signal(factor_score=100, risk_score=0)
    assert result["confidence"] <= 100


# ---------------------------------------------------------------------------
# analyze() tests
# ---------------------------------------------------------------------------


def test_analyze_returns_expected_keys(mock_api):
    from openclaw_skill import analyze

    sys.modules["factors"].compute_factors = MagicMock(
        return_value={
            "composite_score": 72,
            "composite_label": "Strong Buy",
            "factors": [],
        }
    )
    sys.modules["guardrails"].compute_risk = MagicMock(
        return_value={
            "risk_score": 35,
            "risk_level": "Low",
            "flags": [],
        }
    )
    with patch("openclaw_skill._get_api", return_value=mock_api):
        result = analyze("AAPL")

    assert result["symbol"] == "AAPL"
    assert result["signal"] == "BUY"
    assert "factor_score" in result
    assert "risk_score" in result
    assert "timestamp" in result
    assert result["timestamp"] <= int(time.time()) + 2


def test_analyze_upcases_ticker(mock_api):
    from openclaw_skill import analyze

    sys.modules["factors"].compute_factors = MagicMock(
        return_value={
            "composite_score": 50,
            "composite_label": "Hold",
            "factors": [],
        }
    )
    sys.modules["guardrails"].compute_risk = MagicMock(
        return_value={
            "risk_score": 50,
            "risk_level": "Moderate",
            "flags": [],
        }
    )
    with patch("openclaw_skill._get_api", return_value=mock_api):
        result = analyze("aapl")

    assert result["symbol"] == "AAPL"


# ---------------------------------------------------------------------------
# score() tests
# ---------------------------------------------------------------------------


def test_score_returns_signal(mock_api):
    from openclaw_skill import score

    sys.modules["factors"].compute_factors = MagicMock(
        return_value={
            "composite_score": 68,
            "composite_label": "Buy",
            "factors": [],
        }
    )
    sys.modules["guardrails"].compute_risk = MagicMock(
        return_value={
            "risk_score": 45,
            "risk_level": "Moderate",
            "flags": [],
        }
    )
    with patch("openclaw_skill._get_api", return_value=mock_api):
        result = score("MSFT")

    assert result["symbol"] == "MSFT"
    assert result["signal"] in ("BUY", "HOLD", "SELL")
    assert 0 <= result["confidence"] <= 100


# ---------------------------------------------------------------------------
# get_alerts() tests
# ---------------------------------------------------------------------------


def test_get_alerts_no_symbol(tmp_path, monkeypatch):
    import alerts as a

    monkeypatch.setattr(a, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(a, "_ALERTS_FILE", tmp_path / "alerts.json")

    from alerts import add_alert

    add_alert("AAPL", "Price Above", 200.0)
    add_alert("MSFT", "Price Below", 300.0)

    from openclaw_skill import get_alerts

    result = get_alerts()
    assert result["active_count"] == 2
    assert result["symbol"] is None
    assert "timestamp" in result


def test_get_alerts_filtered_by_symbol(tmp_path, monkeypatch):
    import alerts as a

    monkeypatch.setattr(a, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(a, "_ALERTS_FILE", tmp_path / "alerts.json")

    from alerts import add_alert

    add_alert("AAPL", "Price Above", 200.0)
    add_alert("MSFT", "Price Below", 300.0)

    from openclaw_skill import get_alerts

    result = get_alerts("AAPL")
    assert result["active_count"] == 1
    assert result["active"][0]["symbol"] == "AAPL"


# ---------------------------------------------------------------------------
# screen() tests
# ---------------------------------------------------------------------------


def test_screen_returns_results_and_total(mock_api):
    from openclaw_skill import screen

    sys.modules["screener"].run_screener = MagicMock(
        return_value=[
            {"symbol": "AAPL", "factor_score": 72},
            {"symbol": "MSFT", "factor_score": 68},
        ]
    )
    with patch("openclaw_skill._get_api", return_value=mock_api):
        result = screen(["AAPL", "MSFT"])

    assert result["total"] == 2
    assert len(result["results"]) == 2
    assert result["filters"]["min_factor_score"] == 0
    assert "timestamp" in result


def test_screen_respects_limit(mock_api):
    from openclaw_skill import screen

    sys.modules["screener"].run_screener = MagicMock(
        return_value=[{"symbol": f"T{i}"} for i in range(10)]
    )
    with patch("openclaw_skill._get_api", return_value=mock_api):
        result = screen(["T0", "T1", "T2", "T3", "T4"], limit=3)

    assert len(result["results"]) == 3
    assert result["total"] == 10
