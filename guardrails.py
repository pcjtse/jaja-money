"""Risk Guardrail Engine.

Computes a 0-100 risk score from four dimensions and surfaces specific
red-flag conditions as structured alerts.  No Streamlit imports.
"""

from __future__ import annotations

import math
import pandas as pd


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _hist_vol(close: pd.Series, window: int = 20) -> float | None:
    """Annualised historical volatility (%) over the last `window` days."""
    if close is None or len(close) < window + 1:
        return None
    ratio = (close / close.shift(1)).dropna()
    ratio = ratio[ratio > 0]   # guard against zero/negative prices
    if len(ratio) < window:
        return None
    log_returns = ratio.apply(math.log)
    daily_std = float(log_returns.tail(window).std())
    return daily_std * math.sqrt(252) * 100   # annualised %


def _rsi(close: pd.Series, length: int = 14) -> float | None:
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


def _sma(close: pd.Series, length: int) -> float | None:
    if close is None or len(close) < length:
        return None
    return float(close.rolling(window=length).mean().iloc[-1])


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> int:
    return int(max(lo, min(hi, v)))


# ---------------------------------------------------------------------------
# Risk dimension scorers  (each returns an int 0-100, higher = more risk)
# ---------------------------------------------------------------------------

def _dim_volatility(close: pd.Series | None) -> tuple[int, float | None]:
    """0-100 volatility risk + raw annualised HV (%)."""
    hv = _hist_vol(close)
    if hv is None:
        return 50, None
    if hv < 15:
        s = 10
    elif hv < 25:
        s = 28
    elif hv < 35:
        s = 52
    elif hv < 50:
        s = 72
    else:
        s = 92
    return s, hv


def _dim_drawdown(price: float | None, financials: dict | None,
                  close: pd.Series | None) -> tuple[int, float | None]:
    """0-100 drawdown risk + raw drawdown (%)."""
    high52 = (financials or {}).get("52WeekHigh")

    # Fallback: use rolling max from candles
    if high52 is None and close is not None and len(close) > 0:
        high52 = float(close.max())

    if high52 is None or price is None or price <= 0:
        return 50, None

    high52, price = float(high52), float(price)
    dd = (high52 - price) / high52 * 100   # % below 52-week high

    if dd < 5:
        s = 5
    elif dd < 15:
        s = 25
    elif dd < 25:
        s = 50
    elif dd < 40:
        s = 74
    else:
        s = 92
    return s, dd


def _dim_signal_risk(composite_factor_score: int) -> int:
    """Inverted factor score: weak fundamentals → high risk."""
    return _clamp(100 - composite_factor_score)


# ---------------------------------------------------------------------------
# Red-flag definitions
# ---------------------------------------------------------------------------

