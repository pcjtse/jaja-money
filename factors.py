"""Factor Score Engine.

Eight quantitative factors computed from already-fetched data, combined into a
single 0-100 composite score that maps to a Buy / Sell / Neutral signal.

Enhanced with:
- Bollinger Bands %B factor (P1.4)
- OBV (On-Balance Volume) trend signal (P1.4)
- Volume analysis helpers (P1.4)
- Configurable weights via config.py (P4.5)
- Structured logging (P4.3)

All functions are pure Python / pandas — no Streamlit imports.
"""

from __future__ import annotations

import math
import pandas as pd

from config import cfg
from log_setup import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> int:
    return int(max(lo, min(hi, value)))


def _macd_histograms(close: pd.Series, fast=12, slow=26, signal=9):
    """Return (hist_now, hist_prev) or (None, None) if insufficient data."""
    if close is None or len(close) < slow + signal + 1:
        return None, None
    ema_f = close.ewm(span=fast, adjust=False).mean()
    ema_s = close.ewm(span=slow, adjust=False).mean()
    macd = ema_f - ema_s
    sig = macd.ewm(span=signal, adjust=False).mean()
    hist = macd - sig
    return float(hist.iloc[-1]), float(hist.iloc[-2])


def _sma(close: pd.Series, length: int):
    if close is None or len(close) < length:
        return None
    return float(close.rolling(window=length).mean().iloc[-1])


def _rsi(close: pd.Series, length: int = 14):
    if close is None or len(close) < length + 1:
        return None
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / length, min_periods=length).mean()
    avg_loss = loss.ewm(alpha=1 / length, min_periods=length).mean()
    rs = avg_gain / avg_loss
    val = float((100 - (100 / (1 + rs))).iloc[-1])
    return val if not math.isnan(val) else None


# ---------------------------------------------------------------------------
# P1.4: New technical indicator helpers
# ---------------------------------------------------------------------------

def calc_bollinger_bands(
    close: pd.Series,
    window: int = 20,
    num_std: float = 2.0,
) -> dict | None:
    """Compute Bollinger Bands.

    Returns dict with upper, middle, lower, pct_b (0-1 where 1=upper band),
    and bandwidth (%).  Returns None if insufficient data.
    """
    if close is None or len(close) < window:
        return None
    sma = close.rolling(window=window).mean()
    std = close.rolling(window=window).std()
    upper = sma + num_std * std
    lower = sma - num_std * std
    last_close = float(close.iloc[-1])
    last_upper = float(upper.iloc[-1])
    last_lower = float(lower.iloc[-1])
    last_mid = float(sma.iloc[-1])

    band_range = last_upper - last_lower
    pct_b = ((last_close - last_lower) / band_range) if band_range > 0 else 0.5
    bandwidth = (band_range / last_mid * 100) if last_mid > 0 else 0.0

    return {
        "upper": round(last_upper, 2),
        "middle": round(last_mid, 2),
        "lower": round(last_lower, 2),
        "pct_b": round(pct_b, 3),
        "bandwidth": round(bandwidth, 2),
        "upper_series": upper,
        "lower_series": lower,
        "middle_series": sma,
    }


def calc_obv(close: pd.Series, volume: pd.Series | None) -> pd.Series | None:
    """Compute On-Balance Volume series.

    OBV = cumulative sum of +volume on up days, -volume on down days.
    Returns None if volume data is unavailable.
    """
    if close is None or volume is None or len(close) < 2:
        return None
    if len(close) != len(volume):
        return None

    direction = close.diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    obv = (direction * volume).cumsum()
    return obv


