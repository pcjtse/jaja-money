"""Options chain analysis, IV surface, unusual flow, and hedging suggestions (P15.1, P16.3, P17.4).

Extended with:
- P26.1: Volatility Risk Premium (VRP) computation
- P26.2: IV Rank and IV Percentile
"""

from __future__ import annotations

import math

from log_setup import get_logger

log = get_logger(__name__)


def build_iv_surface(chain_data: dict, current_price: float) -> dict:
    """Build IV surface data from options chain.

    Parameters
    ----------
    chain_data:
        Raw options chain dict as returned by FinnhubAPI.get_option_chain().
        Expected structure: {"data": [{"expirationDate": str, "options": {"CALL": [...], "PUT": [...]}}]}
    current_price:
        Current stock price used to label moneyness.

    Returns
    -------
    dict with keys:
        available (bool): False if data insufficient to build surface.
        surface (list of dict): Each entry has strike, expiry, iv, type.
        expirations (list of str): Sorted list of expiration date strings.
    """
    if not chain_data or not chain_data.get("data"):
        return {"available": False, "surface": [], "expirations": []}

    expirations_raw = chain_data["data"]
    if not expirations_raw:
        return {"available": False, "surface": [], "expirations": []}

    surface = []
    expiry_dates = []

    for expiry_block in expirations_raw:
        exp_date = expiry_block.get("expirationDate", "")
        if not exp_date:
            continue
        expiry_dates.append(exp_date)
        options_map = expiry_block.get("options", {})

        for opt_type, option_list in options_map.items():
            if not isinstance(option_list, list):
                continue
            for opt in option_list:
                strike = opt.get("strike")
                iv = opt.get("impliedVolatility")
                if strike is None or iv is None or iv <= 0:
                    continue
                surface.append(
                    {
                        "strike": float(strike),
                        "expiry": exp_date,
                        "iv": round(float(iv) * 100, 2),  # convert to percentage
                        "type": opt_type,
                    }
                )

    if not surface:
        return {"available": False, "surface": [], "expirations": []}

    expiry_dates_sorted = sorted(set(expiry_dates))
    return {
        "available": True,
        "surface": surface,
        "expirations": expiry_dates_sorted,
    }


