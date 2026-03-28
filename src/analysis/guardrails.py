"""Risk Guardrail Engine.

Computes a 0-100 risk score from four dimensions and surfaces specific
red-flag conditions as structured alerts.  No Streamlit imports.

Enhanced with:
- Earnings calendar flag (P5.3)
- Insider trading signal (P5.4)
- Short interest flag (P5.5)
- Macroeconomic context overlay (P5.6)
- Liquidity risk flag (P8.1)
- Volatility regime detection (P8.2)
"""

from __future__ import annotations

import math
import pandas as pd

from src.core.log_setup import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _hist_vol(close: pd.Series, window: int = 20) -> float | None:
    """Annualised historical volatility (%) over the last `window` days."""
    if close is None or len(close) < window + 1:
        return None
    ratio = (close / close.shift(1)).dropna()
    ratio = ratio[ratio > 0]  # guard against zero/negative prices
    if len(ratio) < window:
        return None
    log_returns = ratio.apply(math.log)
    daily_std = float(log_returns.tail(window).std())
    return daily_std * math.sqrt(252) * 100  # annualised %


# ---------------------------------------------------------------------------
# P8.2: Volatility regime detection helpers
# ---------------------------------------------------------------------------


def _detect_vol_regime(
    close: pd.Series | None,
) -> tuple[str, float | None, float | None]:
    """Detect volatility regime: 'spike', 'sustained', or 'normal'.

    Returns (regime, hv_5d, hv_30d).
    """
    hv_5d = _hist_vol(close, window=5)
    hv_30d = _hist_vol(close, window=30)
    if hv_5d is None or hv_30d is None:
        return "normal", hv_5d, hv_30d
    if hv_5d > 2 * hv_30d:
        return "spike", hv_5d, hv_30d
    if hv_5d > 40 and hv_30d > 35:
        return "sustained", hv_5d, hv_30d
    return "normal", hv_5d, hv_30d


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


