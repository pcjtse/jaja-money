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
# Public API
# ---------------------------------------------------------------------------

def compute_factors(
    quote: dict,
    financials: dict | None,
    close: "pd.Series | None",
    earnings: list,
    recommendations: list,
    sentiment_agg: dict | None,
) -> list[dict]:
    """Compute all 8 factors and return them as a list of dicts.

    Each dict has keys: name, score (0–100), label, detail, weight.
    """
    _c = quote.get("c")
    price = float(_c) if (_c is not None and float(_c) > 0) else None

    factors = [
        _factor_valuation(financials),
        _factor_trend(close, price),
        _factor_rsi(close),
        _factor_macd(close),
        _factor_sentiment(sentiment_agg),
        _factor_earnings(earnings),
        _factor_analyst(recommendations),
        _factor_range_position(financials, price),
    ]
    log.debug("Computed %d factors for price=%.2f", len(factors), price or 0)
    return factors


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
