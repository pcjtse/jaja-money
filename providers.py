"""Multi-data-source provider with automatic fallback.

Priority: Finnhub (primary) → yfinance (fallback).

yfinance is an optional dependency; if not installed the provider
silently degrades to Finnhub-only mode.
"""
from __future__ import annotations

import time
from typing import Any


from log_setup import get_logger

log = get_logger(__name__)

# Optional yfinance
try:
    import yfinance as yf
    _HAS_YFINANCE = True
except ImportError:
    _HAS_YFINANCE = False
    log.info("yfinance not installed — Finnhub-only mode")


# ---------------------------------------------------------------------------
# yfinance helpers
# ---------------------------------------------------------------------------

def _yf_quote(symbol: str) -> dict:
    t = yf.Ticker(symbol)
    info = t.info
    price = info.get("currentPrice") or info.get("regularMarketPrice") or 0
    prev = info.get("previousClose") or info.get("regularMarketPreviousClose") or 0
    high = info.get("dayHigh") or info.get("regularMarketDayHigh") or 0
    low = info.get("dayLow") or info.get("regularMarketDayLow") or 0
    change = price - prev
    change_pct = (change / prev * 100) if prev else 0
    return {"c": price, "d": change, "dp": change_pct, "h": high, "l": low, "pc": prev}


def _yf_profile(symbol: str) -> dict:
    t = yf.Ticker(symbol)
    info = t.info
    return {
        "name": info.get("longName") or info.get("shortName") or symbol,
        "finnhubIndustry": info.get("sector") or info.get("industry") or "N/A",
        "logo": info.get("logo_url") or "",
        "country": info.get("country") or "N/A",
        "exchange": info.get("exchange") or "N/A",
    }


def _yf_financials(symbol: str) -> dict:
    t = yf.Ticker(symbol)
    info = t.info
    mc = info.get("marketCap")
    return {
        "peBasicExclExtraTTM": info.get("trailingPE"),
        "epsBasicExclExtraItemsTTM": info.get("trailingEps"),
        "marketCapitalization": mc / 1e6 if mc else None,  # Finnhub uses millions
        "dividendYieldIndicatedAnnual": (info.get("dividendYield") or 0) * 100,
        "52WeekHigh": info.get("fiftyTwoWeekHigh"),
        "52WeekLow": info.get("fiftyTwoWeekLow"),
    }


def _yf_daily(symbol: str, years: int = 2) -> dict:
    t = yf.Ticker(symbol)
    hist = t.history(period=f"{years}y", interval="1d")
    if hist.empty:
        raise ValueError(f"No daily data for '{symbol}' via yfinance")
    return {
        "c": hist["Close"].tolist(),
        "h": hist["High"].tolist(),
        "l": hist["Low"].tolist(),
        "o": hist["Open"].tolist(),
        "v": hist["Volume"].tolist(),
        "t": [int(ts.timestamp()) for ts in hist.index],
        "s": "ok",
    }


def _yf_news(symbol: str, days: int = 7) -> list:
    t = yf.Ticker(symbol)
    news = t.news or []
    cutoff = int(time.time()) - days * 86400
    result = []
    for item in news:
        ts = item.get("providerPublishTime") or item.get("publishTime") or 0
        if ts < cutoff:
            continue
        result.append({
            "headline": item.get("title") or item.get("headline", ""),
            "summary": item.get("summary", ""),
            "source": item.get("publisher") or item.get("source", ""),
            "url": item.get("link") or item.get("url", ""),
            "datetime": ts,
        })
    return result


def _yf_recommendations(symbol: str) -> list:
    t = yf.Ticker(symbol)
    recs = t.recommendations
    if recs is None or recs.empty:
        return []
    # yfinance returns a DataFrame; convert to Finnhub format
    try:
        latest = recs.iloc[-1]
        return [{
            "period": str(recs.index[-1])[:10],
            "strongBuy": int(latest.get("strongBuy", 0)),
            "buy": int(latest.get("buy", 0)),
            "hold": int(latest.get("hold", 0)),
            "sell": int(latest.get("sell", 0)),
            "strongSell": int(latest.get("strongSell", 0)),
        }]
    except Exception:
        return []