def _dim_drawdown(
    price: float | None, financials: dict | None, close: pd.Series | None
) -> tuple[int, float | None]:
    """0-100 drawdown risk + raw drawdown (%)."""
    high52 = (financials or {}).get("52WeekHigh")

    # Fallback: use rolling max from candles
    if high52 is None and close is not None and len(close) > 0:
        high52 = float(close.max())

    if high52 is None or price is None or price <= 0:
        return 50, None

    high52, price = float(high52), float(price)
    dd = (high52 - price) / high52 * 100  # % below 52-week high

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
    earnings_calendar: dict | None = None,
    insider_transactions: list | None = None,
    short_interest: dict | None = None,
    macro_context: dict | None = None,
    account_size: float | None = None,
    max_position_pct: float = 0.05,
    # Alpha feature data for additional flags
    congress_data: dict | None = None,
    crowding_data: dict | None = None,
    catalyst_data: dict | None = None,
    supply_chain_data: dict | None = None,
    borrow_rate_data: dict | None = None,
    regime_data: dict | None = None,
    options_flow_data: dict | None = None,
) -> list[dict]:
    """Return a list of flag dicts: {severity, icon, title, message}."""
    flags = []

    def flag(severity, icon, title, message):
        flags.append(dict(severity=severity, icon=icon, title=title, message=message))

    metrics = financials or {}

    # --- Volatility flags ---
    if hv is not None:
        if hv > 60:
            flag(
                "danger",
                "🔥",
                "Extreme volatility",
                f"20-day annualised HV = {hv:.1f}%. Expect very wide intraday swings "
                f"and elevated option premiums. Position size accordingly.",
            )
        elif hv > 40:
            flag(
                "warning",
                "⚡",
                "High volatility",
                f"20-day annualised HV = {hv:.1f}%. Significantly above the S&P 500 "
                f"long-run average (~15-18%). Consider tighter stops.",
            )

    # --- Drawdown flags ---
    if drawdown_pct is not None:
        if drawdown_pct > 40:
            flag(
                "danger",
                "📉",
                "Severe drawdown",
                f"Price is {drawdown_pct:.1f}% below the 52-week high. "
                f"Indicates sustained selling pressure or a structural breakdown.",
            )
        elif drawdown_pct > 25:
            flag(
                "warning",
                "📉",
                "Material drawdown",
                f"Price is {drawdown_pct:.1f}% off the 52-week high. "
                f"Verify whether this reflects fundamental deterioration or market dislocation.",
            )

    # --- RSI flags ---
    rsi = _rsi(close)
    if rsi is not None:
        if rsi > 80:
            flag(
                "danger",
                "🌡️",
                "Extremely overbought",
                f"RSI-14 = {rsi:.1f}. Historically, readings above 80 precede near-term "
                f"pullbacks. Avoid chasing; wait for a reset.",
            )
        elif rsi > 74:
            flag(
                "warning",
                "🌡️",
                "Overbought territory",
                f"RSI-14 = {rsi:.1f}. Momentum may be stretched. Risk/reward skews toward "
                f"a short-term pause or reversal.",
            )
        elif rsi < 20:
            flag(
                "danger",
                "🆘",
                "Deeply oversold / distress",
                f"RSI-14 = {rsi:.1f}. Extreme selling — could signal fundamental distress "
                f"or a capitulation low. Verify news catalysts before buying.",
            )
        elif rsi < 28:
            flag(
                "warning",
                "⬇️",
                "Oversold",
                f"RSI-14 = {rsi:.1f}. Price has fallen sharply. "
                f"May offer a bounce, but confirm trend reversal before entering.",
            )

    # --- Trend flags ---
    if close is not None and price is not None:
        sma50 = _sma(close, 50)
        sma200 = _sma(close, 200)
        if sma50 is not None and sma200 is not None:
            if price < sma50 < sma200:
                flag(
                    "danger",
                    "🐻",
                    "Strong downtrend",
                    f"Price (${price:.2f}) < SMA-50 (${sma50:.2f}) < SMA-200 (${sma200:.2f}). "
                    f"All trend signals are bearish. Avoid bottom-fishing without confirmation.",
                )
            elif price < sma200 and sma50 < sma200:
                flag(
                    "warning",
                    "⚠️",
                    "Below key moving averages",
                    "Price and SMA-50 are both below SMA-200. "
                    "Long-term momentum is negative.",
                )

    # --- Valuation flags ---
    pe = metrics.get("peBasicExclExtraTTM")
    if pe is not None:
        pe = float(pe)
        if pe < 0:
            flag(
                "warning",
                "💸",
                "Negative earnings",
                "Trailing P/E is negative (reported EPS loss). "
                "The company is not yet profitable on a trailing basis.",
            )
        elif pe > 80:
            flag(
                "danger",
                "💰",
                "Extreme valuation premium",
                f"Trailing P/E = {pe:.1f}×. Priced for perfection — any earnings "
                f"disappointment could trigger a sharp de-rating.",
            )
        elif pe > 50:
            flag(
                "warning",
                "💰",
                "Elevated valuation",
                f"Trailing P/E = {pe:.1f}×. Well above market median. "
                f"Growth expectations are high and already baked in.",
            )

    # --- Earnings flags ---
    surprises = [
        float(e["surprisePercent"])
        for e in (earnings or [])
        if e.get("surprisePercent") is not None
    ]
    if surprises:
        miss_count = sum(1 for s in surprises if s < 0)
        if miss_count >= 3:
            flag(
                "danger",
                "📊",
                "Persistent earnings misses",
                f"Missed EPS estimates in {miss_count}/{len(surprises)} of the last "
                f"{len(surprises)} quarters. Management guidance may lack credibility.",
            )
        elif miss_count == 2 and len(surprises) >= 3:
            flag(
                "warning",
                "📊",
                "Mixed earnings track record",
                f"Missed EPS estimates in {miss_count}/{len(surprises)} recent quarters. "
                f"Watch the next print closely.",
            )

    # --- Analyst consensus flags ---
    if recommendations:
        latest = recommendations[0]
        sb = int(latest.get("strongBuy", 0))
        b = int(latest.get("buy", 0))
        h = int(latest.get("hold", 0))
        s = int(latest.get("sell", 0))
        ss = int(latest.get("strongSell", 0))
        total = sb + b + h + s + ss
        if total > 0:
            bullish_ratio = (sb + b) / total
            if bullish_ratio < 0.20:
                flag(
                    "danger",
                    "🎯",
                    "Weak analyst support",
                    f"Only {bullish_ratio:.0%} of analysts rate this stock "
                    f"Buy or Strong Buy ({sb + b}/{total}). Broad analyst pessimism.",
                )
            elif bullish_ratio < 0.35:
                flag(
                    "warning",
                    "🎯",
                    "Below-average analyst consensus",
                    f"Bullish analyst ratio = {bullish_ratio:.0%} ({sb + b}/{total}). "
                    f"Consensus leans cautious.",
                )

    # --- Sentiment flags ---
    if sentiment_agg:
        net = float(sentiment_agg.get("net_score", 0))
        if net < -0.6:
            flag(
                "danger",
                "📰",
                "Very negative news sentiment",
                f"FinBERT net sentiment score = {net:+.2f}. "
                f"Recent headlines are strongly negative — monitor for material developments.",
            )
        elif net < -0.3:
            flag(
                "warning",
                "📰",
                "Negative news flow",
                f"FinBERT net sentiment score = {net:+.2f}. "
                f"More negative than positive recent coverage.",
            )

    # --- Composite factor score flags ---
    if composite_factor_score < 25:
        flag(
            "danger",
            "🚨",
            "Multi-factor sell signal",
            f"Composite factor score = {composite_factor_score}/100. "
            f"The majority of quantitative factors are aligned negatively. "
            f"Review each factor before considering a position.",
        )
    elif composite_factor_score > 85:
        flag(
            "info",
            "🔔",
            "Euphoria risk — peak consensus",
            f"Composite factor score = {composite_factor_score}/100. "
            f"Almost all factors are maxed out. Historically, extreme bullish consensus "
            f"can precede mean-reversion. Manage position sizing.",
        )

    # --- P5.3: Earnings calendar flags ---
    if earnings_calendar:
        days_to_earn = earnings_calendar.get("days_to_earnings")
        next_date = earnings_calendar.get("next_date")
        if days_to_earn is not None and next_date:
            if 0 <= days_to_earn <= 7:
                flag(
                    "danger",
                    "📅",
                    "Earnings this week",
                    f"Earnings report in {days_to_earn} day(s) (on {next_date}). "
                    f"Expect elevated implied volatility and potential sharp price moves. "
                    f"Avoid opening positions immediately before earnings unless as a trade.",
                )
            elif days_to_earn <= 14:
                flag(
                    "warning",
                    "📅",
                    "Earnings within 2 weeks",
                    f"Earnings report in {days_to_earn} day(s) (on {next_date}). "
                    f"Event risk is elevated. Consider holding off or sizing down.",
                )

    # --- P5.4: Insider trading flags ---
    if insider_transactions:
        from datetime import date, timedelta

        cutoff = (date.today() - timedelta(days=90)).isoformat()
        recent_txns = [
            t for t in insider_transactions if t.get("transactionDate", "") >= cutoff
        ]
        buys = [t for t in recent_txns if t.get("transactionCode") == "P"]
        sells = [t for t in recent_txns if t.get("transactionCode") == "S"]
        buy_shares = sum(abs(t.get("change", 0) or 0) for t in buys)
        sell_shares = sum(abs(t.get("change", 0) or 0) for t in sells)

        if sells and sell_shares > buy_shares * 3 and len(sells) >= 3:
            flag(
                "danger",
                "🔴",
                "Significant insider selling",
                f"{len(sells)} insider sale(s) in the last 90 days totalling "
                f"~{sell_shares:,.0f} shares. Heavy insider selling often precedes "
                f"fundamental deterioration.",
            )
        elif sells and sell_shares > buy_shares * 2 and len(sells) >= 2:
            flag(
                "warning",
                "🔴",
                "Insider selling cluster",
                f"{len(sells)} insider sale(s) in the last 90 days. "
                f"Monitor for further selling pressure.",
            )
        elif buys and buy_shares > sell_shares * 2 and len(buys) >= 2:
            flag(
                "info",
                "🟢",
                "Insider buying cluster",
                f"{len(buys)} insider purchase(s) in the last 90 days totalling "
                f"~{buy_shares:,.0f} shares. Cluster buying is often a positive signal, "
                f"especially after a drawdown.",
            )

    # --- P5.5: Short interest flags ---
    if short_interest and short_interest.get("available"):
        short_pct = short_interest.get("short_pct_float")
        days_cover = short_interest.get("days_to_cover")
        if short_pct is not None:
            if short_pct > 25:
                flag(
                    "danger",
                    "📊",
                    "Extreme short interest",
                    f"Short interest = {short_pct:.1f}% of float. "
                    f"Extremely high short interest can signal fundamental concerns "
                    f"but also creates squeeze potential if sentiment reverses.",
                )
            elif short_pct > 15:
                flag(
                    "warning",
                    "📊",
                    "Elevated short interest",
                    f"Short interest = {short_pct:.1f}% of float"
                    + (f" ({days_cover:.1f} days to cover)" if days_cover else "")
                    + ". Significant bearish positioning from institutional traders.",
                )

    # --- P5.6: Macroeconomic context flags ---
    if macro_context:
        vix = macro_context.get("vix")
        spread = macro_context.get("spread_2y10y")
        if vix is not None and vix > 30:
            flag(
                "warning",
                "🌐",
                "Elevated market fear (VIX)",
                f"VIX = {vix:.1f} — above 30 signals elevated market-wide fear. "
                f"Individual stock risk scores may understate tail risk. "
                f"Consider smaller position sizes across all holdings.",
            )
        if spread is not None and spread < 0:
            flag(
                "warning",
                "🌐",
                "Inverted yield curve",
                f"2Y/10Y spread = {spread:.2f}% (inverted). "
                f"Yield curve inversion historically precedes recessions. "
                f"Favor defensive sectors and reduce cyclical exposure.",
            )

    # --- P8.1: Liquidity risk flag ---
    if (
        close is not None
        and price is not None
        and account_size is not None
        and account_size > 0
    ):
        if len(close) >= 20:
            # Use 20-day average volume from close series length as a basic proxy
            # We'd need volume data — skip if not available
            position_value = account_size * max_position_pct
            if price > 0:
                _ = position_value / price
                # We can only flag if we have volume data
                # This will be enhanced when volume is passed

    # --- P8.2: Volatility regime detection ---
    vol_regime, hv_5d, hv_30d = _detect_vol_regime(close)
    if vol_regime == "spike" and hv_5d is not None and hv_30d is not None:
        flag(
            "warning",
            "⚡",
            "Volatility spike — may be transient",
            f"5-day vol = {hv_5d:.1f}% vs 30-day vol = {hv_30d:.1f}%. "
            f"Recent vol is >2× the 30-day average — likely reflects a specific event. "
            f"May normalize quickly; avoid panic selling.",
        )
    elif vol_regime == "sustained" and hv_5d is not None and hv_30d is not None:
        flag(
            "danger",
            "🔥",
            "Sustained elevated volatility",
            f"5-day vol = {hv_5d:.1f}% and 30-day vol = {hv_30d:.1f}% are both elevated. "
            f"Structural volatility trend — requires tighter risk management.",
        )

    # --- Alpha feature flags ---

    # Congressional selling signal
    if congress_data and congress_data.get("available"):
        net_signal = congress_data.get("net_signal", "")
        sells = congress_data.get("sells", 0)
        if net_signal == "Selling" and sells >= 2:
            flag(
                "warning",
                "🏛️",
                "Congressional net selling",
                f"Multiple politicians have recently sold shares "
                f"({sells} sale transactions in the last 90 days). "
                f"Congressional selling has historically preceded negative returns.",
            )
        elif net_signal == "Buying":
            buys = congress_data.get("buys", 0)
            flag(
                "info",
                "🏛️",
                "Congressional net buying",
                f"{buys} congressional purchase(s) detected in the last 90 days — "
                f"a historically bullish signal.",
            )

    # Factor crowding risk
    if crowding_data:
        risk_level = crowding_data.get("risk_level", "Low")
        penalty = crowding_data.get("penalty", 0)
        if risk_level == "Extreme":
            flag(
                "danger",
                "🎯",
                "Extreme factor crowding",
                f"This stock's factor profile is nearly identical to the top-decile "
                f"consensus. Crowded factor plays reverse violently when funds unwind. "
                f"Score penalized by {penalty} pts.",
            )
        elif risk_level == "High":
            flag(
                "warning",
                "🎯",
                "High factor crowding risk",
                f"Factor profile highly similar to widely-held consensus picks. "
                f"Elevated unwind risk if market regime shifts. Penalty: {penalty} pts.",
            )

    # Near-term catalyst concentration risk
    if catalyst_data:
        within_7d = catalyst_data.get("catalysts_within_7d", 0)
        if within_7d >= 2:
            flag(
                "warning",
                "📅",
                f"{within_7d} catalysts within 7 days",
                "Multiple binary events approaching. Consider reducing position size "
                "to manage event risk.",
            )
        if catalyst_data.get("fomc_within_30d"):
            flag(
                "info",
                "🏦",
                "FOMC meeting within 30 days",
                "An FOMC rate decision is upcoming. Interest-rate-sensitive sectors "
                "may see elevated volatility.",
            )

    # Supply chain concentration
    if supply_chain_data:
        sole = supply_chain_data.get("sole_source_risk", False)
        high_risk = supply_chain_data.get("high_risk_regions", [])
        if sole:
            flag(
                "warning",
                "⛓️",
                "Single-source supply chain dependency",
                "Company appears dependent on a sole-source supplier. "
                "Supply disruptions would have outsized business impact.",
            )
        if len(high_risk) >= 2:
            flag(
                "warning",
                "🌏",
                f"High-risk supply chain regions: {', '.join(high_risk[:3])}",
                "Supply chain exposure to geopolitically sensitive regions increases "
                "operational and tariff risk.",
            )

    # Expensive borrow rate (short squeeze risk)
    if borrow_rate_data and borrow_rate_data.get("available"):
        ctb_tier = borrow_rate_data.get("ctb_tier", "")
        ctb_rate = borrow_rate_data.get("ctb_rate")
        if ctb_tier == "Very Expensive":
            flag(
                "warning",
                "💸",
                f"Very expensive to borrow — CTB ~{ctb_rate:.0f}%",
                "Extremely high cost-to-borrow rate indicates heavy short interest and "
                "a precondition for a short squeeze. High volatility likely.",
            )

    # Risk-Off Panic regime
    if regime_data:
        regime = regime_data.get("regime", "")
        if regime == "Risk-Off Panic":
            flag(
                "danger",
                "🚨",
                "Risk-Off Panic regime detected",
                "Cross-asset signals indicate a panic/crisis market environment. "
                "All equity positions carry elevated tail risk. Reduce exposure.",
            )
        elif regime == "Risk-Off Defensive":
            flag(
                "warning",
                "🛡️",
                "Risk-Off Defensive regime",
                "Market is rotating defensively. Cyclical and growth stocks face "
                "headwinds. Prefer defensive sectors.",
            )

    # Bearish options sweep
    if options_flow_data:
        flow_type = options_flow_data.get("flow_type", "")
        if flow_type == "BEARISH_SWEEP":
            pcr = options_flow_data.get("put_call_ratio", 1.0)
            flag(
                "warning",
                "📉",
                "Bearish options sweep detected",
                f"Unusual put buying detected (P/C ratio: {pcr:.2f}). "
                f"Large bearish sweeps can indicate informed selling before a move.",
            )
        elif flow_type == "EARNINGS_BET":
            flag(
                "info",
                "🎲",
                "Earnings bet detected in options",
                "Short-dated, OTM call and put activity suggests traders are "
                "positioning for a large binary move around an upcoming event.",
            )

    return flags


