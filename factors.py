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
        "78.6%": round(high - 0.236 * diff, 2),
        "61.8%": round(high - 0.382 * diff, 2),
        "50.0%": round(high - 0.500 * diff, 2),
        "38.2%": round(high - 0.618 * diff, 2),
        "23.6%": round(high - 0.764 * diff, 2),
        "0.0%": round(low, 2),
    }
    last_close = float(window["Close"].iloc[-1])
    trend = "up" if last_close >= (high + low) / 2 else "down"

    return {
        "swing_high": round(high, 2),
        "swing_low": round(low, 2),
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
        return dict(
            name="Valuation (P/E)",
            score=50,
            weight=weight,
            label="No data",
            detail="P/E ratio unavailable",
        )
    pe = float(pe)
    if pe <= 0:
        return dict(
            name="Valuation (P/E)",
            score=25,
            weight=weight,
            label="Negative earnings",
            detail=f"P/E={pe:.1f} — company is not yet profitable",
        )
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
    return dict(
        name="Valuation (P/E)",
        score=s,
        weight=weight,
        label=lbl,
        detail=f"Trailing P/E: {pe:.1f}×",
    )


def _factor_trend(close: pd.Series | None, price: float | None) -> dict:
    """Price position relative to SMA-50 and SMA-200."""
    weight = _get_weight("trend", 0.20)
    if close is None or price is None:
        return dict(
            name="Trend (SMA)",
            score=50,
            weight=weight,
            label="No data",
            detail="Price data unavailable",
        )

    sma50 = _sma(close, 50)
    sma200 = _sma(close, 200)

    if sma50 is None:
        return dict(
            name="Trend (SMA)",
            score=50,
            weight=weight,
            label="Insufficient data",
            detail="Fewer than 50 trading days available",
        )

    if sma200 is None:
        if price > sma50:
            s, lbl, detail = (
                65,
                "Above SMA-50",
                f"Price ${price:.2f} > SMA-50 ${sma50:.2f}",
            )
        else:
            s, lbl, detail = (
                38,
                "Below SMA-50",
                f"Price ${price:.2f} < SMA-50 ${sma50:.2f}",
            )
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
        return dict(
            name="Momentum (RSI)",
            score=50,
            weight=weight,
            label="No data",
            detail="Price data unavailable",
        )

    rsi = _rsi(close)
    if rsi is None:
        return dict(
            name="Momentum (RSI)",
            score=50,
            weight=weight,
            label="Insufficient data",
            detail="Fewer than 15 trading days",
        )

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

    return dict(
        name="Momentum (RSI)",
        score=s,
        weight=weight,
        label=lbl,
        detail=f"RSI-14: {rsi:.1f}",
    )


def _factor_macd(close: pd.Series | None) -> dict:
    """MACD histogram direction (current vs previous bar)."""
    weight = _get_weight("macd", 0.10)
    if close is None:
        return dict(
            name="MACD Signal",
            score=50,
            weight=weight,
            label="No data",
            detail="Price data unavailable",
        )

    hist, hist_prev = _macd_histograms(close)
    if hist is None:
        return dict(
            name="MACD Signal",
            score=50,
            weight=weight,
            label="Insufficient data",
            detail="Fewer than 36 trading days",
        )

    if hist > 0 and hist > hist_prev:
        s, lbl = 88, "Bullish & accelerating"
    elif hist > 0 and hist <= hist_prev:
        s, lbl = 62, "Bullish but decelerating"
    elif hist <= 0 and hist > hist_prev:
        s, lbl = 42, "Bearish but recovering"
    else:
        s, lbl = 15, "Bearish & deteriorating"

    direction = "↑" if hist > hist_prev else "↓"
    return dict(
        name="MACD Signal",
        score=s,
        weight=weight,
        label=lbl,
        detail=f"Histogram: {hist:+.4f} {direction}",
    )


def _factor_sentiment(sentiment_agg: dict | None) -> dict:
    """FinBERT aggregate news sentiment net score."""
    weight = _get_weight("sentiment", 0.15)
    if not sentiment_agg:
        return dict(
            name="News Sentiment",
            score=50,
            weight=weight,
            label="No data",
            detail="Sentiment data unavailable",
        )

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
    return dict(
        name="News Sentiment", score=score, weight=weight, label=signal, detail=detail
    )


def _factor_earnings(earnings: list) -> dict:
    """Average EPS surprise % over the last 4 quarters."""
    weight = _get_weight("earnings", 0.15)
    surprises = [
        float(e["surprisePercent"])
        for e in (earnings or [])
        if e.get("surprisePercent") is not None
    ]
    if not surprises:
        return dict(
            name="Earnings Quality",
            score=50,
            weight=weight,
            label="No data",
            detail="No EPS surprise data",
        )

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
        f"Avg surprise: {avg:+.1f}%  |  Beat {beat_count}/{len(surprises)} quarters"
    )
    return dict(
        name="Earnings Quality", score=s, weight=weight, label=lbl, detail=detail
    )


def _factor_analyst(recommendations: list) -> dict:
    """Buy/Hold/Sell consensus from the most recent recommendation period."""
    weight = _get_weight("analyst", 0.10)
    if not recommendations:
        return dict(
            name="Analyst Consensus",
            score=50,
            weight=weight,
            label="No data",
            detail="No analyst recommendations",
        )

    latest = recommendations[0]
    strong_buy = int(latest.get("strongBuy", 0))
    buy = int(latest.get("buy", 0))
    hold = int(latest.get("hold", 0))
    sell = int(latest.get("sell", 0))
    strong_sell = int(latest.get("strongSell", 0))
    total = strong_buy + buy + hold + sell + strong_sell

    if total == 0:
        return dict(
            name="Analyst Consensus",
            score=50,
            weight=weight,
            label="No coverage",
            detail="No analyst ratings available",
        )

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
    return dict(
        name="Analyst Consensus", score=s, weight=weight, label=lbl, detail=detail
    )


def _factor_range_position(financials: dict | None, price: float | None) -> dict:
    """Price position within the 52-week range (momentum / price-strength)."""
    weight = _get_weight("range", 0.05)
    metrics = financials or {}
    high52 = metrics.get("52WeekHigh")
    low52 = metrics.get("52WeekLow")

    if high52 is None or low52 is None or price is None:
        return dict(
            name="52-Wk Strength",
            score=50,
            weight=weight,
            label="No data",
            detail="52-week range unavailable",
        )

    high52, low52, price = float(high52), float(low52), float(price)
    if high52 <= low52:
        return dict(
            name="52-Wk Strength",
            score=50,
            weight=weight,
            label="Flat range",
            detail="52-week high equals low",
        )

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
    return dict(
        name="52-Wk Strength", score=score, weight=weight, label=lbl, detail=detail
    )


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