def calc_fibonacci_levels(df: pd.DataFrame, lookback: int = 100) -> dict | None:
    """Compute Fibonacci retracement levels from the recent price swing.

    Uses the high and low over the last `lookback` bars to compute standard
    retracement levels: 0%, 23.6%, 38.2%, 50%, 61.8%, 78.6%, 100%.

    Returns dict with:
        swing_high: float
        swing_low:  float
        levels:     dict mapping label → price
        trend:      "up" | "down" (based on close vs midpoint)
    Returns None if data is insufficient.
    """
    if df is None or len(df) < 2:
        return None
    required = {"High", "Low", "Close"}
    if not required.issubset(df.columns):
        return None

    window = df.tail(lookback)
    high = float(window["High"].max())
    low = float(window["Low"].min())
    if high <= low:
        return None

    diff = high - low
    levels = {
        "100.0%": round(high, 2),
        "78.6%":  round(high - 0.236 * diff, 2),
        "61.8%":  round(high - 0.382 * diff, 2),
        "50.0%":  round(high - 0.500 * diff, 2),
        "38.2%":  round(high - 0.618 * diff, 2),
        "23.6%":  round(high - 0.764 * diff, 2),
        "0.0%":   round(low, 2),
    }
    last_close = float(window["Close"].iloc[-1])
    trend = "up" if last_close >= (high + low) / 2 else "down"

    return {
        "swing_high": round(high, 2),
        "swing_low":  round(low, 2),
        "levels": levels,
        "trend": trend,
    }


def calc_vwap(df: pd.DataFrame) -> float | None:
    """Compute rolling VWAP (last 20 trading days) from OHLCV DataFrame.

    Expects columns: High, Low, Close, Volume.
    """
    if df is None or len(df) < 1:
        return None
    required = {"High", "Low", "Close", "Volume"}
    if not required.issubset(df.columns):
        return None
    window = df.tail(20).copy()
    typical = (window["High"] + window["Low"] + window["Close"]) / 3
    vp = (typical * window["Volume"]).sum()
    vol = window["Volume"].sum()
    if vol == 0:
        return None
    return round(vp / vol, 2)


# ---------------------------------------------------------------------------
# Individual factor scorers
# ---------------------------------------------------------------------------

def _get_weight(name: str, default: float) -> float:
    weights = cfg.factor_weights
    return float(weights.get(name, default))


def _factor_valuation(financials: dict | None) -> dict:
    """P/E–based valuation. Lower P/E → higher score (value lens)."""
    weight = _get_weight("valuation", 0.15)
    pe = (financials or {}).get("peBasicExclExtraTTM")

    if pe is None:
        return dict(name="Valuation (P/E)", score=50, weight=weight,
                    label="No data", detail="P/E ratio unavailable")
    pe = float(pe)
    if pe <= 0:
        return dict(name="Valuation (P/E)", score=25, weight=weight,
                    label="Negative earnings", detail=f"P/E={pe:.1f} — company is not yet profitable")
    if pe < 15:
        s, lbl = 88, "Attractively valued"
    elif pe < 20:
        s, lbl = 75, "Fairly valued"
    elif pe < 25:
        s, lbl = 63, "Moderately valued"
    elif pe < 35:
        s, lbl = 48, "Moderately rich"
    elif pe < 50:
        s, lbl = 32, "Expensive"
    else:
        s, lbl = 16, "Very expensive"
    return dict(name="Valuation (P/E)", score=s, weight=weight,
                label=lbl, detail=f"Trailing P/E: {pe:.1f}×")


def _factor_trend(close: pd.Series | None, price: float | None) -> dict:
    """Price position relative to SMA-50 and SMA-200."""
    weight = _get_weight("trend", 0.20)
    if close is None or price is None:
        return dict(name="Trend (SMA)", score=50, weight=weight,
                    label="No data", detail="Price data unavailable")

    sma50  = _sma(close, 50)
    sma200 = _sma(close, 200)

    if sma50 is None:
        return dict(name="Trend (SMA)", score=50, weight=weight,
                    label="Insufficient data", detail="Fewer than 50 trading days available")

    if sma200 is None:
        if price > sma50:
            s, lbl, detail = 65, "Above SMA-50", f"Price ${price:.2f} > SMA-50 ${sma50:.2f}"
        else:
            s, lbl, detail = 38, "Below SMA-50", f"Price ${price:.2f} < SMA-50 ${sma50:.2f}"
    elif price > sma50 and sma50 > sma200:
        s, lbl = 90, "Strong uptrend"
        detail = f"Price > SMA-50 > SMA-200 (${sma50:.2f} > ${sma200:.2f})"
    elif price > sma200 and sma50 < sma200:
        s, lbl = 60, "Recovering"
        detail = f"Price above SMA-200 but SMA-50 (${sma50:.2f}) still below SMA-200 (${sma200:.2f})"
    elif price > sma50 and sma50 < sma200:
        s, lbl = 52, "Tentative recovery"
        detail = "Price reclaimed SMA-50 but long-term trend still bearish"
    elif price < sma50 and sma50 > sma200:
        s, lbl = 45, "Pullback in uptrend"
        detail = f"Structural uptrend intact but price below SMA-50 (${sma50:.2f})"
    else:
        s, lbl = 14, "Strong downtrend"
        detail = f"Price < SMA-50 (${sma50:.2f}) < SMA-200 (${sma200:.2f})"

    return dict(name="Trend (SMA)", score=s, weight=weight, label=lbl, detail=detail)