def compute_options_metrics(chain_data: dict, current_price: float) -> dict:
    """Compute extended options metrics from chain data.

    Parameters
    ----------
    chain_data:
        Raw options chain dict as returned by FinnhubAPI.get_option_chain().
    current_price:
        Current stock price.

    Returns
    -------
    dict with keys:
        available (bool)
        put_call_ratio (float|None): Total put OI / total call OI.
        max_pain (float|None): Strike where total option holders lose the most.
        avg_iv_pct (float|None): Average implied volatility across all options (%).
        atm_iv_call (float|None): IV of nearest ATM call (%).
        atm_iv_put (float|None): IV of nearest ATM put (%).
        atm_straddle_cost (float|None): ATM call ask + ATM put ask.
        implied_move_pct (float|None): atm_straddle_cost / current_price * 100.
        unusual_flows (list of dict): Options with volume > 3x open interest.
        total_call_oi (int): Total call open interest across all expirations.
        total_put_oi (int): Total put open interest across all expirations.
    """
    empty = {
        "available": False,
        "put_call_ratio": None,
        "max_pain": None,
        "avg_iv_pct": None,
        "atm_iv_call": None,
        "atm_iv_put": None,
        "atm_straddle_cost": None,
        "implied_move_pct": None,
        "unusual_flows": [],
        "total_call_oi": 0,
        "total_put_oi": 0,
    }

    if not chain_data or not chain_data.get("data"):
        return empty

    expirations_raw = chain_data["data"]
    if not expirations_raw:
        return empty

    # Aggregate across all expirations
    all_calls: list[dict] = []
    all_puts: list[dict] = []

    for expiry_block in expirations_raw:
        exp_date = expiry_block.get("expirationDate", "")
        options_map = expiry_block.get("options", {})
        for opt in options_map.get("CALL", []):
            opt["_expiry"] = exp_date
            opt["_type"] = "CALL"
            all_calls.append(opt)
        for opt in options_map.get("PUT", []):
            opt["_expiry"] = exp_date
            opt["_type"] = "PUT"
            all_puts.append(opt)

    if not all_calls and not all_puts:
        return empty

    # Totals
    total_call_oi = sum(int(c.get("openInterest", 0) or 0) for c in all_calls)
    total_put_oi = sum(int(p.get("openInterest", 0) or 0) for p in all_puts)
    put_call_ratio = (total_put_oi / total_call_oi) if total_call_oi > 0 else None

    # Average IV across all options
    all_ivs = [
        float(o.get("impliedVolatility", 0) or 0)
        for o in (all_calls + all_puts)
        if o.get("impliedVolatility") and float(o["impliedVolatility"]) > 0
    ]
    avg_iv_pct = round(sum(all_ivs) / len(all_ivs) * 100, 1) if all_ivs else None

    # ATM options from nearest expiry
    nearest_block = expirations_raw[0]
    nearest_options = nearest_block.get("options", {})
    nearest_calls = nearest_options.get("CALL", [])
    nearest_puts = nearest_options.get("PUT", [])

    atm_iv_call = None
    atm_iv_put = None
    atm_straddle_cost = None
    implied_move_pct = None

    if nearest_calls and current_price > 0:
        # Find nearest ATM call
        atm_call = min(
            (c for c in nearest_calls if c.get("strike") is not None),
            key=lambda c: abs(float(c["strike"]) - current_price),
            default=None,
        )
        if atm_call:
            iv_val = atm_call.get("impliedVolatility")
            if iv_val:
                atm_iv_call = round(float(iv_val) * 100, 2)

    if nearest_puts and current_price > 0:
        atm_put = min(
            (p for p in nearest_puts if p.get("strike") is not None),
            key=lambda p: abs(float(p["strike"]) - current_price),
            default=None,
        )
        if atm_put:
            iv_val = atm_put.get("impliedVolatility")
            if iv_val:
                atm_iv_put = round(float(iv_val) * 100, 2)

    # ATM straddle cost = ATM call ask + ATM put ask
    try:
        if nearest_calls and nearest_puts and current_price > 0:
            atm_call = min(
                (c for c in nearest_calls if c.get("strike") is not None),
                key=lambda c: abs(float(c["strike"]) - current_price),
                default=None,
            )
            atm_put = min(
                (p for p in nearest_puts if p.get("strike") is not None),
                key=lambda p: abs(float(p["strike"]) - current_price),
                default=None,
            )
            if atm_call and atm_put:
                call_ask = float(
                    atm_call.get("ask", 0) or atm_call.get("lastPrice", 0) or 0
                )
                put_ask = float(
                    atm_put.get("ask", 0) or atm_put.get("lastPrice", 0) or 0
                )
                if call_ask > 0 and put_ask > 0:
                    atm_straddle_cost = round(call_ask + put_ask, 2)
                    implied_move_pct = round(atm_straddle_cost / current_price * 100, 2)
    except Exception as exc:
        log.warning("ATM straddle calculation failed: %s", exc)

    # Max pain calculation:
    # For each strike, compute total dollar loss to option holders if price expires at that strike.
    # Call holders lose when price < strike (intrinsic = 0), put holders lose when price > strike.
    # Total loss at a given expiry price = sum of (OI * max(0, call_strike - expiry_price)) for calls
    #                                    + sum of (OI * max(0, expiry_price - put_strike)) for puts
    # Max pain = strike that minimizes total value of all options (i.e., where holders lose most).
    max_pain = None
    try:
        # Collect all unique strikes
        all_strikes = set()
        for o in all_calls + all_puts:
            s = o.get("strike")
            if s is not None:
                all_strikes.add(float(s))

        if all_strikes:
            min_total_value = None
            for test_price in sorted(all_strikes):
                total_value = 0.0
                # Call holders gain when test_price > call_strike
                for c in all_calls:
                    strike = c.get("strike")
                    oi = int(c.get("openInterest", 0) or 0)
                    if strike is not None and oi > 0:
                        total_value += oi * max(0.0, test_price - float(strike))
                # Put holders gain when test_price < put_strike
                for p in all_puts:
                    strike = p.get("strike")
                    oi = int(p.get("openInterest", 0) or 0)
                    if strike is not None and oi > 0:
                        total_value += oi * max(0.0, float(strike) - test_price)

                if min_total_value is None or total_value < min_total_value:
                    min_total_value = total_value
                    max_pain = test_price
    except Exception as exc:
        log.warning("Max pain calculation failed: %s", exc)

    # Unusual flows: volume > 3x open interest
    unusual_flows = []
    try:
        for opt in all_calls + all_puts:
            volume = int(opt.get("volume", 0) or 0)
            oi = int(opt.get("openInterest", 0) or 0)
            if oi > 0 and volume > 3 * oi and volume > 100:
                ratio = round(volume / oi, 2)
                strike = opt.get("strike")
                expiry = opt.get("_expiry", "")
                opt_type = opt.get("_type", "")
                # Determine direction: calls = bullish, puts = bearish
                direction = "bullish" if opt_type == "CALL" else "bearish"
                unusual_flows.append(
                    {
                        "strike": float(strike) if strike is not None else None,
                        "expiry": expiry,
                        "type": opt_type,
                        "volume": volume,
                        "open_interest": oi,
                        "volume_oi_ratio": ratio,
                        "direction": direction,
                    }
                )
        # Sort by ratio descending
        unusual_flows.sort(key=lambda x: x["volume_oi_ratio"], reverse=True)
    except Exception as exc:
        log.warning("Unusual flow detection failed: %s", exc)

    return {
        "available": True,
        "put_call_ratio": round(put_call_ratio, 3)
        if put_call_ratio is not None
        else None,
        "max_pain": max_pain,
        "avg_iv_pct": avg_iv_pct,
        "atm_iv_call": atm_iv_call,
        "atm_iv_put": atm_iv_put,
        "atm_straddle_cost": atm_straddle_cost,
        "implied_move_pct": implied_move_pct,
        "unusual_flows": unusual_flows,
        "total_call_oi": total_call_oi,
        "total_put_oi": total_put_oi,
    }