def _factor_valuation_sector_adjusted(
    financials: dict | None, sector: str | None
) -> dict:
    """Sector-relative P/E valuation.  Compares stock P/E to sector median."""
    weight = _get_weight("valuation", 0.15)
    pe = (financials or {}).get("peBasicExclExtraTTM")

    if pe is None:
        return dict(
            name="Valuation (P/E)",
            score=50,
            weight=weight,
            label="No data",
            detail="P/E ratio unavailable",
        )
    pe = float(pe)
    if pe <= 0:
        return dict(
            name="Valuation (P/E)",
            score=25,
            weight=weight,
            label="Negative earnings",
            detail=f"P/E={pe:.1f} — company is not yet profitable",
        )

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
        return dict(
            name="Dividend Yield",
            score=50,
            weight=weight,
            label="No data",
            detail="Dividend data unavailable",
        )

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
        return dict(
            name="Estimate Revisions",
            score=50,
            weight=weight,
            label="No data",
            detail="Estimate revision data unavailable",
        )

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

    return dict(
        name="Estimate Revisions", score=s, weight=weight, label=lbl, detail=detail
    )


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
        daily_composite,
        weekly_composite,
        monthly_composite,
        alignment,
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
    valid = [q for q in quarters if q.get("surprisePercent") is not None]
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
        beat_count,
        total,
        streak,
        consistency_score,
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

    detail = (
        " | ".join(details)
        if details
        else "Insufficient data for regime classification"
    )
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
    (70, "Strong Buy", "#1a7f37"),
    (55, "Buy", "#2da44e"),
    (45, "Neutral", "#888888"),
    (30, "Sell", "#e05252"),
    (0, "Strong Sell", "#cf2929"),
]


def composite_label_color(score: int) -> tuple[str, str]:
    """Return (label, hex_color) for a composite score."""
    for threshold, label, color in COMPOSITE_LABEL:
        if score >= threshold:
            return label, color
    return "Strong Sell", "#cf2929"


# ---------------------------------------------------------------------------
# 21.3: Dividend Growth scoring helper
# ---------------------------------------------------------------------------


def compute_dividend_growth_score(financials: dict | None) -> dict:
    """Score dividend quality for dividend growth investing (21.3).

    Combines yield, payout sustainability, and growth signals available
    from Finnhub basic metrics into a 0-100 quality score.

    Returns
    -------
    dict with:
        score           – int 0-100
        yield_pct       – float or None
        payout_ratio    – float or None
        growth_signal   – "Growing" | "Stable" | "At Risk" | "No Dividend"
        qualifies       – bool (meets min criteria for dividend growth strategy)
        detail          – human-readable summary
    """
    metrics = financials or {}
    div_yield = metrics.get("dividendYieldIndicatedAnnual")
    payout_ratio = metrics.get("payoutRatioTTM")
    div_yield_5y = metrics.get("dividendYield5Y")
    div_growth_rate = metrics.get("dividendGrowthRate5Y")

    if div_yield is None or float(div_yield) <= 0:
        return {
            "score": 0,
            "yield_pct": None,
            "payout_ratio": None,
            "growth_signal": "No Dividend",
            "qualifies": False,
            "detail": "No dividend paid",
        }

    div_yield = float(div_yield)
    payout = float(payout_ratio) if payout_ratio is not None else None
    yield_5y = float(div_yield_5y) if div_yield_5y is not None else None
    growth_rate = float(div_growth_rate) if div_growth_rate is not None else None

    score = 0
    detail_parts = [f"Yield: {div_yield:.2f}%"]

    # Yield component (0-30 pts)
    if div_yield >= 4.0:
        score += 25
    elif div_yield >= 3.0:
        score += 30
    elif div_yield >= 2.0:
        score += 22
    elif div_yield >= 1.0:
        score += 12
    else:
        score += 5

    # Payout sustainability (0-30 pts)
    if payout is not None:
        detail_parts.append(f"Payout: {payout:.0f}%")
        if payout <= 40:
            score += 30
        elif payout <= 60:
            score += 22
        elif payout <= 75:
            score += 12
        elif payout <= 100:
            score += 4
        else:
            score += 0  # paying out more than earnings

    # Growth signal (0-40 pts)
    growth_signal = "Stable"
    if growth_rate is not None:
        detail_parts.append(f"5Y div CAGR: {growth_rate:.1f}%")
        if growth_rate >= 7.0:
            score += 40
            growth_signal = "Growing"
        elif growth_rate >= 3.0:
            score += 28
            growth_signal = "Growing"
        elif growth_rate >= 0:
            score += 16
            growth_signal = "Stable"
        else:
            score += 0
            growth_signal = "At Risk"
    elif yield_5y is not None and div_yield >= yield_5y * 0.9:
        # Yield has been at least maintained
        score += 18
        growth_signal = "Stable"
        detail_parts.append("Yield maintained vs 5Y avg")

    # Qualification: yield ≥ 2%, payout ≤ 75%, growth_signal != "At Risk"
    qualifies = (
        div_yield >= 2.0
        and (payout is None or payout <= 75)
        and growth_signal != "At Risk"
    )

    return {
        "score": _clamp(score),
        "yield_pct": round(div_yield, 2),
        "payout_ratio": round(payout, 1) if payout is not None else None,
        "growth_signal": growth_signal,
        "qualifies": qualifies,
        "detail": " | ".join(detail_parts),
    }


# ---------------------------------------------------------------------------
# 21.4: Graham Number / Deep Value
# ---------------------------------------------------------------------------


def compute_graham_number(eps: float, bvps: float) -> float | None:
    """Compute Benjamin Graham's intrinsic value estimate.

    Graham Number = √(22.5 × EPS × BVPS)

    Only valid when both EPS and BVPS are positive.
    Returns None if inputs are invalid.
    """
    if eps is None or bvps is None:
        return None
    try:
        eps, bvps = float(eps), float(bvps)
    except (TypeError, ValueError):
        return None
    if eps <= 0 or bvps <= 0:
        return None
    return round(math.sqrt(22.5 * eps * bvps), 2)


def _factor_graham_number(financials: dict | None, price: float | None) -> dict:
    """Graham Number deep-value factor (21.4).

    Computes margin of safety = (Graham Number - Price) / Graham Number.
    A positive margin means the stock trades below Graham's intrinsic value.
    """
    weight = _get_weight(
        "graham", 0.0
    )  # informational by default; add to cfg to enable
    metrics = financials or {}
    eps = metrics.get("epsTTM") or metrics.get("epsBasicExclExtraItemsTTM")
    bvps = metrics.get("bookValuePerShareAnnual") or metrics.get(
        "bookValuePerShareQuarterly"
    )

    graham = compute_graham_number(eps, bvps) if eps and bvps else None

    if graham is None or price is None or price <= 0:
        return dict(
            name="Graham Number",
            score=50,
            weight=weight,
            label="No data",
            detail="EPS or BVPS unavailable",
            graham_number=None,
            margin_of_safety=None,
        )

    margin = (graham - price) / graham
    detail = f"Graham Number: ${graham:.2f} | Price: ${price:.2f} | MoS: {margin:.0%}"

    if margin >= 0.30:
        s, lbl = 95, "Deep value — large margin of safety"
    elif margin >= 0.15:
        s, lbl = 80, "Value — positive margin of safety"
    elif margin >= 0.0:
        s, lbl = 60, "Fair — near Graham Number"
    elif margin >= -0.20:
        s, lbl = 38, "Slight premium to Graham Number"
    else:
        s, lbl = 18, "Significant premium to Graham Number"

    return dict(
        name="Graham Number",
        score=s,
        weight=weight,
        label=lbl,
        detail=detail,
        graham_number=graham,
        margin_of_safety=round(margin, 4),
    )