def _factor_rsi(close: pd.Series | None) -> dict:
    """RSI-14 momentum / mean-reversion factor."""
    weight = _get_weight("rsi", 0.10)
    if close is None:
        return dict(name="Momentum (RSI)", score=50, weight=weight,
                    label="No data", detail="Price data unavailable")

    rsi = _rsi(close)
    if rsi is None:
        return dict(name="Momentum (RSI)", score=50, weight=weight,
                    label="Insufficient data", detail="Fewer than 15 trading days")

    if rsi < 20:
        s, lbl = 15, "Extreme oversold"
    elif rsi < 30:
        s, lbl = 32, "Oversold"
    elif rsi < 40:
        s, lbl = 52, "Weakening"
    elif rsi < 55:
        s, lbl = 75, "Healthy zone"
    elif rsi < 65:
        s, lbl = 85, "Strong momentum"
    elif rsi < 75:
        s, lbl = 65, "Elevated — watch"
    elif rsi < 85:
        s, lbl = 42, "Overbought"
    else:
        s, lbl = 20, "Extreme overbought"

    return dict(name="Momentum (RSI)", score=s, weight=weight,
                label=lbl, detail=f"RSI-14: {rsi:.1f}")


def _factor_macd(close: pd.Series | None) -> dict:
    """MACD histogram direction (current vs previous bar)."""
    weight = _get_weight("macd", 0.10)
    if close is None:
        return dict(name="MACD Signal", score=50, weight=weight,
                    label="No data", detail="Price data unavailable")

    hist, hist_prev = _macd_histograms(close)
    if hist is None:
        return dict(name="MACD Signal", score=50, weight=weight,
                    label="Insufficient data", detail="Fewer than 36 trading days")

    if hist > 0 and hist > hist_prev:
        s, lbl = 88, "Bullish & accelerating"
    elif hist > 0 and hist <= hist_prev:
        s, lbl = 62, "Bullish but decelerating"
    elif hist <= 0 and hist > hist_prev:
        s, lbl = 42, "Bearish but recovering"
    else:
        s, lbl = 15, "Bearish & deteriorating"

    direction = "↑" if hist > hist_prev else "↓"
    return dict(name="MACD Signal", score=s, weight=weight,
                label=lbl, detail=f"Histogram: {hist:+.4f} {direction}")


def _factor_sentiment(sentiment_agg: dict | None) -> dict:
    """FinBERT aggregate news sentiment net score."""
    weight = _get_weight("sentiment", 0.15)
    if not sentiment_agg:
        return dict(name="News Sentiment", score=50, weight=weight,
                    label="No data", detail="Sentiment data unavailable")

    net = float(sentiment_agg.get("net_score", 0.0))
    score = _clamp((net + 1) / 2 * 100)
    signal = sentiment_agg.get("signal", "Mixed / Neutral")
    counts = sentiment_agg.get("counts", {})
    detail = (
        f"{signal}  |  "
        f"🟢 {counts.get('positive', 0)} · "
        f"🔴 {counts.get('negative', 0)} · "
        f"⚪ {counts.get('neutral', 0)}"
    )
    return dict(name="News Sentiment", score=score, weight=weight,
                label=signal, detail=detail)