def _build_flags(
    close: pd.Series | None,
    price: float | None,
    financials: dict | None,
    earnings: list,
    recommendations: list,
    sentiment_agg: dict | None,
    composite_factor_score: int,
    hv: float | None,
    drawdown_pct: float | None,
) -> list[dict]:
    """Return a list of flag dicts: {severity, icon, title, message}."""
    flags = []

    def flag(severity, icon, title, message):
        flags.append(dict(severity=severity, icon=icon, title=title, message=message))

    metrics = financials or {}

    # --- Volatility flags ---
    if hv is not None:
        if hv > 60:
            flag("danger", "🔥", "Extreme volatility",
                 f"20-day annualised HV = {hv:.1f}%. Expect very wide intraday swings "
                 f"and elevated option premiums. Position size accordingly.")
        elif hv > 40:
            flag("warning", "⚡", "High volatility",
                 f"20-day annualised HV = {hv:.1f}%. Significantly above the S&P 500 "
                 f"long-run average (~15-18%). Consider tighter stops.")

    # --- Drawdown flags ---
    if drawdown_pct is not None:
        if drawdown_pct > 40:
            flag("danger", "📉", "Severe drawdown",
                 f"Price is {drawdown_pct:.1f}% below the 52-week high. "
                 f"Indicates sustained selling pressure or a structural breakdown.")
        elif drawdown_pct > 25:
            flag("warning", "📉", "Material drawdown",
                 f"Price is {drawdown_pct:.1f}% off the 52-week high. "
                 f"Verify whether this reflects fundamental deterioration or market dislocation.")

    # --- RSI flags ---
    rsi = _rsi(close)
    if rsi is not None:
        if rsi > 80:
            flag("danger", "🌡️", "Extremely overbought",
                 f"RSI-14 = {rsi:.1f}. Historically, readings above 80 precede near-term "
                 f"pullbacks. Avoid chasing; wait for a reset.")
        elif rsi > 74:
            flag("warning", "🌡️", "Overbought territory",
                 f"RSI-14 = {rsi:.1f}. Momentum may be stretched. Risk/reward skews toward "
                 f"a short-term pause or reversal.")
        elif rsi < 20:
            flag("danger", "🆘", "Deeply oversold / distress",
                 f"RSI-14 = {rsi:.1f}. Extreme selling — could signal fundamental distress "
                 f"or a capitulation low. Verify news catalysts before buying.")
        elif rsi < 28:
            flag("warning", "⬇️", "Oversold",
                 f"RSI-14 = {rsi:.1f}. Price has fallen sharply. "
                 f"May offer a bounce, but confirm trend reversal before entering.")

    # --- Trend flags ---
    if close is not None and price is not None:
        sma50  = _sma(close, 50)
        sma200 = _sma(close, 200)
        if sma50 is not None and sma200 is not None:
            if price < sma50 < sma200:
                flag("danger", "🐻", "Strong downtrend",
                     f"Price (${price:.2f}) < SMA-50 (${sma50:.2f}) < SMA-200 (${sma200:.2f}). "
                     f"All trend signals are bearish. Avoid bottom-fishing without confirmation.")
            elif price < sma200 and sma50 < sma200:
                flag("warning", "⚠️", "Below key moving averages",
                     f"Price and SMA-50 are both below SMA-200. "
                     f"Long-term momentum is negative.")

    # --- Valuation flags ---
    pe = metrics.get("peBasicExclExtraTTM")
    if pe is not None:
        pe = float(pe)
        if pe < 0:
            flag("warning", "💸", "Negative earnings",
                 f"Trailing P/E is negative (reported EPS loss). "
                 f"The company is not yet profitable on a trailing basis.")
        elif pe > 80:
            flag("danger", "💰", "Extreme valuation premium",
                 f"Trailing P/E = {pe:.1f}×. Priced for perfection — any earnings "
                 f"disappointment could trigger a sharp de-rating.")
        elif pe > 50:
            flag("warning", "💰", "Elevated valuation",
                 f"Trailing P/E = {pe:.1f}×. Well above market median. "
                 f"Growth expectations are high and already baked in.")

    # --- Earnings flags ---
    surprises = [
        float(e["surprisePercent"])
        for e in (earnings or [])
        if e.get("surprisePercent") is not None
    ]
    if surprises:
        miss_count = sum(1 for s in surprises if s < 0)
        if miss_count >= 3:
            flag("danger", "📊", "Persistent earnings misses",
                 f"Missed EPS estimates in {miss_count}/{len(surprises)} of the last "
                 f"{len(surprises)} quarters. Management guidance may lack credibility.")
        elif miss_count == 2 and len(surprises) >= 3:
            flag("warning", "📊", "Mixed earnings track record",
                 f"Missed EPS estimates in {miss_count}/{len(surprises)} recent quarters. "
                 f"Watch the next print closely.")

    # --- Analyst consensus flags ---
    if recommendations:
        latest = recommendations[0]
        sb = int(latest.get("strongBuy", 0))
        b  = int(latest.get("buy", 0))
        h  = int(latest.get("hold", 0))
        s  = int(latest.get("sell", 0))
        ss = int(latest.get("strongSell", 0))
        total = sb + b + h + s + ss
        if total > 0:
            bullish_ratio = (sb + b) / total
            if bullish_ratio < 0.20:
                flag("danger", "🎯", "Weak analyst support",
                     f"Only {bullish_ratio:.0%} of analysts rate this stock "
                     f"Buy or Strong Buy ({sb + b}/{total}). Broad analyst pessimism.")
            elif bullish_ratio < 0.35:
                flag("warning", "🎯", "Below-average analyst consensus",
                     f"Bullish analyst ratio = {bullish_ratio:.0%} ({sb + b}/{total}). "
                     f"Consensus leans cautious.")

    # --- Sentiment flags ---
    if sentiment_agg:
        net = float(sentiment_agg.get("net_score", 0))
        if net < -0.6:
            flag("danger", "📰", "Very negative news sentiment",
                 f"FinBERT net sentiment score = {net:+.2f}. "
                 f"Recent headlines are strongly negative — monitor for material developments.")
        elif net < -0.3:
            flag("warning", "📰", "Negative news flow",
                 f"FinBERT net sentiment score = {net:+.2f}. "
                 f"More negative than positive recent coverage.")

    # --- Composite factor score flags ---
    if composite_factor_score < 25:
        flag("danger", "🚨", "Multi-factor sell signal",
             f"Composite factor score = {composite_factor_score}/100. "
             f"The majority of quantitative factors are aligned negatively. "
             f"Review each factor before considering a position.")
    elif composite_factor_score > 85:
        flag("info", "🔔", "Euphoria risk — peak consensus",
             f"Composite factor score = {composite_factor_score}/100. "
             f"Almost all factors are maxed out. Historically, extreme bullish consensus "
             f"can precede mean-reversion. Manage position sizing.")

    return flags