# ---------------------------------------------------------------------------
# 21.6: Piotroski F-Score
# ---------------------------------------------------------------------------


def compute_piotroski_fscore(financials: dict | None) -> dict:
    """Compute the Piotroski F-Score (0–9) from available fundamentals (21.6).

    The score is composed of three groups of binary signals:

    Profitability (4 signals):
      F1  ROA > 0  (net income positive)
      F2  Operating Cash Flow > 0
      F3  ΔROA > 0  (ROA improved year-over-year)
      F4  Accruals < 0  (CFO/Assets > ROA → cash-backed earnings)

    Leverage & Liquidity (3 signals):
      F5  Long-term leverage decreased
      F6  Current ratio improved
      F7  No dilution (shares not increased)

    Operating Efficiency (2 signals):
      F8  Gross margin improved
      F9  Asset turnover improved

    Scoring: each signal = 1 if condition met, 0 otherwise.
    Total 0-9; ≥7 = strong quality buy, ≤2 = distressed.

    Parameters
    ----------
    financials : Finnhub basic-metrics dict or None

    Returns
    -------
    dict with:
        total_score      – int 0-9
        signals          – dict mapping signal_name -> 0 | 1 | None (None = no data)
        quality_label    – "Strong" | "Moderate" | "Weak" | "Distressed"
        available_signals – int, count of signals with data
        detail           – human-readable summary
    """
    m = financials or {}

    def _get(key):
        v = m.get(key)
        return float(v) if v is not None else None

    roa_ttm = _get("roaTTM")
    roa_ann = _get("roaRfy") or _get("roa5Y")  # prior-year proxy
    cfo_ttm = _get("cashFlowTTM") or _get("freeCashFlowTTM")
    # Leverage
    debt_eq_ann = _get("totalDebt/equityAnnual")
    debt_eq_q = _get("totalDebt/equityQuarterly")
    # Liquidity
    curr_ann = _get("currentRatioAnnual")
    curr_q = _get("currentRatioQuarterly")
    # Margins
    gm_ttm = _get("grossMarginTTM")
    gm_ann = _get("grossMarginAnnual")
    # Total assets proxy (for accruals)
    assets = _get("totalAssets") or _get("bookValuePerShareAnnual")

    signals: dict[str, int | None] = {}

    # F1: ROA > 0
    signals["F1_roa_positive"] = (
        (1 if roa_ttm > 0 else 0) if roa_ttm is not None else None
    )

    # F2: Operating Cash Flow > 0
    signals["F2_cfo_positive"] = (
        (1 if cfo_ttm > 0 else 0) if cfo_ttm is not None else None
    )

    # F3: ΔROA > 0
    if roa_ttm is not None and roa_ann is not None:
        signals["F3_delta_roa"] = 1 if roa_ttm > roa_ann else 0
    else:
        signals["F3_delta_roa"] = None

    # F4: Accruals < 0 (CFO > ROA implies cash-backed earnings)
    if (
        cfo_ttm is not None
        and roa_ttm is not None
        and assets is not None
        and assets > 0
    ):
        cfo_to_assets = cfo_ttm / assets
        accruals = roa_ttm - cfo_to_assets
        signals["F4_low_accruals"] = 1 if accruals < 0 else 0
    else:
        signals["F4_low_accruals"] = None

    # F5: Leverage decreased
    if debt_eq_ann is not None and debt_eq_q is not None:
        signals["F5_leverage_decreased"] = 1 if debt_eq_q < debt_eq_ann else 0
    else:
        signals["F5_leverage_decreased"] = None

    # F6: Liquidity improved
    if curr_ann is not None and curr_q is not None:
        signals["F6_liquidity_improved"] = 1 if curr_q > curr_ann else 0
    else:
        signals["F6_liquidity_improved"] = None

    # F7: No dilution (shares_ann used as proxy; ideal needs prev-year share count)
    # We infer from share buyback signal if available
    signals["F7_no_dilution"] = None  # requires two-year share count data

    # F8: Gross margin improved
    if gm_ttm is not None and gm_ann is not None:
        signals["F8_gm_improved"] = 1 if gm_ttm > gm_ann else 0
    else:
        signals["F8_gm_improved"] = None

    # F9: Asset turnover improved
    signals["F9_asset_turnover"] = None  # requires prior-year asset turnover

    # Compute total from available signals
    available = [v for v in signals.values() if v is not None]
    total_score = sum(v for v in available)
    available_count = len(available)

    # Scale label
    if available_count == 0:
        quality_label = "No data"
    elif total_score >= 7:
        quality_label = "Strong"
    elif total_score >= 5:
        quality_label = "Moderate"
    elif total_score >= 3:
        quality_label = "Weak"
    else:
        quality_label = "Distressed"

    detail = f"F-Score: {total_score}/{available_count} signals available"
    if available_count < 9:
        detail += f" ({9 - available_count} signals require additional data)"

    log.debug(
        "Piotroski F-Score: %d/%d — %s", total_score, available_count, quality_label
    )

    return {
        "total_score": total_score,
        "signals": signals,
        "quality_label": quality_label,
        "available_signals": available_count,
        "detail": detail,
    }


def _factor_piotroski(financials: dict | None) -> dict:
    """Piotroski F-Score as a factor dimension (21.6)."""
    weight = _get_weight(
        "piotroski", 0.0
    )  # informational by default; add to cfg to enable
    result = compute_piotroski_fscore(financials)
    total = result["total_score"]
    avail = result["available_signals"]
    quality_label = result["quality_label"]

    if avail == 0:
        return dict(
            name="Piotroski F-Score",
            score=50,
            weight=weight,
            label="No data",
            detail="Fundamental data unavailable",
            fscore=None,
        )

    # Map 0-9 score to 0-100 factor score
    raw_pct = total / max(avail, 1)
    score = _clamp(raw_pct * 100)

    detail = f"F-Score: {total}/{avail} | {quality_label}"

    return dict(
        name="Piotroski F-Score",
        score=score,
        weight=weight,
        label=quality_label,
        detail=detail,
        fscore=total,
    )


# ---------------------------------------------------------------------------
# 21.7: Extended Macro Regime Detection
# ---------------------------------------------------------------------------

# Per-regime factor weight adjustment presets (additive deltas to defaults)
_REGIME_WEIGHT_DELTAS: dict[str, dict[str, float]] = {
    "Strong Bull": {
        "trend": +0.05,
        "rsi": +0.02,
        "valuation": -0.02,
    },
    "Bull": {
        "trend": +0.02,
    },
    "Neutral": {},
    "Bear": {
        "valuation": +0.03,
        "earnings": +0.03,
        "trend": -0.03,
    },
    "Strong Bear": {
        "valuation": +0.05,
        "earnings": +0.05,
        "trend": -0.05,
        "rsi": -0.02,
    },
    "Stagflation": {
        "valuation": +0.06,  # value stocks outperform
        "dividend": +0.04,  # income important in stagflation
        "trend": -0.04,
        "rsi": -0.02,
    },
    "Recovery": {
        "trend": +0.04,
        "rsi": +0.03,
        "earnings": +0.03,
        "valuation": -0.02,
    },
}


