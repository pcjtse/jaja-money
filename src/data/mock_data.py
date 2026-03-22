"""Mock data module for local testing without real API keys.

Provides realistic stock data for all FinnhubAPI endpoints so the dashboard
can be run and tested locally with ``MOCK_DATA=1 streamlit run app.py``.
"""

from __future__ import annotations

import random
import time

# ---------------------------------------------------------------------------
# Seed for reproducible mock data
# ---------------------------------------------------------------------------
random.seed(42)


def _generate_candles(base_price: float, days: int, volatility: float = 0.02) -> dict:
    """Generate realistic OHLCV candle data."""
    now = int(time.time())
    day_sec = 86400
    closes = []
    opens = []
    highs = []
    lows = []
    volumes = []
    timestamps = []

    price = base_price * 0.7  # start lower so there's a visible uptrend
    for i in range(days):
        change = random.gauss(0.0003, volatility)
        price = price * (1 + change)
        o = round(price * (1 + random.uniform(-0.005, 0.005)), 2)
        c = round(price, 2)
        h = round(max(o, c) * (1 + random.uniform(0, 0.015)), 2)
        lo = round(min(o, c) * (1 - random.uniform(0, 0.015)), 2)
        v = int(random.gauss(50_000_000, 15_000_000))
        if v < 1_000_000:
            v = 1_000_000

        opens.append(o)
        closes.append(c)
        highs.append(h)
        lows.append(lo)
        volumes.append(v)
        timestamps.append(now - (days - i) * day_sec)

    return {
        "s": "ok",
        "o": opens,
        "c": closes,
        "h": highs,
        "l": lows,
        "v": volumes,
        "t": timestamps,
    }


# ---------------------------------------------------------------------------
# Per-ticker mock data definitions
# ---------------------------------------------------------------------------

MOCK_PROFILES = {
    "AAPL": {
        "country": "US",
        "currency": "USD",
        "exchange": "NASDAQ NMS - GLOBAL MARKET",
        "finnhubIndustry": "Technology",
        "ipo": "1980-12-12",
        "logo": "https://static2.finnhub.io/file/publicdatany/finnhubimage/stock_logo/AAPL.png",
        "marketCapitalization": 3200000,
        "name": "Apple Inc",
        "phone": "14089961010",
        "shareOutstanding": 15400,
        "ticker": "AAPL",
        "weburl": "https://www.apple.com/",
    },
    "MSFT": {
        "country": "US",
        "currency": "USD",
        "exchange": "NASDAQ NMS - GLOBAL MARKET",
        "finnhubIndustry": "Technology",
        "ipo": "1986-03-13",
        "logo": "https://static2.finnhub.io/file/publicdatany/finnhubimage/stock_logo/MSFT.png",
        "marketCapitalization": 3100000,
        "name": "Microsoft Corporation",
        "phone": "14258828080",
        "shareOutstanding": 7430,
        "ticker": "MSFT",
        "weburl": "https://www.microsoft.com",
    },
    "GOOGL": {
        "country": "US",
        "currency": "USD",
        "exchange": "NASDAQ NMS - GLOBAL MARKET",
        "finnhubIndustry": "Technology",
        "ipo": "2004-08-19",
        "logo": "https://static2.finnhub.io/file/publicdatany/finnhubimage/stock_logo/GOOGL.png",
        "marketCapitalization": 2100000,
        "name": "Alphabet Inc",
        "phone": "16502530000",
        "shareOutstanding": 5920,
        "ticker": "GOOGL",
        "weburl": "https://abc.xyz",
    },
    "TSLA": {
        "country": "US",
        "currency": "USD",
        "exchange": "NASDAQ NMS - GLOBAL MARKET",
        "finnhubIndustry": "Automobiles",
        "ipo": "2010-06-29",
        "logo": "https://static2.finnhub.io/file/publicdatany/finnhubimage/stock_logo/TSLA.png",
        "marketCapitalization": 800000,
        "name": "Tesla Inc",
        "phone": "16506815000",
        "shareOutstanding": 3190,
        "ticker": "TSLA",
        "weburl": "https://www.tesla.com",
    },
    "NVDA": {
        "country": "US",
        "currency": "USD",
        "exchange": "NASDAQ NMS - GLOBAL MARKET",
        "finnhubIndustry": "Technology",
        "ipo": "1999-01-22",
        "logo": "https://static2.finnhub.io/file/publicdatany/finnhubimage/stock_logo/NVDA.png",
        "marketCapitalization": 2800000,
        "name": "NVIDIA Corporation",
        "phone": "14084862000",
        "shareOutstanding": 24500,
        "ticker": "NVDA",
        "weburl": "https://www.nvidia.com",
    },
}

