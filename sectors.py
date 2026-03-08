"""Sector & Industry Rotation Tracker (P3.3).

Analyzes sector ETFs to identify relative strength, rotation trends,
and leading/lagging sectors.

Usage:
    from sectors import get_sector_data, sector_momentum_score
"""
from __future__ import annotations

import math

import pandas as pd

from config import cfg
from log_setup import get_logger

log = get_logger(__name__)

# Sector ETF definitions (from config, with fallback)
SECTOR_ETFS = cfg.sector_etfs


# ---------------------------------------------------------------------------
# Momentum helpers
# ---------------------------------------------------------------------------

def _perf_pct(close: pd.Series, days: int) -> float | None:
    """Return percentage price change over the last `days` trading days."""
    if close is None or len(close) < days + 1:
        return None
    return float((close.iloc[-1] / close.iloc[-days - 1] - 1) * 100)


def _hist_vol(close: pd.Series, window: int = 20) -> float | None:
    if close is None or len(close) < window + 1:
        return None
    ratio = (close / close.shift(1)).dropna()
    ratio = ratio[ratio > 0]
    if len(ratio) < window:
        return None
    log_r = ratio.apply(math.log)
    return float(log_r.tail(window).std() * math.sqrt(252) * 100)


def _rsi(close: pd.Series, length: int = 14) -> float | None:
    if close is None or len(close) < length + 1:
        return None
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/length, min_periods=length).mean()
    avg_loss = loss.ewm(alpha=1/length, min_periods=length).mean()
    rs = avg_gain / avg_loss
    val = float((100 - 100/(1+rs)).iloc[-1])
    return None if math.isnan(val) else val


def sector_momentum_score(close: pd.Series) -> dict:
    """Compute a composite momentum score for a sector ETF.

    Returns dict with: score (0-100), perf_1m, perf_3m, perf_6m,
    rsi, volatility, above_sma50, above_sma200.
    """
    if close is None or len(close) < 20:
        return {
            "score": 50, "perf_1m": None, "perf_3m": None,
            "perf_6m": None, "rsi": None, "volatility": None,
            "above_sma50": None, "above_sma200": None,
        }

    perf_1m = _perf_pct(close, 21)
    perf_3m = _perf_pct(close, 63)
    perf_6m = _perf_pct(close, 126)
    rsi = _rsi(close)
    vol = _hist_vol(close)

    price = float(close.iloc[-1])

    sma50 = None
    above_sma50 = None
    if len(close) >= 50:
        sma50 = float(close.rolling(50).mean().iloc[-1])
        above_sma50 = price > sma50

    sma200 = None
    above_sma200 = None
    if len(close) >= 200:
        sma200 = float(close.rolling(200).mean().iloc[-1])
        above_sma200 = price > sma200

    # Composite momentum score
    components = []

    # 1M performance: 25% weight
    if perf_1m is not None:
        s1 = min(100, max(0, 50 + perf_1m * 3))
        components.append(("perf_1m", s1, 0.25))

    # 3M performance: 30% weight
    if perf_3m is not None:
        s3 = min(100, max(0, 50 + perf_3m * 1.5))
        components.append(("perf_3m", s3, 0.30))

    # 6M performance: 20% weight
    if perf_6m is not None:
        s6 = min(100, max(0, 50 + perf_6m * 0.8))
        components.append(("perf_6m", s6, 0.20))

    # RSI: 15% weight
    if rsi is not None:
        sr = min(100, max(0, rsi))
        components.append(("rsi", sr, 0.15))

    # SMA trend: 10% weight
    if above_sma50 is not None and above_sma200 is not None:
        st = 80 if (above_sma50 and above_sma200) else \
             55 if above_sma200 else \
             40 if above_sma50 else 20
        components.append(("trend", st, 0.10))

    if components:
        total_w = sum(w for _, _, w in components)
        score = int(sum(s * w for _, s, w in components) / total_w)
    else:
        score = 50

    return {
        "score": score,
        "perf_1m": round(perf_1m, 2) if perf_1m is not None else None,
        "perf_3m": round(perf_3m, 2) if perf_3m is not None else None,
        "perf_6m": round(perf_6m, 2) if perf_6m is not None else None,
        "rsi": round(rsi, 1) if rsi is not None else None,
        "volatility": round(vol, 1) if vol is not None else None,
        "above_sma50": above_sma50,
        "above_sma200": above_sma200,
    }


def get_sector_data(api) -> list[dict]:
    """Fetch and analyze all sector ETFs.

    Returns list of dicts sorted by momentum score desc.
    """
    results = []
    for etf in SECTOR_ETFS:
        ticker = etf["ticker"]
        name = etf["name"]
        try:
            daily = api.get_daily(ticker, years=2)
            import pandas as pd
            close = pd.Series(daily["c"])
            quote = api.get_quote(ticker)
            price = float(quote.get("c") or 0)
            change_pct = float(quote.get("dp") or 0)

            metrics = sector_momentum_score(close)
            results.append({
                "ticker": ticker,
                "name": name,
                "price": price,
                "change_pct": change_pct,
                **metrics,
            })
            log.debug("Sector ETF %s: score=%d", ticker, metrics["score"])
        except Exception as exc:
            log.warning("Failed to fetch sector ETF %s: %s", ticker, exc)
            results.append({
                "ticker": ticker,
                "name": name,
                "price": None,
                "change_pct": None,
                "score": 50,
                "perf_1m": None,
                "perf_3m": None,
                "perf_6m": None,
                "rsi": None,
                "volatility": None,
                "above_sma50": None,
                "above_sma200": None,
            })

    results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return results


def classify_rotation_phase(score: int, perf_1m: float | None, perf_3m: float | None) -> str:
    """Classify a sector into a rotation quadrant."""
    if score >= 70:
        if perf_1m is not None and perf_3m is not None:
            if perf_1m > 0 and perf_3m > 0:
                return "Leading"
            elif perf_1m > 0 and perf_3m <= 0:
                return "Improving"
    if score < 40:
        if perf_1m is not None and perf_3m is not None:
            if perf_1m < 0 and perf_3m < 0:
                return "Lagging"
            elif perf_1m < 0 and perf_3m >= 0:
                return "Weakening"
    return "Neutral"
