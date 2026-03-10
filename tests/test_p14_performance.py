"""Tests for P14.x: Performance & Scale — Async API, Redis Cache, FastAPI Server."""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from cache import DiskCache, RedisCacheBackend, get_cache


# ---------------------------------------------------------------------------
# P14.1: Concurrent API Fetching tests
# ---------------------------------------------------------------------------


class TestConcurrentFetching:
    def test_fetch_all_parallel_returns_dict(self):
        """Test that fetch_all_parallel returns a dict with expected keys."""
        from api import FinnhubAPI

        mock_client = MagicMock()
        mock_client.quote.return_value = {"c": 150.0, "dp": 1.0, "pc": 148.0}
        mock_client.company_profile2.return_value = {"name": "Apple", "finnhubIndustry": "Technology"}
        mock_client.company_basic_financials.return_value = {"metric": {"peBasicExclExtraTTM": 25.0}}
        mock_client.stock_candles.return_value = {
            "s": "ok", "c": [100, 101, 102], "t": [1000, 2000, 3000],
            "o": [99, 100, 101], "h": [101, 102, 103], "l": [98, 99, 100], "v": [1e6, 1e6, 1e6]
        }
        mock_client.company_news.return_value = []
        mock_client.company_insider_transactions.return_value = {"data": []}
        mock_client.recommendation_trends.return_value = []
        mock_client.company_earnings.return_value = []

        with patch.object(FinnhubAPI, "__init__", lambda self: None):
            api = FinnhubAPI.__new__(FinnhubAPI)
            api.client = mock_client
            api._disk_cache = MagicMock()
            api._disk_cache.get = MagicMock(return_value=None)
            api._disk_cache.set = MagicMock()

            # Patch the _cached method to just call the function directly
            def mock_cached(key, fn, ttl=None):
                return fn()
            api._cached = mock_cached

            result = api.fetch_all_parallel("AAPL")

        assert isinstance(result, dict)
        assert "latency_breakdown" in result
        assert "_total" in result["latency_breakdown"]

    def test_fetch_all_parallel_includes_latency(self):
        """Verify latency_breakdown contains per-source timing."""
        from api import FinnhubAPI

        with patch.object(FinnhubAPI, "__init__", lambda self: None):
            api = FinnhubAPI.__new__(FinnhubAPI)

            def mock_cached(key, fn, ttl=None):
                return {"mock": True}
            api._cached = mock_cached

            result = api.fetch_all_parallel("AAPL")

        breakdown = result.get("latency_breakdown", {})
        assert "_total" in breakdown
        assert breakdown["_total"] >= 0


# ---------------------------------------------------------------------------
# P14.2: Redis Cache Backend tests
# ---------------------------------------------------------------------------