_PRICE_BASES = {
    "AAPL": 195.0,
    "MSFT": 420.0,
    "GOOGL": 175.0,
    "TSLA": 250.0,
    "NVDA": 130.0,
}

_PE_RATIOS = {
    "AAPL": 32.5,
    "MSFT": 37.2,
    "GOOGL": 25.8,
    "TSLA": 72.3,
    "NVDA": 65.1,
}

_EPS = {
    "AAPL": 6.42,
    "MSFT": 11.53,
    "GOOGL": 6.85,
    "TSLA": 3.45,
    "NVDA": 2.13,
}


def _default_profile(symbol: str) -> dict:
    """Generate a generic profile for unknown tickers."""
    return {
        "country": "US",
        "currency": "USD",
        "exchange": "NASDAQ",
        "finnhubIndustry": "Technology",
        "ipo": "2015-01-01",
        "logo": "",
        "marketCapitalization": 50000,
        "name": f"{symbol} Inc",
        "phone": "10000000000",
        "shareOutstanding": 1000,
        "ticker": symbol,
        "weburl": f"https://www.{symbol.lower()}.com",
    }


def get_mock_quote(symbol: str) -> dict:
    base = _PRICE_BASES.get(symbol, 100.0)
    # Add small random variation
    c = round(base * (1 + random.uniform(-0.02, 0.02)), 2)
    pc = round(c * (1 + random.uniform(-0.03, -0.001)), 2)
    d = round(c - pc, 2)
    dp = round(d / pc * 100, 2)
    return {
        "c": c,
        "d": d,
        "dp": dp,
        "h": round(c * 1.012, 2),
        "l": round(c * 0.988, 2),
        "o": round(pc * (1 + random.uniform(-0.005, 0.005)), 2),
        "pc": pc,
        "t": int(time.time()),
    }


def get_mock_profile(symbol: str) -> dict:
    return MOCK_PROFILES.get(symbol, _default_profile(symbol))


def get_mock_financials(symbol: str) -> dict:
    pe = _PE_RATIOS.get(symbol, 28.0)
    eps = _EPS.get(symbol, 4.50)
    base = _PRICE_BASES.get(symbol, 100.0)
    mcap = MOCK_PROFILES.get(symbol, {}).get("marketCapitalization", 50000)
    return {
        "peBasicExclExtraTTM": pe,
        "peTTM": pe,
        "epsBasicExclExtraItemsTTM": eps,
        "epsTTM": eps,
        "revenuePerShareTTM": round(eps * 5.2, 2),
        "roeTTM": round(random.uniform(15, 45), 2),
        "roaTTM": round(random.uniform(8, 25), 2),
        "debtEquityTTM": round(random.uniform(0.3, 2.5), 2),
        "currentRatioTTM": round(random.uniform(0.8, 3.0), 2),
        "grossMarginTTM": round(random.uniform(35, 75), 2),
        "operatingMarginTTM": round(random.uniform(15, 45), 2),
        "netProfitMarginTTM": round(random.uniform(10, 35), 2),
        "dividendYieldIndicatedAnnual": round(random.uniform(0, 2.5), 4),
        "payoutRatioTTM": round(random.uniform(10, 50), 2),
        "revenueGrowthTTMYoy": round(random.uniform(-5, 30), 2),
        "epsGrowthTTMYoy": round(random.uniform(-10, 40), 2),
        "52WeekHigh": round(base * 1.15, 2),
        "52WeekLow": round(base * 0.72, 2),
        "10DayAverageTradingVolume": round(random.uniform(30, 100), 2),
        "3MonthAverageTradingVolume": round(random.uniform(30, 90), 2),
        "marketCapitalization": mcap,
        "beta": round(random.uniform(0.8, 1.8), 3),
        "priceSalesRatioTTM": round(random.uniform(3, 15), 2),
        "priceBookValueTTM": round(random.uniform(5, 50), 2),
        "freeCashFlowPerShareTTM": round(eps * 1.2, 2),
        "cashPerShareTTM": round(eps * 3.5, 2),
    }


