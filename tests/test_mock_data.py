"""Tests for the mock data module and MockFinnhubAPI class."""

import os
import sys

# Ensure mock mode is active for these tests
os.environ["MOCK_DATA"] = "1"
os.environ["FINNHUB_API_KEY"] = "mock"
os.environ["ANTHROPIC_API_KEY"] = "mock"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# mock_data module tests
# ---------------------------------------------------------------------------


class TestMockData:
    def test_get_mock_quote_known_ticker(self):
        from mock_data import get_mock_quote

        q = get_mock_quote("AAPL")
        assert isinstance(q, dict)
        assert "c" in q and "d" in q and "dp" in q
        assert q["c"] > 0
        assert "h" in q and "l" in q and "o" in q and "pc" in q
        assert q["h"] >= q["l"]

    def test_get_mock_quote_unknown_ticker(self):
        from mock_data import get_mock_quote

        q = get_mock_quote("XYZZY")
        assert isinstance(q, dict)
        assert q["c"] > 0

    def test_get_mock_profile_known(self):
        from mock_data import get_mock_profile

        p = get_mock_profile("AAPL")
        assert p["name"] == "Apple Inc"
        assert p["ticker"] == "AAPL"
        assert p["finnhubIndustry"] == "Technology"

    def test_get_mock_profile_unknown(self):
        from mock_data import get_mock_profile

        p = get_mock_profile("XYZ")
        assert p["name"] == "XYZ Inc"
        assert p["ticker"] == "XYZ"

    def test_get_mock_financials(self):
        from mock_data import get_mock_financials

        f = get_mock_financials("AAPL")
        assert "peTTM" in f
        assert "epsTTM" in f
        assert "52WeekHigh" in f
        assert "52WeekLow" in f
        assert f["52WeekHigh"] > f["52WeekLow"]

    def test_get_mock_daily(self):
        from mock_data import get_mock_daily

        d = get_mock_daily("AAPL", years=2)
        assert d["s"] == "ok"
        assert len(d["c"]) == 504  # 2 * 252
        assert len(d["o"]) == len(d["c"])
        assert len(d["h"]) == len(d["c"])
        assert len(d["l"]) == len(d["c"])
        assert len(d["v"]) == len(d["c"])
        assert len(d["t"]) == len(d["c"])

    def test_get_mock_weekly(self):
        from mock_data import get_mock_weekly

        w = get_mock_weekly("AAPL", years=3)
        assert w["s"] == "ok"
        assert len(w["c"]) == 156  # 3 * 52

    def test_get_mock_monthly(self):
        from mock_data import get_mock_monthly

        m = get_mock_monthly("AAPL", years=5)
        assert m["s"] == "ok"
        assert len(m["c"]) == 60  # 5 * 12

    def test_get_mock_news(self):
        from mock_data import get_mock_news

        news = get_mock_news("AAPL")
        assert len(news) == 10
        for article in news:
            assert "headline" in article
            assert "source" in article
            assert "url" in article
            assert "datetime" in article

    def test_get_mock_recommendations(self):
        from mock_data import get_mock_recommendations

        recs = get_mock_recommendations("AAPL")
        assert len(recs) >= 1
        r = recs[0]
        assert "buy" in r and "hold" in r and "sell" in r

    def test_get_mock_earnings(self):
        from mock_data import get_mock_earnings

        e = get_mock_earnings("AAPL", limit=4)
        assert len(e) == 4
        for entry in e:
            assert "actual" in entry
            assert "estimate" in entry

    def test_get_mock_peers(self):
        from mock_data import get_mock_peers

        p = get_mock_peers("AAPL")
        assert len(p) >= 3
        assert "MSFT" in p

    def test_get_mock_option_chain(self):
        from mock_data import get_mock_option_chain

        chain = get_mock_option_chain("AAPL")
        assert "data" in chain
        assert len(chain["data"]) >= 1
        expiry = chain["data"][0]
        assert "CALL" in expiry["options"]
        assert "PUT" in expiry["options"]

    def test_get_mock_insider_transactions(self):
        from mock_data import get_mock_insider_transactions

        txns = get_mock_insider_transactions("AAPL")
        assert len(txns) >= 1
        for t in txns:
            assert "name" in t
            assert "transactionCode" in t

    def test_get_mock_short_interest(self):
        from mock_data import get_mock_short_interest

        si = get_mock_short_interest("AAPL")
        assert si["available"] is True
        assert si["short_pct_float"] > 0

    def test_get_mock_macro_context(self):
        from mock_data import get_mock_macro_context

        m = get_mock_macro_context()
        assert m["vix"] is not None
        assert m["risk_free_rate"] == 0.05

    def test_get_mock_estimate_revisions(self):
        from mock_data import get_mock_estimate_revisions

        r = get_mock_estimate_revisions("AAPL")
        assert r["available"] is True
        assert r["forward_eps"] is not None

    def test_get_mock_analyst_price_targets(self):
        from mock_data import get_mock_analyst_price_targets

        t = get_mock_analyst_price_targets("AAPL")
        assert t["available"] is True
        assert t["low_target"] < t["high_target"]

    def test_get_mock_earnings_history(self):
        from mock_data import get_mock_earnings_history

        h = get_mock_earnings_history("AAPL")
        assert len(h) == 10
        for entry in h:
            assert "date" in entry
            assert "actual" in entry

    def test_get_mock_dividends(self):
        from mock_data import get_mock_dividends

        d = get_mock_dividends("AAPL")
        assert "dates" in d and "amounts" in d
        assert len(d["dates"]) == len(d["amounts"])
        assert len(d["dates"]) > 0

    def test_get_mock_analysis_text(self):
        from mock_data import get_mock_analysis_text

        text = get_mock_analysis_text("AAPL")
        assert "Apple Inc" in text
        assert "AAPL" in text
        assert len(text) > 100

    def test_get_mock_sentiment_text(self):
        from mock_data import get_mock_sentiment_text

        text = get_mock_sentiment_text("AAPL")
        assert "AAPL" in text
        assert "Sentiment" in text


