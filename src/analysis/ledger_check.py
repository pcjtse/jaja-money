"""Signal Ledger Check — headless orchestrator for GH Actions cron.

Runs daily at market close (21:00 UTC weekdays). For each watchlist ticker:
  1. Fetch full data (quote, financials, candles, news, etc.)
  2. Compute composite score via compute_factors() + composite_score()
  3. Close open positions that are expired (hold_days) or below exit_score
  4. Fire new BUY signals for tickers scoring >= buy_threshold

Entry point for GH Actions:
    python -m src.analysis.ledger_check

Configuration read from config.yaml:
    ledger.buy_threshold  (default 75)
    ledger.hold_days      (default 30)
    ledger.exit_score     (default 40)
    ledger.watchlist      (optional; falls back to analysis_history distinct symbols)
"""

from __future__ import annotations

from datetime import date, datetime, timezone, timedelta

import pandas as pd

from src.core.config import cfg
from src.core.log_setup import get_logger

log = get_logger(__name__)

_BUY_THRESHOLD = int(cfg.get("ledger", "buy_threshold", default=75))
_HOLD_DAYS = int(cfg.get("ledger", "hold_days", default=30))
_EXIT_SCORE = int(cfg.get("ledger", "exit_score", default=40))


# ---------------------------------------------------------------------------
# Watchlist resolution
# ---------------------------------------------------------------------------


def _resolve_watchlist() -> list[str]:
    """Return watchlist from config, or distinct symbols from analysis_history."""
    from_config = cfg.get("ledger", "watchlist", default=None)
    if from_config and isinstance(from_config, list):
        return [str(t).upper() for t in from_config if t]

    # Fall back to distinct symbols in analysis_history
    try:
        from src.data.history import _connect

        with _connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT symbol FROM analysis_history ORDER BY symbol"
            ).fetchall()
        symbols = [r[0] for r in rows if r[0]]
        if symbols:
            log.info(
                "Watchlist resolved from analysis_history: %d symbols", len(symbols)
            )
            return symbols
    except Exception as exc:
        log.warning("Could not load watchlist from history: %s", exc)

    log.warning("No watchlist configured and no analysis_history — nothing to check")
    return []


# ---------------------------------------------------------------------------
# Per-ticker data fetch + scoring
# ---------------------------------------------------------------------------


def _score_ticker(ticker: str) -> tuple[int, dict[str, float], float] | None:
    """Fetch data, compute composite score and factor scores for *ticker*.

    Returns (composite_score, factor_scores_dict, current_price) or None on error.
    factor_scores_dict maps factor display names to 0-100 raw scores.
    """
    from src.data.api import get_api
    from src.data.sentiment import score_articles, aggregate_sentiment
    from src.analysis.factors import compute_factors, composite_score

    try:
        api = get_api()
        data = api.fetch_all_parallel(ticker)

        quote = data.get("quote") or {}
        if isinstance(quote, Exception) or not quote:
            log.warning("No quote for %s — skipping", ticker)
            return None

        price = float(quote.get("c") or 0)
        if price <= 0:
            log.warning("Zero price for %s — skipping", ticker)
            return None

        financials = (
            data.get("financials")
            if not isinstance(data.get("financials"), Exception)
            else None
        )
        daily_data = (
            data.get("daily") if not isinstance(data.get("daily"), Exception) else None
        )
        news = data.get("news") if not isinstance(data.get("news"), Exception) else []
        earnings = (
            data.get("earnings")
            if not isinstance(data.get("earnings"), Exception)
            else []
        )
        recommendations = (
            data.get("recommendations")
            if not isinstance(data.get("recommendations"), Exception)
            else []
        )
        profile = (
            data.get("profile")
            if not isinstance(data.get("profile"), Exception)
            else {}
        )

        # Build close series
        close: pd.Series | None = None
        if daily_data and daily_data.get("s") == "ok":
            closes = daily_data.get("c", [])
            if closes:
                close = pd.Series(closes, dtype=float)

        # Build sentiment
        sentiment_agg = None
        if news:
            try:
                scores = score_articles(news)
                if scores:
                    sentiment_agg = aggregate_sentiment(scores)
            except Exception:
                pass

        sector = profile.get("finnhubIndustry") if profile else None

        factors = compute_factors(
            quote=quote,
            financials=financials,
            close=close,
            earnings=earnings if isinstance(earnings, list) else [],
            recommendations=recommendations
            if isinstance(recommendations, list)
            else [],
            sentiment_agg=sentiment_agg,
            sector=sector,
        )

        score = composite_score(factors)
        factor_scores = {f["name"]: float(f["score"]) for f in factors}
        return score, factor_scores, price

    except Exception as exc:
        log.error("Failed to score %s: %s", ticker, exc)
        return None


# ---------------------------------------------------------------------------
# SPY price fetch
# ---------------------------------------------------------------------------