def compute_hedge_suggestions(
    current_price: float,
    chain_data: dict,
    position_value: float = 10_000.0,
) -> dict:
    """Compute protective put and zero-cost collar hedging suggestions.

    Parameters
    ----------
    current_price:
        Current stock price.
    chain_data:
        Raw options chain dict as returned by FinnhubAPI.get_option_chain().
    position_value:
        Total dollar value of the position to hedge (default $10,000).

    Returns
    -------
    dict with keys:
        available (bool): False if insufficient options data.
        protective_put (dict):
            strike (float), expiry (str), cost_per_share (float),
            cost_pct_position (float), breakeven (float), max_loss_pct (float).
        collar (dict):
            put_strike (float), call_strike (float), expiry (str),
            net_cost_per_share (float), description (str).
    """
    empty = {"available": False, "protective_put": {}, "collar": {}}

    if not chain_data or not chain_data.get("data") or current_price <= 0:
        return empty

    expirations_raw = chain_data["data"]
    if not expirations_raw:
        return empty

    # Use the second nearest expiry if available (30-60 days), else nearest
    target_block = (
        expirations_raw[1] if len(expirations_raw) > 1 else expirations_raw[0]
    )
    exp_date = target_block.get("expirationDate", "")
    options_map = target_block.get("options", {})
    puts = options_map.get("PUT", [])
    calls = options_map.get("CALL", [])

    if not puts or not calls:
        return empty

    # Filter to options with valid strikes and prices
    valid_puts = [
        p
        for p in puts
        if p.get("strike") is not None and (p.get("ask") or p.get("lastPrice"))
    ]
    valid_calls = [
        c
        for c in calls
        if c.get("strike") is not None and (c.get("ask") or c.get("lastPrice"))
    ]

    if not valid_puts:
        return empty

    protective_put: dict = {}
    collar: dict = {}

    try:
        # Protective put: ~5% OTM put (strike ~95% of current price)
        target_put_strike = current_price * 0.95
        best_put = min(
            valid_puts,
            key=lambda p: abs(float(p["strike"]) - target_put_strike),
        )
        put_strike = float(best_put["strike"])
        put_cost = float(best_put.get("ask") or best_put.get("lastPrice") or 0)

        if put_cost > 0:
            shares = position_value / current_price if current_price > 0 else 0
            total_put_cost = put_cost * shares
            cost_pct = (
                (total_put_cost / position_value * 100) if position_value > 0 else 0
            )
            breakeven = current_price - put_cost
            # Max loss: drop to put strike + cost of put
            max_loss_pct = (current_price - put_strike + put_cost) / current_price * 100

            protective_put = {
                "strike": put_strike,
                "expiry": exp_date,
                "cost_per_share": round(put_cost, 2),
                "cost_pct_position": round(cost_pct, 2),
                "breakeven": round(breakeven, 2),
                "max_loss_pct": round(max_loss_pct, 2),
            }
    except Exception as exc:
        log.warning("Protective put calculation failed: %s", exc)

    try:
        # Zero-cost collar: buy ~5% OTM put, sell ~5% OTM call to offset cost
        if protective_put and valid_calls:
            target_call_strike = current_price * 1.05
            best_call = min(
                valid_calls,
                key=lambda c: abs(float(c["strike"]) - target_call_strike),
            )
            call_strike = float(best_call["strike"])
            call_bid = float(best_call.get("bid") or best_call.get("lastPrice") or 0)
            put_ask = protective_put["cost_per_share"]
            net_cost = round(put_ask - call_bid, 2)

            description = (
                f"Buy ${put_strike:.2f} put / Sell ${call_strike:.2f} call "
                f"expiring {exp_date}. "
                f"Net {'cost' if net_cost >= 0 else 'credit'}: "
                f"${abs(net_cost):.2f}/share. "
                f"Limits downside below ${put_strike:.2f}, caps upside above ${call_strike:.2f}."
            )

            collar = {
                "put_strike": protective_put["strike"],
                "call_strike": call_strike,
                "expiry": exp_date,
                "net_cost_per_share": net_cost,
                "description": description,
            }
    except Exception as exc:
        log.warning("Collar calculation failed: %s", exc)

    if not protective_put and not collar:
        return empty

    return {
        "available": True,
        "protective_put": protective_put,
        "collar": collar,
    }