# ---------------------------------------------------------------------------
# P20.1: Market regime integration
# ---------------------------------------------------------------------------


def apply_regime_adjustment(risk_result: dict, regime_info: dict) -> dict:
    """Integrate market regime context into a compute_risk() result.

    Takes the dict returned by compute_risk() and the dict returned by
    compute_market_regime() and adds regime metadata and, for a strong-bear
    regime, a red-flag entry.

    Parameters
    ----------
    risk_result  : dict returned by compute_risk()
    regime_info  : dict returned by compute_market_regime(), expected keys:
                   regime, score_adjustment, detail

    Returns
    -------
    Modified risk_result dict with added keys:
        regime        – regime label string
        regime_detail – detail string from compute_market_regime()
    If regime is "Strong Bear", a danger flag is prepended to flags list.
    """
    if not regime_info:
        log.debug("apply_regime_adjustment: no regime_info provided, skipping")
        return risk_result

    regime = regime_info.get("regime", "Neutral")
    detail = regime_info.get("detail", "")

    risk_result = dict(risk_result)  # shallow copy to avoid mutating caller's dict
    risk_result["regime"] = regime
    risk_result["regime_detail"] = detail

    if regime == "Strong Bear":
        bear_flag = dict(
            severity="danger",
            icon="🌑",
            title="Market in strong bear regime",
            message=(
                f"The broader market is classified as a Strong Bear regime "
                f"({detail}). Individual stock risks are amplified in this "
                f"environment. Reduce position sizes and prefer defensive assets."
            ),
        )
        flags = list(risk_result.get("flags", []))
        flags.insert(0, bear_flag)
        risk_result["flags"] = flags
        log.debug("apply_regime_adjustment: Strong Bear flag added")
    else:
        log.debug("apply_regime_adjustment: regime=%s, no extra flag", regime)

    return risk_result