def _yf_earnings(symbol: str, limit: int = 4) -> list:
    t = yf.Ticker(symbol)
    try:
        hist = t.quarterly_earnings
        if hist is None or hist.empty:
            return []
        result = []
        for idx, row in hist.tail(limit).iterrows():
            actual = row.get("Reported EPS") or row.get("actual")
            estimate = row.get("EPS Estimate") or row.get("estimate")
            surprise_pct = None
            if actual is not None and estimate and estimate != 0:
                surprise_pct = (actual - estimate) / abs(estimate) * 100
            result.append({
                "period": str(idx)[:10] if hasattr(idx, "__str__") else "",
                "actual": actual,
                "estimate": estimate,
                "surprisePercent": surprise_pct,
            })
        return result
    except Exception:
        return []


def _yf_peers(symbol: str) -> list:
    # yfinance doesn't have a direct peers endpoint
    return []


# ---------------------------------------------------------------------------
# Public provider class
# ---------------------------------------------------------------------------

class DataProvider:
    """Unified data provider: Finnhub first, yfinance fallback."""

    def __init__(self, source_preference: str = "auto") -> None:
        """
        source_preference: "auto" | "finnhub" | "yfinance"
        """
        self._pref = source_preference
        self._source_used = "finnhub"

        # Lazy import to avoid circular dep
        from api import FinnhubAPI
        try:
            self._finnhub = FinnhubAPI()
            self._has_finnhub = True
        except ValueError:
            self._has_finnhub = False
            log.warning("Finnhub API key not set; will use yfinance only")

    @property
    def source_used(self) -> str:
        return self._source_used

    def _try_finnhub(self, method: str, *args, **kwargs) -> Any:
        if not self._has_finnhub:
            raise RuntimeError("Finnhub unavailable")
        fn = getattr(self._finnhub, method)
        return fn(*args, **kwargs)

    def _call(self, finnhub_method: str, yf_fn, *args, **kwargs) -> Any:
        if self._pref == "yfinance":
            if not _HAS_YFINANCE:
                raise ValueError("yfinance not installed")
            self._source_used = "yfinance"
            return yf_fn(*args)

        # Try Finnhub first (auto or explicit)
        if self._has_finnhub and self._pref != "yfinance":
            try:
                result = self._try_finnhub(finnhub_method, *args, **kwargs)
                self._source_used = "finnhub"
                return result
            except Exception as exc:
                log.warning("Finnhub %s failed (%s); falling back to yfinance", finnhub_method, exc)

        # Fallback to yfinance
        if _HAS_YFINANCE:
            self._source_used = "yfinance"
            return yf_fn(*args)

        raise ValueError(f"No data source available for {finnhub_method}")

    def get_quote(self, symbol: str) -> dict:
        return self._call("get_quote", _yf_quote, symbol)

    def get_profile(self, symbol: str) -> dict:
        return self._call("get_profile", _yf_profile, symbol)

    def get_financials(self, symbol: str) -> dict:
        return self._call("get_financials", _yf_financials, symbol)

    def get_daily(self, symbol: str, years: int = 2) -> dict:
        return self._call("get_daily", _yf_daily, symbol, years=years)

    def get_news(self, symbol: str, days: int = 7) -> list:
        return self._call("get_news", _yf_news, symbol, days=days)

    def get_recommendations(self, symbol: str) -> list:
        return self._call("get_recommendations", _yf_recommendations, symbol)

    def get_earnings(self, symbol: str, limit: int = 4) -> list:
        return self._call("get_earnings", _yf_earnings, symbol, limit=limit)

    def get_peers(self, symbol: str) -> list:
        if self._has_finnhub:
            try:
                result = self._try_finnhub("get_peers", symbol)
                self._source_used = "finnhub"
                return result
            except Exception:
                pass
        return _yf_peers(symbol)