# ---------------------------------------------------------------------------
# MockFinnhubAPI tests
# ---------------------------------------------------------------------------


class TestMockFinnhubAPI:
    def test_mock_mode_flag(self):
        from api import MOCK_MODE

        assert MOCK_MODE is True

    def test_get_api_returns_mock(self):
        from api import MockFinnhubAPI, get_api

        api = get_api()
        assert isinstance(api, MockFinnhubAPI)

    def test_all_endpoints_return_valid_data(self):
        from api import get_api

        api = get_api()

        # Quote
        q = api.get_quote("AAPL")
        assert q["c"] > 0

        # Profile
        p = api.get_profile("MSFT")
        assert p["name"] == "Microsoft Corporation"

        # Financials
        f = api.get_financials("TSLA")
        assert "peTTM" in f

        # Daily
        d = api.get_daily("NVDA", years=1)
        assert d["s"] == "ok"

        # News
        n = api.get_news("GOOGL")
        assert len(n) > 0

        # Recommendations
        r = api.get_recommendations("AAPL")
        assert len(r) > 0

        # Earnings
        e = api.get_earnings("AAPL", limit=4)
        assert len(e) == 4

        # Peers
        peers = api.get_peers("AAPL")
        assert len(peers) > 0

        # Options
        opts = api.get_option_metrics("AAPL")
        assert opts["available"] is True

        # Insider
        ins = api.get_insider_transactions("AAPL")
        assert len(ins) > 0

        # Short interest
        si = api.get_short_interest("AAPL")
        assert si["available"] is True

        # Macro
        m = api.get_macro_context()
        assert m["vix"] is not None

        # Risk-free rate
        rf = api.get_risk_free_rate()
        assert rf > 0

        # Earnings calendar
        ec = api.get_earnings_calendar("AAPL")
        assert ec["next_date"] is not None

        # Transcripts
        tl = api.get_transcripts_list("AAPL")
        assert len(tl) > 0

        t = api.get_transcript(tl[0]["id"])
        assert "transcript" in t

        # Analyst targets
        at = api.get_analyst_price_targets("AAPL")
        assert at["available"] is True

        # Earnings history
        eh = api.get_earnings_history("AAPL")
        assert len(eh) > 0

        # Dividends
        dv = api.get_dividends("AAPL")
        assert len(dv["dates"]) > 0

        # Weekly / Monthly
        w = api.get_weekly("AAPL")
        assert w["s"] == "ok"
        mo = api.get_monthly("AAPL")
        assert mo["s"] == "ok"

        # Estimate revisions
        er = api.get_estimate_revisions("AAPL")
        assert er["available"] is True

    def test_fetch_all_parallel(self):
        from api import get_api

        api = get_api()
        result = api.fetch_all_parallel("AAPL")
        assert "quote" in result
        assert "profile" in result
        assert "financials" in result
        assert "daily" in result
        assert "news" in result
        assert "latency_breakdown" in result
        assert result["latency_breakdown"]["_total"] >= 0


# ---------------------------------------------------------------------------
# Mock sentiment tests
# ---------------------------------------------------------------------------


