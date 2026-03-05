"""Portfolio suggestion engine.

Pure-Python module.  Derives position sizing, entry strategy, stop-loss levels,
and price targets from risk tolerance, investment horizon, the factor composite
score, the risk guardrail score, and optional price/volatility data.
No Streamlit imports.
"""

from __future__ import annotations

import math
import pandas as pd


# ---------------------------------------------------------------------------
# Public constants (used for UI dropdowns)
# ---------------------------------------------------------------------------

RISK_TOLERANCES = ["Conservative", "Moderate", "Aggressive"]

HORIZONS = [
    "Short-term  (< 1 year)",
    "Medium-term  (1 – 3 years)",
    "Long-term  (3+ years)",
]

_HORIZON_KEY = {
    HORIZONS[0]: "short",
    HORIZONS[1]: "medium",
    HORIZONS[2]: "long",
}

_TOLERANCE_KEY = {t: t.lower() for t in RISK_TOLERANCES}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _hist_vol(close: pd.Series, window: int = 20) -> float | None:
    if close is None or len(close) < window + 1:
        return None
    log_returns = (close / close.shift(1)).apply(math.log).dropna()
    return float(log_returns.tail(window).std()) * math.sqrt(252)  # annualised (ratio, not %)


def _rsi(close: pd.Series, length: int = 14) -> float | None:
    if close is None or len(close) < length + 1:
        return None
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / length, min_periods=length).mean()
    avg_loss = loss.ewm(alpha=1 / length, min_periods=length).mean()
    rs = avg_gain / avg_loss
    return float((100 - (100 / (1 + rs))).iloc[-1])


# ---------------------------------------------------------------------------
# Core suggestion logic
# ---------------------------------------------------------------------------