def _factor_earnings(earnings: list) -> dict:
    """Average EPS surprise % over the last 4 quarters."""
    weight = _get_weight("earnings", 0.15)
    surprises = [
        float(e["surprisePercent"])
        for e in (earnings or [])
        if e.get("surprisePercent") is not None
    ]
    if not surprises:
        return dict(name="Earnings Quality", score=50, weight=weight,
                    label="No data", detail="No EPS surprise data")

    avg = sum(surprises) / len(surprises)
    beat_count = sum(1 for s in surprises if s > 0)

    if avg > 10:
        s, lbl = 90, "Consistently beating"
    elif avg > 5:
        s, lbl = 78, "Solid beats"
    elif avg > 2:
        s, lbl = 65, "Moderate beats"
    elif avg >= 0:
        s, lbl = 54, "Roughly in-line"
    elif avg > -5:
        s, lbl = 36, "Missing estimates"
    else:
        s, lbl = 18, "Significantly missing"

    detail = (
        f"Avg surprise: {avg:+.1f}%  |  "
        f"Beat {beat_count}/{len(surprises)} quarters"
    )
    return dict(name="Earnings Quality", score=s, weight=weight,
                label=lbl, detail=detail)


def _factor_analyst(recommendations: list) -> dict:
    """Buy/Hold/Sell consensus from the most recent recommendation period."""
    weight = _get_weight("analyst", 0.10)
    if not recommendations:
        return dict(name="Analyst Consensus", score=50, weight=weight,
                    label="No data", detail="No analyst recommendations")

    latest = recommendations[0]
    strong_buy  = int(latest.get("strongBuy", 0))
    buy         = int(latest.get("buy", 0))
    hold        = int(latest.get("hold", 0))
    sell        = int(latest.get("sell", 0))
    strong_sell = int(latest.get("strongSell", 0))
    total = strong_buy + buy + hold + sell + strong_sell

    if total == 0:
        return dict(name="Analyst Consensus", score=50, weight=weight,
                    label="No coverage", detail="No analyst ratings available")

    bullish = strong_buy + buy
    ratio = bullish / total

    if ratio >= 0.75:
        s, lbl = 90, "Overwhelmingly bullish"
    elif ratio >= 0.60:
        s, lbl = 74, "Bullish"
    elif ratio >= 0.45:
        s, lbl = 56, "Mildly bullish"
    elif ratio >= 0.30:
        s, lbl = 40, "Mixed / cautious"
    else:
        s, lbl = 20, "Bearish"

    detail = (
        f"SB:{strong_buy} B:{buy} H:{hold} S:{sell} SS:{strong_sell}  |  "
        f"Bull ratio: {ratio:.0%}  |  Period: {latest.get('period', '?')}"
    )
    return dict(name="Analyst Consensus", score=s, weight=weight,
                label=lbl, detail=detail)


def _factor_range_position(financials: dict | None, price: float | None) -> dict:
    """Price position within the 52-week range (momentum / price-strength)."""
    weight = _get_weight("range", 0.05)
    metrics = financials or {}
    high52 = metrics.get("52WeekHigh")
    low52  = metrics.get("52WeekLow")

    if high52 is None or low52 is None or price is None:
        return dict(name="52-Wk Strength", score=50, weight=weight,
                    label="No data", detail="52-week range unavailable")

    high52, low52, price = float(high52), float(low52), float(price)
    if high52 <= low52:
        return dict(name="52-Wk Strength", score=50, weight=weight,
                    label="Flat range", detail="52-week high equals low")

    pct = (price - low52) / (high52 - low52)
    score = _clamp(pct * 100)

    if pct >= 0.80:
        lbl = "Near 52-wk high"
    elif pct >= 0.60:
        lbl = "Upper half of range"
    elif pct >= 0.40:
        lbl = "Mid range"
    elif pct >= 0.20:
        lbl = "Lower half of range"
    else:
        lbl = "Near 52-wk low"

    detail = (
        f"${price:.2f}  |  Low: ${low52:.2f}  High: ${high52:.2f}  |  "
        f"Percentile: {pct:.0%}"
    )
    return dict(name="52-Wk Strength", score=score, weight=weight,
                label=lbl, detail=detail)