def get_mock_daily(symbol: str, years: int = 2) -> dict:
    base = _PRICE_BASES.get(symbol, 100.0)
    return _generate_candles(base, days=years * 252)


def get_mock_weekly(symbol: str, years: int = 3) -> dict:
    base = _PRICE_BASES.get(symbol, 100.0)
    return _generate_candles(base, days=years * 52, volatility=0.035)


def get_mock_monthly(symbol: str, years: int = 5) -> dict:
    base = _PRICE_BASES.get(symbol, 100.0)
    return _generate_candles(base, days=years * 12, volatility=0.06)


def get_mock_news(symbol: str, days: int = 7) -> list:
    name = MOCK_PROFILES.get(symbol, {}).get("name", symbol)
    headlines = [
        f"{name} Reports Strong Quarterly Earnings, Beats Estimates",
        f"Analysts Upgrade {symbol} After Impressive Revenue Growth",
        f"{name} Announces New Product Launch for 2026",
        f"Wall Street Remains Bullish on {symbol} Ahead of Earnings",
        f"{name} Expands Into New Markets with Strategic Partnership",
        f"{symbol} Stock Hits 52-Week High Amid Market Rally",
        f"Institutional Investors Increase Stakes in {name}",
        f"{name} CEO Outlines Vision for AI Integration",
        f"Supply Chain Improvements Boost {name} Margins",
        f"{symbol} Dividend Increase Signals Management Confidence",
    ]
    now = int(time.time())
    articles = []
    for i, headline in enumerate(headlines):
        articles.append(
            {
                "category": "company",
                "datetime": now - i * 8600,
                "headline": headline,
                "id": 100000 + i,
                "image": "",
                "related": symbol,
                "source": random.choice(
                    ["Reuters", "Bloomberg", "CNBC", "MarketWatch", "WSJ"]
                ),
                "summary": f"Summary for: {headline}",
                "url": f"https://example.com/news/{symbol.lower()}-{i}",
            }
        )
    return articles


def get_mock_recommendations(symbol: str) -> list:
    now_month = time.strftime("%Y-%m-01")
    return [
        {
            "buy": random.randint(10, 25),
            "hold": random.randint(5, 15),
            "period": now_month,
            "sell": random.randint(0, 5),
            "strongBuy": random.randint(5, 15),
            "strongSell": random.randint(0, 3),
            "symbol": symbol,
        }
    ]