def compute_market_regime_extended(
    spy_close: "pd.Series | None",
    vix: float | None,
    yield_spread: float | None,
    vix_prev: float | None = None,
    days_since_sma_cross: int | None = None,
) -> dict:
    """Classify the macro regime into one of seven states (21.7).

    Extends the base `compute_market_regime` function to distinguish
    Stagflation and Recovery phases in addition to the core five.

    Parameters
    ----------
    spy_close           : pd.Series of SPY daily closes (most recent last)
    vix                 : current VIX level, or None
    yield_spread        : 10Y-2Y Treasury spread in ppt (positive = normal,
                          negative = inverted), or None
    vix_prev            : VIX level from ~20 trading days ago (for trend), or None
    days_since_sma_cross : days since SPY crossed its 200d SMA, or None
                           (positive = recently crossed above, negative = below)

    Returns
    -------
    dict with:
        regime              – str (one of seven regime labels)
        score_adjustment    – int applied to composite scores
        detail              – human-readable explanation
        weight_deltas       – dict of per-factor weight adjustments
    """
    spy_above_200 = None
    sma200 = None
    if spy_close is not None and len(spy_close) >= 200:
        sma200 = float(spy_close.rolling(window=200).mean().iloc[-1])
        current = float(spy_close.iloc[-1])
        spy_above_200 = current > sma200

    details = []
    if spy_above_200 is not None:
        details.append(f"SPY {'above' if spy_above_200 else 'below'} 200d SMA")
    if vix is not None:
        details.append(f"VIX={vix:.1f}")
    if vix_prev is not None:
        vix_trend = "↓" if vix < vix_prev else "↑"
        details.append(f"VIX trend={vix_trend}")
    if yield_spread is not None:
        details.append(f"yield spread={yield_spread:+.2f}%")
    if days_since_sma_cross is not None:
        details.append(f"SMA cross={days_since_sma_cross}d ago")

    # Classification logic (extended)
    vix_high = vix is not None and vix > 25
    vix_very_high = vix is not None and vix > 35
    vix_declining = vix is not None and vix_prev is not None and vix < vix_prev * 0.85
    yield_inverted = yield_spread is not None and yield_spread < -0.10
    recent_sma_cross = (
        days_since_sma_cross is not None and 0 < days_since_sma_cross <= 60
    )

    if vix_very_high and spy_above_200 is False:
        regime, adj = "Strong Bear", -10

    elif vix_high and yield_inverted and spy_above_200 is False:
        # High volatility + inverted yield curve + falling market = Stagflation
        regime, adj = "Stagflation", -8

    elif vix_high:
        regime, adj = "Bear", -5

    elif spy_above_200 is True and vix_declining and recent_sma_cross:
        # VIX declining + SPY recently crossed back above 200d = early Recovery
        regime, adj = "Recovery", +4

    elif spy_above_200 is True and vix is not None and vix < 18:
        if yield_spread is not None and yield_spread > 0:
            regime, adj = "Strong Bull", +5
        else:
            regime, adj = "Bull", +2

    elif spy_above_200 is True:
        regime, adj = "Bull", +2

    else:
        regime, adj = "Neutral", 0

    detail = " | ".join(details) if details else "Insufficient data"
    weight_deltas = _REGIME_WEIGHT_DELTAS.get(regime, {})

    log.debug("Extended regime: %s (adj=%+d)", regime, adj)

    return {
        "regime": regime,
        "score_adjustment": adj,
        "detail": detail,
        "weight_deltas": weight_deltas,
    }


def get_regime_factor_weights(
    regime: str, base_weights: dict[str, float] | None = None
) -> dict[str, float]:
    """Return factor weights adjusted for the given macro regime (21.7).

    Parameters
    ----------
    regime      : regime string from compute_market_regime_extended()
    base_weights: starting weights dict; defaults to cfg.factor_weights

    Returns
    -------
    dict mapping factor name -> adjusted weight (values normalized to sum to 1).
    """
    if base_weights is None:
        base_weights = dict(cfg.factor_weights)

    deltas = _REGIME_WEIGHT_DELTAS.get(regime, {})
    adjusted = {}
    for k, v in base_weights.items():
        delta = deltas.get(k, 0.0)
        adjusted[k] = max(0.0, v + delta)

    total = sum(adjusted.values())
    if total > 0:
        adjusted = {k: round(v / total, 4) for k, v in adjusted.items()}

    return adjusted


# ---------------------------------------------------------------------------
# 21.8: Seasonal / Calendar Pattern Overlay
# ---------------------------------------------------------------------------

# Monthly seasonal bias in composite score points (−5 to +5)
# Sources: January Effect, Sell in May, September Effect, Santa Claus rally
_MONTHLY_SEASONAL_BIAS: dict[int, int] = {
    1: +3,  # January Effect — small-cap strength, new money inflows
    2: +1,  # Post-January momentum continuation
    3: 0,  # Neutral
    4: +2,  # Spring rally — pre-earnings momentum
    5: -2,  # "Sell in May" seasonal weakness begins
    6: -1,  # Pre-summer lull
    7: +1,  # Summer rally — light vol, upward drift
    8: -1,  # Late summer weakness
    9: -3,  # September: historically the weakest month of the year
    10: +1,  # October recovery after September weakness
    11: +2,  # Pre-holiday buying, Q4 momentum
    12: +3,  # Santa Claus rally, year-end positioning, tax-loss reversal
}

# Event-level biases for specific calendar windows
_CALENDAR_EVENTS: list[dict] = [
    {
        "name": "Tax-Loss Harvesting Season",
        "months": [11, 12],
        "days_start": 15,
        "bias": -1,
    },
    {"name": "Santa Claus Rally Window", "months": [12], "days_start": 24, "bias": +2},
    {"name": "January Effect Window", "months": [1], "days_start": 1, "bias": +2},
    {
        "name": "Pre-Earnings Season Momentum",
        "months": [1, 4, 7, 10],
        "days_start": 1,
        "bias": +1,
    },
]