# ---------------------------------------------------------------------------
# P26.1: Volatility Risk Premium (VRP)
# ---------------------------------------------------------------------------


def compute_vrp(
    avg_iv_pct: float | None,
    close: "object | None",  # pd.Series
) -> dict:
    """Compute Volatility Risk Premium = Implied Vol − 30-day Historical Vol (26.1).

    VRP measures how much implied volatility exceeds realised volatility.
    A large positive VRP (IV > HV) signals a premium-selling opportunity
    (covered calls, cash-secured puts). Typical threshold: VRP > 5 vol pts.

    Parameters
    ----------
    avg_iv_pct : average implied volatility across all options, in % (e.g. 35.0)
    close      : pd.Series of daily close prices for HV computation

    Returns
    -------
    dict with:
        vrp_pts    – float or None (IV − HV30, in percentage points)
        iv_pct     – float or None (implied volatility %)
        hv30_pct   – float or None (30-day historical vol %)
        signal     – "Premium Selling" | "Neutral" | "Breakout Watch" | "No data"
        score      – int 0-100 (higher = stronger premium-selling opportunity)
        detail     – str
    """
    import pandas as pd

    if avg_iv_pct is None:
        return {
            "vrp_pts": None,
            "iv_pct": None,
            "hv30_pct": None,
            "signal": "No data",
            "score": 50,
            "detail": "Implied volatility data unavailable",
        }

    hv30_pct: float | None = None
    if close is not None and isinstance(close, pd.Series) and len(close) >= 31:
        ratio = (close / close.shift(1)).dropna()
        ratio = ratio[ratio > 0]
        if len(ratio) >= 30:
            log_ret = ratio.apply(math.log)
            daily_std = float(log_ret.tail(30).std())
            hv30_pct = round(daily_std * math.sqrt(252) * 100, 2)

    vrp_pts: float | None = None
    if hv30_pct is not None:
        vrp_pts = round(avg_iv_pct - hv30_pct, 2)

    if vrp_pts is None:
        signal = "No data"
        score = 50
        detail = f"IV: {avg_iv_pct:.1f}% | HV30: N/A"
    elif vrp_pts >= 10:
        signal = "Premium Selling"
        score = 90
        detail = f"IV: {avg_iv_pct:.1f}% | HV30: {hv30_pct:.1f}% | VRP: +{vrp_pts:.1f} pts (strong)"
    elif vrp_pts >= 5:
        signal = "Premium Selling"
        score = 75
        detail = f"IV: {avg_iv_pct:.1f}% | HV30: {hv30_pct:.1f}% | VRP: +{vrp_pts:.1f} pts"
    elif vrp_pts >= 0:
        signal = "Neutral"
        score = 55
        detail = f"IV: {avg_iv_pct:.1f}% | HV30: {hv30_pct:.1f}% | VRP: +{vrp_pts:.1f} pts (flat)"
    else:
        signal = "Breakout Watch"
        score = 35
        detail = f"IV: {avg_iv_pct:.1f}% | HV30: {hv30_pct:.1f}% | VRP: {vrp_pts:.1f} pts (IV compressed)"

    log.debug("VRP: iv=%.1f hv30=%s vrp=%s signal=%s", avg_iv_pct, hv30_pct, vrp_pts, signal)

    return {
        "vrp_pts": vrp_pts,
        "iv_pct": round(avg_iv_pct, 2),
        "hv30_pct": hv30_pct,
        "signal": signal,
        "score": score,
        "detail": detail,
    }