# ---------------------------------------------------------------------------
# P5.1: Sector-median P/E reference table
# ---------------------------------------------------------------------------

# Approximate trailing P/E sector medians (updated periodically)
_SECTOR_PE_MEDIANS: dict[str, float] = {
    "Technology": 28.0,
    "Software": 35.0,
    "Semiconductors": 22.0,
    "Healthcare": 22.0,
    "Biotechnology": 25.0,
    "Pharmaceuticals": 18.0,
    "Financial Services": 13.0,
    "Banks": 11.0,
    "Insurance": 12.0,
    "Consumer Discretionary": 22.0,
    "Retail": 20.0,
    "Consumer Staples": 20.0,
    "Energy": 12.0,
    "Utilities": 18.0,
    "Real Estate": 25.0,
    "REITs": 25.0,
    "Communication Services": 20.0,
    "Media": 18.0,
    "Industrials": 20.0,
    "Materials": 16.0,
    "Transportation": 18.0,
    "default": 20.0,
}


def _get_sector_pe_median(sector: str | None) -> float:
    """Look up sector median P/E, with fuzzy matching."""
    if not sector:
        return _SECTOR_PE_MEDIANS["default"]
    sector_l = sector.lower()
    for key, val in _SECTOR_PE_MEDIANS.items():
        if key.lower() in sector_l or sector_l in key.lower():
            return val
    return _SECTOR_PE_MEDIANS["default"]


def _factor_valuation_sector_adjusted(financials: dict | None, sector: str | None) -> dict:
    """Sector-relative P/E valuation.  Compares stock P/E to sector median."""
    weight = _get_weight("valuation", 0.15)
    pe = (financials or {}).get("peBasicExclExtraTTM")

    if pe is None:
        return dict(name="Valuation (P/E)", score=50, weight=weight,
                    label="No data", detail="P/E ratio unavailable")
    pe = float(pe)
    if pe <= 0:
        return dict(name="Valuation (P/E)", score=25, weight=weight,
                    label="Negative earnings", detail=f"P/E={pe:.1f} — company is not yet profitable")

    sector_median = _get_sector_pe_median(sector)
    relative = pe / sector_median  # 1.0 = at sector median

    if relative < 0.6:
        s, lbl = 92, "Deep value vs. sector"
    elif relative < 0.8:
        s, lbl = 80, "Discounted vs. sector"
    elif relative < 1.0:
        s, lbl = 68, "Slight discount vs. sector"
    elif relative < 1.2:
        s, lbl = 55, "Near sector median"
    elif relative < 1.5:
        s, lbl = 40, "Premium vs. sector"
    elif relative < 2.0:
        s, lbl = 26, "Significant premium vs. sector"
    else:
        s, lbl = 12, "Extreme premium vs. sector"

    return dict(
        name="Valuation (P/E)",
        score=s,
        weight=weight,
        label=lbl,
        detail=f"P/E: {pe:.1f}× | Sector median: {sector_median:.1f}× | Relative: {relative:.2f}×",
    )


# ---------------------------------------------------------------------------
# P5.7: Dividend Yield Factor
# ---------------------------------------------------------------------------

