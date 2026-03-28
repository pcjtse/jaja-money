"""Finnhub API wrapper.

Enhanced with:
- Disk cache (P1.5)
- Options market data (P2.6)
- Earnings call transcript fetch (P2.3)
- Structured logging (P4.3)
- Centralized rate limiting (audit fix)
- Retry with exponential backoff on transient errors (audit fix)
- Mock data mode for local testing (set MOCK_DATA=1)
"""

from __future__ import annotations

import os
import time

from dotenv import load_dotenv

load_dotenv()

# Mock mode flag — set MOCK_DATA=1 to use synthetic data without API keys
MOCK_MODE = os.getenv("MOCK_DATA", "").strip().lower() in ("1", "true", "yes")

try:
    import finnhub
except ImportError:
    finnhub = None  # type: ignore[assignment]

from src.core.cache import get_cache, CACHE_MISS  # noqa: E402
from src.core.config import cfg  # noqa: E402
from src.core.log_setup import get_logger  # noqa: E402
from src.core.rate_limiter import finnhub_limiter  # noqa: E402

log = get_logger(__name__)
_disk_cache = get_cache()

# Transient exceptions that warrant a retry
_RETRYABLE_MSGS = ("429", "too many requests", "rate limit", "503", "502", "timeout")
_MAX_RETRIES = 3


def _is_retryable(exc: Exception) -> bool:
    """Return True if the exception looks transient / rate-limited."""
    msg = str(exc).lower()
    return any(token in msg for token in _RETRYABLE_MSGS)


