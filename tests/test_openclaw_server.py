"""Tests for OpenClaw server endpoints (/signals, /openclaw/*).

Skips all tests if fastapi or httpx (required for TestClient) are not installed.
"""

from __future__ import annotations

import importlib
import os
import sys
import types

import pytest
from unittest.mock import MagicMock, patch

try:
    from fastapi.testclient import TestClient
except Exception:
    pytest.skip("fastapi[testclient] not available", allow_module_level=True)


# ---------------------------------------------------------------------------
# Pre-stub heavy deps (pandas, numpy) so patch() can find the modules
# ---------------------------------------------------------------------------


def _stub_heavy_deps() -> None:
    """Install lightweight stubs for modules that require pandas/numpy.

    Tries the real import first; only creates a stub when the real import
    fails (e.g. pandas not installed), so real modules are never shadowed
    in environments where they are available.
    """
    mod_mapping = {
        "factors": "src.analysis.factors",
        "guardrails": "src.analysis.guardrails",
        "screener": "src.trading.screener",
    }
    for mod_name, full_name in mod_mapping.items():
        if full_name not in sys.modules:
            try:
                importlib.import_module(full_name)
            except (ImportError, ModuleNotFoundError):
                sys.modules[full_name] = types.ModuleType(full_name)

    factors_mod = sys.modules.get("src.analysis.factors")
    if factors_mod is not None and not hasattr(factors_mod, "compute_factors"):
        factors_mod.compute_factors = MagicMock(
            return_value={
                "composite_score": 70,
                "composite_label": "Buy",
                "factors": [],
            }
        )

    guardrails_mod = sys.modules.get("src.analysis.guardrails")
    if guardrails_mod is not None and not hasattr(guardrails_mod, "compute_risk"):
        guardrails_mod.compute_risk = MagicMock(
            return_value={
                "risk_score": 40,
                "risk_level": "Low",
                "flags": [],
            }
        )

    screener_mod = sys.modules.get("src.trading.screener")
    if screener_mod is not None and not hasattr(screener_mod, "run_screener"):
        screener_mod.run_screener = MagicMock(return_value=[])


_stub_heavy_deps()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    os.environ.pop("JAJA_API_KEY", None)

    import src.services.server as server

    server._api_instance = None
    server._api_error = None

    with TestClient(server.app) as c:
        yield c


def _mock_api():
    """Minimal mock FinnhubAPI for OpenClaw endpoint tests."""
    mock = MagicMock()
    # Generate simple price series without numpy
    import random as _random

    rng = _random.Random(42)
    prices = [100.0 + sum(rng.gauss(0, 1) for _ in range(i + 1)) for i in range(252)]
    ts = list(range(1_600_000_000, 1_600_000_000 + 252 * 86400, 86400))

    mock.get_quote.return_value = {"c": 150.0, "dp": 1.5}
    mock.get_financials.return_value = {"peBasicExclExtraTTM": 25.0}
    mock.get_daily.return_value = {"c": prices, "t": ts, "v": [1_000_000] * 252}
    mock.get_news.return_value = []
    mock.fetch_all_parallel.return_value = {
        "quote": {"c": 150.0, "dp": 1.5},
        "profile": {"name": "Apple Inc.", "finnhubIndustry": "Technology"},
        "financials": {"peBasicExclExtraTTM": 25.0},
        "daily": {"c": prices, "t": ts, "v": [1_000_000] * 252},
        "news": [],
    }
    return mock


# ---------------------------------------------------------------------------
# /signals endpoint
# ---------------------------------------------------------------------------