def get_mock_earnings(symbol: str, limit: int = 4) -> list:
    eps = _EPS.get(symbol, 4.50)
    results = []
    for i in range(min(limit, 8)):
        q = (i % 4) + 1
        year = 2025 - (i // 4)
        estimate = round(eps * (1 + random.uniform(-0.1, 0.1)), 2)
        actual = round(estimate * (1 + random.uniform(-0.05, 0.15)), 2)
        results.append(
            {
                "actual": actual,
                "estimate": estimate,
                "period": f"{year}-{q * 3:02d}-30",
                "quarter": q,
                "surprise": round(actual - estimate, 4),
                "surprisePercent": round((actual - estimate) / abs(estimate) * 100, 2)
                if estimate
                else 0,
                "symbol": symbol,
                "year": year,
            }
        )
    return results


def get_mock_peers(symbol: str) -> list:
    peer_map = {
        "AAPL": ["MSFT", "GOOGL", "AMZN", "META", "NVDA"],
        "MSFT": ["AAPL", "GOOGL", "AMZN", "META", "CRM"],
        "GOOGL": ["META", "MSFT", "AMZN", "AAPL", "SNAP"],
        "TSLA": ["F", "GM", "RIVN", "NIO", "LCID"],
        "NVDA": ["AMD", "INTC", "AVGO", "QCOM", "MRVL"],
    }
    return peer_map.get(symbol, ["AAPL", "MSFT", "GOOGL"])


def get_mock_option_chain(symbol: str) -> dict:
    base = _PRICE_BASES.get(symbol, 100.0)
    strikes = [round(base * (0.85 + i * 0.05), 2) for i in range(7)]
    calls = []
    puts = []
    for strike in strikes:
        distance = abs(strike - base) / base
        iv = round(0.25 + distance * 0.5 + random.uniform(0, 0.1), 4)
        calls.append(
            {
                "strike": strike,
                "lastPrice": round(max(base - strike, 0) + random.uniform(1, 8), 2),
                "ask": round(max(base - strike, 0) + random.uniform(2, 10), 2),
                "bid": round(max(base - strike, 0) + random.uniform(0.5, 7), 2),
                "volume": random.randint(100, 5000),
                "openInterest": random.randint(500, 20000),
                "impliedVolatility": iv,
            }
        )
        puts.append(
            {
                "strike": strike,
                "lastPrice": round(max(strike - base, 0) + random.uniform(1, 8), 2),
                "ask": round(max(strike - base, 0) + random.uniform(2, 10), 2),
                "bid": round(max(strike - base, 0) + random.uniform(0.5, 7), 2),
                "volume": random.randint(100, 5000),
                "openInterest": random.randint(500, 20000),
                "impliedVolatility": iv,
            }
        )
    return {
        "code": symbol,
        "data": [
            {
                "expirationDate": "2026-04-17",
                "options": {"CALL": calls, "PUT": puts},
            }
        ],
    }


def get_mock_insider_transactions(symbol: str) -> list:
    names = [
        "John Smith (CEO)",
        "Jane Doe (CFO)",
        "Robert Johnson (Director)",
        "Emily Williams (VP Engineering)",
    ]
    txns = []
    for i, name in enumerate(names):
        txns.append(
            {
                "name": name,
                "share": random.randint(1000, 50000),
                "change": random.randint(-20000, 30000),
                "transactionDate": f"2026-03-{15 - i * 3:02d}",
                "transactionCode": random.choice(["P", "S", "P"]),
                "transactionPrice": round(
                    _PRICE_BASES.get(symbol, 100) * random.uniform(0.95, 1.05), 2
                ),
            }
        )
    return txns


def get_mock_short_interest(symbol: str) -> dict:
    return {
        "available": True,
        "short_pct_float": round(random.uniform(1.0, 8.0), 2),
        "shares_short": random.randint(5_000_000, 50_000_000),
        "days_to_cover": round(random.uniform(1.0, 5.0), 1),
    }


def get_mock_macro_context() -> dict:
    return {
        "vix": round(random.uniform(12, 25), 2),
        "yield_2y": round(random.uniform(3.5, 5.0), 3),
        "yield_10y": round(random.uniform(3.8, 4.8), 3),
        "spread_2y10y": round(random.uniform(-0.5, 0.5), 3),
        "tbill_3m": round(random.uniform(4.5, 5.5), 3),
        "risk_free_rate": 0.05,
    }


def get_mock_estimate_revisions(symbol: str) -> dict:
    eps = _EPS.get(symbol, 4.50)
    return {
        "forward_eps": round(eps * 1.1, 2),
        "trailing_eps": eps,
        "analyst_count": random.randint(20, 45),
        "recommendation_mean": round(random.uniform(1.5, 3.0), 1),
        "revision_direction": random.choice(["up", "up", "flat"]),
        "available": True,
    }


def get_mock_transcripts_list(symbol: str) -> list:
    return [
        {"id": f"{symbol}_2025_Q4", "title": f"{symbol} Q4 2025 Earnings Call"},
        {"id": f"{symbol}_2025_Q3", "title": f"{symbol} Q3 2025 Earnings Call"},
    ]


def get_mock_transcript(transcript_id: str) -> dict:
    symbol = transcript_id.split("_")[0] if "_" in transcript_id else "AAPL"
    name = MOCK_PROFILES.get(symbol, {}).get("name", symbol)
    return {
        "symbol": symbol,
        "transcript": [
            {
                "name": "Operator",
                "speech": [f"Good afternoon, and welcome to the {name} earnings call."],
            },
            {
                "name": "CEO",
                "speech": [
                    "Thank you. We delivered strong results this quarter.",
                    "Revenue grew 15% year-over-year driven by our core business.",
                    "We continue to invest in AI capabilities across our product lineup.",
                ],
            },
            {
                "name": "CFO",
                "speech": [
                    "Gross margin expanded 200 basis points to 46%.",
                    "Free cash flow was $12 billion for the quarter.",
                    "We returned $8 billion to shareholders through buybacks.",
                ],
            },
        ],
    }


def get_mock_earnings_calendar(symbol: str) -> dict:
    return {
        "next_date": "2026-04-25",
        "days_to_earnings": 34,
        "historical_reactions": [],
        "implied_move_pct": round(random.uniform(3.0, 8.0), 2),
    }


def get_mock_analyst_price_targets(symbol: str) -> dict:
    base = _PRICE_BASES.get(symbol, 100.0)
    mean_t = round(base * random.uniform(1.05, 1.25), 2)
    return {
        "available": True,
        "current_price_target": mean_t,
        "low_target": round(base * 0.85, 2),
        "high_target": round(base * 1.45, 2),
        "mean_target": mean_t,
        "median_target": round(mean_t * 0.98, 2),
        "analyst_count": random.randint(20, 40),
    }


def get_mock_earnings_history(symbol: str) -> list:
    eps = _EPS.get(symbol, 4.50)
    results = []
    for i in range(10):
        q = (i % 4) + 1
        year = 2025 - (i // 4)
        estimate = round(eps * (1 + random.uniform(-0.15, 0.15)), 2)
        actual = round(estimate * (1 + random.uniform(-0.05, 0.12)), 2)
        surprise = round(actual - estimate, 4)
        surprise_pct = round(surprise / abs(estimate) * 100, 2) if estimate else 0
        results.append(
            {
                "date": f"{year}-{q * 3:02d}-30",
                "actual": actual,
                "estimate": estimate,
                "surprise": surprise,
                "surprisePercent": surprise_pct,
            }
        )
    return results


def get_mock_dividends(symbol: str) -> dict:
    """Return mock dividend history."""
    dates = []
    amounts = []
    base_div = round(random.uniform(0.2, 1.5), 2)
    for yr in range(2021, 2026):
        for q in [3, 6, 9, 12]:
            dates.append(f"{yr}-{q:02d}-15")
            amounts.append(round(base_div * (1 + random.uniform(-0.05, 0.08)), 4))
    return {"dates": dates, "amounts": amounts}


# ---------------------------------------------------------------------------
# Mock AI analysis text
# ---------------------------------------------------------------------------


def get_mock_analysis_text(symbol: str) -> str:
    name = MOCK_PROFILES.get(symbol, {}).get("name", f"{symbol} Inc")
    return f"""## Fundamental Analysis: {name} ({symbol})

### Overview
{name} continues to demonstrate strong market positioning with solid revenue
growth and expanding margins. The company benefits from secular tailwinds in
its core markets and has shown consistent execution.

### Key Strengths
- **Revenue Growth**: Double-digit year-over-year revenue growth driven by
  strong demand across product segments
- **Margin Expansion**: Operating margins have improved 200bps YoY reflecting
  operating leverage and cost discipline
- **Free Cash Flow**: Robust FCF generation enabling share buybacks and
  strategic investments
- **Market Position**: Dominant market share in core segments with expanding TAM

### Key Risks
- **Valuation**: Trading at premium multiples relative to historical averages
- **Macro Sensitivity**: Revenue could decelerate in an economic slowdown
- **Competition**: Intensifying competitive landscape in key growth areas
- **Regulatory**: Potential for increased regulatory scrutiny

### Outlook
Management guidance suggests continued momentum with expected revenue growth
of 12-15% in the next quarter. The company's investment in AI capabilities
positions it well for the next wave of technology adoption.

**Overall Assessment**: {name} remains well-positioned for long-term growth
with a balanced risk/reward profile at current levels.
"""


def get_mock_sentiment_text(symbol: str) -> str:
    name = MOCK_PROFILES.get(symbol, {}).get("name", f"{symbol} Inc")
    return f"""## News Sentiment Analysis: {symbol}

### Dominant Themes
1. **Earnings Momentum** — Recent results exceeded expectations, driving
   positive sentiment. Multiple analysts have raised price targets.
2. **AI/Technology** — {name}'s AI strategy is generating significant buzz.
   Market participants view AI investments as a key growth catalyst.
3. **Market Leadership** — Coverage highlights {name}'s dominant position
   and competitive moats in core markets.

### Sentiment Summary
- **Overall Tone**: Moderately Bullish
- **Key Catalysts**: Strong earnings, AI narrative, margin improvement
- **Key Concerns**: Valuation stretch, macro uncertainty
- Consensus remains positive with 70% of coverage maintaining buy ratings.
"""
