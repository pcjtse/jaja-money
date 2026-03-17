"""Tests for ownership.py and social.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


# ===========================================================================
# ownership.py
# ===========================================================================


class TestFetchInstitutionalOwnership:
    def _make_holders_df(self):
        return pd.DataFrame(
            {
                "Holder": ["Vanguard Group", "BlackRock Inc.", "State Street"],
                "Shares": [1_200_000, 900_000, 600_000],
                "% Out": [0.08, 0.06, 0.04],
                "Value": [200_000_000, 150_000_000, 100_000_000],
            }
        )

    def _patch_yf_ticker(self, ticker_mock):
        """Context manager: patch yfinance.Ticker inside ownership.py.

        ownership.py imports yfinance inside the function body (`import yfinance as yf`),
        so we patch the class directly in the yfinance module namespace.
        """
        return patch("yfinance.Ticker", return_value=ticker_mock)

    def test_returns_unavailable_when_no_data(self):
        from ownership import fetch_institutional_ownership

        ticker_mock = MagicMock()
        ticker_mock.institutional_holders = None
        with self._patch_yf_ticker(ticker_mock):
            result = fetch_institutional_ownership("AAPL")
        assert result["available"] is False
        assert result["top_holders"] == []

    def test_returns_unavailable_when_empty_df(self):
        from ownership import fetch_institutional_ownership

        ticker_mock = MagicMock()
        ticker_mock.institutional_holders = pd.DataFrame()
        with self._patch_yf_ticker(ticker_mock):
            result = fetch_institutional_ownership("AAPL")
        assert result["available"] is False

    def test_returns_available_with_data(self):
        from ownership import fetch_institutional_ownership

        ticker_mock = MagicMock()
        ticker_mock.institutional_holders = self._make_holders_df()
        with self._patch_yf_ticker(ticker_mock):
            result = fetch_institutional_ownership("AAPL")
        assert result["available"] is True
        assert len(result["top_holders"]) == 3

    def test_sorted_by_shares_descending(self):
        from ownership import fetch_institutional_ownership

        ticker_mock = MagicMock()
        ticker_mock.institutional_holders = self._make_holders_df()
        with self._patch_yf_ticker(ticker_mock):
            result = fetch_institutional_ownership("AAPL")
        shares = [h["shares"] for h in result["top_holders"]]
        assert shares == sorted(shares, reverse=True)

    def test_concentration_flag_when_top5_over_50pct(self):
        from ownership import fetch_institutional_ownership

        # Each holder has 15% → top 5 = 75% → concentrated
        holders_df = pd.DataFrame(
            {
                "Holder": ["A", "B", "C", "D", "E"],
                "Shares": [1000] * 5,
                "% Out": [15.0, 15.0, 15.0, 15.0, 15.0],
                "Value": [1_000_000] * 5,
            }
        )
        ticker_mock = MagicMock()
        ticker_mock.institutional_holders = holders_df
        with self._patch_yf_ticker(ticker_mock):
            result = fetch_institutional_ownership("AAPL")
        assert result["concentrated"] is True
        assert result["concentration_warning"] is not None

    def test_no_concentration_when_spread_ownership(self):
        from ownership import fetch_institutional_ownership

        # Each holder has 5% → top 5 = 25% → not concentrated
        holders_df = pd.DataFrame(
            {
                "Holder": ["A", "B", "C", "D", "E"],
                "Shares": [100] * 5,
                "% Out": [5.0, 5.0, 5.0, 5.0, 5.0],
                "Value": [100_000] * 5,
            }
        )
        ticker_mock = MagicMock()
        ticker_mock.institutional_holders = holders_df
        with self._patch_yf_ticker(ticker_mock):
            result = fetch_institutional_ownership("AAPL")
        assert result["concentrated"] is False

    def test_graceful_error_handling(self):
        from ownership import fetch_institutional_ownership

        with patch("yfinance.Ticker", side_effect=Exception("no yfinance")):
            result = fetch_institutional_ownership("AAPL")
        assert result["available"] is False

    def test_decimal_pct_converted_to_percentage(self):
        """yfinance returns % Out as decimal like 0.05 → should become 5.0."""
        from ownership import fetch_institutional_ownership

        holders_df = pd.DataFrame(
            {
                "Holder": ["X"],
                "Shares": [100],
                "% Out": [0.05],  # decimal form
                "Value": [100_000],
            }
        )
        ticker_mock = MagicMock()
        ticker_mock.institutional_holders = holders_df
        with self._patch_yf_ticker(ticker_mock):
            result = fetch_institutional_ownership("AAPL")
        assert result["top_holders"][0]["pct_held"] == pytest.approx(5.0)


class TestFetchInsiderSummary:
    def test_empty_input_returns_no_activity(self):
        from ownership import fetch_insider_summary

        result = fetch_insider_summary([])
        assert result["signal"] == "No activity"
        assert result["total_buys"] == 0
        assert result["total_sells"] == 0

    def test_purchases_counted_correctly(self):
        from ownership import fetch_insider_summary

        txns = [
            {"transactionCode": "P", "name": "CEO", "share": 1000, "price": 100.0},
            {"transactionCode": "P", "name": "CFO", "share": 500, "price": 100.0},
        ]
        result = fetch_insider_summary(txns)
        assert result["total_buys"] == 2
        assert result["total_sells"] == 0
        assert result["signal"] == "Buying"

    def test_sales_counted_correctly(self):
        from ownership import fetch_insider_summary

        txns = [
            {"transactionCode": "S", "name": "CEO", "share": 2000, "price": 150.0},
        ]
        result = fetch_insider_summary(txns)
        assert result["total_sells"] == 1
        assert result["signal"] == "Selling"

    def test_mixed_activity_signal(self):
        from ownership import fetch_insider_summary

        txns = [
            {"transactionCode": "P", "name": "A", "share": 100},
            {"transactionCode": "S", "name": "A", "share": 100},
            {"transactionCode": "S", "name": "B", "share": 200},
        ]
        result = fetch_insider_summary(txns)
        assert result["signal"] in ("Mixed", "Selling")

    def test_net_shares_calculated(self):
        from ownership import fetch_insider_summary

        txns = [
            {"transactionCode": "P", "name": "A", "share": 500},
            {"transactionCode": "S", "name": "B", "share": 200},
        ]
        result = fetch_insider_summary(txns)
        assert result["net_shares_bought"] == 300

    def test_buy_value_estimated(self):
        from ownership import fetch_insider_summary

        txns = [
            {"transactionCode": "P", "name": "A", "share": 100, "price": 50.0},
        ]
        result = fetch_insider_summary(txns)
        assert result["buy_value"] == pytest.approx(5000.0)

    def test_recent_buyers_list(self):
        from ownership import fetch_insider_summary

        txns = [
            {"transactionCode": "P", "name": "Alice"},
            {"transactionCode": "P", "name": "Bob"},
        ]
        result = fetch_insider_summary(txns)
        assert "Alice" in result["recent_buyers"]
        assert "Bob" in result["recent_buyers"]

    def test_no_duplicate_names_in_buyers(self):
        from ownership import fetch_insider_summary

        txns = [
            {"transactionCode": "P", "name": "CEO"},
            {"transactionCode": "P", "name": "CEO"},
        ]
        result = fetch_insider_summary(txns)
        assert result["recent_buyers"].count("CEO") == 1


class TestComputeShortSellingScore:
    def test_no_data_gives_low_score(self):
        from ownership import compute_short_selling_score

        result = compute_short_selling_score(50, None, None)
        assert result["score"] >= 0
        assert result["label"] == "No Signal"

    def test_weak_fundamentals_increase_score(self):
        from ownership import compute_short_selling_score

        # factor_score=10 (very weak) → large fundamental_sub
        result = compute_short_selling_score(10, None, None)
        assert result["fundamental_sub"] > 0

    def test_strong_fundamentals_give_zero_sub(self):
        from ownership import compute_short_selling_score

        # factor_score=60 (above 50) → fundamental weakness = 0
        result = compute_short_selling_score(60, None, None)
        assert result["fundamental_sub"] == 0

    def test_high_short_interest_increases_score(self):
        from ownership import compute_short_selling_score

        short_data = {"short_pct_float": 30.0, "days_to_cover": 12.0}
        result = compute_short_selling_score(50, None, short_data)
        assert result["short_int_sub"] > 0

    def test_insider_selling_increases_score(self):
        from ownership import compute_short_selling_score

        insider = {"signal": "Selling", "net_shares_bought": -500}
        result = compute_short_selling_score(50, insider, None)
        assert result["insider_sub"] == 25

    def test_strong_short_label(self):
        from ownership import compute_short_selling_score

        # Max everything to hit Strong Short
        short_data = {"short_pct_float": 30.0, "days_to_cover": 12.0}
        insider = {"signal": "Selling", "net_shares_bought": -1000}
        result = compute_short_selling_score(5, insider, short_data)
        assert result["label"] in ("Strong Short", "Moderate Short")

    def test_score_components_sum_to_total(self):
        from ownership import compute_short_selling_score

        short_data = {"short_pct_float": 20.0, "days_to_cover": 6.0}
        insider = {"signal": "Mixed", "net_shares_bought": -100}
        result = compute_short_selling_score(30, insider, short_data)
        assert result["score"] == (
            result["fundamental_sub"] + result["short_int_sub"] + result["insider_sub"]
        )

    def test_result_has_required_keys(self):
        from ownership import compute_short_selling_score

        result = compute_short_selling_score(50, None, None)
        for key in ("score", "fundamental_sub", "short_int_sub", "insider_sub", "label", "detail"):
            assert key in result


# ===========================================================================
# social.py
# ===========================================================================


class TestComputeSocialSentiment:
    def test_empty_inputs(self):
        from social import compute_social_sentiment

        result = compute_social_sentiment([], [])
        assert result["available"] is False
        assert result["mention_count"] == 0
        assert result["overall_signal"] == "Mixed"

    def test_bullish_signal_when_mostly_bullish(self):
        from social import compute_social_sentiment

        st_messages = [{"sentiment": "bullish"} for _ in range(10)] + [
            {"sentiment": "bearish"}
        ]
        result = compute_social_sentiment([], st_messages)
        assert result["overall_signal"] == "Bullish"
        assert result["st_bullish"] == 10
        assert result["st_bearish"] == 1

    def test_bearish_signal_when_mostly_bearish(self):
        from social import compute_social_sentiment

        st_messages = [{"sentiment": "bearish"} for _ in range(10)] + [
            {"sentiment": "bullish"}
        ]
        result = compute_social_sentiment([], st_messages)
        assert result["overall_signal"] == "Bearish"

    def test_mixed_signal_when_balanced(self):
        from social import compute_social_sentiment

        st_messages = [
            {"sentiment": "bullish"},
            {"sentiment": "bearish"},
        ]
        result = compute_social_sentiment([], st_messages)
        assert result["overall_signal"] == "Mixed"

    def test_reddit_mentions_counted(self):
        from social import compute_social_sentiment

        posts = [
            {"title": "Buy AAPL", "score": 100, "num_comments": 50, "created_utc": 0, "subreddit": "stocks"},
            {"title": "AAPL moon", "score": 200, "num_comments": 30, "created_utc": 0, "subreddit": "wsb"},
        ]
        result = compute_social_sentiment(posts, [])
        assert result["reddit_mentions"] == 2
        assert result["available"] is True

    def test_reddit_avg_score_computed(self):
        from social import compute_social_sentiment

        posts = [
            {"title": "A", "score": 100, "num_comments": 0, "created_utc": 0, "subreddit": "s"},
            {"title": "B", "score": 200, "num_comments": 0, "created_utc": 0, "subreddit": "s"},
        ]
        result = compute_social_sentiment(posts, [])
        assert result["reddit_avg_score"] == pytest.approx(150.0)

    def test_neutral_st_messages_counted(self):
        from social import compute_social_sentiment

        st_messages = [
            {"sentiment": None},
            {"sentiment": None},
            {"sentiment": "bullish"},
        ]
        result = compute_social_sentiment([], st_messages)
        assert result["st_neutral"] == 2
        assert result["st_bullish"] == 1

    def test_finbert_pipe_used_when_provided(self):
        from social import compute_social_sentiment

        posts = [{"title": "AAPL is going to the moon!", "score": 10, "num_comments": 0, "created_utc": 0, "subreddit": "s"}]
        mock_pipe = MagicMock(return_value=[{"label": "positive", "score": 0.9}])
        result = compute_social_sentiment(posts, [], finbert_pipe=mock_pipe)
        mock_pipe.assert_called_once()
        # Should have incremented reddit_bullish internally (affects overall signal)
        assert result["available"] is True

    def test_mention_count_sum_of_both_sources(self):
        from social import compute_social_sentiment

        posts = [{"title": "X", "score": 1, "num_comments": 0, "created_utc": 0, "subreddit": "s"}] * 3
        st_msgs = [{"sentiment": "bullish"}] * 2
        result = compute_social_sentiment(posts, st_msgs)
        assert result["mention_count"] == 5


class TestFetchRedditMentions:
    def test_returns_empty_on_network_error(self):
        from social import fetch_reddit_mentions
        import urllib.error

        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("fail")):
            result = fetch_reddit_mentions("AAPL")
        assert result == []

    def test_returns_list_on_success(self):
        from social import fetch_reddit_mentions
        import json
        from unittest.mock import MagicMock

        fake_data = {
            "data": {
                "children": [
                    {
                        "data": {
                            "title": "AAPL is great",
                            "score": 100,
                            "num_comments": 50,
                            "created_utc": 1700000000.0,
                            "subreddit": "stocks",
                        }
                    }
                ]
            }
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(fake_data).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fetch_reddit_mentions("AAPL")

        assert len(result) == 1
        assert result[0]["title"] == "AAPL is great"


class TestFetchStocktwitsMessages:
    def test_returns_empty_on_network_error(self):
        from social import fetch_stocktwits_messages
        import urllib.error

        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("fail")):
            result = fetch_stocktwits_messages("AAPL")
        assert result == []

    def test_returns_messages_on_success(self):
        from social import fetch_stocktwits_messages
        import json

        fake_data = {
            "messages": [
                {
                    "body": "AAPL to the moon!",
                    "entities": {"sentiment": {"basic": "Bullish"}},
                    "created_at": "2024-01-01T10:00:00Z",
                }
            ]
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(fake_data).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fetch_stocktwits_messages("AAPL")

        assert len(result) == 1
        assert result[0]["sentiment"] == "bullish"
        assert result[0]["body"] == "AAPL to the moon!"