class TestSignalsEndpoint:
    def test_signals_returns_200(self, client):
        import src.services.server as server

        server._api_instance = _mock_api()
        with (
            patch("src.analysis.factors.compute_factors") as mf,
            patch("src.analysis.guardrails.compute_risk") as mr,
        ):
            mf.return_value = {
                "composite_score": 70,
                "composite_label": "Buy",
                "factors": [],
            }
            mr.return_value = {
                "risk_score": 40,
                "risk_level": "Low",
                "flags": [],
            }
            response = client.post("/signals", json={"symbols": ["AAPL"]})

        assert response.status_code == 200

    def test_signals_returns_list(self, client):
        import src.services.server as server

        server._api_instance = _mock_api()
        with (
            patch("src.analysis.factors.compute_factors") as mf,
            patch("src.analysis.guardrails.compute_risk") as mr,
        ):
            mf.return_value = {
                "composite_score": 70,
                "composite_label": "Buy",
                "factors": [],
            }
            mr.return_value = {
                "risk_score": 40,
                "risk_level": "Low",
                "flags": [],
            }
            response = client.post("/signals", json={"symbols": ["AAPL", "MSFT"]})

        data = response.json()
        assert "signals" in data
        assert data["count"] == 2

    def test_signals_has_signal_field(self, client):
        import src.services.server as server

        server._api_instance = _mock_api()
        with (
            patch("src.analysis.factors.compute_factors") as mf,
            patch("src.analysis.guardrails.compute_risk") as mr,
        ):
            mf.return_value = {
                "composite_score": 70,
                "composite_label": "Buy",
                "factors": [],
            }
            mr.return_value = {
                "risk_score": 40,
                "risk_level": "Low",
                "flags": [],
            }
            response = client.post("/signals", json={"symbols": ["AAPL"]})

        data = response.json()
        sig = data["signals"][0]
        assert "signal" in sig
        assert sig["signal"] in ("BUY", "HOLD", "SELL")
        assert "confidence" in sig


# ---------------------------------------------------------------------------
# /openclaw/manifest endpoint
# ---------------------------------------------------------------------------


class TestOpenClawManifest:
    def test_manifest_returns_200(self, client):
        response = client.get("/openclaw/manifest")
        assert response.status_code == 200

    def test_manifest_has_name(self, client):
        response = client.get("/openclaw/manifest")
        data = response.json()
        assert data["name"] == "jaja-money"

    def test_manifest_has_functions(self, client):
        response = client.get("/openclaw/manifest")
        data = response.json()
        assert "functions" in data
        assert "analyze" in data["functions"]


# ---------------------------------------------------------------------------
# /openclaw/webhook endpoint
# ---------------------------------------------------------------------------