def _get_spy_price() -> float | None:
    """Return current SPY close price, or None on failure."""
    try:
        from src.data.api import get_api

        api = get_api()
        quote = api.get_quote("SPY")
        price = float(quote.get("c") or 0)
        return price if price > 0 else None
    except Exception as exc:
        log.warning("SPY price fetch failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Position close logic
# ---------------------------------------------------------------------------


def _days_since(iso_datetime: str) -> int:
    """Return calendar days since an ISO 8601 datetime string."""
    try:
        fired = datetime.fromisoformat(iso_datetime.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - fired).days
    except Exception:
        return 0


def _price_from_daily(daily_data: dict, target_date: str) -> float | None:
    """Return closing price on or before target_date from a get_daily() response.

    Finds the nearest prior trading day if target_date falls on a weekend or holiday.
    """
    if not daily_data or daily_data.get("s") != "ok":
        return None
    timestamps = daily_data.get("t", [])
    closes = daily_data.get("c", [])
    if not timestamps or not closes:
        return None
    try:
        import datetime as _dt

        target = _dt.date.fromisoformat(target_date)
        best_close = None
        best_date: _dt.date | None = None
        for ts, c in zip(timestamps, closes):
            dt = _dt.datetime.fromtimestamp(ts, tz=_dt.timezone.utc).date()
            if dt <= target:
                if best_date is None or dt > best_date:
                    best_date = dt
                    best_close = c
        return float(best_close) if best_close is not None else None
    except Exception:
        return None


def _fetch_t_prices(
    ticker: str, fired_date_str: str
) -> tuple[float | None, float | None, float | None, float | None]:
    """Fetch T+5, T+10, T+30 prices for ticker and SPY T+30 using get_daily().

    Returns (price_t5, price_t10, price_t30, spy_price_t30).
    Never raises — returns None values on any API failure.
    """
    try:
        from src.data.api import get_api

        api = get_api()
        fired_dt = date.fromisoformat(fired_date_str)
        t5_str = (fired_dt + timedelta(days=5)).isoformat()
        t10_str = (fired_dt + timedelta(days=10)).isoformat()
        t30_str = (fired_dt + timedelta(days=30)).isoformat()

        daily = api.get_daily(ticker, years=2)
        p5 = _price_from_daily(daily, t5_str)
        p10 = _price_from_daily(daily, t10_str)
        p30 = _price_from_daily(daily, t30_str)

        spy_daily = api.get_daily("SPY", years=2)
        spy_t30 = _price_from_daily(spy_daily, t30_str)

        return p5, p10, p30, spy_t30
    except Exception as exc:
        log.warning("T-price fetch failed for %s: %s", ticker, exc)
        return None, None, None, None


def _close_expired_positions(spy_price: float | None, summary: dict) -> None:
    """Close positions that have passed hold_days or dropped below exit_score."""
    from src.analysis.ledger import get_open_positions, close_position

    open_positions = get_open_positions()
    for pos in open_positions:
        days_held = _days_since(pos["fired_at"])
        ticker = pos["ticker"]
        signal_id = pos["signal_id"]

        # Re-score to check exit_score condition
        result = _score_ticker(ticker)
        current_score = result[0] if result else None
        current_price = result[2] if result else None

        should_close = days_held >= _HOLD_DAYS
        if current_score is not None and current_score < _EXIT_SCORE:
            should_close = True
            log.info(
                "Early exit: %s score=%d < exit_score=%d",
                ticker,
                current_score,
                _EXIT_SCORE,
            )

        if not should_close:
            continue

        # Fetch T+5/T+10/T+30 and SPY T+30 prices via get_daily()
        fired_date = pos["fired_at"][:10]
        price_t5, price_t10, price_t30, spy_price_t30 = _fetch_t_prices(
            ticker, fired_date
        )

        exit_price = current_price or pos.get("price_at_signal", 0)
        exit_spy = spy_price or pos.get("spy_entry_price", 0)

        try:
            close_position(
                signal_id=signal_id,
                exit_price=exit_price,
                spy_exit_price=exit_spy,
                price_t5=price_t5,
                price_t10=price_t10,
                price_t30=price_t30,
                spy_price_t30=spy_price_t30,
            )
            summary["closed"].append(ticker)
        except Exception as exc:
            log.error("Failed to close %s: %s", ticker, exc)


# ---------------------------------------------------------------------------
# Market regime
# ---------------------------------------------------------------------------


def _get_market_regime(spy_price: float | None) -> str:
    """Return 'bull', 'bear', or 'flat' based on SPY 20-day return."""
    try:
        from src.data.api import get_api

        api = get_api()
        data = api.get_daily("SPY", years=1)
        if not data or data.get("s") != "ok":
            return "flat"
        closes = data.get("c", [])
        if len(closes) < 21:
            return "flat"
        recent = float(closes[-1])
        twenty_days_ago = float(closes[-21])
        if twenty_days_ago <= 0:
            return "flat"
        ret = (recent - twenty_days_ago) / twenty_days_ago
        if ret > 0.01:
            return "bull"
        elif ret < -0.01:
            return "bear"
        return "flat"
    except Exception:
        return "flat"


# ---------------------------------------------------------------------------
# Baseline co-fire
# ---------------------------------------------------------------------------


def _fire_baseline_signal(
    real_ticker: str,
    spy_price: float | None,
    score: int,
    factor_scores: dict,
    regime: str = "flat",
) -> None:
    """Co-fire a baseline (SPY-proxy) signal alongside a real signal.

    One baseline per cron run per day — if any source='baseline' entry already
    exists for today, skip entirely regardless of ticker.
    """
    from src.core.config import cfg
    from src.analysis.ledger import add_signal, get_open_positions, get_all_signals

    # One-per-day guard: skip if any baseline signal already fired today
    today = datetime.now(timezone.utc).date().isoformat()
    for s in get_all_signals():
        if s.get("source") == "baseline" and s["fired_at"][:10] == today:
            log.debug("Baseline already fired today — skipping co-fire for %s", real_ticker)
            return

    universe = cfg.get("screener", "default_universe", default=[]) or []
    open_tickers = {p["ticker"] for p in get_open_positions(include_baseline=True)}
    candidates = [t for t in universe if t != real_ticker and t not in open_tickers]
    if not candidates:
        log.debug(
            "No baseline target available for %s (%d open positions) — pool exhausted",
            real_ticker,
            len(open_tickers),
        )
        return
    import random

    baseline_ticker = random.choice(candidates)
    try:
        add_signal(
            ticker=baseline_ticker,
            composite_score=score,
            factor_scores=factor_scores,
            price=spy_price or 0.0,
            spy_price=spy_price or 0.0,
            is_baseline=True,
            regime=regime,
            source="baseline",
        )
    except ValueError:
        pass  # already has open position


# ---------------------------------------------------------------------------
# Signal fire logic
# ---------------------------------------------------------------------------


def _fire_new_signals(
    watchlist: list[str],
    spy_price: float | None,
    summary: dict,
) -> None:
    """Score watchlist and fire BUY signals for qualifying tickers."""
    from src.analysis.ledger import add_signal, get_open_positions

    open_tickers = {p["ticker"] for p in get_open_positions()}

    regime = _get_market_regime(spy_price)

    for ticker in watchlist:
        if ticker in open_tickers:
            log.debug("Skipping %s — already has open position", ticker)
            continue

        result = _score_ticker(ticker)
        if result is None:
            summary["errors"].append(ticker)
            continue

        score, factor_scores, price = result
        summary["scored"].append({"ticker": ticker, "score": score})

        if score < _BUY_THRESHOLD:
            log.debug("%s score=%d below threshold=%d", ticker, score, _BUY_THRESHOLD)
            continue

        if spy_price is None:
            log.warning("SPY price unavailable — recording 0.0 as spy_entry_price")

        try:
            signal_id = add_signal(
                ticker=ticker,
                composite_score=score,
                factor_scores=factor_scores,
                price=price,
                spy_price=spy_price or 0.0,
                regime=regime,
                source="forward",
            )
            log.info(
                "BUY signal fired: %s score=%d id=%s", ticker, score, signal_id[:8]
            )
            summary["signals_fired"].append(ticker)
            _fire_baseline_signal(ticker, spy_price, score, factor_scores, regime)
        except ValueError as exc:
            # Duplicate guard hit — position already exists
            log.info("Signal skipped for %s: %s", ticker, exc)


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


def run_ledger_check(watchlist: list[str] | None = None) -> dict:
    """Score all watchlist tickers, close expired/weak positions, fire new signals.

    Returns a summary dict with keys: scored, signals_fired, closed, errors.
    """
    summary: dict = {
        "scored": [],
        "signals_fired": [],
        "closed": [],
        "errors": [],
        "run_at": datetime.now(timezone.utc).isoformat(),
    }

    if watchlist is None:
        watchlist = _resolve_watchlist()

    if not watchlist:
        log.warning("Empty watchlist — ledger check has nothing to do")
        return summary

    log.info(
        "Ledger check starting: %d tickers (threshold=%d, hold=%dd, exit=%d)",
        len(watchlist),
        _BUY_THRESHOLD,
        _HOLD_DAYS,
        _EXIT_SCORE,
    )

    spy_price = _get_spy_price()

    # Phase 1: close expired / below exit_score positions
    _close_expired_positions(spy_price, summary)

    # Phase 2: fire new signals
    _fire_new_signals(watchlist, spy_price, summary)

    log.info(
        "Ledger check complete: %d scored, %d signals fired, %d closed, %d errors",
        len(summary["scored"]),
        len(summary["signals_fired"]),
        len(summary["closed"]),
        len(summary["errors"]),
    )
    return summary


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    result = run_ledger_check()
    print(
        f"Ledger check complete:\n"
        f"  Scored:        {len(result['scored'])} tickers\n"
        f"  Signals fired: {result['signals_fired']}\n"
        f"  Positions closed: {result['closed']}\n"
        f"  Errors:        {result['errors']}\n"
    )