class FinnhubAPI:
    def __init__(self):
        if finnhub is None:
            raise ImportError(
                "The `finnhub-python` package is not installed. "
                "Run `pip install finnhub-python` or set MOCK_DATA=1 for local testing."
            )
        api_key = os.getenv("FINNHUB_API_KEY")
        if not api_key or api_key == "your_api_key_here":
            raise ValueError(
                "FINNHUB_API_KEY not set. "
                "Copy .env.example to .env and add your API key."
            )
        self.client = finnhub.Client(api_key=api_key)

    def _cached(self, key: str, fn, ttl: int | None = None):
        """Get from disk cache or call fn() with rate limiting and retry."""
        ttl = ttl if ttl is not None else cfg.cache_ttl
        if cfg.use_disk_cache:
            cached = _disk_cache.get(key)
            if cached is not CACHE_MISS:
                return cached

        # Rate-limit + retry with exponential backoff
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            finnhub_limiter.acquire()
            try:
                t0 = time.monotonic()
                result = fn()
                elapsed = time.monotonic() - t0
                log.debug("API call '%s' took %.2fs", key, elapsed)
                if cfg.use_disk_cache:
                    _disk_cache.set(key, result, ttl=ttl)
                return result
            except Exception as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES and _is_retryable(exc):
                    wait = 2**attempt  # 1s, 2s, 4s
                    log.warning(
                        "API call '%s' failed (attempt %d/%d): %s — retrying in %ds",
                        key,
                        attempt + 1,
                        _MAX_RETRIES + 1,
                        exc,
                        wait,
                    )
                    time.sleep(wait)
                else:
                    raise
        raise last_exc  # type: ignore[misc]

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

    # ------------------------------------------------------------------
    # P5.3: Earnings Calendar
    # ------------------------------------------------------------------

    def get_earnings_calendar(
        self,
        symbol: str,
        option_chain: dict | None = None,
        quote: dict | None = None,
    ) -> dict:
        """Return next earnings date and implied move from ATM straddle.

        Parameters
        ----------
        symbol       : stock ticker symbol
        option_chain : pre-fetched option chain (avoids extra API call)
        quote        : pre-fetched quote (avoids extra API call)

        Returns dict with: next_date (str|None), days_to_earnings (int|None),
        historical_reactions (list of {date, change_pct}),
        implied_move_pct (float|None) computed from ATM straddle / current price.

        Note: without pre-fetched data this triggers up to 3 API calls
        (calendar + option_chain + quote).
        """
        # Capture pre-fetched data in closure to avoid extra API calls
        _prefetched_chain = option_chain
        _prefetched_quote = quote

        def _fetch():
            try:
                import time as _time

                from_dt = _time.strftime("%Y-%m-%d")
                to_dt = _time.strftime(
                    "%Y-%m-%d", _time.localtime(_time.time() + 90 * 24 * 3600)
                )
                cal = self.client.earnings_calendar(
                    _from=from_dt, to=to_dt, symbol=symbol
                )
                earnings_list = (cal or {}).get("earningsCalendar", [])
                if not earnings_list:
                    return {
                        "next_date": None,
                        "days_to_earnings": None,
                        "historical_reactions": [],
                        "implied_move_pct": None,
                    }
                # Sort by date ascending and pick first future date
                import datetime as _dt

                today = _dt.date.today()
                future = [e for e in earnings_list if e.get("date")]
                future.sort(key=lambda x: x["date"])
                next_event = future[0] if future else None
                next_date = next_event["date"] if next_event else None
                days = None
                if next_date:
                    try:
                        d = _dt.date.fromisoformat(next_date)
                        days = (d - today).days
                    except Exception:
                        pass

                # Compute implied move from ATM straddle if options available
                implied_move_pct = None
                try:
                    chain = (
                        _prefetched_chain
                        if _prefetched_chain is not None
                        else self.get_option_chain(symbol)
                    )
                    if chain and chain.get("data"):
                        q = (
                            _prefetched_quote
                            if _prefetched_quote is not None
                            else self.get_quote(symbol)
                        )
                        current_price = float(q.get("c", 0) or 0)
                        if current_price > 0:
                            nearest = chain["data"][0]
                            options_map = nearest.get("options", {})
                            calls = options_map.get("CALL", [])
                            puts = options_map.get("PUT", [])
                            valid_calls = [
                                c for c in calls if c.get("strike") is not None
                            ]
                            valid_puts = [
                                p for p in puts if p.get("strike") is not None
                            ]
                            if valid_calls and valid_puts:
                                atm_call = min(
                                    valid_calls,
                                    key=lambda c: abs(
                                        float(c["strike"]) - current_price
                                    ),
                                )
                                atm_put = min(
                                    valid_puts,
                                    key=lambda p: abs(
                                        float(p["strike"]) - current_price
                                    ),
                                )
                                call_ask = float(
                                    atm_call.get("ask")
                                    or atm_call.get("lastPrice")
                                    or 0
                                )
                                put_ask = float(
                                    atm_put.get("ask") or atm_put.get("lastPrice") or 0
                                )
                                if call_ask > 0 and put_ask > 0:
                                    straddle = call_ask + put_ask
                                    implied_move_pct = round(
                                        straddle / current_price * 100, 2
                                    )
                except Exception as exc:
                    log.debug("Implied move calc failed for %s: %s", symbol, exc)

                return {
                    "next_date": next_date,
                    "days_to_earnings": days,
                    "historical_reactions": [],
                    "implied_move_pct": implied_move_pct,
                }
            except Exception as exc:
                log.warning("Earnings calendar unavailable for %s: %s", symbol, exc)
                return {
                    "next_date": None,
                    "days_to_earnings": None,
                    "historical_reactions": [],
                    "implied_move_pct": None,
                }

        return self._cached(f"earnings_cal:{symbol}", _fetch, ttl=3600 * 6)

    # ------------------------------------------------------------------
    # P5.4: Insider Trading
    # ------------------------------------------------------------------

    def get_insider_transactions(self, symbol: str) -> list:
        """Return insider transactions for the last 90 days.

        Each entry: {name, share, change, transactionDate, transactionCode}
        transactionCode: 'P' = purchase, 'S' = sale
        """

        def _fetch():
            try:
                import time as _t

                to_dt = _t.strftime("%Y-%m-%d")
                from_dt = _t.strftime(
                    "%Y-%m-%d", _t.localtime(_t.time() - 90 * 24 * 3600)
                )
                data = self.client.stock_insider_transactions(
                    symbol, _from=from_dt, to=to_dt
                )
                txns = (data or {}).get("data", [])
                return txns if txns else []
            except Exception as exc:
                log.warning("Insider transactions unavailable for %s: %s", symbol, exc)
                return []

        return self._cached(f"insider:{symbol}", _fetch, ttl=3600 * 12)

    # ------------------------------------------------------------------
    # P5.5: Short Interest
    # ------------------------------------------------------------------

    def get_short_interest(self, symbol: str) -> dict:
        """Return short interest data.

        Falls back to yfinance for short percent of float if Finnhub unavailable.
        Returns: {short_interest (shares), short_pct_float, days_to_cover, available}
        """

        def _fetch():
            # Try yfinance first as it has better short data
            try:
                import yfinance as yf

                ticker = yf.Ticker(symbol)
                info = ticker.info or {}
                short_pct = info.get("shortPercentOfFloat")
                shares_short = info.get("sharesShort")
                avg_vol = info.get("averageVolume")
                days_to_cover = None
                if shares_short and avg_vol and avg_vol > 0:
                    days_to_cover = round(shares_short / avg_vol, 1)
                return {
                    "available": short_pct is not None,
                    "short_pct_float": round(float(short_pct) * 100, 2)
                    if short_pct
                    else None,
                    "shares_short": shares_short,
                    "days_to_cover": days_to_cover,
                }
            except Exception as exc:
                log.warning("Short interest unavailable for %s: %s", symbol, exc)
                return {"available": False}

        return self._cached(f"short_interest:{symbol}", _fetch, ttl=3600 * 6)

    # ------------------------------------------------------------------
    # P5.6 / P8.3: Macroeconomic Context & Live Risk-Free Rate
    # ------------------------------------------------------------------

    def get_macro_context(self) -> dict:
        """Return VIX, yield spread, and 3-month T-bill rate.

        Uses yfinance for VIX and Treasury data (free, no key required).
        Returns: {vix, yield_2y, yield_10y, spread_2y10y, tbill_3m, risk_free_rate}
        """

        def _fetch():
            result = {
                "vix": None,
                "yield_2y": None,
                "yield_10y": None,
                "spread_2y10y": None,
                "tbill_3m": None,
                "risk_free_rate": 0.05,  # default fallback
            }
            try:
                import yfinance as yf

                # Fetch VIX, 2Y, 10Y Treasury, 3M T-bill
                tickers = yf.download(
                    ["^VIX", "^IRX", "^TNX", "^TYX"],
                    period="5d",
                    progress=False,
                    auto_adjust=True,
                )
                if tickers is not None and not tickers.empty:
                    close = tickers["Close"] if "Close" in tickers else tickers

                    def _last(col):
                        try:
                            s = close[col].dropna()
                            return float(s.iloc[-1]) if len(s) > 0 else None
                        except Exception:
                            return None

                    vix = _last("^VIX")
                    irx = _last("^IRX")  # 13-week T-bill rate (annualized %)
                    tnx = _last("^TNX")  # 10Y Treasury yield
                    # 2Y not directly available; use ^TNX - spread approximation
                    _last("^TYX")  # 30Y Treasury

                    result["vix"] = round(vix, 2) if vix else None
                    result["yield_10y"] = (
                        round(tnx / 10, 3) if tnx else None
                    )  # ^TNX is in *10
                    # ^TNX reports in units of 0.1%, so actual yield = value / 10
                    tnx_pct = round(tnx / 10, 3) if tnx else None
                    irx_pct = round(irx / 10, 3) if irx else None
                    result["yield_10y"] = tnx_pct
                    result["tbill_3m"] = irx_pct
                    if irx_pct:
                        result["risk_free_rate"] = irx_pct / 100

                    # 2Y not directly in yfinance; approximate from ^TNX and ^IRX midpoint
                    if tnx_pct and irx_pct:
                        yield_2y = (tnx_pct + irx_pct) / 2
                        result["yield_2y"] = round(yield_2y, 3)
                        result["spread_2y10y"] = round(tnx_pct - yield_2y, 3)
            except Exception as exc:
                log.warning("Macro context fetch failed: %s", exc)
            return result

        return self._cached("macro_context", _fetch, ttl=3600 * 24)

    def get_risk_free_rate(self) -> float:
        """Return the current 3-month T-bill rate (as decimal, e.g., 0.05 = 5%).

        Cached for 24 hours. Falls back to 5% if unavailable.
        """
        macro = self.get_macro_context()
        return macro.get("risk_free_rate", 0.05)

    # ------------------------------------------------------------------
    # P5.2: Analyst Estimate Revisions
    # ------------------------------------------------------------------

    def get_estimate_revisions(self, symbol: str) -> dict:
        """Return EPS estimate revision data from yfinance.

        Returns dict with current_estimate, revision_direction ('up'|'down'|'flat'),
        analyst_count.
        """

        def _fetch():
            try:
                import yfinance as yf

                ticker = yf.Ticker(symbol)
                info = ticker.info or {}
                # Use forward EPS and number of analyst opinions as proxy
                forward_eps = info.get("forwardEps")
                trailing_eps = info.get("trailingEps")
                analyst_count = info.get("numberOfAnalystOpinions")
                recommendation_mean = info.get(
                    "recommendationMean"
                )  # 1=Strong Buy, 5=Sell

                # Try to get earnings estimates history
                try:
                    earnings_df = ticker.earnings_history
                    if earnings_df is not None and not earnings_df.empty:
                        # Check surprise direction for recent quarters
                        recent = earnings_df.tail(4)
                        pos_surprises = (
                            (recent["Surprise(%)"] > 0).sum()
                            if "Surprise(%)" in recent.columns
                            else 0
                        )
                        neg_surprises = (
                            (recent["Surprise(%)"] < 0).sum()
                            if "Surprise(%)" in recent.columns
                            else 0
                        )
                        if pos_surprises > neg_surprises:
                            direction = "up"
                        elif neg_surprises > pos_surprises:
                            direction = "down"
                        else:
                            direction = "flat"
                    else:
                        direction = "flat"
                except Exception:
                    direction = "flat"

                return {
                    "forward_eps": forward_eps,
                    "trailing_eps": trailing_eps,
                    "analyst_count": analyst_count,
                    "recommendation_mean": recommendation_mean,
                    "revision_direction": direction,
                    "available": forward_eps is not None,
                }
            except Exception as exc:
                log.warning("Estimate revisions unavailable for %s: %s", symbol, exc)
                return {"available": False, "revision_direction": "flat"}

        return self._cached(f"estimates:{symbol}", _fetch, ttl=3600 * 12)

    # ------------------------------------------------------------------
    # P6.3: Historical dividends for backtest reinvestment
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # P15.3: Weekly and Monthly Candles (multi-timeframe)
    # ------------------------------------------------------------------

    def get_weekly(self, symbol: str, years: int = 3) -> dict:
        """Return weekly candles for the last `years` years.

        Useful for multi-timeframe trend analysis. Cached for 1 hour.
        """

        def _fetch():
            to_ts = int(time.time())
            from_ts = to_ts - (years * 365 * 24 * 60 * 60)
            data = self.client.stock_candles(symbol, "W", from_ts, to_ts)
            if not data or data.get("s") != "ok":
                raise ValueError(f"No weekly price data found for symbol '{symbol}'.")
            return data

        return self._cached(f"weekly:{symbol}:{years}y", _fetch, ttl=3600)

    def get_monthly(self, symbol: str, years: int = 5) -> dict:
        """Return monthly candles for the last `years` years.

        Useful for long-term trend analysis. Cached for 24 hours.
        """

        def _fetch():
            to_ts = int(time.time())
            from_ts = to_ts - (years * 365 * 24 * 60 * 60)
            data = self.client.stock_candles(symbol, "M", from_ts, to_ts)
            if not data or data.get("s") != "ok":
                raise ValueError(f"No monthly price data found for symbol '{symbol}'.")
            return data

        return self._cached(f"monthly:{symbol}:{years}y", _fetch, ttl=86400)

    # ------------------------------------------------------------------
    # P19.1: Analyst Price Targets
    # ------------------------------------------------------------------

    def get_analyst_price_targets(self, symbol: str) -> dict:
        """Return analyst consensus price targets from Finnhub.

        Returns dict with keys: available, current_price_target, low_target,
        high_target, mean_target, median_target, analyst_count.
        Cached for 24 hours.
        """

        def _fetch():
            try:
                data = self.client.stock_price_target(symbol)
                if not data:
                    return {"available": False}
                mean_target = data.get("targetMean") or data.get("targetConsensus")
                return {
                    "available": mean_target is not None,
                    "current_price_target": data.get("targetConsensus"),
                    "low_target": data.get("targetLow"),
                    "high_target": data.get("targetHigh"),
                    "mean_target": data.get("targetMean"),
                    "median_target": data.get("targetMedian"),
                    "analyst_count": data.get(
                        "lastUpdated"
                    ),  # Finnhub returns lastUpdated
                }
            except Exception as exc:
                log.warning("Analyst price targets unavailable for %s: %s", symbol, exc)
                return {"available": False}

        return self._cached(f"price_targets:{symbol}", _fetch, ttl=86400)

    # ------------------------------------------------------------------
    # P19.4: Extended Earnings History (8+ quarters)
    # ------------------------------------------------------------------

    def get_earnings_history(self, symbol: str) -> list:
        """Return up to 10 quarters of earnings history.

        Each entry includes: date, actual, estimate, surprise, surprisePercent.
        Cached for 24 hours.
        """

        def _fetch():
            try:
                data = self.client.company_earnings(symbol, limit=10)
                if not data:
                    return []
                results = []
                for entry in data:
                    surprise = None
                    surprise_pct = None
                    actual = entry.get("actual")
                    estimate = entry.get("estimate")
                    if actual is not None and estimate is not None:
                        try:
                            surprise = round(float(actual) - float(estimate), 4)
                            if estimate != 0:
                                surprise_pct = round(
                                    surprise / abs(float(estimate)) * 100, 2
                                )
                        except (TypeError, ValueError):
                            pass
                    results.append(
                        {
                            "date": entry.get("period", entry.get("date", "")),
                            "actual": actual,
                            "estimate": estimate,
                            "surprise": surprise,
                            "surprisePercent": surprise_pct,
                        }
                    )
                return results
            except Exception as exc:
                log.warning("Earnings history unavailable for %s: %s", symbol, exc)
                return []

        return self._cached(f"earnings_history:{symbol}", _fetch, ttl=86400)

    def get_dividends(self, symbol: str, years: int = 5) -> dict:
        """Return historical dividend data for dividend-reinvestment backtest.

        Returns dict with:
            dates  : list of ISO date strings (YYYY-MM-DD)
            amounts: list of dividend amounts (per share) matching dates
        """

        def _fetch():
            try:
                import yfinance as yf

                ticker = yf.Ticker(symbol)
                divs = ticker.dividends  # pandas Series, DatetimeIndex → float
                if divs is None or divs.empty:
                    return {"dates": [], "amounts": []}
                # Filter to requested window
                import pandas as pd

                cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(
                    days=int(years * 365)
                )
                divs = divs[divs.index >= cutoff]
                # Normalize index to tz-naive date strings
                dates = [
                    d.strftime("%Y-%m-%d")
                    for d in divs.index.tz_localize(None)
                    if hasattr(d, "strftime")
                ]
                amounts = [round(float(a), 6) for a in divs.values]
                return {"dates": dates, "amounts": amounts}
            except Exception as exc:
                log.warning("Dividend data unavailable for %s: %s", symbol, exc)
                return {"dates": [], "amounts": []}

        return self._cached(f"dividends:{symbol}:{years}", _fetch, ttl=3600 * 24)

    # ------------------------------------------------------------------
    # P14.1: Concurrent / Parallel Data Fetching
    # ------------------------------------------------------------------

    def fetch_all_parallel(self, symbol: str) -> dict:
        """Fetch all analysis data for a symbol in parallel using ThreadPoolExecutor.

        Runs quote, profile, financials, candles, news, insider, recommendations,
        and earnings concurrently to reduce total latency.
        Workers are capped at 4 to avoid bursting the Finnhub 60 req/min limit.
        Each call goes through the centralized rate limiter.

        Returns
        -------
        dict mapping data type → result (or Exception on failure)
        with 'latency_breakdown' dict showing per-source timing.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import time as _time

        tasks = {
            "quote": lambda: self.get_quote(symbol),
            "profile": lambda: self.get_profile(symbol),
            "financials": lambda: self.get_financials(symbol),
            "daily": lambda: self.get_daily(symbol, years=2),
            "news": lambda: self.get_news(symbol, days=7),
            "insider": lambda: self.get_insider_transactions(symbol),
            "recommendations": lambda: self.get_recommendations(symbol),
            "earnings": lambda: self.get_earnings(symbol, limit=8),
        }

        results = {}
        latency = {}
        t_total_start = _time.monotonic()

        with ThreadPoolExecutor(max_workers=4) as executor:
            future_to_name = {
                executor.submit(_timed_call, fn): name for name, fn in tasks.items()
            }
            for future in as_completed(future_to_name):
                name = future_to_name[future]
                try:
                    result, elapsed = future.result()
                    results[name] = result
                    latency[name] = round(elapsed, 3)
                except Exception as exc:
                    results[name] = exc
                    latency[name] = -1
                    log.warning("Parallel fetch '%s' failed: %s", name, exc)

        total_elapsed = _time.monotonic() - t_total_start
        latency["_total"] = round(total_elapsed, 3)
        results["latency_breakdown"] = latency

        log.info(
            "fetch_all_parallel(%s): %d sources in %.2fs",
            symbol,
            len(tasks),
            total_elapsed,
        )
        return results

    def get_alt_data_signals(self, symbol: str, company_name: str) -> dict:
        """Return combined Google Trends + job posting velocity signal.

        Results are cached for 6 hours.  Returns ``{"available": False}``
        when either the optional libraries or API credentials are absent.
        """
        from src.data.alt_data import compute_alt_data_signals
        from src.core.config import cfg

        trends_w = float(cfg.get("alt_data", "trends_weight", default=0.5))
        jobs_w = float(cfg.get("alt_data", "jobs_weight", default=0.5))

        def _fetch():
            return compute_alt_data_signals(
                symbol=symbol,
                company_name=company_name,
                trends_weight=trends_w,
                jobs_weight=jobs_w,
            )

        return self._cached(
            f"alt_data:{symbol}",
            _fetch,
            ttl=int(cfg.get("alt_data", "cache_ttl_hours", default=6)) * 3600,
        )


def _timed_call(fn):
    """Call fn() and return (result, elapsed_seconds)."""
    import time as _time

    t0 = _time.monotonic()
    result = fn()
    return result, _time.monotonic() - t0


# ---------------------------------------------------------------------------
# Mock mode: synthetic data for local testing without API keys
# ---------------------------------------------------------------------------


class MockFinnhubAPI:
    """Drop-in replacement for FinnhubAPI that returns realistic mock data.

    Activate by setting the MOCK_DATA=1 environment variable.
    """

    def __init__(self):
        from src.data.mock_data import get_mock_profile  # noqa: F401

        log.info("MockFinnhubAPI initialised — using synthetic data")

    def get_quote(self, symbol: str) -> dict:
        from src.data.mock_data import get_mock_quote

        return get_mock_quote(symbol)

    def get_profile(self, symbol: str) -> dict:
        from src.data.mock_data import get_mock_profile

        return get_mock_profile(symbol)

    def get_financials(self, symbol: str) -> dict:
        from src.data.mock_data import get_mock_financials

        return get_mock_financials(symbol)

    def get_daily(self, symbol: str, years: int = 2) -> dict:
        from src.data.mock_data import get_mock_daily

        return get_mock_daily(symbol, years)

    def get_weekly(self, symbol: str, years: int = 3) -> dict:
        from src.data.mock_data import get_mock_weekly

        return get_mock_weekly(symbol, years)

    def get_monthly(self, symbol: str, years: int = 5) -> dict:
        from src.data.mock_data import get_mock_monthly

        return get_mock_monthly(symbol, years)

    def get_news(self, symbol: str, days: int = 7) -> list:
        from src.data.mock_data import get_mock_news

        return get_mock_news(symbol, days)

    def get_recommendations(self, symbol: str) -> list:
        from src.data.mock_data import get_mock_recommendations

        return get_mock_recommendations(symbol)

    def get_earnings(self, symbol: str, limit: int = 4) -> list:
        from src.data.mock_data import get_mock_earnings

        return get_mock_earnings(symbol, limit)

    def get_peers(self, symbol: str) -> list:
        from src.data.mock_data import get_mock_peers

        return get_mock_peers(symbol)

    def get_option_chain(self, symbol: str) -> dict:
        from src.data.mock_data import get_mock_option_chain

        return get_mock_option_chain(symbol)

    def get_option_metrics(self, symbol: str) -> dict:
        chain = self.get_option_chain(symbol)
        if not chain or not chain.get("data"):
            return {"available": False}
        nearest = chain["data"][0]
        options_list = nearest.get("options", {})
        calls = options_list.get("CALL", [])
        puts = options_list.get("PUT", [])
        total_call_vol = sum(c.get("volume", 0) or 0 for c in calls)
        total_put_vol = sum(p.get("volume", 0) or 0 for p in puts)
        pc_ratio = (total_put_vol / total_call_vol) if total_call_vol > 0 else None
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

    def get_transcripts_list(self, symbol: str) -> list:
        from src.data.mock_data import get_mock_transcripts_list

        return get_mock_transcripts_list(symbol)

    def get_transcript(self, transcript_id: str) -> dict:
        from src.data.mock_data import get_mock_transcript

        return get_mock_transcript(transcript_id)

    def get_earnings_calendar(
        self,
        symbol: str,
        option_chain: dict | None = None,
        quote: dict | None = None,
    ) -> dict:
        from src.data.mock_data import get_mock_earnings_calendar

        return get_mock_earnings_calendar(symbol)

    def get_insider_transactions(self, symbol: str) -> list:
        from src.data.mock_data import get_mock_insider_transactions

        return get_mock_insider_transactions(symbol)

    def get_short_interest(self, symbol: str) -> dict:
        from src.data.mock_data import get_mock_short_interest

        return get_mock_short_interest(symbol)

    def get_macro_context(self) -> dict:
        from src.data.mock_data import get_mock_macro_context

        return get_mock_macro_context()

    def get_risk_free_rate(self) -> float:
        return self.get_macro_context().get("risk_free_rate", 0.05)

    def get_estimate_revisions(self, symbol: str) -> dict:
        from src.data.mock_data import get_mock_estimate_revisions

        return get_mock_estimate_revisions(symbol)

    def get_analyst_price_targets(self, symbol: str) -> dict:
        from src.data.mock_data import get_mock_analyst_price_targets

        return get_mock_analyst_price_targets(symbol)

    def get_earnings_history(self, symbol: str) -> list:
        from src.data.mock_data import get_mock_earnings_history

        return get_mock_earnings_history(symbol)

    def get_dividends(self, symbol: str, years: int = 5) -> dict:
        from src.data.mock_data import get_mock_dividends

        return get_mock_dividends(symbol)

    def get_alt_data_signals(self, symbol: str, company_name: str) -> dict:
        """Return synthetic alternative data signal for testing."""
        return {
            "available": True,
            "score": 62,
            "label": "Positive alt signal",
            "detail": "Trends: Accelerating interest (68/100) | Jobs: Hiring growth (56/100)",
            "trends": {
                "available": True,
                "values": [45, 48, 52, 55, 60, 63, 68],
                "slope": 0.035,
                "score": 68,
                "label": "Accelerating interest",
                "detail": "Google Trends: accelerating | Recent interest: 68/100 | 90-day slope: +0.035",
            },
            "jobs": {
                "available": True,
                "recent_count": 120,
                "prior_count": 100,
                "velocity_pct": 20.0,
                "score": 56,
                "label": "Hiring growth",
                "detail": "Job postings: 120 (last 30d) vs 100 (prior 30d) | Velocity: +20.0%",
            },
        }

    def fetch_all_parallel(self, symbol: str) -> dict:
        """Mock parallel fetch — just calls each method sequentially."""
        import time as _time

        t0 = _time.monotonic()
        results = {
            "quote": self.get_quote(symbol),
            "profile": self.get_profile(symbol),
            "financials": self.get_financials(symbol),
            "daily": self.get_daily(symbol, years=2),
            "news": self.get_news(symbol, days=7),
            "insider": self.get_insider_transactions(symbol),
            "recommendations": self.get_recommendations(symbol),
            "earnings": self.get_earnings(symbol, limit=8),
        }
        elapsed = _time.monotonic() - t0
        results["latency_breakdown"] = {"_total": round(elapsed, 3)}
        return results


def get_api() -> FinnhubAPI | MockFinnhubAPI:
    """Factory: return MockFinnhubAPI when MOCK_DATA is set, else FinnhubAPI."""
    if MOCK_MODE:
        return MockFinnhubAPI()
    return FinnhubAPI()