def compute_seasonal_bias(month: int | None = None, day: int | None = None) -> dict:
    """Compute calendar-based score adjustment for the current date (21.8).

    Parameters
    ----------
    month : calendar month (1-12); uses current month if None
    day   : day of month (1-31); uses current day if None

    Returns
    -------
    dict with:
        month           – int
        base_bias       – int, monthly bias in score points
        event_bias      – int, additional event-level adjustment
        total_bias      – int, total seasonal adjustment
        active_event    – str or None, name of active calendar event
        detail          – human-readable description
    """
    import datetime

    if month is None or day is None:
        today = datetime.date.today()
        month = month or today.month
        day = day or today.day

    base_bias = _MONTHLY_SEASONAL_BIAS.get(month, 0)

    # Check for active calendar events
    event_bias = 0
    active_event = None
    for event in _CALENDAR_EVENTS:
        if month in event["months"] and day >= event["days_start"]:
            if abs(event["bias"]) > abs(event_bias):
                event_bias = event["bias"]
                active_event = event["name"]

    total_bias = base_bias + event_bias

    month_names = {
        1: "January",
        2: "February",
        3: "March",
        4: "April",
        5: "May",
        6: "June",
        7: "July",
        8: "August",
        9: "September",
        10: "October",
        11: "November",
        12: "December",
    }
    month_name = month_names.get(month, str(month))

    bias_str = f"{total_bias:+d} pts"
    detail = f"{month_name} seasonal bias: {bias_str}"
    if active_event:
        detail += f" | Active: {active_event}"

    log.debug("Seasonal bias month=%d day=%d: %+d pts", month, day, total_bias)

    return {
        "month": month,
        "base_bias": base_bias,
        "event_bias": event_bias,
        "total_bias": total_bias,
        "active_event": active_event,
        "detail": detail,
    }


# ---------------------------------------------------------------------------
# P23.1: Low Volatility Anomaly
# ---------------------------------------------------------------------------


def compute_low_volatility_score(close: "pd.Series | None") -> dict:
    """Score based on the low-volatility anomaly (23.1).

    Lower 60-day realized volatility = higher score (inverse relationship).
    Historically, lower-volatility stocks outperform on a risk-adjusted basis.

    Returns
    -------
    dict with:
        score        – int 0-100 (higher = lower vol = more favourable)
        volatility_60d – float annualised % or None
        label        – str
        detail       – str
    """
    if close is None or len(close) < 62:
        return {
            "score": 50,
            "volatility_60d": None,
            "label": "No data",
            "detail": "Insufficient price history (need 62+ days)",
        }

    ratio = (close / close.shift(1)).dropna()
    ratio = ratio[ratio > 0]
    if len(ratio) < 60:
        return {
            "score": 50,
            "volatility_60d": None,
            "label": "No data",
            "detail": "Insufficient price history",
        }

    log_returns = ratio.apply(math.log)
    daily_std = float(log_returns.tail(60).std())
    vol_60d = daily_std * math.sqrt(252) * 100  # annualised %

    if vol_60d < 15:
        score, label = 90, "Very low volatility"
    elif vol_60d < 20:
        score, label = 78, "Low volatility"
    elif vol_60d < 30:
        score, label = 60, "Moderate volatility"
    elif vol_60d < 40:
        score, label = 40, "High volatility"
    elif vol_60d < 55:
        score, label = 24, "Very high volatility"
    else:
        score, label = 10, "Extreme volatility"

    return {
        "score": score,
        "volatility_60d": round(vol_60d, 2),
        "label": label,
        "detail": f"60-day annualised vol: {vol_60d:.1f}%",
    }


# ---------------------------------------------------------------------------
# P23.2: Shareholder Yield
# ---------------------------------------------------------------------------


def compute_shareholder_yield(financials: dict | None) -> dict:
    """Compute total shareholder yield = dividend yield + buyback yield (23.2).

    Combines dividend yield + net share repurchase yield into a single
    composite return metric. Firms returning >8% combined yield historically
    outperform on a total-return basis.

    Returns
    -------
    dict with:
        score               – int 0-100
        dividend_yield_pct  – float
        buyback_yield_pct   – float or None
        total_yield_pct     – float
        label               – str
        detail              – str
    """
    m = financials or {}
    div_yield = m.get("dividendYieldIndicatedAnnual")
    buyback = m.get("repurchaseOfCommonStockAnnual") or m.get(
        "commonStockRepurchasedAnnual"
    )
    market_cap = m.get("marketCapitalization")

    div_pct = float(div_yield) if div_yield is not None else 0.0
    buyback_pct: float | None = None

    if buyback is not None and market_cap is not None:
        mc = float(market_cap)
        if mc > 0:
            buyback_pct = round(abs(float(buyback)) / mc * 100, 2)

    total_yield = div_pct + (buyback_pct or 0.0)

    if total_yield >= 10:
        score, label = 95, "Exceptional shareholder yield"
    elif total_yield >= 8:
        score, label = 85, "Very high shareholder yield"
    elif total_yield >= 5:
        score, label = 72, "High shareholder yield"
    elif total_yield >= 3:
        score, label = 58, "Moderate shareholder yield"
    elif total_yield >= 1:
        score, label = 42, "Low shareholder yield"
    else:
        score, label = 20, "Minimal shareholder return"

    parts = [f"Dividend: {div_pct:.2f}%"]
    if buyback_pct is not None:
        parts.append(f"Buyback: {buyback_pct:.2f}%")
    parts.append(f"Total yield: {total_yield:.2f}%")

    return {
        "score": score,
        "dividend_yield_pct": round(div_pct, 2),
        "buyback_yield_pct": buyback_pct,
        "total_yield_pct": round(total_yield, 2),
        "label": label,
        "detail": " | ".join(parts),
    }


# ---------------------------------------------------------------------------
# P23.3: Earnings Revision Momentum
# ---------------------------------------------------------------------------


def compute_earnings_revision_momentum(
    earnings: list | None,
    revisions: dict | None,
) -> dict:
    """Compute earnings revision momentum from EPS surprise trend (23.3).

    Detects whether EPS surprises are accelerating or decelerating across
    recent quarters by computing a linear slope of the surprise % series.
    Augmented by analyst estimate revision direction if available.

    Returns
    -------
    dict with:
        score          – int 0-100
        trend          – "Accelerating" | "Improving" | "Stable" | "Decelerating" | ...
        surprise_slope – float or None (positive = improving quarter-over-quarter)
        avg_surprise   – float or None
        detail         – str
    """
    surprises: list[float] = []
    if earnings:
        for e in (earnings or [])[:8]:
            sp = e.get("surprisePercent")
            if sp is not None:
                surprises.append(float(sp))

    revision_dir = (revisions or {}).get("revision_direction", "flat") if revisions else "flat"

    if len(surprises) < 2:
        if revision_dir == "up":
            return {
                "score": 72,
                "trend": "Improving",
                "surprise_slope": None,
                "avg_surprise": None,
                "detail": "Analyst estimates revised upward",
            }
        if revision_dir == "down":
            return {
                "score": 28,
                "trend": "Deteriorating",
                "surprise_slope": None,
                "avg_surprise": None,
                "detail": "Analyst estimates revised downward",
            }
        return {
            "score": 50,
            "trend": "No data",
            "surprise_slope": None,
            "avg_surprise": None,
            "detail": "Insufficient earnings data",
        }

    # Compute slope of surprise series (oldest → newest)
    series = list(reversed(surprises[:4]))
    n = len(series)
    x_mean = (n - 1) / 2.0
    y_mean = sum(series) / n
    numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(series))
    denominator = sum((i - x_mean) ** 2 for i in range(n))
    slope = numerator / denominator if denominator > 0 else 0.0
    avg_surprise = sum(series) / n

    if slope > 3:
        score, trend = 88, "Accelerating"
    elif slope > 1:
        score, trend = 75, "Improving"
    elif slope > -1:
        if avg_surprise > 3:
            score, trend = 65, "Stable positive"
        elif avg_surprise > 0:
            score, trend = 55, "Stable"
        else:
            score, trend = 42, "Stable negative"
    elif slope > -3:
        score, trend = 32, "Decelerating"
    else:
        score, trend = 18, "Deteriorating"

    if revision_dir == "up":
        score = min(100, score + 8)
    elif revision_dir == "down":
        score = max(0, score - 8)

    detail = (
        f"Surprise slope: {slope:+.2f}/qtr | "
        f"Avg: {avg_surprise:+.1f}% | Revisions: {revision_dir}"
    )

    return {
        "score": _clamp(score),
        "trend": trend,
        "surprise_slope": round(slope, 3),
        "avg_surprise": round(avg_surprise, 2),
        "detail": detail,
    }


