"""Tests for api.py — mocks the Finnhub SDK to test all API wrappers (P4.4)."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Ensure FINNHUB_API_KEY is set before importing api.py
os.environ.setdefault("FINNHUB_API_KEY", "test_key_ci")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_api():
    """Return a FinnhubAPI instance with a mocked finnhub client."""
    with patch("finnhub.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        from api import FinnhubAPI
        api = FinnhubAPI.__new__(FinnhubAPI)
        api.client = mock_client
        return api, mock_client


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

def test_init_requires_api_key(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "")
    with patch("finnhub.Client"):
        from importlib import reload
        import api as _api_mod
        with pytest.raises(ValueError, match="FINNHUB_API_KEY"):
            _api_mod.FinnhubAPI()


def test_init_succeeds_with_key(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "valid_key")
    with patch("finnhub.Client") as mock_cls:
        mock_cls.return_value = MagicMock()
        from api import FinnhubAPI
        api = FinnhubAPI()
        assert api.client is not None


# ---------------------------------------------------------------------------
# get_quote
# ---------------------------------------------------------------------------

def test_get_quote_returns_dict():
    api, client = _make_api()
    client.quote.return_value = {"c": 150.0, "d": 1.5, "dp": 1.0, "h": 152.0, "l": 148.0, "pc": 148.5}
    with patch.object(api, "_cached", side_effect=lambda key, fn, **kw: fn()):
        result = api.get_quote("AAPL")
    assert result["c"] == 150.0


def test_get_quote_raises_on_empty():
    api, client = _make_api()
    client.quote.return_value = {"c": 0}
    with patch.object(api, "_cached", side_effect=lambda key, fn, **kw: fn()):
        with pytest.raises(ValueError, match="No quote data"):
            api.get_quote("INVALID")


def test_get_quote_raises_on_none():
    api, client = _make_api()
    client.quote.return_value = None
    with patch.object(api, "_cached", side_effect=lambda key, fn, **kw: fn()):
        with pytest.raises(ValueError):
            api.get_quote("INVALID")


# ---------------------------------------------------------------------------
# get_profile
# ---------------------------------------------------------------------------

def test_get_profile_returns_dict():
    api, client = _make_api()
    client.company_profile2.return_value = {"name": "Apple Inc.", "finnhubIndustry": "Technology"}
    with patch.object(api, "_cached", side_effect=lambda key, fn, **kw: fn()):
        result = api.get_profile("AAPL")
    assert result["name"] == "Apple Inc."


def test_get_profile_raises_on_empty():
    api, client = _make_api()
    client.company_profile2.return_value = {}
    with patch.object(api, "_cached", side_effect=lambda key, fn, **kw: fn()):
        with pytest.raises(ValueError, match="No profile data"):
            api.get_profile("AAPL")


# ---------------------------------------------------------------------------
# get_financials
# ---------------------------------------------------------------------------

def test_get_financials_extracts_metric():
    api, client = _make_api()
    client.company_basic_financials.return_value = {
        "metric": {"peBasicExclExtraTTM": 28.5, "epsBasicExclExtraItemsTTM": 6.5}
    }
    with patch.object(api, "_cached", side_effect=lambda key, fn, **kw: fn()):
        result = api.get_financials("AAPL")
    assert result["peBasicExclExtraTTM"] == 28.5


def test_get_financials_raises_on_missing_metric():
    api, client = _make_api()
    client.company_basic_financials.return_value = {"metric": None}
    with patch.object(api, "_cached", side_effect=lambda key, fn, **kw: fn()):
        with pytest.raises(ValueError, match="No financial data"):
            api.get_financials("AAPL")


# ---------------------------------------------------------------------------
# get_daily
# ---------------------------------------------------------------------------

def test_get_daily_returns_candle_data():
    api, client = _make_api()
    client.stock_candles.return_value = {
        "s": "ok",
        "c": [100, 101, 102],
        "o": [99, 100, 101],
        "h": [103, 104, 105],
        "l": [98, 99, 100],
        "v": [1000, 1100, 1200],
        "t": [1700000000, 1700086400, 1700172800],
    }
    with patch.object(api, "_cached", side_effect=lambda key, fn, **kw: fn()):
        result = api.get_daily("AAPL", years=1)
    assert result["s"] == "ok"
    assert len(result["c"]) == 3


def test_get_daily_raises_on_bad_status():
    api, client = _make_api()
    client.stock_candles.return_value = {"s": "no_data", "c": []}
    with patch.object(api, "_cached", side_effect=lambda key, fn, **kw: fn()):
        with pytest.raises(ValueError, match="No daily price data"):
            api.get_daily("AAPL", years=1)


# ---------------------------------------------------------------------------
# get_news
# ---------------------------------------------------------------------------

def test_get_news_returns_list():
    api, client = _make_api()
    client.company_news.return_value = [
        {"headline": "Apple hits new high", "source": "Reuters", "datetime": 1700000000}
    ]
    with patch.object(api, "_cached", side_effect=lambda key, fn, **kw: fn()):
        result = api.get_news("AAPL")
    assert isinstance(result, list)
    assert result[0]["headline"] == "Apple hits new high"


def test_get_news_returns_empty_on_none():
    api, client = _make_api()
    client.company_news.return_value = None
    with patch.object(api, "_cached", side_effect=lambda key, fn, **kw: fn()):
        result = api.get_news("AAPL")
    assert result == []


# ---------------------------------------------------------------------------
# get_recommendations
# ---------------------------------------------------------------------------

def test_get_recommendations_returns_list():
    api, client = _make_api()
    client.recommendation_trends.return_value = [
        {"period": "2024-01", "strongBuy": 20, "buy": 10, "hold": 5, "sell": 2, "strongSell": 1}
    ]
    with patch.object(api, "_cached", side_effect=lambda key, fn, **kw: fn()):
        result = api.get_recommendations("AAPL")
    assert result[0]["strongBuy"] == 20


# ---------------------------------------------------------------------------
# get_earnings
# ---------------------------------------------------------------------------

def test_get_earnings_returns_list():
    api, client = _make_api()
    client.company_earnings.return_value = [
        {"period": "2024-Q1", "actual": 2.5, "estimate": 2.3, "surprisePercent": 8.7}
    ]
    with patch.object(api, "_cached", side_effect=lambda key, fn, **kw: fn()):
        result = api.get_earnings("AAPL", limit=4)
    assert result[0]["surprisePercent"] == 8.7


# ---------------------------------------------------------------------------
# get_peers
# ---------------------------------------------------------------------------

def test_get_peers_returns_list():
    api, client = _make_api()
    client.company_peers.return_value = ["MSFT", "GOOGL", "AMZN"]
    with patch.object(api, "_cached", side_effect=lambda key, fn, **kw: fn()):
        result = api.get_peers("AAPL")
    assert "MSFT" in result


# ---------------------------------------------------------------------------
# get_option_metrics — no data
# ---------------------------------------------------------------------------

def test_get_option_metrics_unavailable():
    api, client = _make_api()
    with patch.object(api, "get_option_chain", return_value={"data": []}):
        result = api.get_option_metrics("AAPL")
    assert result["available"] is False


def test_get_option_metrics_no_chain():
    api, client = _make_api()
    with patch.object(api, "get_option_chain", return_value={}):
        result = api.get_option_metrics("AAPL")
    assert result["available"] is False


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------

def test_cached_stores_and_retrieves(tmp_path):
    """Verify _cached() calls fn once and returns the same value on repeat."""
    api, client = _make_api()
    call_count = 0

    def _fn():
        nonlocal call_count
        call_count += 1
        return {"value": 42}

    from cache import DiskCache
    with patch("api._disk_cache", DiskCache(cache_dir=str(tmp_path))):
        r1 = api._cached("test:key", _fn, ttl=60)
        r2 = api._cached("test:key", _fn, ttl=60)

    assert r1["value"] == 42
    assert r2["value"] == 42
    assert call_count == 1  # second call should hit disk cache