# ---------------------------------------------------------------------------
# P26.2: IV Rank and IV Percentile
# ---------------------------------------------------------------------------


def compute_iv_rank(
    current_iv: float | None,
    iv_history: list[float],
) -> dict:
    """Compute IV Rank and IV Percentile from a history of IV readings (26.2).

    IV Rank = (current IV − 52w low) / (52w high − 52w low) × 100
    IV Percentile = % of historical days where IV was below current IV

    Interpretation:
      IV Rank > 80  → elevated premium-selling opportunity
      IV Rank < 20  → IV compressed → potential breakout / directional move

    Parameters
    ----------
    current_iv  : current average IV in % (e.g. 35.0)
    iv_history  : list of historical daily IV readings (same units), most recent last

    Returns
    -------
    dict with:
        iv_rank_pct       – float 0-100 or None
        iv_percentile_pct – float 0-100 or None
        iv_52w_high       – float or None
        iv_52w_low        – float or None
        signal            – "High IV Rank" | "Low IV Rank" | "Normal" | "No data"
        detail            – str
    """
    if current_iv is None:
        return {
            "iv_rank_pct": None,
            "iv_percentile_pct": None,
            "iv_52w_high": None,
            "iv_52w_low": None,
            "signal": "No data",
            "detail": "Current IV unavailable",
        }

    if not iv_history or len(iv_history) < 5:
        return {
            "iv_rank_pct": None,
            "iv_percentile_pct": None,
            "iv_52w_high": None,
            "iv_52w_low": None,
            "signal": "No data",
            "detail": f"IV: {current_iv:.1f}% | Insufficient IV history",
        }

    # Use up to 252 trading days of history
    hist = iv_history[-252:]
    iv_high = max(hist)
    iv_low = min(hist)

    iv_rank: float | None = None
    if iv_high > iv_low:
        iv_rank = round((current_iv - iv_low) / (iv_high - iv_low) * 100, 1)
    else:
        iv_rank = 50.0

    iv_percentile = round(sum(1 for v in hist if v < current_iv) / len(hist) * 100, 1)

    if iv_rank is not None and iv_rank >= 80:
        signal = "High IV Rank"
    elif iv_rank is not None and iv_rank <= 20:
        signal = "Low IV Rank"
    else:
        signal = "Normal"

    detail = (
        f"IV: {current_iv:.1f}% | "
        f"Rank: {iv_rank:.0f}% | "
        f"Percentile: {iv_percentile:.0f}% | "
        f"52W High: {iv_high:.1f}% | Low: {iv_low:.1f}%"
    )

    log.debug("IV Rank: %.0f%% IV Percentile: %.0f%% signal=%s", iv_rank or 0, iv_percentile, signal)

    return {
        "iv_rank_pct": iv_rank,
        "iv_percentile_pct": iv_percentile,
        "iv_52w_high": round(iv_high, 2),
        "iv_52w_low": round(iv_low, 2),
        "signal": signal,
        "detail": detail,
    }
