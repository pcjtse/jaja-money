"""Options Flow Anomaly Detector.

Classifies options activity as bullish/bearish sweeps, earnings bets,
strangles, or neutral. Large directional sweeps (high vol vs OI, OTM,
near-expiry) often precede price moves and provide a leading signal.
"""

from __future__ import annotations

import math
from datetime import datetime

from src.core.log_setup import get_logger

log = get_logger(__name__)

FLOW_NEUTRAL = "NEUTRAL"
FLOW_BULLISH_SWEEP = "BULLISH_SWEEP"
FLOW_BEARISH_SWEEP = "BEARISH_SWEEP"
FLOW_EARNINGS_BET = "EARNINGS_BET"
FLOW_STRANGLE = "STRANGLE"


def classify_options_flow(
    chain_data: dict | None,
    current_price: float | None,
    days_to_earnings: int | None = None,
) -> dict:
    """Classify options flow direction and anomaly type.

    Parameters
    ----------
    chain_data      : output of FinnhubAPI.get_option_chain() or similar.
                      Expected keys: options (list), callVolume, putVolume,
                      putCallRatio, unusualActivity (list, optional).
    current_price   : current stock price for moneyness calculations
    days_to_earnings: if provided, used to detect earnings bets

    Returns
    -------
    dict with keys:
        flow_type (str): one of the FLOW_* constants
        call_volume (int)
        put_volume (int)
        put_call_ratio (float)
        unusual_strikes (list of dict): anomalous option rows
        iv_spike (bool): True if IV significantly above recent average
        score (int): 0-100 (>50 bullish, <50 bearish)
        label (str)
        detail (str)
    """
    if not chain_data:
        return _neutral(50, "No options data")

    call_vol = int(chain_data.get("callVolume") or 0)
    put_vol = int(chain_data.get("putVolume") or 0)
    pcr = chain_data.get("putCallRatio")
    if pcr is None and call_vol + put_vol > 0:
        pcr = put_vol / max(call_vol, 1)
    pcr = round(float(pcr or 1.0), 3)

    options = chain_data.get("options", [])

    unusual_strikes = _find_unusual_strikes(options, current_price)

    # Detect earnings bet: short-dated, high-vol, OTM calls AND puts
    earnings_bet = False
    if days_to_earnings is not None and days_to_earnings <= 14:
        short_dated_unusual = [
            s for s in unusual_strikes
            if s.get("days_to_expiry", 999) <= 14
        ]
        if len(short_dated_unusual) >= 2:
            call_unusual = sum(1 for s in short_dated_unusual if s["type"] == "call")
            put_unusual = sum(1 for s in short_dated_unusual if s["type"] == "put")
            if call_unusual >= 1 and put_unusual >= 1:
                earnings_bet = True

    # IV spike detection
    ivs = _collect_ivs(options)
    iv_spike = _detect_iv_spike(ivs)

    # Strangle: balanced unusual call AND put activity
    unusual_calls = [s for s in unusual_strikes if s["type"] == "call"]
    unusual_puts = [s for s in unusual_strikes if s["type"] == "put"]
    strangle = len(unusual_calls) >= 1 and len(unusual_puts) >= 1 and not earnings_bet

    # Determine flow type and score
    if earnings_bet:
        flow_type = FLOW_EARNINGS_BET
        score = 50
        label = "Earnings bet detected"
    elif strangle:
        flow_type = FLOW_STRANGLE
        score = 50
        label = "Strangle / straddle activity"
    elif pcr < 0.5 and unusual_calls:
        flow_type = FLOW_BULLISH_SWEEP
        score = _bullish_score(pcr, unusual_calls, iv_spike)
        label = "Bullish sweep — aggressive call buying"
    elif pcr > 1.5 and unusual_puts:
        flow_type = FLOW_BEARISH_SWEEP
        score = _bearish_score(pcr, unusual_puts, iv_spike)
        label = "Bearish sweep — elevated put buying"
    elif pcr < 0.7:
        flow_type = FLOW_BULLISH_SWEEP
        score = 65
        label = "Mild bullish options flow"
    elif pcr > 1.2:
        flow_type = FLOW_BEARISH_SWEEP
        score = 35
        label = "Mild bearish options flow"
    else:
        flow_type = FLOW_NEUTRAL
        score = 50
        label = "Neutral options flow"

    detail = (
        f"P/C Ratio: {pcr:.2f} | "
        f"Calls: {call_vol:,} | Puts: {put_vol:,} | "
        f"Unusual strikes: {len(unusual_strikes)}"
    )
    if iv_spike:
        detail += " | IV spike detected"

    return {
        "flow_type": flow_type,
        "call_volume": call_vol,
        "put_volume": put_vol,
        "put_call_ratio": pcr,
        "unusual_strikes": unusual_strikes[:10],
        "iv_spike": iv_spike,
        "score": score,
        "label": label,
        "detail": detail,
    }


def _find_unusual_strikes(options: list, current_price: float | None) -> list[dict]:
    """Identify strikes with volume > 3× open interest."""
    unusual = []
    for opt in options or []:
        oi = int(opt.get("openInterest") or opt.get("oi") or 0)
        vol = int(opt.get("volume") or opt.get("vol") or 0)
        if oi > 0 and vol >= 3 * oi and vol > 100:
            strike = opt.get("strike") or opt.get("strikePrice")
            expiry = opt.get("expiration") or opt.get("expiryDate", "")
            opt_type = str(opt.get("type", opt.get("side", ""))).lower()
            days_to_expiry = _days_to_expiry(expiry)
            moneyness = None
            if strike and current_price:
                moneyness = round(float(strike) / float(current_price) - 1, 4)
            unusual.append({
                "type": "call" if "call" in opt_type else "put",
                "strike": strike,
                "expiry": expiry,
                "volume": vol,
                "open_interest": oi,
                "vol_oi_ratio": round(vol / max(oi, 1), 1),
                "moneyness": moneyness,
                "days_to_expiry": days_to_expiry,
            })
    unusual.sort(key=lambda x: x["vol_oi_ratio"], reverse=True)
    return unusual


