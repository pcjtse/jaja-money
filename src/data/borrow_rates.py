"""Cost-to-Borrow (CTB) Rate Fetcher.

Retrieves short borrow rates to enhance the short squeeze signal.
High CTB rates indicate expensive shorting — key precondition for squeezes.

Sources (in order of preference):
  1. Quiver Quantitative free tier
  2. IBKR-style heuristic from short interest metrics via yfinance
"""

from __future__ import annotations

from src.core.log_setup import get_logger

log = get_logger(__name__)

# Approximate CTB tiers based on short float (heuristic when no API data)
_CTB_TIERS = [
    (30.0, 75.0),   # > 30% short float → ~75% CTB
    (20.0, 40.0),
    (15.0, 20.0),
    (10.0, 10.0),
    (5.0, 3.0),
    (0.0, 0.5),
]


def fetch_borrow_rates(symbol: str) -> dict:
    """Fetch cost-to-borrow rate for a symbol.

    Returns
    -------
    dict with keys:
        available (bool)
        ctb_rate (float | None): Annual borrow rate %.
        ctb_tier (str): "Very Expensive" | "Expensive" | "Moderate" | "Cheap"
        source (str): data source used
        detail (str)
    """
    symbol = symbol.upper()
    result = _fetch_quiver(symbol)
    if result["available"]:
        return result
    return _estimate_from_short_interest(symbol)


def _fetch_quiver(symbol: str) -> dict:
    """Try Quiver Quantitative CTB data."""
    try:
        import requests

        resp = requests.get(
            f"https://api.quiverquant.com/beta/live/shortinterest/{symbol}",
            timeout=8,
            headers={"User-Agent": "jaja-money/1.0"},
        )
        if resp.status_code != 200:
            return {"available": False, "ctb_rate": None, "ctb_tier": "Unknown", "source": "none", "detail": ""}

        data = resp.json()
        items = data if isinstance(data, list) else [data]
        if not items:
            return {"available": False, "ctb_rate": None, "ctb_tier": "Unknown", "source": "none", "detail": ""}

        latest = items[0]
        ctb = latest.get("CTB") or latest.get("ctb") or latest.get("borrowRate")
        if ctb is None:
            return {"available": False, "ctb_rate": None, "ctb_tier": "Unknown", "source": "none", "detail": ""}

        ctb = float(ctb)
        tier = _classify_ctb(ctb)
        return {
            "available": True,
            "ctb_rate": round(ctb, 2),
            "ctb_tier": tier,
            "source": "quiver",
            "detail": f"CTB rate: {ctb:.1f}% ({tier})",
        }
    except Exception as exc:
        log.debug("Quiver CTB fetch failed for %s: %s", symbol, exc)
        return {"available": False, "ctb_rate": None, "ctb_tier": "Unknown", "source": "none", "detail": ""}


def _estimate_from_short_interest(symbol: str) -> dict:
    """Estimate CTB from short float using heuristic tiers."""
    try:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        info = ticker.info or {}
        short_pct = info.get("shortPercentOfFloat") or info.get("shortRatio")
        if short_pct is None:
            return {
                "available": False,
                "ctb_rate": None,
                "ctb_tier": "Unknown",
                "source": "none",
                "detail": "Short interest data unavailable",
            }
        short_pct_float = float(short_pct)
        if short_pct_float < 1.0:
            short_pct_float *= 100  # convert decimal to percentage

        ctb = _estimate_ctb_from_short_pct(short_pct_float)
        tier = _classify_ctb(ctb)
        return {
            "available": True,
            "ctb_rate": round(ctb, 1),
            "ctb_tier": tier,
            "source": "heuristic",
            "detail": f"Estimated CTB: ~{ctb:.0f}% (from {short_pct_float:.1f}% short float)",
        }
    except Exception as exc:
        log.warning("CTB estimation failed for %s: %s", symbol, exc)
        return {
            "available": False,
            "ctb_rate": None,
            "ctb_tier": "Unknown",
            "source": "none",
            "detail": "CTB data unavailable",
        }


def _estimate_ctb_from_short_pct(short_pct: float) -> float:
    """Estimate CTB rate from short float percentage using tiers."""
    for threshold, ctb in _CTB_TIERS:
        if short_pct >= threshold:
            return ctb
    return 0.5


def _classify_ctb(ctb: float) -> str:
    if ctb >= 50:
        return "Very Expensive"
    if ctb >= 20:
        return "Expensive"
    if ctb >= 5:
        return "Moderate"
    return "Cheap"
