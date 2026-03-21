"""Fake finnhub module for integration tests.

Returns realistic mock data without making real API calls.
"""

from __future__ import annotations
import time

# ---------------------------------------------------------------------------
# Shared mock data helpers
# ---------------------------------------------------------------------------


def _make_candles(symbol: str, n: int = 200) -> dict:
    """Generate fake daily candle data."""
    import random

    random.seed(hash(symbol) % 2**32)
    base = 150.0
    ts_end = int(time.time())
    ts_start = ts_end - n * 86400

    timestamps = list(range(ts_start, ts_end, 86400))[:n]
    closes = []
    opens = []
    highs = []
    lows = []
    volumes = []

    price = base
    for _ in timestamps:
        change = random.gauss(0, 2.5)
        price = max(10.0, price + change)
        open_p = price * random.uniform(0.99, 1.01)
        high_p = max(price, open_p) * random.uniform(1.0, 1.02)
        low_p = min(price, open_p) * random.uniform(0.98, 1.0)
        vol = int(random.uniform(5_000_000, 30_000_000))
        closes.append(round(price, 2))
        opens.append(round(open_p, 2))
        highs.append(round(high_p, 2))
        lows.append(round(low_p, 2))
        volumes.append(vol)

    return {
        "c": closes,
        "o": opens,
        "h": highs,
        "l": lows,
        "v": volumes,
        "t": timestamps,
        "s": "ok",
    }


# Pre-built mock responses keyed by symbol
_MOCK_QUOTE = {
    "c": 178.25,
    "d": 2.45,
    "dp": 1.39,
    "h": 179.80,
    "l": 175.20,
    "o": 176.00,
    "pc": 175.80,
    "t": int(time.time()),
}

_MOCK_PROFILE = {
    "name": "Apple Inc.",
    "ticker": "AAPL",
    "finnhubIndustry": "Technology",
    "exchange": "NASDAQ",
    "ipo": "1980-12-12",
    "logo": "",
    "marketCapitalization": 2_800_000,
    "shareOutstanding": 15_700_000,
    "weburl": "https://www.apple.com",
    "country": "US",
    "currency": "USD",
    "phone": "14089961010",
}

_MOCK_FINANCIALS_METRIC = {
    "peBasicExclExtraTTM": 28.5,
    "epsBasicExclExtraItemsTTM": 6.25,
    "marketCapitalization": 2_800_000,
    "52WeekHigh": 199.62,
    "52WeekLow": 124.17,
    "dividendYieldIndicatedAnnual": 0.55,
    "beta": 1.20,
    "revenueGrowthTTMYoy": 0.085,
    "grossMarginTTM": 0.44,
    "netProfitMarginTTM": 0.25,
    "currentRatioAnnual": 1.07,
    "longTermDebt/equityAnnual": 1.52,
    "10DayAverageTradingVolume": 55_000_000.0,
    "3MonthAverageTradingVolume": 60_000_000.0,
}

_MOCK_NEWS = [
    {
        "headline": "Apple unveils new AI-powered chips for next-gen devices",
        "summary": "Apple announced breakthrough neural processing units.",
        "source": "TechCrunch",
        "url": "https://example.com/apple-chips",
        "datetime": int(time.time()) - 3600,
        "sentiment": 0.8,
        "category": "technology",
    },
    {
        "headline": "Apple reports strong Q3 earnings, beats analyst estimates",
        "summary": "Revenue grew 8% year-over-year to $91.2 billion.",
        "source": "Reuters",
        "url": "https://example.com/apple-earnings",
        "datetime": int(time.time()) - 7200,
        "sentiment": 0.7,
        "category": "earnings",
    },
    {
        "headline": "Analysts raise Apple price targets ahead of product launch",
        "summary": "Multiple Wall Street firms lifted their targets.",
        "source": "Bloomberg",
        "url": "https://example.com/apple-targets",
        "datetime": int(time.time()) - 10800,
        "sentiment": 0.6,
        "category": "analyst",
    },
]

_MOCK_RECOMMENDATIONS = [
    {
        "buy": 28,
        "hold": 8,
        "sell": 2,
        "strongBuy": 15,
        "strongSell": 0,
        "period": "2024-01-01",
    },
    {
        "buy": 25,
        "hold": 10,
        "sell": 3,
        "strongBuy": 12,
        "strongSell": 1,
        "period": "2023-10-01",
    },
    {
        "buy": 22,
        "hold": 12,
        "sell": 4,
        "strongBuy": 10,
        "strongSell": 0,
        "period": "2023-07-01",
    },
]