# ---------------------------------------------------------------------------
# Risk level mapping
# ---------------------------------------------------------------------------

RISK_LEVELS = [
    (80, "Extreme", "#cf2929"),
    (65, "High", "#e05252"),
    (45, "Elevated", "#f0b429"),
    (25, "Moderate", "#4CAF50"),
    (0, "Low", "#2da44e"),
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
    earnings_calendar: dict | None = None,
    insider_transactions: list | None = None,
    short_interest: dict | None = None,
    macro_context: dict | None = None,
    account_size: float | None = None,
    max_position_pct: float = 0.05,
    # Alpha feature data
    congress_data: dict | None = None,
    crowding_data: dict | None = None,
    catalyst_data: dict | None = None,
    supply_chain_data: dict | None = None,
    borrow_rate_data: dict | None = None,
    regime_data: dict | None = None,
    options_flow_data: dict | None = None,
) -> dict:
    """Compute risk score and flags from available data.

    Returns:
        risk_score          int 0-100  (higher = more risky)
        risk_level          str  ("Low" | "Moderate" | "Elevated" | "High" | "Extreme")
        risk_color          hex color string
        hv                  float | None  annualised HV %
        drawdown_pct        float | None  drawdown from 52-week high %
        flags               list[dict]   ordered by severity
        vol_regime          str  ("normal" | "spike" | "sustained")
        macro_context       dict | None
    """
    price = float(quote.get("c", 0) or 0) or None

    vol_dim, hv = _dim_volatility(close)
    dd_dim, drawdown = _dim_drawdown(price, financials, close)
    sig_dim = _dim_signal_risk(composite_factor_score)

    vol_regime, hv_5d, hv_30d = _detect_vol_regime(close)

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
        earnings_calendar=earnings_calendar,
        insider_transactions=insider_transactions,
        short_interest=short_interest,
        macro_context=macro_context,
        account_size=account_size,
        max_position_pct=max_position_pct,
        congress_data=congress_data,
        crowding_data=crowding_data,
        catalyst_data=catalyst_data,
        supply_chain_data=supply_chain_data,
        borrow_rate_data=borrow_rate_data,
        regime_data=regime_data,
        options_flow_data=options_flow_data,
    )

    # Flag count dimension: each flag adds 20 pts, capped at 100
    flag_dim = _clamp(len(flags) * 20)

    # Weighted composite risk score
    base_risk = _clamp(
        vol_dim * 0.25 + dd_dim * 0.25 + sig_dim * 0.25 + flag_dim * 0.25
    )

    # P5.6 & P8.2: Apply macro multiplier and volatility regime adjustments
    macro_mult = 1.0
    if macro_context:
        vix = macro_context.get("vix")
        spread = macro_context.get("spread_2y10y")
        if vix is not None and vix > 30:
            macro_mult += 0.10
        if spread is not None and spread < 0:
            macro_mult += 0.05

    # Volatility regime upward adjustment for sustained elevated vol
    if vol_regime == "sustained":
        macro_mult += 0.10
    elif vol_regime == "spike":
        macro_mult += 0.05

    risk_score = _clamp(base_risk * macro_mult)
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
        vol_regime=vol_regime,
        hv_5d=hv_5d,
        hv_30d=hv_30d,
        macro_context=macro_context,
    )