class TestRedisCacheBackend:
    def test_redis_disabled_when_not_installed(self):
        """Redis backend should gracefully handle missing redis package."""
        with patch.dict("sys.modules", {"redis": None}):
            cache = RedisCacheBackend(redis_url="redis://localhost:6379/0")
            assert cache._enabled is False

    def test_redis_disabled_on_connection_failure(self):
        """Redis backend should disable itself on connection failure."""
        mock_redis_module = MagicMock()
        mock_client = MagicMock()
        mock_client.ping.side_effect = Exception("Connection refused")
        mock_redis_module.Redis.from_url.return_value = mock_client

        with patch.dict("sys.modules", {"redis": mock_redis_module}):
            cache = RedisCacheBackend(redis_url="redis://invalid:6379/0")
            assert cache._enabled is False

    def test_redis_get_returns_none_when_disabled(self):
        cache = RedisCacheBackend.__new__(RedisCacheBackend)
        cache._enabled = False
        cache._client = None
        assert cache.get("any_key") is None

    def test_redis_set_noop_when_disabled(self):
        cache = RedisCacheBackend.__new__(RedisCacheBackend)
        cache._enabled = False
        cache._client = None
        # Should not raise
        cache.set("key", "value", ttl=60)

    def test_redis_get_and_set_when_enabled(self):
        """Test Redis get/set using a mock client."""
        import pickle

        mock_redis_module = MagicMock()
        mock_client = MagicMock()
        mock_client.ping.return_value = True

        stored_data = {}

        def mock_setex(key, ttl, data):
            stored_data[key] = data

        def mock_get(key):
            return stored_data.get(key)

        mock_client.setex = mock_setex
        mock_client.get = mock_get
        mock_redis_module.Redis.from_url.return_value = mock_client

        with patch.dict("sys.modules", {"redis": mock_redis_module}):
            with patch("cache.cfg") as mock_cfg:
                mock_cfg.cache_ttl = 300
                cache = RedisCacheBackend(redis_url="redis://localhost:6379/0")
                cache.set("test_key", {"data": 42}, ttl=60)
                result = cache.get("test_key")

        assert result is not None
        assert result == {"data": 42}

    def test_redis_stats_when_disabled(self):
        cache = RedisCacheBackend.__new__(RedisCacheBackend)
        cache._enabled = False
        cache._url = "redis://localhost:6379/0"
        stats = cache.stats()
        assert stats["enabled"] is False
        assert stats["backend"] == "redis"

    def test_redis_clear_when_disabled(self):
        cache = RedisCacheBackend.__new__(RedisCacheBackend)
        cache._enabled = False
        result = cache.clear()
        assert result == 0

    def test_get_cache_returns_disk_by_default(self, monkeypatch):
        """get_cache() should return DiskCache when CACHE_BACKEND=disk."""
        monkeypatch.setenv("CACHE_BACKEND", "disk")
        # Reimport to trigger factory
        import importlib
        import cache as cache_module
        new_cache = cache_module._create_cache()
        assert isinstance(new_cache, DiskCache)

    def test_get_cache_returns_redis_when_configured(self, monkeypatch):
        """get_cache() should return RedisCacheBackend when CACHE_BACKEND=redis."""
        monkeypatch.setenv("CACHE_BACKEND", "redis")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

        import cache as cache_module
        with patch.object(RedisCacheBackend, "_connect", lambda self: None):
            new_cache = cache_module._create_cache()
            assert isinstance(new_cache, RedisCacheBackend)


# ---------------------------------------------------------------------------
# P14.3: FastAPI Server tests
# ---------------------------------------------------------------------------


class TestFastAPIServer:
    def test_server_import(self):
        """server.py should import without errors when FastAPI is installed."""
        try:
            import server
            assert hasattr(server, "app")
        except ImportError:
            pytest.skip("FastAPI not installed")

    def test_health_endpoint(self):
        """Health endpoint should return 200 with status ok."""
        try:
            from fastapi.testclient import TestClient
            import server
            client = TestClient(server.app)
            response = client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert "version" in data
        except ImportError:
            pytest.skip("FastAPI or httpx not installed")

    def test_health_endpoint_fields(self):
        """Health endpoint should include API key configuration status."""
        try:
            from fastapi.testclient import TestClient
            import server
            client = TestClient(server.app)
            response = client.get("/health")
            data = response.json()
            assert "finnhub_configured" in data
            assert "anthropic_configured" in data
        except ImportError:
            pytest.skip("FastAPI or httpx not installed")

    def test_analyze_requires_valid_ticker(self):
        """Analyze endpoint should handle missing API gracefully."""
        try:
            from fastapi.testclient import TestClient
            import server
            client = TestClient(server.app)

            with patch("server._get_api") as mock_get_api:
                mock_api = MagicMock()
                mock_api.fetch_all_parallel.side_effect = Exception("No data for INVALID")
                mock_get_api.return_value = mock_api

                response = client.post("/analyze", json={"symbol": "INVALID"})
                assert response.status_code in (404, 500)
        except ImportError:
            pytest.skip("FastAPI or httpx not installed")

    def test_openapi_docs_available(self):
        """OpenAPI docs should be accessible."""
        try:
            from fastapi.testclient import TestClient
            import server
            client = TestClient(server.app)
            response = client.get("/docs")
            assert response.status_code == 200
        except ImportError:
            pytest.skip("FastAPI or httpx not installed")

    def test_api_key_auth_rejected(self):
        """Requests with wrong API key should be rejected."""
        try:
            from fastapi.testclient import TestClient
            import server

            with patch.object(server, "_API_KEY", "secret-key-123"):
                client = TestClient(server.app)
                response = client.post(
                    "/analyze",
                    json={"symbol": "AAPL"},
                    headers={"X-API-Key": "wrong-key"},
                )
                assert response.status_code == 401
        except ImportError:
            pytest.skip("FastAPI or httpx not installed")
