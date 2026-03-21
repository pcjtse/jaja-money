"""Tests for providers.py — DataProvider fallback logic."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_provider(pref="auto"):
    """Create a DataProvider with a mocked FinnhubAPI.

    DataProvider imports FinnhubAPI lazily inside __init__ via `from api import FinnhubAPI`,
    so we patch the symbol in the `api` module namespace.
    """
    mock_api = MagicMock()
    with patch("api.FinnhubAPI", return_value=mock_api):
        from providers import DataProvider

        dp = DataProvider(source_preference=pref)
    return dp, mock_api


# ---------------------------------------------------------------------------
# _yf_* helper unit tests (pure transformations, no network)
# ---------------------------------------------------------------------------


class TestYfQuote:
    def test_returns_expected_keys(self):
        fake_info = {
            "currentPrice": 150.0,
            "previousClose": 148.0,
            "dayHigh": 152.0,
            "dayLow": 147.0,
        }
        ticker_mock = MagicMock()
        ticker_mock.info = fake_info
        with patch("providers.yf") as mock_yf:
            mock_yf.Ticker.return_value = ticker_mock
            from providers import _yf_quote

            result = _yf_quote("AAPL")

        assert result["c"] == 150.0
        assert result["pc"] == 148.0
        assert result["h"] == 152.0
        assert result["l"] == 147.0
        assert abs(result["d"] - 2.0) < 0.01
        assert abs(result["dp"] - (2.0 / 148.0 * 100)) < 0.01

    def test_zero_prev_close_no_error(self):
        fake_info = {"currentPrice": 100.0, "previousClose": 0}
        ticker_mock = MagicMock()
        ticker_mock.info = fake_info
        with patch("providers.yf") as mock_yf:
            mock_yf.Ticker.return_value = ticker_mock
            from providers import _yf_quote

            result = _yf_quote("X")

        assert result["dp"] == 0


class TestYfProfile:
    def test_maps_fields_correctly(self):
        fake_info = {
            "longName": "Apple Inc.",
            "sector": "Technology",
            "country": "US",
            "exchange": "NASDAQ",
        }
        ticker_mock = MagicMock()
        ticker_mock.info = fake_info
        with patch("providers.yf") as mock_yf:
            mock_yf.Ticker.return_value = ticker_mock
            from providers import _yf_profile

            result = _yf_profile("AAPL")

        assert result["name"] == "Apple Inc."
        assert result["finnhubIndustry"] == "Technology"
        assert result["country"] == "US"

    def test_fallback_to_symbol_if_no_name(self):
        ticker_mock = MagicMock()
        ticker_mock.info = {}
        with patch("providers.yf") as mock_yf:
            mock_yf.Ticker.return_value = ticker_mock
            from providers import _yf_profile

            result = _yf_profile("MSFT")

        assert result["name"] == "MSFT"


class TestYfFinancials:
    def test_market_cap_converted_to_millions(self):
        fake_info = {"marketCap": 2_000_000_000_000}  # $2T
        ticker_mock = MagicMock()
        ticker_mock.info = fake_info
        with patch("providers.yf") as mock_yf:
            mock_yf.Ticker.return_value = ticker_mock
            from providers import _yf_financials

            result = _yf_financials("AAPL")

        assert result["marketCapitalization"] == pytest.approx(2_000_000, rel=1e-3)

    def test_none_market_cap(self):
        ticker_mock = MagicMock()
        ticker_mock.info = {}
        with patch("providers.yf") as mock_yf:
            mock_yf.Ticker.return_value = ticker_mock
            from providers import _yf_financials

            result = _yf_financials("X")

        assert result["marketCapitalization"] is None

    def test_dividend_yield_multiplied_by_100(self):
        ticker_mock = MagicMock()
        ticker_mock.info = {"dividendYield": 0.015}  # 1.5% stored as decimal
        with patch("providers.yf") as mock_yf:
            mock_yf.Ticker.return_value = ticker_mock
            from providers import _yf_financials

            result = _yf_financials("X")

        assert abs(result["dividendYieldIndicatedAnnual"] - 1.5) < 0.001


class TestYfNews:
    def test_filters_old_articles(self):
        import time

        now = int(time.time())
        old_ts = now - 10 * 86400  # 10 days ago
        recent_ts = now - 2 * 86400  # 2 days ago

        news = [
            {"title": "Old", "providerPublishTime": old_ts, "publisher": "A"},
            {"title": "Recent", "providerPublishTime": recent_ts, "publisher": "B"},
        ]
        ticker_mock = MagicMock()
        ticker_mock.news = news
        with patch("providers.yf") as mock_yf:
            mock_yf.Ticker.return_value = ticker_mock
            from providers import _yf_news

            result = _yf_news("AAPL", days=7)

        assert len(result) == 1
        assert result[0]["headline"] == "Recent"

    def test_empty_news(self):
        ticker_mock = MagicMock()
        ticker_mock.news = []
        with patch("providers.yf") as mock_yf:
            mock_yf.Ticker.return_value = ticker_mock
            from providers import _yf_news

            result = _yf_news("X")

        assert result == []


class TestYfPeers:
    def test_returns_empty_list(self):
        from providers import _yf_peers

        assert _yf_peers("AAPL") == []


# ---------------------------------------------------------------------------
# DataProvider._call fallback logic
# ---------------------------------------------------------------------------


class TestDataProviderFallback:
    def test_uses_finnhub_by_default(self):
        dp, mock_api = _make_provider("auto")
        mock_api.get_quote.return_value = {"c": 100.0}
        result = dp.get_quote("AAPL")
        assert result == {"c": 100.0}
        assert dp.source_used == "finnhub"

    def test_falls_back_to_yfinance_when_finnhub_raises(self):
        dp, mock_api = _make_provider("auto")
        mock_api.get_quote.side_effect = RuntimeError("timeout")

        fake_quote = {"c": 99.0, "d": 0, "dp": 0, "h": 100, "l": 98, "pc": 99}
        with (
            patch("providers._HAS_YFINANCE", True),
            patch("providers._yf_quote", return_value=fake_quote),
        ):
            result = dp.get_quote("AAPL")

        assert result["c"] == 99.0
        assert dp.source_used == "yfinance"

    def test_yfinance_preference_skips_finnhub(self):
        dp, mock_api = _make_provider("yfinance")
        fake_quote = {"c": 42.0, "d": 0, "dp": 0, "h": 43, "l": 41, "pc": 42}
        with (
            patch("providers._HAS_YFINANCE", True),
            patch("providers._yf_quote", return_value=fake_quote),
        ):
            result = dp.get_quote("X")

        mock_api.get_quote.assert_not_called()
        assert result["c"] == 42.0
        assert dp.source_used == "yfinance"

    def test_raises_when_no_source_available(self):
        dp, mock_api = _make_provider("auto")
        mock_api.get_quote.side_effect = RuntimeError("fail")
        with patch("providers._HAS_YFINANCE", False):
            with pytest.raises(ValueError, match="No data source"):
                dp.get_quote("AAPL")

    def test_get_financials_tries_alpha_vantage_on_double_failure(self):
        dp, mock_api = _make_provider("auto")
        mock_api.get_financials.side_effect = RuntimeError("fh fail")
        fake_av = {"peBasicExclExtraTTM": 25.0, "_av_source": "alpha_vantage"}

        with (
            patch("providers._HAS_YFINANCE", True),
            patch("providers._yf_financials", side_effect=RuntimeError("yf fail")),
            patch("providers._av_financials", return_value=fake_av),
        ):
            result = dp.get_financials("AAPL")

        assert result["_av_source"] == "alpha_vantage"
        assert dp.source_used == "alpha_vantage"

    def test_get_peers_falls_back_gracefully(self):
        dp, mock_api = _make_provider("auto")
        mock_api.get_peers.side_effect = RuntimeError("no peers")
        with patch("providers._yf_peers", return_value=[]):
            result = dp.get_peers("AAPL")
        assert result == []

    def test_source_used_property_default(self):
        dp, _ = _make_provider()
        assert dp.source_used == "finnhub"


# ---------------------------------------------------------------------------
# _av_financials unit tests
# ---------------------------------------------------------------------------


class TestAvFinancials:
    def test_raises_without_api_key(self):
        import os

        orig = os.environ.pop("ALPHA_VANTAGE_API_KEY", None)
        try:
            from providers import _av_financials

            with pytest.raises(ValueError, match="ALPHA_VANTAGE_API_KEY"):
                _av_financials("AAPL")
        finally:
            if orig:
                os.environ["ALPHA_VANTAGE_API_KEY"] = orig

    def test_maps_alpha_vantage_response(self):
        import os

        os.environ["ALPHA_VANTAGE_API_KEY"] = "test_key"
        fake_resp = MagicMock()
        fake_resp.json.return_value = {
            "Symbol": "AAPL",
            "TrailingPE": "28.5",
            "EPS": "6.13",
            "MarketCapitalization": "2000000000000",
            "DividendYield": "0.005",
            "52WeekHigh": "200.0",
            "52WeekLow": "140.0",
        }
        fake_resp.raise_for_status = lambda: None

        with (
            patch("providers._HAS_REQUESTS", True),
            patch("providers._requests.get", return_value=fake_resp),
        ):
            from providers import _av_financials

            result = _av_financials("AAPL")

        assert result["peBasicExclExtraTTM"] == pytest.approx(28.5)
        assert result["epsBasicExclExtraItemsTTM"] == pytest.approx(6.13)
        assert result["_av_source"] == "alpha_vantage"

        del os.environ["ALPHA_VANTAGE_API_KEY"]

    def test_raises_on_empty_response(self):
        import os

        os.environ["ALPHA_VANTAGE_API_KEY"] = "test_key"
        fake_resp = MagicMock()
        fake_resp.json.return_value = {}
        fake_resp.raise_for_status = lambda: None

        with (
            patch("providers._HAS_REQUESTS", True),
            patch("providers._requests.get", return_value=fake_resp),
        ):
            from providers import _av_financials

            with pytest.raises(ValueError, match="No Alpha Vantage data"):
                _av_financials("AAPL")

        del os.environ["ALPHA_VANTAGE_API_KEY"]
