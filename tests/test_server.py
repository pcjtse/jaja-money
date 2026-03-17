"""Tests for server.py — FastAPI REST API endpoints using TestClient.

Skips all tests if fastapi or httpx (required for TestClient) are not installed.
"""

from __future__ import annotations

import os
import pytest

from unittest.mock import MagicMock

# Skip the whole module if fastapi[testclient] or httpx is not available.
# We must guard the import itself, because conftest.py stubs `fastapi` as a
# plain ModuleType (not a package), so importorskip("fastapi") passes even
# when the real package is absent — leaving from fastapi.testclient to fail.
try:
    from fastapi.testclient import TestClient
except Exception:  # ImportError or ModuleNotFoundError with "not a package"
    pytest.skip("fastapi[testclient] not available", allow_module_level=True)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    """Create a TestClient for the server app with a mocked FinnhubAPI."""
    # Ensure auth is disabled for tests
    os.environ.pop("JAJA_API_KEY", None)

    import server

    # Reset module-level singleton so each test gets a fresh mock
    server._api_instance = None
    server._api_error = None

    with TestClient(server.app) as c:
        yield c


def _mock_api():
    """Build a minimal mock FinnhubAPI."""
    import numpy as np

    mock = MagicMock()
    prices = (100 + np.cumsum(np.random.default_rng(0).normal(0, 1, 252))).tolist()
    timestamps = list(range(1_600_000_000, 1_600_000_000 + 252 * 86400, 86400))

    mock.get_quote.return_value = {"c": 150.0, "dp": 1.5, "d": 2.2}
    mock.get_profile.return_value = {
        "name": "Apple Inc.",
        "finnhubIndustry": "Technology",
    }
    mock.get_financials.return_value = {
        "peBasicExclExtraTTM": 28.0,
        "marketCapitalization": 2_500_000,
    }
    mock.get_daily.return_value = {"c": prices, "t": timestamps, "v": [1_000_000] * 252}
    mock.get_news.return_value = []
    mock.get_recommendations.return_value = []
    mock.get_earnings.return_value = []
    mock.fetch_all_parallel.return_value = {
        "quote": {"c": 150.0, "dp": 1.5, "d": 2.2},
        "profile": {"name": "Apple Inc.", "finnhubIndustry": "Technology"},
        "financials": {"peBasicExclExtraTTM": 28.0, "marketCapitalization": 2_500_000},
        "daily": {"c": prices, "t": timestamps, "v": [1_000_000] * 252},
        "news": [],
    }
    return mock


# ---------------------------------------------------------------------------
# /health endpoint
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_returns_ok_status(self, client):
        response = client.get("/health")
        data = response.json()
        assert data["status"] == "ok"

    def test_health_has_version(self, client):
        response = client.get("/health")
        data = response.json()
        assert "version" in data

    def test_health_has_timestamp(self, client):
        response = client.get("/health")
        data = response.json()
        assert "timestamp" in data
        assert isinstance(data["timestamp"], int)

    def test_health_shows_finnhub_configured(self, client):
        response = client.get("/health")
        data = response.json()
        assert "finnhub_configured" in data


# ---------------------------------------------------------------------------
# /forward-test/portfolio (create portfolio)
# ---------------------------------------------------------------------------


class TestForwardTestPortfolioCreate:
    def test_create_portfolio_returns_201_or_200(self, client):
        response = client.post("/forward-test/portfolio", json={"name": "Test Portfolio"})
        assert response.status_code in (200, 201)

    def test_create_portfolio_returns_id(self, client):
        response = client.post("/forward-test/portfolio", json={"name": "My Paper Fund"})
        data = response.json()
        assert "portfolio_id" in data
        assert isinstance(data["portfolio_id"], int)

    def test_create_portfolio_echoes_name(self, client):
        response = client.post("/forward-test/portfolio", json={"name": "Alpha Strategy"})
        data = response.json()
        assert data["name"] == "Alpha Strategy"

    def test_create_portfolio_missing_name_returns_422(self, client):
        response = client.post("/forward-test/portfolio", json={})
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# /forward-test/portfolios (list portfolios)
# ---------------------------------------------------------------------------