def _collect_ivs(options: list) -> list[float]:
    ivs = []
    for opt in options or []:
        iv = opt.get("impliedVolatility") or opt.get("iv")
        if iv is not None:
            try:
                ivs.append(float(iv))
            except (TypeError, ValueError):
                pass
    return ivs


def _detect_iv_spike(ivs: list[float], threshold_multiplier: float = 1.5) -> bool:
    if len(ivs) < 4:
        return False
    median_iv = sorted(ivs)[len(ivs) // 2]
    max_iv = max(ivs)
    return max_iv > threshold_multiplier * median_iv and median_iv > 0


def _days_to_expiry(expiry_str: str) -> int | None:
    if not expiry_str:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y%m%d"):
        try:
            exp_date = datetime.strptime(str(expiry_str)[:10], fmt)
            return max(0, (exp_date - datetime.utcnow()).days)
        except ValueError:
            continue
    return None


def _bullish_score(pcr: float, unusual_calls: list, iv_spike: bool) -> int:
    base = 70
    if pcr < 0.3:
        base += 12
    if len(unusual_calls) >= 3:
        base += 8
    if iv_spike:
        base += 5
    # OTM calls are more aggressive
    otm_calls = [c for c in unusual_calls if c.get("moneyness") and c["moneyness"] > 0.03]
    if otm_calls:
        base += 5
    return min(96, base)


def _bearish_score(pcr: float, unusual_puts: list, iv_spike: bool) -> int:
    base = 30
    if pcr > 2.0:
        base -= 12
    if len(unusual_puts) >= 3:
        base -= 8
    if iv_spike:
        base -= 5
    otm_puts = [p for p in unusual_puts if p.get("moneyness") and p["moneyness"] < -0.03]
    if otm_puts:
        base -= 5
    return max(4, base)


def _neutral(score: int, detail: str) -> dict:
    return {
        "flow_type": FLOW_NEUTRAL,
        "call_volume": 0,
        "put_volume": 0,
        "put_call_ratio": 1.0,
        "unusual_strikes": [],
        "iv_spike": False,
        "score": score,
        "label": "Neutral options flow",
        "detail": detail,
    }


def compute_gamma_exposure(
    chain_data: dict | None,
    current_price: float | None,
) -> dict:
    """Estimate net dealer gamma exposure and flag squeeze conditions.

    Positive gamma = dealers buy dips / sell rips (stabilizing).
    Negative gamma = dealers chase price (amplifying / squeeze risk).

    Returns
    -------
    dict with keys:
        net_gamma_pct (float | None): estimated net gamma as % of total
        gamma_condition (str): "positive" | "negative" | "neutral" | "unknown"
        squeeze_risk (bool)
        detail (str)
    """
    if not chain_data:
        return {"net_gamma_pct": None, "gamma_condition": "unknown", "squeeze_risk": False, "detail": "No data"}

    options = chain_data.get("options", [])
    if not options or current_price is None:
        return {"net_gamma_pct": None, "gamma_condition": "unknown", "squeeze_risk": False, "detail": "No options data"}

    call_gamma = 0.0
    put_gamma = 0.0

    for opt in options:
        oi = float(opt.get("openInterest") or 0)
        gamma_raw = opt.get("gamma")
        iv = float(opt.get("impliedVolatility") or 0)
        strike = opt.get("strike") or opt.get("strikePrice")
        opt_type = str(opt.get("type", opt.get("side", ""))).lower()

        if gamma_raw is not None:
            g = float(gamma_raw) * oi * 100
        elif iv > 0 and strike and current_price:
            # Rough gamma approximation (at-the-money)
            S, K = float(current_price), float(strike)
            g = _approx_gamma(S, K, iv) * oi * 100
        else:
            continue

        if "call" in opt_type:
            call_gamma += g
        else:
            put_gamma += g

    total = call_gamma + put_gamma
    if total == 0:
        return {"net_gamma_pct": None, "gamma_condition": "unknown", "squeeze_risk": False, "detail": "No gamma data"}

    net_gamma = call_gamma - put_gamma
    net_gamma_pct = round(net_gamma / total * 100, 1)

    if net_gamma_pct > 20:
        condition = "positive"
        squeeze_risk = False
    elif net_gamma_pct < -20:
        condition = "negative"
        squeeze_risk = True
    else:
        condition = "neutral"
        squeeze_risk = False

    return {
        "net_gamma_pct": net_gamma_pct,
        "gamma_condition": condition,
        "squeeze_risk": squeeze_risk,
        "detail": f"Net gamma: {net_gamma_pct:+.1f}% ({condition})",
    }


def _approx_gamma(S: float, K: float, iv: float, T: float = 0.1) -> float:
    """Very rough gamma approximation using Black-Scholes ATM formula."""
    if S <= 0 or iv <= 0 or T <= 0:
        return 0.0
    try:
        d1 = math.log(S / K) / (iv * math.sqrt(T)) + 0.5 * iv * math.sqrt(T)
        # Normal PDF approximation
        n_d1 = math.exp(-0.5 * d1 * d1) / math.sqrt(2 * math.pi)
        return n_d1 / (S * iv * math.sqrt(T))
    except (ValueError, ZeroDivisionError):
        return 0.0