def _factor_dividend_yield(financials: dict | None) -> dict:
    """Dividend yield factor.  Higher sustainable yield = positive signal."""
    weight = _get_weight("dividend", 0.05)
    metrics = financials or {}
    div_yield = metrics.get("dividendYieldIndicatedAnnual")
    payout_ratio = metrics.get("payoutRatioTTM")

    if div_yield is None:
        return dict(name="Dividend Yield", score=50, weight=weight,
                    label="No data", detail="Dividend data unavailable")

    div_yield = float(div_yield)

    if div_yield <= 0:
        s, lbl = 48, "No dividend"
        detail = "No dividend paid"
    elif div_yield < 1.5:
        s, lbl = 55, "Low yield"
        detail = f"Yield: {div_yield:.2f}%"
    elif div_yield < 3.0:
        s, lbl = 70, "Moderate yield"
        detail = f"Yield: {div_yield:.2f}%"
    elif div_yield < 5.0:
        s, lbl = 82, "Attractive yield"
        detail = f"Yield: {div_yield:.2f}%"
    else:
        s, lbl = 75, "High yield (verify sustainability)"
        detail = f"Yield: {div_yield:.2f}% — verify payout ratio"

    # Penalize unsustainable payout ratio
    if payout_ratio is not None:
        pr = float(payout_ratio)
        if pr > 100:
            s = max(20, s - 25)
            lbl = "Unsustainable payout"
            detail += f" | Payout ratio: {pr:.1f}% (>100% = paying more than earnings)"
        elif pr > 80:
            s = max(35, s - 10)
            detail += f" | Payout ratio: {pr:.1f}% (elevated)"
        else:
            detail += f" | Payout ratio: {pr:.1f}%"

    return dict(name="Dividend Yield", score=s, weight=weight, label=lbl, detail=detail)


# ---------------------------------------------------------------------------
# P5.2: Analyst Estimate Revision Momentum
# ---------------------------------------------------------------------------

def _factor_estimate_revisions(revisions: dict | None) -> dict:
    """EPS estimate revision direction as a factor signal."""
    weight = _get_weight("estimate_revision", 0.08)

    if not revisions or not revisions.get("available"):
        return dict(name="Estimate Revisions", score=50, weight=weight,
                    label="No data", detail="Estimate revision data unavailable")

    direction = revisions.get("revision_direction", "flat")
    analyst_count = revisions.get("analyst_count")
    fwd_eps = revisions.get("forward_eps")
    revisions.get("trailing_eps")

    if direction == "up":
        s, lbl = 78, "Upward revisions"
    elif direction == "down":
        s, lbl = 28, "Downward revisions"
    else:
        s, lbl = 52, "Stable estimates"

    detail_parts = [f"Direction: {direction}"]
    if analyst_count:
        detail_parts.append(f"{analyst_count} analysts")
    if fwd_eps is not None:
        detail_parts.append(f"Fwd EPS: ${fwd_eps:.2f}")
    detail = " | ".join(detail_parts)

    return dict(name="Estimate Revisions", score=s, weight=weight, label=lbl, detail=detail)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_factors(
    quote: dict,
    financials: dict | None,
    close: "pd.Series | None",
    earnings: list,
    recommendations: list,
    sentiment_agg: dict | None,
    sector: str | None = None,
    revisions: dict | None = None,
) -> list[dict]:
    """Compute factors and return them as a list of dicts.

    Each dict has keys: name, score (0–100), label, detail, weight.
    Now includes sector-relative valuation (P5.1), dividend yield (P5.7),
    and estimate revision momentum (P5.2).
    """
    _c = quote.get("c")
    price = float(_c) if (_c is not None and float(_c) > 0) else None

    factors = [
        _factor_valuation_sector_adjusted(financials, sector),
        _factor_trend(close, price),
        _factor_rsi(close),
        _factor_macd(close),
        _factor_sentiment(sentiment_agg),
        _factor_earnings(earnings),
        _factor_analyst(recommendations),
        _factor_range_position(financials, price),
        _factor_dividend_yield(financials),
        _factor_estimate_revisions(revisions),
    ]
    log.debug("Computed %d factors for price=%.2f", len(factors), price or 0)
    return factors


# ---------------------------------------------------------------------------
# P15.3: Multi-timeframe factor support
# ---------------------------------------------------------------------------

