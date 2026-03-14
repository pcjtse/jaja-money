"""Post-Earnings Announcement Drift (PEAD) Strategy (21.2).

Tracks price drift in the days/weeks following large earnings surprises.
A significant beat (>+5% EPS surprise) historically precedes positive drift;
a significant miss (<-5%) historically precedes negative drift.

Usage:
    from pead import compute_pead_drift, screen_pead_candidates, PEADResult
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import pandas as pd

from log_setup import get_logger

log = get_logger(__name__)

# Default surprise thresholds
POSITIVE_SURPRISE_THRESHOLD = 5.0  # % EPS beat → long signal
NEGATIVE_SURPRISE_THRESHOLD = -5.0  # % EPS miss → short signal


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class PEADDrift:
    quarter: str  # e.g. "2024-09-30"
    surprise_pct: float  # EPS surprise %
    direction: str  # "beat" | "miss" | "inline"
    drift_1w_pct: float | None  # price return 1 week post-earnings
    drift_2w_pct: float | None  # price return 2 weeks post-earnings
    drift_1m_pct: float | None  # price return 1 month post-earnings


@dataclass
class PEADResult:
    symbol: str
    latest_surprise_pct: float | None
    signal: str  # "Long (PEAD Beat)" | "Short Signal (PEAD Miss)" | "Neutral"
    avg_beat_drift_1m: float | None  # avg 1-month return after beats
    avg_miss_drift_1m: float | None  # avg 1-month return after misses
    beat_drift_consistency: (
        float | None
    )  # % of beats followed by positive 1-month drift
    drifts: list[PEADDrift] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------


def compute_pead_drift(
    symbol: str,
    earnings: list[dict],
    close_series: pd.Series | None,
    dates_series: pd.Series | None,
    min_surprise_pct: float = POSITIVE_SURPRISE_THRESHOLD,
) -> PEADResult:
    """Compute post-earnings drift for a single stock.

    Parameters
    ----------
    symbol          : ticker symbol (used for labelling only)
    earnings        : list of earnings dicts (most recent first) with keys:
                      period (str), surprisePercent (float)
    close_series    : pd.Series of daily closing prices (oldest first)
    dates_series    : pd.Series of Timestamps / date strings matching close_series
    min_surprise_pct: minimum |surprise %| to flag as beat/miss

    Returns
    -------
    PEADResult with per-quarter drift breakdown and summary stats.
    """
    if (
        not earnings
        or close_series is None
        or dates_series is None
        or len(close_series) < 5
    ):
        return PEADResult(
            symbol=symbol,
            latest_surprise_pct=None,
            signal="Neutral",
            avg_beat_drift_1m=None,
            avg_miss_drift_1m=None,
            beat_drift_consistency=None,
        )

    # Build date-indexed price series
    dates_idx = pd.to_datetime(dates_series)
    price_df = pd.Series(close_series.values, index=dates_idx).sort_index()

    drifts: list[PEADDrift] = []
    for q in earnings:
        surprise = q.get("surprisePercent")
        if surprise is None:
            continue
        surprise = float(surprise)
        period = str(q.get("period", "") or "")

        direction = (
            "beat"
            if surprise >= min_surprise_pct
            else "miss"
            if surprise <= -min_surprise_pct
            else "inline"
        )

        # Locate earnings date in price series
        earn_date = None
        if period:
            try:
                earn_date = pd.Timestamp(period)
            except Exception:
                pass

        drift_1w = drift_2w = drift_1m = None
        if earn_date is not None:
            future = price_df[price_df.index >= earn_date]
            if len(future) >= 1:
                base = float(future.iloc[0])
                if base > 0:
                    if len(future) >= 5:
                        drift_1w = round((float(future.iloc[4]) / base - 1) * 100, 2)
                    if len(future) >= 10:
                        drift_2w = round((float(future.iloc[9]) / base - 1) * 100, 2)
                    if len(future) >= 21:
                        drift_1m = round((float(future.iloc[20]) / base - 1) * 100, 2)

        drifts.append(
            PEADDrift(
                quarter=period or "Unknown",
                surprise_pct=round(surprise, 2),
                direction=direction,
                drift_1w_pct=drift_1w,
                drift_2w_pct=drift_2w,
                drift_1m_pct=drift_1m,
            )
        )

    # Determine signal from latest earnings
    latest_surprise = None
    signal = "Neutral"
    if earnings:
        sp = earnings[0].get("surprisePercent")
        if sp is not None:
            latest_surprise = round(float(sp), 2)
            if latest_surprise >= min_surprise_pct:
                signal = "Long (PEAD Beat)"
            elif latest_surprise <= -min_surprise_pct:
                signal = "Short Signal (PEAD Miss)"

    # Aggregate drift stats
    beat_1m = [
        d.drift_1m_pct
        for d in drifts
        if d.direction == "beat" and d.drift_1m_pct is not None
    ]
    miss_1m = [
        d.drift_1m_pct
        for d in drifts
        if d.direction == "miss" and d.drift_1m_pct is not None
    ]

    avg_beat_1m = round(sum(beat_1m) / len(beat_1m), 2) if beat_1m else None
    avg_miss_1m = round(sum(miss_1m) / len(miss_1m), 2) if miss_1m else None
    beat_consistency = (
        round(sum(1 for d in beat_1m if d > 0) / len(beat_1m) * 100, 1)
        if beat_1m
        else None
    )

    log.debug(
        "PEAD %s: signal=%s, latest_surprise=%.1f%%, beat_consistency=%s",
        symbol,
        signal,
        latest_surprise or 0,
        f"{beat_consistency:.0f}%" if beat_consistency is not None else "N/A",
    )

    return PEADResult(
        symbol=symbol,
        latest_surprise_pct=latest_surprise,
        signal=signal,
        avg_beat_drift_1m=avg_beat_1m,
        avg_miss_drift_1m=avg_miss_1m,
        beat_drift_consistency=beat_consistency,
        drifts=drifts,
    )


# ---------------------------------------------------------------------------
# Screener
# ---------------------------------------------------------------------------


def screen_pead_candidates(
    tickers: list[str],
    api,
    min_surprise_pct: float = POSITIVE_SURPRISE_THRESHOLD,
    max_workers: int = 4,
    delay_between: float = 0.2,
) -> list[dict]:
    """Screen a ticker universe for PEAD candidates.

    Filters to tickers whose most recent earnings report showed a
    surprise >= min_surprise_pct (beats) or <= -min_surprise_pct (misses).

    Returns list of dicts sorted by surprise_pct descending (biggest beats first).
    Each dict has: symbol, surprise_pct, signal, avg_beat_drift_1m, beat_consistency.
    """
    from concurrent.futures import ThreadPoolExecutor

    def _analyze(symbol: str) -> dict | None:
        time.sleep(delay_between)
        try:
            earnings = api.get_earnings(symbol, limit=8)
            if not earnings:
                return None
            latest = earnings[0]
            sp = latest.get("surprisePercent")
            if sp is None or abs(float(sp)) < min_surprise_pct:
                return None

            try:
                daily = api.get_daily(symbol, years=2)
                close = pd.Series(daily["c"])
                dates = pd.Series(pd.to_datetime(daily["t"], unit="s"))
            except Exception:
                close = None
                dates = None

            result = compute_pead_drift(
                symbol, earnings, close, dates, min_surprise_pct
            )
            return {
                "symbol": symbol,
                "surprise_pct": round(float(sp), 2),
                "signal": result.signal,
                "avg_beat_drift_1m": result.avg_beat_drift_1m,
                "beat_consistency": result.beat_drift_consistency,
            }
        except Exception as exc:
            log.debug("PEAD screen skipped %s: %s", symbol, exc)
            return None

    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_analyze, t): t for t in tickers}
        for fut in futures:
            r = fut.result()
            if r:
                results.append(r)

    results.sort(key=lambda x: x.get("surprise_pct", 0), reverse=True)
    log.info("PEAD screen: %d candidates from %d tickers", len(results), len(tickers))
    return results
