"""Buyback Effectiveness Tracker.

Scores whether a company's buyback program is actually reducing share count
and whether buybacks were executed at value-accretive prices relative to
an intrinsic value estimate (Graham Number).

High score = net shares declining + buybacks below intrinsic value.
Low score  = share count increasing despite buyback program (dilution).
"""

from __future__ import annotations

from src.core.log_setup import get_logger

log = get_logger(__name__)


def fetch_buyback_data(symbol: str) -> dict:
    """Fetch buyback-related data via yfinance.

    Returns
    -------
    dict with keys:
        available (bool)
        share_count_trend (str): "decreasing" | "flat" | "increasing"
        buyback_yield_pct (float | None): Annual buyback as % of market cap.
        shares_yoy_change_pct (float | None): YoY % change in basic shares.
        repurchase_latest (float | None): Most recent annual repurchase $ value.
        market_cap (float | None)
        detail (str)
    """
    try:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        cf = ticker.cashflow  # columns are dates, rows are line items

        repurchase_latest = None
        if cf is not None and not cf.empty:
            # Look for repurchase row (yfinance naming varies)
            for row_name in cf.index:
                rn_lower = str(row_name).lower()
                if "repurchase" in rn_lower and "capital" in rn_lower:
                    vals = cf.loc[row_name].dropna()
                    if len(vals) > 0:
                        # Cash outflow is negative in yfinance; take abs
                        repurchase_latest = abs(float(vals.iloc[0]))
                    break

        # Share count trend from balance sheet
        bs = ticker.balance_sheet
        share_counts = []
        if bs is not None and not bs.empty:
            for row_name in bs.index:
                rn_lower = str(row_name).lower()
                if "ordinary shares number" in rn_lower or "common stock shares" in rn_lower:
                    vals = bs.loc[row_name].dropna()
                    share_counts = [float(v) for v in vals.values[:4] if v is not None]
                    break
            if not share_counts:
                # Fallback: try shares_outstanding from info
                info = ticker.info or {}
                so = info.get("sharesOutstanding")
                if so:
                    share_counts = [float(so)]

        shares_yoy_change_pct = None
        share_count_trend = "flat"
        if len(share_counts) >= 2:
            latest, prior = share_counts[0], share_counts[1]
            if prior and prior != 0:
                shares_yoy_change_pct = round((latest - prior) / abs(prior) * 100, 2)
            if shares_yoy_change_pct is not None:
                if shares_yoy_change_pct < -0.5:
                    share_count_trend = "decreasing"
                elif shares_yoy_change_pct > 0.5:
                    share_count_trend = "increasing"

        info = ticker.info or {}
        market_cap = info.get("marketCap")
        buyback_yield_pct = None
        if repurchase_latest and market_cap and market_cap > 0:
            buyback_yield_pct = round(repurchase_latest / market_cap * 100, 2)

        detail_parts = [f"Share trend: {share_count_trend}"]
        if shares_yoy_change_pct is not None:
            detail_parts.append(f"YoY change: {shares_yoy_change_pct:+.1f}%")
        if buyback_yield_pct is not None:
            detail_parts.append(f"Buyback yield: {buyback_yield_pct:.1f}%")

        return {
            "available": True,
            "share_count_trend": share_count_trend,
            "buyback_yield_pct": buyback_yield_pct,
            "shares_yoy_change_pct": shares_yoy_change_pct,
            "repurchase_latest": repurchase_latest,
            "market_cap": market_cap,
            "detail": " | ".join(detail_parts),
        }
    except Exception as exc:
        log.warning("Buyback data fetch failed for %s: %s", symbol, exc)
        return {
            "available": False,
            "share_count_trend": "flat",
            "buyback_yield_pct": None,
            "shares_yoy_change_pct": None,
            "repurchase_latest": None,
            "market_cap": None,
            "detail": "Buyback data unavailable",
        }


def score_buyback_effectiveness(
    buyback_data: dict,
    graham_number: float | None = None,
    price: float | None = None,
) -> dict:
    """Compute a 0-100 buyback effectiveness score.

    Parameters
    ----------
    buyback_data  : output of fetch_buyback_data()
    graham_number : intrinsic value estimate; if provided, checks
                    whether buybacks are value-accretive (price < graham)
    price         : current price for value-accretion check

    Returns
    -------
    dict with score (int), label (str), detail (str)
    """
    if not buyback_data.get("available"):
        return {"score": 50, "label": "No data", "detail": "Buyback data unavailable"}

    trend = buyback_data.get("share_count_trend", "flat")
    yoy_pct = buyback_data.get("shares_yoy_change_pct")
    buyback_yield = buyback_data.get("buyback_yield_pct", 0) or 0

    # Base score from share count trend
    if trend == "decreasing":
        base = 70
    elif trend == "increasing":
        base = 25
    else:
        base = 50

    # Adjust for magnitude of change
    if yoy_pct is not None:
        if yoy_pct < -3:
            base = min(95, base + 20)
        elif yoy_pct < -1:
            base = min(88, base + 10)
        elif yoy_pct > 3:
            base = max(10, base - 20)
        elif yoy_pct > 1:
            base = max(18, base - 10)

    # Bonus for value-accretive buybacks (price < Graham Number)
    if graham_number and price and price > 0:
        if price < graham_number:
            base = min(98, base + 10)  # accretive
        elif price > graham_number * 1.5:
            base = max(5, base - 10)  # dilutive at premium

    # Adjust for buyback yield
    if buyback_yield >= 3:
        base = min(98, base + 8)
    elif buyback_yield >= 1:
        base = min(95, base + 4)

    score = max(0, min(100, base))

    if score >= 80:
        label = "Strong buyback — net accretive"
    elif score >= 60:
        label = "Moderate buyback activity"
    elif score >= 40:
        label = "Flat buyback activity"
    else:
        label = "Dilutive — shares outstanding rising"

    detail = buyback_data.get("detail", "")
    if graham_number and price:
        detail += f" | Graham: ${graham_number:.0f} vs Price: ${price:.0f}"

    return {"score": score, "label": label, "detail": detail}