def compute_factors_timeframe(
    quote: dict,
    financials: dict | None,
    close_daily: "pd.Series | None",
    close_weekly: "pd.Series | None",
    close_monthly: "pd.Series | None",
    earnings: list,
    recommendations: list,
    sentiment_agg: dict | None,
    sector: str | None = None,
    revisions: dict | None = None,
) -> dict:
    """Compute factors across daily, weekly, and monthly timeframes.

    Calls compute_factors() for each timeframe using the appropriate close
    series, then derives a composite score per timeframe and an alignment
    signal across all three.

    Parameters
    ----------
    quote : current quote dict (price data)
    financials : fundamental metrics dict or None
    close_daily : daily close price Series or None
    close_weekly : weekly close price Series or None
    close_monthly : monthly close price Series or None
    earnings : list of earnings surprise dicts
    recommendations : list of analyst recommendation dicts
    sentiment_agg : aggregated sentiment dict or None
    sector : sector name for relative valuation, or None
    revisions : estimate revision dict or None

    Returns
    -------
    dict with keys:
        daily, weekly, monthly  – factor lists from compute_factors()
        daily_composite, weekly_composite, monthly_composite  – int 0-100
        alignment – "Aligned Bull" | "Aligned Bear" | "Mixed"
    """
    daily_factors = compute_factors(
        quote=quote,
        financials=financials,
        close=close_daily,
        earnings=earnings,
        recommendations=recommendations,
        sentiment_agg=sentiment_agg,
        sector=sector,
        revisions=revisions,
    )
    weekly_factors = compute_factors(
        quote=quote,
        financials=financials,
        close=close_weekly,
        earnings=earnings,
        recommendations=recommendations,
        sentiment_agg=sentiment_agg,
        sector=sector,
        revisions=revisions,
    )
    monthly_factors = compute_factors(
        quote=quote,
        financials=financials,
        close=close_monthly,
        earnings=earnings,
        recommendations=recommendations,
        sentiment_agg=sentiment_agg,
        sector=sector,
        revisions=revisions,
    )

    daily_composite = composite_score(daily_factors)
    weekly_composite = composite_score(weekly_factors)
    monthly_composite = composite_score(monthly_factors)

    if all(c >= 55 for c in (daily_composite, weekly_composite, monthly_composite)):
        alignment = "Aligned Bull"
    elif all(c <= 45 for c in (daily_composite, weekly_composite, monthly_composite)):
        alignment = "Aligned Bear"
    else:
        alignment = "Mixed"

    log.debug(
        "Timeframe composites — daily=%d weekly=%d monthly=%d alignment=%s",
        daily_composite, weekly_composite, monthly_composite, alignment,
    )

    return {
        "daily": daily_factors,
        "weekly": weekly_factors,
        "monthly": monthly_factors,
        "daily_composite": daily_composite,
        "weekly_composite": weekly_composite,
        "monthly_composite": monthly_composite,
        "alignment": alignment,
    }


# ---------------------------------------------------------------------------
# P19.4: Earnings 8-quarter beat consistency
# ---------------------------------------------------------------------------

def compute_beat_consistency(earnings_history: list) -> dict:
    """Compute earnings beat consistency over up to 8 quarters.

    Parameters
    ----------
    earnings_history : list of dicts, each with keys:
        actual (float), estimate (float), surprisePercent (float).
        Most recent quarter first (or any order — all are evaluated).

    Returns
    -------
    dict with:
        beat_count          – int, number of quarters where actual > estimate
        total_quarters      – int, number of quarters with valid data
        beat_rate_pct       – float, beat_count / total_quarters * 100
        avg_surprise_pct    – float, average surprisePercent across quarters
        streak              – int, consecutive beats from the most-recent quarter
        consistency_score   – int 0-100
    """
    if not earnings_history:
        return {
            "beat_count": 0,
            "total_quarters": 0,
            "beat_rate_pct": 0.0,
            "avg_surprise_pct": 0.0,
            "streak": 0,
            "consistency_score": 0,
        }

    # Use up to 8 quarters; assume list order is most-recent first
    quarters = earnings_history[:8]
    valid = [
        q for q in quarters
        if q.get("surprisePercent") is not None
    ]
    total = len(valid)

    if total == 0:
        return {
            "beat_count": 0,
            "total_quarters": 0,
            "beat_rate_pct": 0.0,
            "avg_surprise_pct": 0.0,
            "streak": 0,
            "consistency_score": 0,
        }

    surprises = [float(q["surprisePercent"]) for q in valid]
    beat_count = sum(1 for s in surprises if s > 0)
    avg_surprise = sum(surprises) / total

    # Streak: consecutive beats from most recent (index 0)
    streak = 0
    for s in surprises:
        if s > 0:
            streak += 1
        else:
            break

    beat_rate = beat_count / total
    # Consistency score formula
    raw = (beat_rate * 70) + (min(streak, 4) / 4 * 30)
    consistency_score = _clamp(raw)

    log.debug(
        "Beat consistency: %d/%d beats, streak=%d, score=%d",
        beat_count, total, streak, consistency_score,
    )

    return {
        "beat_count": beat_count,
        "total_quarters": total,
        "beat_rate_pct": round(beat_rate * 100, 1),
        "avg_surprise_pct": round(avg_surprise, 2),
        "streak": streak,
        "consistency_score": consistency_score,
    }