class TestOpenClawWebhook:
    def test_webhook_unknown_event_returns_200(self, client):
        response = client.post(
            "/openclaw/webhook",
            json={"event_type": "unknown_event", "payload": {}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "received"

    def test_webhook_analyze_request(self, client):
        import src.services.server as server

        server._api_instance = _mock_api()
        with (
            patch("src.analysis.factors.compute_factors") as mf,
            patch("src.analysis.guardrails.compute_risk") as mr,
        ):
            mf.return_value = {
                "composite_score": 72,
                "composite_label": "Buy",
                "factors": [],
            }
            mr.return_value = {
                "risk_score": 35,
                "risk_level": "Low",
                "flags": [],
            }
            response = client.post(
                "/openclaw/webhook",
                json={
                    "event_type": "analyze_request",
                    "payload": {"symbol": "AAPL"},
                    "agent_id": "test-agent-001",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "AAPL"
        assert "signal" in data

    def test_webhook_analyze_missing_symbol_returns_400(self, client):
        response = client.post(
            "/openclaw/webhook",
            json={"event_type": "analyze_request", "payload": {}},
        )
        assert response.status_code == 400

    def test_webhook_alert_request(self, client, tmp_path, monkeypatch):
        import src.ui.alerts as a

        monkeypatch.setattr(a, "_DATA_DIR", tmp_path)
        monkeypatch.setattr(a, "_ALERTS_FILE", tmp_path / "alerts.json")

        response = client.post(
            "/openclaw/webhook",
            json={
                "event_type": "alert_request",
                "payload": {
                    "symbol": "AAPL",
                    "condition": "Price Above",
                    "threshold": 200.0,
                    "note": "OpenClaw trigger",
                },
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "alert_created"
        assert data["symbol"] == "AAPL"

    def test_webhook_alert_missing_symbol_returns_400(self, client):
        response = client.post(
            "/openclaw/webhook",
            json={
                "event_type": "alert_request",
                "payload": {"condition": "Price Above", "threshold": 200.0},
            },
        )
        assert response.status_code == 400

    def test_webhook_screen_request(self, client):
        import src.services.server as server

        server._api_instance = _mock_api()
        with patch("src.trading.screener.run_screener") as mock_screener:
            mock_screener.return_value = [{"symbol": "AAPL", "factor_score": 72}]
            response = client.post(
                "/openclaw/webhook",
                json={
                    "event_type": "screen_request",
                    "payload": {
                        "tickers": ["AAPL", "MSFT"],
                        "min_factor_score": 60,
                    },
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert data["total"] == 1


# ---------------------------------------------------------------------------
# /openclaw/rebalance endpoint
# ---------------------------------------------------------------------------


class TestOpenClawRebalance:
    def test_rebalance_returns_suggestions(self, client):
        import src.services.server as server

        server._api_instance = _mock_api()
        with (
            patch("src.analysis.factors.compute_factors") as mf,
            patch("src.analysis.guardrails.compute_risk") as mr,
        ):
            mf.return_value = {
                "composite_score": 65,
                "composite_label": "Buy",
                "factors": [],
            }
            mr.return_value = {
                "risk_score": 45,
                "risk_level": "Moderate",
                "flags": [],
            }
            response = client.post(
                "/openclaw/rebalance",
                json={
                    "tickers": ["AAPL", "MSFT"],
                    "target_weights": {"AAPL": 0.6, "MSFT": 0.4},
                    "current_weights": {"AAPL": 0.7, "MSFT": 0.3},
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert "suggestions" in data
        assert len(data["suggestions"]) == 2

    def test_rebalance_bad_weights_returns_400(self, client):
        response = client.post(
            "/openclaw/rebalance",
            json={
                "tickers": ["AAPL", "MSFT"],
                "target_weights": {"AAPL": 0.5, "MSFT": 0.3},  # sums to 0.8
            },
        )
        assert response.status_code == 400

    def test_rebalance_empty_tickers_returns_400(self, client):
        response = client.post(
            "/openclaw/rebalance",
            json={"tickers": [], "target_weights": {}},
        )
        assert response.status_code == 400

    def test_rebalance_drift_action_overweight(self, client):
        """Ticker with current > target should get SELL action."""
        import src.services.server as server

        server._api_instance = _mock_api()
        with (
            patch("src.analysis.factors.compute_factors") as mf,
            patch("src.analysis.guardrails.compute_risk") as mr,
        ):
            mf.return_value = {
                "composite_score": 50,
                "composite_label": "Hold",
                "factors": [],
            }
            mr.return_value = {
                "risk_score": 50,
                "risk_level": "Moderate",
                "flags": [],
            }
            response = client.post(
                "/openclaw/rebalance",
                json={
                    "tickers": ["AAPL"],
                    "target_weights": {"AAPL": 1.0},
                    "current_weights": {"AAPL": 1.0},
                },
            )

        data = response.json()
        assert data["suggestions"][0]["rebalance_action"] == "HOLD"


# ---------------------------------------------------------------------------
# /openclaw/agent endpoint
# ---------------------------------------------------------------------------


class TestOpenClawAgent:
    def test_agent_returns_200_streaming(self, client):
        import src.services.server as server

        server._api_instance = _mock_api()
        with patch("src.services.agent.run_research_agent") as mock_agent:
            mock_agent.return_value = iter(["Research result for AAPL"])
            response = client.post(
                "/openclaw/agent",
                json={
                    "symbol": "AAPL",
                    "question": "What is the bull case?",
                },
            )

        assert response.status_code == 200
        assert "text" in response.headers.get("content-type", "")

    def test_agent_default_question(self, client):
        import src.services.server as server

        server._api_instance = _mock_api()
        with patch("src.services.agent.run_research_agent") as mock_agent:
            mock_agent.return_value = iter(["Investment memo for AAPL"])
            response = client.post(
                "/openclaw/agent",
                json={"symbol": "AAPL"},
            )

        assert response.status_code == 200


# ---------------------------------------------------------------------------
# /score endpoint
# ---------------------------------------------------------------------------


class TestScoreEndpoint:
    def test_score_returns_200(self, client):
        import src.services.server as server

        server._api_instance = _mock_api()
        with (
            patch("src.analysis.factors.compute_factors") as mf,
            patch("src.analysis.guardrails.compute_risk") as mr,
        ):
            mf.return_value = {
                "composite_score": 70,
                "composite_label": "Buy",
                "factors": [],
            }
            mr.return_value = {
                "risk_score": 40,
                "risk_level": "Low",
                "flags": [],
            }
            response = client.post("/score", json={"symbol": "AAPL"})

        assert response.status_code == 200

    def test_score_has_required_fields(self, client):
        import src.services.server as server

        server._api_instance = _mock_api()
        with (
            patch("src.analysis.factors.compute_factors") as mf,
            patch("src.analysis.guardrails.compute_risk") as mr,
        ):
            mf.return_value = {
                "composite_score": 70,
                "composite_label": "Buy",
                "factors": [],
            }
            mr.return_value = {
                "risk_score": 40,
                "risk_level": "Low",
                "flags": [],
            }
            response = client.post("/score", json={"symbol": "AAPL"})

        data = response.json()
        assert data["symbol"] == "AAPL"
        assert "factor_score" in data
        assert "risk_score" in data
        assert "signal" in data
        assert data["signal"] in ("BUY", "HOLD", "SELL")
        assert "confidence" in data
        assert "timestamp" in data

    def test_score_signal_is_buy_when_scores_qualify(self, client):
        import src.services.server as server

        server._api_instance = _mock_api()
        with (
            patch("src.analysis.factors.compute_factors") as mf,
            patch("src.analysis.guardrails.compute_risk") as mr,
        ):
            mf.return_value = {
                "composite_score": 70,
                "composite_label": "Buy",
                "factors": [],
            }
            mr.return_value = {
                "risk_score": 40,
                "risk_level": "Low",
                "flags": [],
            }
            response = client.post("/score", json={"symbol": "AAPL"})

        assert response.json()["signal"] == "BUY"


# ---------------------------------------------------------------------------
# /alerts endpoint
# ---------------------------------------------------------------------------


class TestAlertsEndpoint:
    def test_alerts_returns_200(self, client, tmp_path, monkeypatch):
        import src.ui.alerts as a

        monkeypatch.setattr(a, "_DATA_DIR", tmp_path)
        monkeypatch.setattr(a, "_ALERTS_FILE", tmp_path / "alerts.json")

        response = client.get("/alerts")
        assert response.status_code == 200

    def test_alerts_empty_by_default(self, client, tmp_path, monkeypatch):
        import src.ui.alerts as a

        monkeypatch.setattr(a, "_DATA_DIR", tmp_path)
        monkeypatch.setattr(a, "_ALERTS_FILE", tmp_path / "alerts.json")

        response = client.get("/alerts")
        data = response.json()
        assert data["active_count"] == 0
        assert data["triggered_count"] == 0
        assert data["active"] == []

    def test_alerts_returns_created_alert(self, client, tmp_path, monkeypatch):
        import src.ui.alerts as a

        monkeypatch.setattr(a, "_DATA_DIR", tmp_path)
        monkeypatch.setattr(a, "_ALERTS_FILE", tmp_path / "alerts.json")

        from src.ui.alerts import add_alert

        add_alert("AAPL", "Price Above", 200.0)

        response = client.get("/alerts")
        data = response.json()
        assert data["active_count"] == 1
        assert data["active"][0]["symbol"] == "AAPL"

    def test_alerts_filtered_by_symbol(self, client, tmp_path, monkeypatch):
        import src.ui.alerts as a

        monkeypatch.setattr(a, "_DATA_DIR", tmp_path)
        monkeypatch.setattr(a, "_ALERTS_FILE", tmp_path / "alerts.json")

        from src.ui.alerts import add_alert

        add_alert("AAPL", "Price Above", 200.0)
        add_alert("MSFT", "Price Below", 300.0)

        response = client.get("/alerts", params={"symbol": "AAPL"})
        data = response.json()
        assert data["active_count"] == 1
        assert data["active"][0]["symbol"] == "AAPL"
        assert data["symbol"] == "AAPL"