# ---------------------------------------------------------------------------
# P23.4: Altman Z-Score
# ---------------------------------------------------------------------------


def compute_altman_zscore(financials: dict | None) -> dict:
    """Compute the Altman Z-Score for bankruptcy risk prediction (23.4).

    Z = 1.2×X1 + 1.4×X2 + 3.3×X3 + 0.6×X4 + 1.0×X5

    Where:
      X1 = Working Capital / Total Assets
      X2 = Retained Earnings / Total Assets
      X3 = EBIT / Total Assets
      X4 = Market Value of Equity / Book Value of Total Liabilities
      X5 = Revenue / Total Assets

    Zones:
      Z > 2.99  = Safe zone
      1.8–2.99  = Grey zone
      Z ≤ 1.8   = Distress zone

    Returns
    -------
    dict with:
        z_score    – float or None
        zone       – "Safe" | "Grey" | "Distress" | "No data"
        score      – int 0-100 (higher = safer / less distress risk)
        components – dict of X1–X5 values (float or None)
        detail     – str
    """
    m = financials or {}

    def _get(key: str) -> float | None:
        v = m.get(key)
        return float(v) if v is not None else None

    current_assets = _get("totalCurrentAssetsAnnual") or _get("totalCurrentAssets")
    current_liab = _get("totalCurrentLiabilitiesAnnual") or _get("totalCurrentLiabilities")
    total_assets = _get("totalAssetsAnnual") or _get("totalAssets")
    retained_earnings = _get("retainedEarningsAnnual") or _get("retainedEarnings")
    ebit = _get("ebitAnnual") or _get("ebitTTM")
    market_cap = _get("marketCapitalization")
    total_liab = _get("totalLiabilitiesAnnual") or _get("totalLiabilities")
    revenue = _get("revenueAnnual") or _get("revenueTTM")

    components: dict[str, float | None] = {}

    if current_assets is not None and current_liab is not None and total_assets and total_assets > 0:
        components["X1"] = (current_assets - current_liab) / total_assets
    else:
        components["X1"] = None

    if retained_earnings is not None and total_assets and total_assets > 0:
        components["X2"] = retained_earnings / total_assets
    else:
        components["X2"] = None

    if ebit is not None and total_assets and total_assets > 0:
        components["X3"] = ebit / total_assets
    else:
        components["X3"] = None

    if market_cap is not None and total_liab and total_liab > 0:
        components["X4"] = float(market_cap) / total_liab
    else:
        components["X4"] = None

    if revenue is not None and total_assets and total_assets > 0:
        components["X5"] = revenue / total_assets
    else:
        components["X5"] = None

    available = [k for k, v in components.items() if v is not None]

    if len(available) < 3:
        return {
            "z_score": None,
            "zone": "No data",
            "score": 50,
            "components": components,
            "detail": f"Only {len(available)}/5 Altman components available",
        }

    weights = {"X1": 1.2, "X2": 1.4, "X3": 3.3, "X4": 0.6, "X5": 1.0}
    total_w = sum(weights[k] for k in available)
    full_w = sum(weights.values())

    z_raw = sum(weights[k] * components[k] for k in available)  # type: ignore[operator]
    # Scale proportionally when components are missing
    z = z_raw * (full_w / total_w) if total_w > 0 else z_raw
    z = round(z, 3)

    if z > 2.99:
        zone = "Safe"
        score = _clamp(75 + min(25, int((z - 3.0) * 10)))
    elif z > 1.8:
        zone = "Grey"
        score = _clamp(35 + int((z - 1.8) / 1.2 * 30))
    else:
        zone = "Distress"
        score = _clamp(max(5, int(30 + z * 5)))

    detail = f"Z-Score: {z:.2f} | Zone: {zone} | Components: {len(available)}/5"
    log.debug("Altman Z-Score: %.2f (%s)", z, zone)

    return {
        "z_score": z,
        "zone": zone,
        "score": score,
        "components": {k: round(v, 4) if v is not None else None for k, v in components.items()},
        "detail": detail,
    }


# ---------------------------------------------------------------------------
# P23.5: Net Current Asset Value (NCAV) Screen
# ---------------------------------------------------------------------------


def compute_ncav(financials: dict | None, price: float | None) -> dict:
    """Compute Net Current Asset Value per share for net-net screening (23.5).

    NCAV = Current Assets − Total Liabilities
    NCAV/share = NCAV (in $M × 1e6) / Shares Outstanding

    Stocks trading below NCAV per share are Benjamin Graham "net-nets",
    historically a deep-value anomaly with strong empirical returns.

    Returns
    -------
    dict with:
        ncav_per_share   – float or None
        margin_of_safety – float or None (positive = trading below NCAV)
        is_net_net       – bool
        score            – int 0-100
        detail           – str
    """
    m = financials or {}
    current_assets = m.get("totalCurrentAssetsAnnual") or m.get("totalCurrentAssets")
    total_liab = m.get("totalLiabilitiesAnnual") or m.get("totalLiabilities")
    shares = m.get("shareOutstanding") or m.get("sharesOutstanding")

    if current_assets is None or total_liab is None or shares is None:
        return {
            "ncav_per_share": None,
            "margin_of_safety": None,
            "is_net_net": False,
            "score": 50,
            "detail": "Insufficient balance sheet data for NCAV",
        }

    shares_val = float(shares)
    if shares_val <= 0:
        return {
            "ncav_per_share": None,
            "margin_of_safety": None,
            "is_net_net": False,
            "score": 50,
            "detail": "Invalid share count",
        }

    # Finnhub balance sheet values are in $M; shares outstanding is raw count
    ncav_m = float(current_assets) - float(total_liab)  # millions
    ncav_per_share = (ncav_m * 1_000_000) / shares_val

    if price is None or price <= 0:
        return {
            "ncav_per_share": round(ncav_per_share, 2),
            "margin_of_safety": None,
            "is_net_net": ncav_per_share > 0,
            "score": 60 if ncav_per_share > 0 else 30,
            "detail": f"NCAV/share: ${ncav_per_share:.2f} | Price unavailable",
        }

    is_net_net = price < ncav_per_share
    margin = (ncav_per_share - price) / ncav_per_share if ncav_per_share > 0 else -1.0

    if is_net_net and margin >= 0.30:
        score, lbl = 95, "Deep net-net — trading well below NCAV"
    elif is_net_net and margin >= 0.10:
        score, lbl = 82, "Net-net — trading below NCAV"
    elif is_net_net:
        score, lbl = 70, "Near net-net — slight NCAV discount"
    elif ncav_per_share > 0 and margin >= -0.30:
        score, lbl = 50, "Positive NCAV — modest premium"
    elif ncav_per_share > 0:
        score, lbl = 35, "Positive NCAV — significant premium"
    else:
        score, lbl = 15, "Negative NCAV — liabilities exceed current assets"

    detail = (
        f"NCAV/share: ${ncav_per_share:.2f} | Price: ${price:.2f} | "
        f"MoS: {margin:.0%} | {lbl}"
    )

    return {
        "ncav_per_share": round(ncav_per_share, 2),
        "margin_of_safety": round(margin, 4),
        "is_net_net": is_net_net,
        "score": score,
        "detail": detail,
    }


