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
    tests work even when pandas/numpy are absent.

    Tries the real import first; only installs a stub when the import fails
    (e.g. pandas is missing), so the real module is not shadowed in envs
    where pandas IS available.
    """
    import importlib

    for mod_name in ("factors", "guardrails", "screener"):
        if mod_name not in sys.modules:
            try:
                importlib.import_module(mod_name)
            except (ImportError, ModuleNotFoundError):
                sys.modules[mod_name] = types.ModuleType(mod_name)

    factors_mod = sys.modules.get("factors")
    if factors_mod is not None and not hasattr(factors_mod, "compute_factors"):
        factors_mod.compute_factors = MagicMock(
            return_value={
                "composite_score": 70,
                "composite_label": "Buy",
                "factors": [],
            }
        )

    guardrails_mod = sys.modules.get("guardrails")
    if guardrails_mod is not None and not hasattr(guardrails_mod, "compute_risk"):
        guardrails_mod.compute_risk = MagicMock(
            return_value={
                "risk_score": 40,
                "risk_level": "Low",
                "flags": [],
            }
        )

    screener_mod = sys.modules.get("screener")
    if screener_mod is not None and not hasattr(screener_mod, "run_screener"):
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


# ---------------------------------------------------------------------------
# JajaMoneyClient — remote HTTP client
# ---------------------------------------------------------------------------


class TestJajaMoneyClient:
    """Tests for the JajaMoneyClient remote HTTP wrapper."""

    def _make_client(self, base_url="http://localhost:8080", api_key=None):
        from openclaw_skill import JajaMoneyClient

        return JajaMoneyClient(base_url=base_url, api_key=api_key)

    def test_client_sets_base_url(self):
        client = self._make_client("http://remote-host:9000")
        assert client.base_url == "http://remote-host:9000"

    def test_client_strips_trailing_slash(self):
        client = self._make_client("http://remote-host:9000/")
        assert client.base_url == "http://remote-host:9000"

    def test_client_sets_api_key_header(self):
        client = self._make_client(api_key="mysecret")
        assert client._headers.get("X-API-Key") == "mysecret"

    def test_client_no_api_key_when_none(self):
        client = self._make_client(api_key=None)
        assert "X-API-Key" not in client._headers

    def test_client_analyze_calls_post(self):
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"symbol": "AAPL", "factor_score": 70}
        with patch.object(
            client._requests, "post", return_value=mock_resp
        ) as mock_post:
            result = client.analyze("AAPL")
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert "/analyze" in call_kwargs[0][0]
        assert result["symbol"] == "AAPL"

    def test_client_score_calls_post(self):
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"symbol": "MSFT", "factor_score": 65}
        with patch.object(
            client._requests, "post", return_value=mock_resp
        ) as mock_post:
            result = client.score("MSFT")
        mock_post.assert_called_once()
        assert "/score" in mock_post.call_args[0][0]
        assert result["symbol"] == "MSFT"

    def test_client_screen_calls_post(self):
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"results": [], "total": 0}
        with patch.object(
            client._requests, "post", return_value=mock_resp
        ) as mock_post:
            result = client.screen(["AAPL", "MSFT"])
        mock_post.assert_called_once()
        assert "/screen" in mock_post.call_args[0][0]
        assert result["total"] == 0

    def test_client_get_alerts_calls_get(self):
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"active_count": 0, "active": []}
        with patch.object(client._requests, "get", return_value=mock_resp) as mock_get:
            result = client.get_alerts()
        mock_get.assert_called_once()
        assert "/alerts" in mock_get.call_args[0][0]
        assert result["active_count"] == 0

    def test_client_get_alerts_with_symbol(self):
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "active_count": 1,
            "active": [{"symbol": "AAPL"}],
        }
        with patch.object(client._requests, "get", return_value=mock_resp) as mock_get:
            result = client.get_alerts("AAPL")
        call_kwargs = mock_get.call_args
        params = call_kwargs[1].get("params") or call_kwargs.kwargs.get("params", {})
        assert params.get("symbol") == "AAPL"
        assert result["active_count"] == 1

    def test_client_signals_calls_post(self):
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"signals": [], "count": 0}
        with patch.object(
            client._requests, "post", return_value=mock_resp
        ) as mock_post:
            result = client.signals(["AAPL"])
        assert "/signals" in mock_post.call_args[0][0]
        assert result["count"] == 0

    def test_client_health_calls_get(self):
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"status": "ok"}
        with patch.object(client._requests, "get", return_value=mock_resp) as mock_get:
            result = client.health()
        assert "/health" in mock_get.call_args[0][0]
        assert result["status"] == "ok"


# ---------------------------------------------------------------------------
# Remote mode via JAJA_API_URL env var
# ---------------------------------------------------------------------------


class TestRemoteMode:
    """Tests that skill functions delegate to JajaMoneyClient when JAJA_API_URL is set."""

    def test_analyze_delegates_to_remote_client(self, monkeypatch):
        monkeypatch.setenv("JAJA_API_URL", "http://remote:8080")
        from openclaw_skill import analyze, JajaMoneyClient

        expected = {"symbol": "AAPL", "factor_score": 72, "signal": "BUY"}
        with patch.object(JajaMoneyClient, "analyze", return_value=expected) as mock_m:
            result = analyze("AAPL")
        mock_m.assert_called_once_with("AAPL", use_cache=True)
        assert result == expected

    def test_score_delegates_to_remote_client(self, monkeypatch):
        monkeypatch.setenv("JAJA_API_URL", "http://remote:8080")
        from openclaw_skill import score, JajaMoneyClient

        expected = {"symbol": "MSFT", "factor_score": 65}
        with patch.object(JajaMoneyClient, "score", return_value=expected) as mock_m:
            result = score("MSFT")
        mock_m.assert_called_once_with("MSFT")
        assert result == expected

    def test_screen_delegates_to_remote_client(self, monkeypatch):
        monkeypatch.setenv("JAJA_API_URL", "http://remote:8080")
        from openclaw_skill import screen, JajaMoneyClient

        expected = {"results": [], "total": 0}
        with patch.object(JajaMoneyClient, "screen", return_value=expected) as mock_m:
            result = screen(["AAPL"])
        mock_m.assert_called_once()
        assert result == expected

    def test_get_alerts_delegates_to_remote_client(self, monkeypatch):
        monkeypatch.setenv("JAJA_API_URL", "http://remote:8080")
        from openclaw_skill import get_alerts, JajaMoneyClient

        expected = {"active_count": 0, "active": []}
        with patch.object(
            JajaMoneyClient, "get_alerts", return_value=expected
        ) as mock_m:
            result = get_alerts()
        mock_m.assert_called_once_with(None)
        assert result == expected

    def test_research_delegates_to_remote_client(self, monkeypatch):
        monkeypatch.setenv("JAJA_API_URL", "http://remote:8080")
        from openclaw_skill import research, JajaMoneyClient

        expected = {"symbol": "AAPL", "memo": "Investment memo..."}
        with patch.object(JajaMoneyClient, "research", return_value=expected) as mock_m:
            result = research("AAPL", question="What is the bear case?")
        mock_m.assert_called_once()
        assert result == expected

    def test_no_remote_when_env_not_set(self, monkeypatch):
        monkeypatch.delenv("JAJA_API_URL", raising=False)
        from openclaw_skill import _get_remote_client

        assert _get_remote_client() is None

    def test_remote_client_created_when_env_set(self, monkeypatch):
        monkeypatch.setenv("JAJA_API_URL", "http://myserver:8080")
        from openclaw_skill import _get_remote_client, JajaMoneyClient

        client = _get_remote_client()
        assert isinstance(client, JajaMoneyClient)
        assert client.base_url == "http://myserver:8080"

    def test_remote_client_uses_api_key(self, monkeypatch):
        monkeypatch.setenv("JAJA_API_URL", "http://myserver:8080")
        monkeypatch.setenv("JAJA_API_KEY", "testkey")
        from openclaw_skill import _get_remote_client

        client = _get_remote_client()
        assert client._headers.get("X-API-Key") == "testkey"