class TestMockSentiment:
    def test_mock_sentiment_scoring(self):
        from sentiment import score_articles

        articles = [
            {"headline": "Company reports strong earnings beat"},
            {"headline": "Stock declines amid weak guidance"},
            {"headline": "Annual meeting held downtown"},
        ]
        scores = score_articles(articles)
        assert len(scores) == 3
        for s in scores:
            assert s["label"] in ("positive", "negative", "neutral")
            assert 0 < s["score"] <= 1.0

    def test_mock_sentiment_positive_keywords(self):
        from sentiment import score_articles

        articles = [{"headline": "Strong growth beats expectations"}]
        scores = score_articles(articles)
        assert scores[0]["label"] == "positive"

    def test_mock_sentiment_negative_keywords(self):
        from sentiment import score_articles

        articles = [{"headline": "Weak earnings miss estimates, stock declines"}]
        scores = score_articles(articles)
        assert scores[0]["label"] == "negative"


# ---------------------------------------------------------------------------
# Mock AI backend tests
# ---------------------------------------------------------------------------


class TestMockAIBackend:
    def test_mock_ai_streams_text(self):
        from analyzer import MockAIBackend

        backend = MockAIBackend()
        chunks = list(
            backend.stream(
                model="test",
                max_tokens=100,
                messages=[{"role": "user", "content": "Analyze AAPL stock"}],
            )
        )
        text = "".join(chunks)
        assert len(text) > 100
        assert "Apple" in text

    def test_mock_ai_sentiment_context(self):
        from analyzer import MockAIBackend

        backend = MockAIBackend()
        chunks = list(
            backend.stream(
                model="test",
                max_tokens=100,
                messages=[{"role": "user", "content": "Analyze MSFT stock"}],
                system="You are a sentiment analysis expert",
            )
        )
        text = "".join(chunks)
        assert "Sentiment" in text

    def test_mock_ai_unknown_ticker(self):
        from analyzer import MockAIBackend

        backend = MockAIBackend()
        chunks = list(
            backend.stream(
                model="test",
                max_tokens=100,
                messages=[{"role": "user", "content": "Do something generic"}],
            )
        )
        text = "".join(chunks)
        assert "mock analysis" in text.lower()


# ---------------------------------------------------------------------------
# Integration: factor computation with mock data
# ---------------------------------------------------------------------------


class TestMockFactorIntegration:
    def test_factors_with_mock_data(self):
        import pandas as pd

        from api import get_api
        from factors import composite_score, compute_factors
        from sentiment import aggregate_sentiment, score_articles

        api = get_api()
        quote = api.get_quote("AAPL")
        financials = api.get_financials("AAPL")
        daily = api.get_daily("AAPL")
        close = pd.Series(daily["c"])
        news = api.get_news("AAPL")
        scores = score_articles(news)
        agg = aggregate_sentiment(scores)

        factors = compute_factors(
            quote=quote,
            financials=financials,
            close=close,
            earnings=api.get_earnings("AAPL"),
            recommendations=api.get_recommendations("AAPL"),
            sentiment_agg=agg,
            sector="Technology",
        )
        assert len(factors) >= 8
        score = composite_score(factors)
        assert 0 <= score <= 100

    def test_risk_with_mock_data(self):
        import pandas as pd

        from api import get_api
        from factors import composite_score, compute_factors
        from guardrails import compute_risk
        from sentiment import aggregate_sentiment, score_articles

        api = get_api()
        quote = api.get_quote("AAPL")
        financials = api.get_financials("AAPL")
        daily = api.get_daily("AAPL")
        close = pd.Series(daily["c"])
        news = api.get_news("AAPL")
        scores = score_articles(news)
        agg = aggregate_sentiment(scores)

        factors = compute_factors(
            quote=quote,
            financials=financials,
            close=close,
            earnings=api.get_earnings("AAPL"),
            recommendations=api.get_recommendations("AAPL"),
            sentiment_agg=agg,
            sector="Technology",
        )
        fscore = composite_score(factors)

        risk = compute_risk(
            quote=quote,
            financials=financials,
            close=close,
            earnings=api.get_earnings("AAPL"),
            recommendations=api.get_recommendations("AAPL"),
            sentiment_agg=agg,
            composite_factor_score=fscore,
            macro_context=api.get_macro_context(),
        )
        assert 0 <= risk["risk_score"] <= 100
        assert risk["risk_level"] in ("Low", "Moderate", "Elevated", "High", "Extreme")

    def test_backtest_with_mock_data(self):
        import pandas as pd

        from api import get_api
        from backtest import run_backtest

        api = get_api()
        daily = api.get_daily("AAPL", years=3)
        df = pd.DataFrame(
            {
                "Date": pd.to_datetime(daily["t"], unit="s"),
                "Open": daily["o"],
                "High": daily["h"],
                "Low": daily["l"],
                "Close": daily["c"],
                "Volume": daily["v"],
            }
        )
        result = run_backtest(df, symbol="AAPL", entry_threshold=65, exit_threshold=40)
        assert result.total_trades >= 0
        assert result.total_return_pct is not None