# ---------------------------------------------------------------------------
# Risk level mapping
# ---------------------------------------------------------------------------

RISK_LEVELS = [
    (80, "Extreme",  "#cf2929"),
    (65, "High",     "#e05252"),
    (45, "Elevated", "#f0b429"),
    (25, "Moderate", "#4CAF50"),
    ( 0, "Low",      "#2da44e"),
]


def risk_level_color(risk_score: int) -> tuple[str, str]:
    """Return (level_label, hex_color) for a 0-100 risk score."""
    for threshold, label, color in RISK_LEVELS:
        if risk_score >= threshold:
            return label, color
    return "Low", "#2da44e"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_risk(
    quote: dict,
    financials: dict | None,
    close: "pd.Series | None",
    earnings: list,
    recommendations: list,
    sentiment_agg: dict | None,
    composite_factor_score: int,
) -> dict:
    """Compute risk score and flags from available data.

    Returns:
        risk_score          int 0-100  (higher = more risky)
        risk_level          str  ("Low" | "Moderate" | "Elevated" | "High" | "Extreme")
        risk_color          hex color string
        hv                  float | None  annualised HV %
        drawdown_pct        float | None  drawdown from 52-week high %
        flags               list[dict]   ordered by severity
    """
    price = float(quote.get("c", 0) or 0) or None

    vol_dim,  hv         = _dim_volatility(close)
    dd_dim,   drawdown   = _dim_drawdown(price, financials, close)
    sig_dim              = _dim_signal_risk(composite_factor_score)

    flags = _build_flags(
        close=close,
        price=price,
        financials=financials,
        earnings=earnings,
        recommendations=recommendations,
        sentiment_agg=sentiment_agg,
        composite_factor_score=composite_factor_score,
        hv=hv,
        drawdown_pct=drawdown,
    )

    # Flag count dimension: each flag adds 20 pts, capped at 100
    flag_dim = _clamp(len(flags) * 20)

    # Weighted composite risk score
    risk_score = _clamp(
        vol_dim  * 0.25
        + dd_dim * 0.25
        + sig_dim * 0.25
        + flag_dim * 0.25
    )

    risk_level, risk_color = risk_level_color(risk_score)

    # Sort flags: danger first, then warning, then info
    _order = {"danger": 0, "warning": 1, "info": 2}
    flags.sort(key=lambda f: _order.get(f["severity"], 99))

    return dict(
        risk_score=risk_score,
        risk_level=risk_level,
        risk_color=risk_color,
        hv=hv,
        drawdown_pct=drawdown,
        flags=flags,
    )