# ---------------------------------------------------------------------------
# P24.1: 52-Week High Breakout Signal
# ---------------------------------------------------------------------------


def compute_breakout_signal(
    close: "pd.Series | None",
    volume: "pd.Series | None",
    financials: dict | None,
) -> dict:
    """Detect 52-week high breakout with volume confirmation (24.1).

    A breakout is signaled when price is within 1% of or above the 52-week
    high AND current volume is ≥ 1.5× the 20-day average volume.

    Returns
    -------
    dict with:
        score             – int 0-100
        is_breakout       – bool
        pct_from_52w_high – float (negative = below high)
        volume_ratio      – float or None (current / 20d avg)
        label             – str
        detail            – str
    """
    m = financials or {}
    high52 = m.get("52WeekHigh")

    if close is None or len(close) < 20:
        return {
            "score": 50,
            "is_breakout": False,
            "pct_from_52w_high": None,
            "volume_ratio": None,
            "label": "No data",
            "detail": "Insufficient price history",
        }

    price = float(close.iloc[-1])

    if high52 is None:
        lookback = min(252, len(close))
        high52 = float(close.tail(lookback).max())
    else:
        high52 = float(high52)

    if high52 <= 0:
        return {
            "score": 50,
            "is_breakout": False,
            "pct_from_52w_high": None,
            "volume_ratio": None,
            "label": "No data",
            "detail": "Invalid 52-week high",
        }

    pct_from_high = (price - high52) / high52 * 100

    volume_ratio: float | None = None
    if volume is not None and len(volume) >= 20:
        avg_vol = float(volume.tail(20).mean())
        if avg_vol > 0:
            volume_ratio = round(float(volume.iloc[-1]) / avg_vol, 2)

    vol_confirmed = volume_ratio is not None and volume_ratio >= 1.5
    is_breakout = pct_from_high >= -1.0

    if is_breakout and vol_confirmed:
        score, label = 90, "Confirmed breakout"
    elif is_breakout:
        score, label = 72, "Potential breakout (low volume)"
    elif pct_from_high >= -5:
        score, label = 60, "Near 52-week high"
    elif pct_from_high >= -15:
        score, label = 50, "Mid-range"
    elif pct_from_high >= -30:
        score, label = 38, "Below 52-week high"
    else:
        score, label = 22, "Far below 52-week high"

    vol_str = f" | Vol ratio: {volume_ratio:.1f}x" if volume_ratio is not None else ""
    detail = f"Price vs 52W High: {pct_from_high:+.1f}%{vol_str}"

    return {
        "score": score,
        "is_breakout": is_breakout,
        "pct_from_52w_high": round(pct_from_high, 2),
        "volume_ratio": volume_ratio,
        "label": label,
        "detail": detail,
    }


# ---------------------------------------------------------------------------
# P24.3: Index Trend Gate (MA Filter)
# ---------------------------------------------------------------------------


def get_index_trend_gate(spy_close: "pd.Series | None") -> dict:
    """Compute SPY 200-day SMA trend gate to suppress long signals (24.3).

    When SPY is below its 200-day SMA, apply a score penalty to all long
    signals as a simple but powerful market-regime filter.

    Returns
    -------
    dict with:
        gate_open  – bool (True = SPY above 200d SMA, long-friendly)
        spy_price  – float or None
        sma200     – float or None
        pct_vs_sma – float or None
        penalty    – int (points to subtract from long signals when gate closed)
        detail     – str
    """
    if spy_close is None or len(spy_close) < 200:
        return {
            "gate_open": True,
            "spy_price": None,
            "sma200": None,
            "pct_vs_sma": None,
            "penalty": 0,
            "detail": "SPY data unavailable — gate defaulting to open",
        }

    sma200 = float(spy_close.rolling(window=200).mean().iloc[-1])
    spy_price = float(spy_close.iloc[-1])
    pct_vs_sma = round((spy_price / sma200 - 1) * 100, 2)
    gate_open = spy_price > sma200

    if gate_open:
        penalty = 0
        qual = "strong bull" if pct_vs_sma >= 5 else "above"
        detail = f"Gate OPEN — SPY {pct_vs_sma:+.1f}% above 200d SMA ({qual})"
    else:
        penalty = 10
        detail = f"Gate CLOSED — SPY {pct_vs_sma:+.1f}% below 200d SMA (suppress longs)"

    log.debug(
        "Index trend gate: %s (SPY %.2f vs SMA200 %.2f)",
        "OPEN" if gate_open else "CLOSED",
        spy_price,
        sma200,
    )

    return {
        "gate_open": gate_open,
        "spy_price": round(spy_price, 2),
        "sma200": round(sma200, 2),
        "pct_vs_sma": pct_vs_sma,
        "penalty": penalty,
        "detail": detail,
    }


# ---------------------------------------------------------------------------
# P25.2: Tax-Loss Harvesting Bounce Signal
# ---------------------------------------------------------------------------


def compute_tax_loss_bounce_signal(
    close: "pd.Series | None",
    month: int | None = None,
) -> dict:
    """Detect tax-loss harvesting bounce candidates (25.2).

    Stocks down >40% YTD in Q4 (Oct–Dec) experience excess selling from
    tax-loss harvesting. A systematic reversal entry in late December /
    early January captures the mean-reversion bounce.

    Parameters
    ----------
    close : daily close series (most recent last)
    month : current month (1-12); auto-detected if None

    Returns
    -------
    dict with:
        score          – int 0-100
        ytd_return_pct – float or None
        is_candidate   – bool
        signal_active  – bool (True in Nov/Dec/Jan window)
        label          – str
        detail         – str
    """
    import datetime

    if month is None:
        month = datetime.date.today().month

    signal_active = month in (11, 12, 1)

    if close is None or len(close) < 21:
        return {
            "score": 50,
            "ytd_return_pct": None,
            "is_candidate": False,
            "signal_active": signal_active,
            "label": "No data",
            "detail": "Insufficient price history",
        }

    lookback = min(252, len(close) - 1)
    price_now = float(close.iloc[-1])
    price_start = float(close.iloc[-lookback])
    ytd_return = (price_now / price_start - 1) * 100 if price_start > 0 else 0.0

    is_candidate = ytd_return <= -40.0

    if is_candidate and signal_active:
        score, label = (88 if ytd_return <= -60 else 75), (
            "Strong bounce candidate (severe YTD decline)"
            if ytd_return <= -60
            else "Bounce candidate (>40% YTD decline)"
        )
    elif is_candidate:
        score, label = 60, "Potential candidate (outside seasonal window)"
    elif ytd_return <= -25:
        score, label = 45, "Significant YTD decline (monitor in Q4)"
    elif ytd_return <= -10:
        score, label = 40, "Moderate YTD decline"
    else:
        score, label = 30, "Not a bounce candidate"

    season_note = " | In seasonal window" if signal_active else " | Outside seasonal window"
    detail = f"YTD return: {ytd_return:+.1f}%{season_note}"

    return {
        "score": score,
        "ytd_return_pct": round(ytd_return, 2),
        "is_candidate": is_candidate,
        "signal_active": signal_active,
        "label": label,
        "detail": detail,
    }