_MOCK_EARNINGS = [
    {
        "actual": 1.52,
        "estimate": 1.43,
        "period": "2024-06-30",
        "symbol": "AAPL",
        "surprise": 0.09,
        "surprisePercent": 6.29,
    },
    {
        "actual": 2.18,
        "estimate": 2.10,
        "period": "2024-03-31",
        "symbol": "AAPL",
        "surprise": 0.08,
        "surprisePercent": 3.81,
    },
    {
        "actual": 2.18,
        "estimate": 2.11,
        "period": "2023-12-31",
        "symbol": "AAPL",
        "surprise": 0.07,
        "surprisePercent": 3.32,
    },
    {
        "actual": 1.26,
        "estimate": 1.19,
        "period": "2023-09-30",
        "symbol": "AAPL",
        "surprise": 0.07,
        "surprisePercent": 5.88,
    },
]

_MOCK_PEERS = ["MSFT", "GOOGL", "META", "AMZN", "NVDA"]


class Client:
    """Fake Finnhub client that returns mock data."""

    def __init__(self, api_key: str = ""):
        self._api_key = api_key
        self._candle_cache: dict[str, dict] = {}

    def quote(self, symbol: str) -> dict:
        import random

        random.seed(hash(symbol) % 2**32)
        base_price = random.uniform(50, 500)
        change = random.uniform(-5, 5)
        return {
            "c": round(base_price, 2),
            "d": round(change, 2),
            "dp": round(change / base_price * 100, 2),
            "h": round(base_price + abs(change) + random.uniform(0, 3), 2),
            "l": round(base_price - abs(change) - random.uniform(0, 3), 2),
            "o": round(base_price - change * 0.5, 2),
            "pc": round(base_price - change, 2),
            "t": int(time.time()),
        }

    def company_profile2(self, symbol: str = "") -> dict:
        sectors = {
            "AAPL": "Technology",
            "MSFT": "Technology",
            "GOOGL": "Technology",
            "AMZN": "Consumer Cyclical",
            "META": "Technology",
            "NVDA": "Technology",
            "JPM": "Financial Services",
            "BAC": "Financial Services",
            "XOM": "Energy",
            "CVX": "Energy",
            "JNJ": "Healthcare",
            "PFE": "Healthcare",
        }
        names = {
            "AAPL": "Apple Inc.",
            "MSFT": "Microsoft Corporation",
            "GOOGL": "Alphabet Inc.",
            "AMZN": "Amazon.com Inc.",
            "META": "Meta Platforms Inc.",
            "NVDA": "NVIDIA Corporation",
            "JPM": "JPMorgan Chase & Co.",
            "BAC": "Bank of America Corporation",
        }
        return {
            "name": names.get(symbol, f"{symbol} Corporation"),
            "ticker": symbol,
            "finnhubIndustry": sectors.get(symbol, "Technology"),
            "exchange": "NASDAQ",
            "ipo": "1995-01-01",
            "logo": "",
            "marketCapitalization": 2_000_000,
            "shareOutstanding": 10_000_000,
            "weburl": f"https://www.{symbol.lower()}.com",
            "country": "US",
            "currency": "USD",
            "phone": "14081234567",
        }

    def company_basic_financials(self, symbol: str, metric_type: str = "all") -> dict:
        import random

        random.seed(hash(symbol) % 2**32 + 1)
        return {
            "symbol": symbol,
            "metricType": "all",
            "metric": {
                "peBasicExclExtraTTM": round(random.uniform(15, 45), 1),
                "epsBasicExclExtraItemsTTM": round(random.uniform(2, 10), 2),
                "marketCapitalization": random.randint(500_000, 3_000_000),
                "52WeekHigh": round(random.uniform(150, 250), 2),
                "52WeekLow": round(random.uniform(80, 130), 2),
                "dividendYieldIndicatedAnnual": round(random.uniform(0, 3), 2),
                "beta": round(random.uniform(0.5, 1.8), 2),
                "revenueGrowthTTMYoy": round(random.uniform(-0.05, 0.25), 3),
                "grossMarginTTM": round(random.uniform(0.25, 0.60), 3),
                "netProfitMarginTTM": round(random.uniform(0.05, 0.30), 3),
                "currentRatioAnnual": round(random.uniform(0.8, 2.5), 2),
                "longTermDebt/equityAnnual": round(random.uniform(0.2, 2.0), 2),
                "10DayAverageTradingVolume": random.randint(20_000_000, 80_000_000),
                "3MonthAverageTradingVolume": random.randint(25_000_000, 75_000_000),
            },
        }

    def stock_candles(self, symbol: str, resolution: str, _from: int, to: int) -> dict:
        cache_key = f"{symbol}:{resolution}"
        if cache_key not in self._candle_cache:
            self._candle_cache[cache_key] = _make_candles(symbol + resolution)
        return self._candle_cache[cache_key]

    def company_news(self, symbol: str, _from: str = "", to: str = "") -> list:
        return [
            {
                "headline": f"{symbol} reports strong quarterly results",
                "summary": f"{symbol} exceeded analyst expectations with solid revenue growth.",
                "source": "Reuters",
                "url": "https://example.com/news/1",
                "datetime": int(time.time()) - 3600,
                "category": "company",
            },
            {
                "headline": f"Analysts bullish on {symbol} outlook",
                "summary": f"Multiple investment banks upgraded their price targets for {symbol}.",
                "source": "Bloomberg",
                "url": "https://example.com/news/2",
                "datetime": int(time.time()) - 7200,
                "category": "company",
            },
            {
                "headline": f"{symbol} expands into new markets with strategic acquisition",
                "summary": f"{symbol} announced a deal to accelerate growth.",
                "source": "WSJ",
                "url": "https://example.com/news/3",
                "datetime": int(time.time()) - 10800,
                "category": "merger",
            },
        ]

    def recommendation_trends(self, symbol: str) -> list:
        return [
            {
                "buy": 25,
                "hold": 8,
                "sell": 2,
                "strongBuy": 12,
                "strongSell": 0,
                "period": "2024-01-01",
            },
            {
                "buy": 22,
                "hold": 10,
                "sell": 3,
                "strongBuy": 10,
                "strongSell": 1,
                "period": "2023-10-01",
            },
            {
                "buy": 20,
                "hold": 12,
                "sell": 4,
                "strongBuy": 8,
                "strongSell": 0,
                "period": "2023-07-01",
            },
        ]

    def company_earnings(self, symbol: str, limit: int = 4) -> list:
        import random

        random.seed(hash(symbol) % 2**32 + 2)
        results = []
        periods = [
            "2024-06-30",
            "2024-03-31",
            "2023-12-31",
            "2023-09-30",
            "2023-06-30",
            "2023-03-31",
            "2022-12-31",
            "2022-09-30",
            "2022-06-30",
            "2022-03-31",
        ]
        for period in periods[:limit]:
            est = round(random.uniform(1.0, 3.0), 2)
            surprise = round(random.uniform(-0.1, 0.2), 2)
            actual = round(est + surprise, 2)
            results.append(
                {
                    "actual": actual,
                    "estimate": est,
                    "period": period,
                    "symbol": symbol,
                    "surprise": round(surprise, 2),
                    "surprisePercent": round(surprise / est * 100, 2),
                }
            )
        return results

    def company_peers(self, symbol: str) -> list:
        peer_map = {
            "AAPL": ["MSFT", "GOOGL", "META", "AMZN", "NVDA"],
            "MSFT": ["AAPL", "GOOGL", "AMZN", "ORCL", "CRM"],
            "GOOGL": ["META", "MSFT", "AAPL", "AMZN", "NFLX"],
        }
        return peer_map.get(symbol, ["SPY", "QQQ", "MSFT", "AAPL"])

    def stock_options(self, symbol: str) -> dict:
        return {}  # No options data on free tier

    def stock_transcripts_list(self, symbol: str) -> dict:
        return {"transcripts": []}

    def stock_transcript(self, transcript_id: str) -> dict:
        return {}

    def earnings_calendar(
        self, _from: str = "", to: str = "", symbol: str = ""
    ) -> dict:
        return {"earningsCalendar": []}

    def stock_insider_transactions(
        self, symbol: str, _from: str = "", to: str = ""
    ) -> dict:
        return {"data": []}

    def stock_price_target(self, symbol: str) -> dict:
        import random

        random.seed(hash(symbol) % 2**32 + 3)
        base = random.uniform(100, 300)
        return {
            "lastUpdated": "2024-01-01",
            "symbol": symbol,
            "targetHigh": round(base * 1.3, 2),
            "targetLow": round(base * 0.8, 2),
            "targetMean": round(base * 1.1, 2),
            "targetMedian": round(base * 1.08, 2),
        }