# ---------------------------------------------------------------------------
# P20.1: Market regime factor
# ---------------------------------------------------------------------------

def compute_market_regime(
    spy_close: "pd.Series | None",
    vix: "float | None",
    yield_spread: "float | None",
) -> dict:
    """Classify the current macro regime using SPY trend, VIX, and yield spread.

    Parameters
    ----------
    spy_close : pd.Series of SPY daily closes (most recent last), or None
    vix       : current VIX level as a float, or None
    yield_spread : 10Y-2Y Treasury spread in percentage points, or None
                   (positive = normal, negative = inverted)

    Returns
    -------
    dict with:
        regime          – "Strong Bull" | "Bull" | "Neutral" | "Bear" | "Strong Bear"
        score_adjustment – int applied to composite scores (+5, +2, 0, -5, -10)
        detail          – human-readable explanation string
    """
    # Determine SPY vs 200-day SMA
    spy_above_200 = None
    if spy_close is not None and len(spy_close) >= 200:
        sma200 = float(spy_close.rolling(window=200).mean().iloc[-1])
        current = float(spy_close.iloc[-1])
        spy_above_200 = current > sma200

    details = []
    if spy_above_200 is not None:
        details.append(f"SPY {'above' if spy_above_200 else 'below'} 200-day SMA")
    if vix is not None:
        details.append(f"VIX={vix:.1f}")
    if yield_spread is not None:
        details.append(f"yield spread={yield_spread:+.2f}%")

    # Classification logic
    if vix is not None and vix > 30 and spy_above_200 is False:
        regime = "Strong Bear"
        adj = -10
    elif vix is not None and vix > 25:
        regime = "Bear"
        adj = -5
    elif spy_above_200 is True and vix is not None and vix < 18:
        if yield_spread is not None and yield_spread > 0:
            regime = "Strong Bull"
            adj = +5
        else:
            regime = "Bull"
            adj = +2
    elif spy_above_200 is True and vix is None:
        # SPY above 200 SMA but no VIX data
        regime = "Bull"
        adj = +2
    else:
        regime = "Neutral"
        adj = 0

    detail = " | ".join(details) if details else "Insufficient data for regime classification"
    log.debug("Market regime: %s (adj=%+d) — %s", regime, adj, detail)

    return {
        "regime": regime,
        "score_adjustment": adj,
        "detail": detail,
    }


def composite_score(factors: list[dict]) -> int:
    """Weighted average of factor scores, rounded to the nearest integer."""
    total_weight = sum(f["weight"] for f in factors)
    if total_weight == 0:
        return 50
    weighted_sum = sum(f["score"] * f["weight"] for f in factors)
    return _clamp(weighted_sum / total_weight)


COMPOSITE_LABEL = [
    (70, "Strong Buy",   "#1a7f37"),
    (55, "Buy",          "#2da44e"),
    (45, "Neutral",      "#888888"),
    (30, "Sell",         "#e05252"),
    ( 0, "Strong Sell",  "#cf2929"),
]


def composite_label_color(score: int) -> tuple[str, str]:
    """Return (label, hex_color) for a composite score."""
    for threshold, label, color in COMPOSITE_LABEL:
        if score >= threshold:
            return label, color
    return "Strong Sell", "#cf2929"