# ---------------------------------------------------------------------------
# P27.1: Interest Rate Sensitivity
# ---------------------------------------------------------------------------


def compute_rate_sensitivity(
    close: "pd.Series | None",
    tlt_close: "pd.Series | None",
    window: int = 60,
) -> dict:
    """Compute a stock's beta vs TLT (long-bond ETF) as rate sensitivity (27.1).

    A negative TLT beta means the stock moves opposite bonds (hurt by rate
    rises). High |beta_tlt| > 0.3 is classified as rate-sensitive.

    Parameters
    ----------
    close     : stock daily close series
    tlt_close : TLT (iShares 20+ Year Treasury Bond ETF) daily close series
    window    : lookback window in trading days (default 60)

    Returns
    -------
    dict with:
        beta_tlt          – float or None
        is_rate_sensitive – bool
        direction         – "Rate-Sensitive (inverse)" | "Rate-Sensitive (direct)" | "Neutral"
        score_penalty     – int (points to subtract in rising-rate environments)
        label             – str
        detail            – str
    """
    if close is None or tlt_close is None:
        return {
            "beta_tlt": None,
            "is_rate_sensitive": False,
            "direction": "Unknown",
            "score_penalty": 0,
            "label": "No data",
            "detail": "TLT or price data unavailable",
        }

    min_len = min(len(close), len(tlt_close))
    if min_len < window + 5:
        return {
            "beta_tlt": None,
            "is_rate_sensitive": False,
            "direction": "Unknown",
            "score_penalty": 0,
            "label": "Insufficient data",
            "detail": f"Need {window + 5} days of aligned data",
        }

    stock_ret = close.tail(min_len).pct_change().dropna()
    tlt_ret = tlt_close.tail(min_len).pct_change().dropna()

    n = min(len(stock_ret), len(tlt_ret), window)
    sr = stock_ret.tail(n)
    tr = tlt_ret.tail(n)

    var_tlt = float(tr.var())
    if len(sr) < 10 or var_tlt == 0:
        return {
            "beta_tlt": None,
            "is_rate_sensitive": False,
            "direction": "Unknown",
            "score_penalty": 0,
            "label": "Insufficient data",
            "detail": "Cannot compute TLT beta",
        }

    cov = float(sr.cov(tr))
    beta_tlt = round(cov / var_tlt, 3)

    abs_beta = abs(beta_tlt)
    is_rate_sensitive = abs_beta > 0.3

    if beta_tlt < -0.3:
        direction = "Rate-Sensitive (inverse)"
        score_penalty = int(min(15, abs_beta * 20))
    elif beta_tlt > 0.3:
        direction = "Rate-Sensitive (direct)"
        score_penalty = int(min(10, abs_beta * 15))
    else:
        direction = "Neutral"
        score_penalty = 0

    if abs_beta > 0.6:
        label = "Highly rate-sensitive"
    elif abs_beta > 0.3:
        label = "Moderately rate-sensitive"
    else:
        label = "Rate-neutral"

    return {
        "beta_tlt": beta_tlt,
        "is_rate_sensitive": is_rate_sensitive,
        "direction": direction,
        "score_penalty": score_penalty,
        "label": label,
        "detail": f"TLT beta: {beta_tlt:+.3f} | {direction}",
    }


# ---------------------------------------------------------------------------
# P27.2: FX Exposure Adjustment
# ---------------------------------------------------------------------------


def compute_fx_exposure_adjustment(
    financials: dict | None,
    dxy_trend: str | None = None,
) -> dict:
    """Estimate international revenue exposure and FX headwind/tailwind (27.2).

    Uses international revenue % (if available in fundamentals) and DXY
    trend direction to compute a score adjustment for internationally exposed
    companies.

    Parameters
    ----------
    financials : Finnhub metrics dict or None
    dxy_trend  : "strengthening" | "weakening" | "neutral" | None

    Returns
    -------
    dict with:
        intl_revenue_pct  – float or None (0-100)
        fx_exposure       – "High" | "Moderate" | "Low" | "Unknown"
        score_adjustment  – int (-8 to +8 based on exposure × DXY trend)
        label             – str
        detail            – str
    """
    m = financials or {}

    intl_rev_pct: float | None = None
    rev_intl = m.get("revenueInternational") or m.get("internationalRevenue")
    revenue = m.get("revenueAnnual") or m.get("revenueTTM")

    if rev_intl is not None and revenue and float(revenue) > 0:
        intl_rev_pct = round(float(rev_intl) / float(revenue) * 100, 1)

    if intl_rev_pct is None:
        fx_exposure = "Unknown"
    elif intl_rev_pct >= 50:
        fx_exposure = "High"
    elif intl_rev_pct >= 30:
        fx_exposure = "Moderate"
    else:
        fx_exposure = "Low"

    score_adjustment = 0
    if fx_exposure in ("High", "Moderate") and dxy_trend is not None:
        mult = 1.0 if fx_exposure == "High" else 0.5
        if dxy_trend == "weakening":
            score_adjustment = int(8 * mult)
        elif dxy_trend == "strengthening":
            score_adjustment = int(-8 * mult)

    detail_parts: list[str] = []
    if intl_rev_pct is not None:
        detail_parts.append(f"Intl revenue: {intl_rev_pct:.0f}%")
    detail_parts.append(f"FX exposure: {fx_exposure}")
    if dxy_trend:
        detail_parts.append(f"USD trend: {dxy_trend}")
    if score_adjustment != 0:
        detail_parts.append(f"Score adj: {score_adjustment:+d} pts")

    label_map = {
        "High": "High FX exposure",
        "Moderate": "Moderate FX exposure",
        "Low": "Low FX exposure",
        "Unknown": "FX exposure unknown",
    }

    return {
        "intl_revenue_pct": intl_rev_pct,
        "fx_exposure": fx_exposure,
        "score_adjustment": score_adjustment,
        "label": label_map[fx_exposure],
        "detail": " | ".join(detail_parts) if detail_parts else "No FX data available",
    }