class TestForwardTestListPortfolios:
    def test_list_portfolios_returns_200(self, client):
        response = client.get("/forward-test/portfolios")
        assert response.status_code == 200

    def test_list_portfolios_returns_dict_with_portfolios_key(self, client):
        response = client.get("/forward-test/portfolios")
        data = response.json()
        assert "portfolios" in data
        assert isinstance(data["portfolios"], list)


# ---------------------------------------------------------------------------
# /forward-test/trade (add trade)
# ---------------------------------------------------------------------------


class TestForwardTestTrade:
    def _create_portfolio(self, client) -> int:
        resp = client.post("/forward-test/portfolio", json={"name": "Trade Test"})
        return resp.json()["portfolio_id"]

    def test_add_trade_returns_200(self, client):
        pid = self._create_portfolio(client)
        response = client.post(
            "/forward-test/trade",
            json={
                "portfolio_id": pid,
                "symbol": "AAPL",
                "entry_price": 150.0,
                "shares": 10,
            },
        )
        assert response.status_code == 200

    def test_add_trade_returns_expected_fields(self, client):
        pid = self._create_portfolio(client)
        response = client.post(
            "/forward-test/trade",
            json={
                "portfolio_id": pid,
                "symbol": "MSFT",
                "entry_price": 380.0,
                "shares": 5,
            },
        )
        data = response.json()
        assert "trade_id" in data
        assert data["symbol"] == "MSFT"
        assert data["entry_price"] == 380.0

    def test_add_trade_missing_required_fields_returns_422(self, client):
        response = client.post("/forward-test/trade", json={"symbol": "AAPL"})
        assert response.status_code == 422

    def test_add_trade_uppercases_symbol(self, client):
        pid = self._create_portfolio(client)
        response = client.post(
            "/forward-test/trade",
            json={
                "portfolio_id": pid,
                "symbol": "tsla",
                "entry_price": 250.0,
                "shares": 2,
            },
        )
        data = response.json()
        assert data["symbol"] == "TSLA"


# ---------------------------------------------------------------------------
# /forward-test/portfolio/{id} (summary)
# ---------------------------------------------------------------------------


class TestForwardTestSummary:
    def test_summary_returns_200_for_existing_portfolio(self, client):
        # First create a portfolio
        resp = client.post("/forward-test/portfolio", json={"name": "Summary Test"})
        pid = resp.json()["portfolio_id"]
        response = client.get(f"/forward-test/portfolio/{pid}")
        assert response.status_code == 200

    def test_summary_returns_dict(self, client):
        resp = client.post("/forward-test/portfolio", json={"name": "Summary Dict Test"})
        pid = resp.json()["portfolio_id"]
        response = client.get(f"/forward-test/portfolio/{pid}")
        assert isinstance(response.json(), dict)


# ---------------------------------------------------------------------------
# Authentication (when JAJA_API_KEY is set)
# ---------------------------------------------------------------------------


class TestAuthentication:
    def test_health_accessible_without_key(self, client):
        """Health endpoint should always be accessible."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_missing_key_returns_401_when_auth_enabled(self):
        """When JAJA_API_KEY is configured, missing key → 401."""
        os.environ["JAJA_API_KEY"] = "secret123"
        try:
            import server

            server._api_instance = None
            server._api_error = None
            with TestClient(server.app) as c:
                response = c.post(
                    "/forward-test/portfolio", json={"name": "Unauthorized"}
                )
                assert response.status_code == 401
        finally:
            os.environ.pop("JAJA_API_KEY", None)
            import server

            server._api_instance = None

    def test_valid_key_accepted(self):
        """When JAJA_API_KEY is configured, correct key is accepted."""
        os.environ["JAJA_API_KEY"] = "secret123"
        try:
            import server

            server._api_instance = None
            server._api_error = None
            with TestClient(server.app) as c:
                response = c.post(
                    "/forward-test/portfolio",
                    json={"name": "Authorized"},
                    headers={"X-API-Key": "secret123"},
                )
                assert response.status_code in (200, 201)
        finally:
            os.environ.pop("JAJA_API_KEY", None)
            import server

            server._api_instance = None