def suggest_position(
    risk_tolerance: str,
    horizon: str,
    composite_factor: int,
    risk_score: int,
    quote: dict,
    close: "pd.Series | None" = None,
) -> dict:
    """Return a full portfolio suggestion dict.

    Parameters
    ----------
    risk_tolerance : "Conservative" | "Moderate" | "Aggressive"
    horizon        : one of HORIZONS strings
    composite_factor : 0-100 factor score from factors.py
    risk_score     : 0-100 risk score from guardrails.py
    quote          : Finnhub quote dict (needs "c" for current price)
    close          : optional daily close pd.Series for HV / RSI

    Returns
    -------
    dict with keys: action, action_color, position_pct, position_label,
    entry_strategy, stop_price, stop_pct, target_1, target_2,
    risk_reward, rationale (list[str])
    """

    tol = _TOLERANCE_KEY.get(risk_tolerance, "moderate")
    hor = _HORIZON_KEY.get(horizon, "medium")
    price = float(quote.get("c", 0) or 0)

    # ----- 1. Action label -----
    if composite_factor >= 70 and risk_score < 45:
        action, action_color = "Buy",           "#2da44e"
    elif composite_factor >= 55 and risk_score < 65:
        action, action_color = "Accumulate",    "#4CAF50"
    elif composite_factor >= 45 and risk_score < 65:
        action, action_color = "Hold",          "#f0b429"
    elif composite_factor >= 30 and risk_score < 80:
        action, action_color = "Reduce",        "#e05252"
    else:
        action, action_color = "Avoid",         "#cf2929"

    # ----- 2. Position sizing -----
    base_max = {"conservative": 5.0, "moderate": 10.0, "aggressive": 20.0}[tol]

    factor_mult = (
        1.00 if composite_factor >= 70 else
        0.75 if composite_factor >= 55 else
        0.50 if composite_factor >= 45 else
        0.25 if composite_factor >= 30 else
        0.05
    )
    risk_mult = (
        1.00 if risk_score < 25 else
        0.85 if risk_score < 45 else
        0.65 if risk_score < 65 else
        0.35 if risk_score < 80 else
        0.10
    )
    horizon_mult = {"short": 0.70, "medium": 1.00, "long": 1.15}[hor]

    raw_pct = base_max * factor_mult * risk_mult * horizon_mult
    # Round to nearest 0.5, floor at 0, ceiling at base_max
    position_pct = max(0.0, min(base_max, round(raw_pct * 2) / 2))
    lo = max(0.0, position_pct - 1.0)
    hi = position_pct + 1.0
    position_label = f"{lo:.1f}–{hi:.1f}%"

    # ----- 3. Entry strategy -----
    rsi = _rsi(close) if close is not None else None
    if action == "Avoid":
        entry_strategy = "Do not initiate a new position until risk conditions improve."
    elif action == "Reduce":
        entry_strategy = "Trim existing holdings on any strength. Do not add."
    elif rsi is not None and rsi > 72:
        entry_strategy = (
            "Wait for an RSI reset (target < 60) or a pullback to SMA-50 "
            "before initiating. Momentum is stretched."
        )
    elif rsi is not None and rsi < 30:
        entry_strategy = (
            "Oversold territory — wait for price stabilisation and an RSI "
            "uptick above 35 before scaling in."
        )
    elif hor == "short":
        entry_strategy = (
            "Buy in a single tranche at market. Keep the holding period tight "
            "and respect the stop-loss strictly."
        )
    elif hor == "long":
        entry_strategy = (
            "Scale in across 3 tranches over 4–6 weeks to average cost. "
            "Use pullbacks to SMA-50 as preferred entry points."
        )
    else:
        entry_strategy = (
            "Initiate a half-position now; add the remainder on a 3–5% "
            "pullback or on positive earnings confirmation."
        )

    # ----- 4. Stop-loss -----
    stop_price: float | None = None
    stop_pct: float | None   = None

    hv_ratio = _hist_vol(close) if close is not None else None
    if price > 0 and hv_ratio is not None:
        # volatility-normalised stop: z-sigma move over 2-week window
        daily_vol = hv_ratio / math.sqrt(252)
        z_mult = {"conservative": 1.5, "moderate": 2.0, "aggressive": 2.5}[tol]
        stop_pct = daily_vol * math.sqrt(14) * z_mult * 100   # convert to %
        stop_pct = round(stop_pct, 1)
        stop_price = round(price * (1 - stop_pct / 100), 2)
    elif price > 0:
        # Fallback: fixed % stop
        fixed = {"conservative": 7.0, "moderate": 10.0, "aggressive": 14.0}[tol]
        stop_pct = fixed
        stop_price = round(price * (1 - fixed / 100), 2)

    # ----- 5. Price targets -----
    target_pcts = {
        "short":  (0.10, 0.18),
        "medium": (0.20, 0.35),
        "long":   (0.35, 0.60),
    }[hor]
    # Scale targets up for strong factors, down for weak
    t_scale = (
        1.15 if composite_factor >= 70 else
        1.00 if composite_factor >= 55 else
        0.80
    )
    target_1 = round(price * (1 + target_pcts[0] * t_scale), 2) if price > 0 else None
    target_2 = round(price * (1 + target_pcts[1] * t_scale), 2) if price > 0 else None

    # ----- 6. Risk / reward -----
    risk_reward: float | None = None
    if stop_pct and target_1 and price > 0:
        reward_pct = (target_1 / price - 1) * 100
        risk_reward = round(reward_pct / stop_pct, 2)

    # ----- 7. Rationale bullets -----
    rationale = []

    # Factor score context
    if composite_factor >= 70:
        rationale.append(f"Factor score {composite_factor}/100 — strong buy signal across most dimensions.")
    elif composite_factor >= 55:
        rationale.append(f"Factor score {composite_factor}/100 — moderate buy signal; majority of factors are positive.")
    elif composite_factor >= 45:
        rationale.append(f"Factor score {composite_factor}/100 — neutral; no strong directional bias from fundamentals/technicals.")
    else:
        rationale.append(f"Factor score {composite_factor}/100 — multiple factors are negative; unfavourable entry conditions.")

    # Risk context
    if risk_score < 25:
        rationale.append(f"Risk score {risk_score}/100 (Low) — volatility, drawdown, and flag conditions are all benign.")
    elif risk_score < 45:
        rationale.append(f"Risk score {risk_score}/100 (Moderate) — conditions are manageable with standard position sizing.")
    elif risk_score < 65:
        rationale.append(f"Risk score {risk_score}/100 (Elevated) — position size is reduced proportionally to compensate.")
    elif risk_score < 80:
        rationale.append(f"Risk score {risk_score}/100 (High) — only a minimal allocation is warranted if any.")
    else:
        rationale.append(f"Risk score {risk_score}/100 (Extreme) — avoid new positions until risk conditions improve.")

    # RSI context
    if rsi is not None:
        if rsi > 72:
            rationale.append(f"RSI-14 at {rsi:.0f} — overbought; entry timing is unfavourable for the short run.")
        elif rsi < 30:
            rationale.append(f"RSI-14 at {rsi:.0f} — oversold; wait for stabilisation before committing capital.")
        else:
            rationale.append(f"RSI-14 at {rsi:.0f} — within normal momentum range; timing is acceptable.")

    # Horizon context
    horizon_notes = {
        "short":  "Short horizon limits upside runway — strict stop discipline is essential.",
        "medium": "Medium horizon gives the thesis time to play out through one earnings cycle.",
        "long":   "Long horizon allows compounding if the fundamental thesis proves correct; scale in patiently.",
    }
    rationale.append(horizon_notes[hor])

    # Tolerance context
    tolerance_notes = {
        "conservative": f"Conservative risk profile caps max allocation at {base_max:.0f}% of portfolio.",
        "moderate":     f"Moderate risk profile allows up to {base_max:.0f}% of portfolio.",
        "aggressive":   f"Aggressive risk profile permits up to {base_max:.0f}% of portfolio for high-conviction ideas.",
    }
    rationale.append(tolerance_notes[tol])

    return dict(
        action=action,
        action_color=action_color,
        position_pct=position_pct,
        position_label=position_label,
        entry_strategy=entry_strategy,
        stop_price=stop_price,
        stop_pct=stop_pct,
        target_1=target_1,
        target_2=target_2,
        risk_reward=risk_reward,
        rationale=rationale,
    )
