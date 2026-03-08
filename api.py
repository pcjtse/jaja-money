"""Finnhub API wrapper.

Enhanced with:
- Disk cache (P1.5)
- Options market data (P2.6)
- Earnings call transcript fetch (P2.3)
- Structured logging (P4.3)
"""
from __future__ import annotations

import os
import time
import finnhub
from dotenv import load_dotenv

from cache import get_cache
from config import cfg
from log_setup import get_logger

load_dotenv()

log = get_logger(__name__)
_disk_cache = get_cache()


class FinnhubAPI:
    def __init__(self):
        api_key = os.getenv("FINNHUB_API_KEY")
        if not api_key or api_key == "your_api_key_here":
            raise ValueError(
                "FINNHUB_API_KEY not set. "
                "Copy .env.example to .env and add your API key."
            )
        self.client = finnhub.Client(api_key=api_key)

    def _cached(self, key: str, fn, ttl: int | None = None):
        """Get from disk cache or call fn() and store result."""
        ttl = ttl if ttl is not None else cfg.cache_ttl
        if cfg.use_disk_cache:
            cached = _disk_cache.get(key)
            if cached is not None:
                return cached
        t0 = time.monotonic()
        result = fn()
        elapsed = time.monotonic() - t0
        log.debug("API call '%s' took %.2fs", key, elapsed)
        if cfg.use_disk_cache:
            _disk_cache.set(key, result, ttl=ttl)
        return result

    def get_quote(self, symbol: str) -> dict:
        """Return real-time quote with keys: c, d, dp, h, l, o, pc, t."""
        def _fetch():
            data = self.client.quote(symbol)
            if not data or data.get("c") is None or data.get("c") == 0:
                raise ValueError(f"No quote data found for symbol '{symbol}'.")
            return data
        return self._cached(f"quote:{symbol}", _fetch, ttl=60)  # quotes expire faster

    def get_profile(self, symbol: str) -> dict:
        """Return company profile: name, finnhubIndustry, logo, etc."""
        def _fetch():
            data = self.client.company_profile2(symbol=symbol)
            if not data or not data.get("name"):
                raise ValueError(f"No profile data found for symbol '{symbol}'.")
            return data
        return self._cached(f"profile:{symbol}", _fetch)

    def get_financials(self, symbol: str) -> dict:
        """Return basic financials (metric key has P/E, EPS, market cap, etc.)."""
        def _fetch():
            data = self.client.company_basic_financials(symbol, "all")
            if not data or not data.get("metric"):
                raise ValueError(f"No financial data found for symbol '{symbol}'.")
            return data["metric"]
        return self._cached(f"financials:{symbol}", _fetch)

    def get_daily(self, symbol: str, years: int = 2) -> dict:
        """Return daily candles for the last `years` years."""
        def _fetch():
            to_ts = int(time.time())
            from_ts = to_ts - (years * 365 * 24 * 60 * 60)
            data = self.client.stock_candles(symbol, "D", from_ts, to_ts)
            if not data or data.get("s") != "ok":
                raise ValueError(f"No daily price data found for symbol '{symbol}'.")
            return data
        return self._cached(f"daily:{symbol}:{years}y", _fetch)

    def get_news(self, symbol: str, days: int = 7) -> list:
        """Return recent company news articles for the last `days` days."""
        def _fetch():
            to_dt = time.strftime("%Y-%m-%d", time.localtime())
            from_dt = time.strftime(
                "%Y-%m-%d",
                time.localtime(time.time() - days * 24 * 60 * 60),
            )
            data = self.client.company_news(symbol, _from=from_dt, to=to_dt)
            return data if data else []
        return self._cached(f"news:{symbol}:{days}d", _fetch, ttl=900)

    def get_recommendations(self, symbol: str) -> list:
        """Return analyst recommendation trends (buy/hold/sell counts)."""
        def _fetch():
            data = self.client.recommendation_trends(symbol)
            return data if data else []
        return self._cached(f"recs:{symbol}", _fetch)

    def get_earnings(self, symbol: str, limit: int = 4) -> list:
        """Return recent EPS surprises (actual vs. estimated earnings)."""
        def _fetch():
            data = self.client.company_earnings(symbol, limit=limit)
            return data if data else []
        return self._cached(f"earnings:{symbol}:{limit}", _fetch)

    def get_peers(self, symbol: str) -> list:
        """Return list of peer/comparable company ticker symbols."""
        def _fetch():
            data = self.client.company_peers(symbol)
            return data if data else []
        return self._cached(f"peers:{symbol}", _fetch)

    # ------------------------------------------------------------------
    # P2.6: Options Market Data
    # ------------------------------------------------------------------

    def get_option_chain(self, symbol: str) -> dict:
        """Return option chain data.

        Returns dict with keys: code, data (list of expiry dates with strikes).
        Falls back to empty dict if unavailable on free tier.
        """
        def _fetch():
            try:
                data = self.client.stock_options(symbol)
                return data if data else {}
            except Exception as exc:
                log.warning("Option chain unavailable for %s: %s", symbol, exc)
                return {}
        return self._cached(f"options:{symbol}", _fetch, ttl=600)

    def get_option_metrics(self, symbol: str) -> dict:
        """Derive simple options metrics: IV estimate, put/call ratio.

        Finnhub free tier has limited options data; we compute what we can
        and return empty fields where data is unavailable.
        """
        chain = self.get_option_chain(symbol)
        if not chain or not chain.get("data"):
            return {"available": False}

        expirations = chain.get("data", [])
        if not expirations:
            return {"available": False}

        # Use nearest expiry
        nearest = expirations[0]
        options_list = nearest.get("options", {})
        calls = options_list.get("CALL", [])
        puts = options_list.get("PUT", [])

        total_call_vol = sum(c.get("volume", 0) or 0 for c in calls)
        total_put_vol = sum(p.get("volume", 0) or 0 for p in puts)

        pc_ratio = (total_put_vol / total_call_vol) if total_call_vol > 0 else None

        # Average implied volatility from ATM options
        all_ivs = [
            o.get("impliedVolatility", 0) or 0
            for o in (calls + puts)
            if o.get("impliedVolatility")
        ]
        avg_iv = (sum(all_ivs) / len(all_ivs) * 100) if all_ivs else None

        return {
            "available": True,
            "expiry": nearest.get("expirationDate", ""),
            "put_call_ratio": round(pc_ratio, 3) if pc_ratio else None,
            "avg_iv_pct": round(avg_iv, 1) if avg_iv else None,
            "total_call_volume": total_call_vol,
            "total_put_volume": total_put_vol,
        }

    # ------------------------------------------------------------------
    # P2.3: Earnings Call Transcripts
    # ------------------------------------------------------------------

    def get_transcripts_list(self, symbol: str) -> list:
        """Return list of available earnings call transcripts."""
        def _fetch():
            try:
                data = self.client.stock_transcripts_list(symbol)
                return data.get("transcripts", []) if data else []
            except Exception as exc:
                log.warning("Transcripts list unavailable for %s: %s", symbol, exc)
                return []
        return self._cached(f"transcripts_list:{symbol}", _fetch, ttl=86400)

    def get_transcript(self, transcript_id: str) -> dict:
        """Return a specific earnings call transcript by ID."""
        def _fetch():
            try:
                data = self.client.stock_transcript(transcript_id)
                return data if data else {}
            except Exception as exc:
                log.warning("Transcript %s unavailable: %s", transcript_id, exc)
                return {}
        return self._cached(f"transcript:{transcript_id}", _fetch, ttl=86400 * 7)
