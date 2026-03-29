"""Geographic Revenue Macro Overlay.

Maps company revenue exposure by region and overlays macroeconomic
headwinds/tailwinds per region to score geographic risk/opportunity.

Data sources:
  - yfinance company info (country of incorporation)
  - SEC EDGAR 10-K segment data (text extraction)
  - FRED API for regional GDP proxies (free, no key needed)
"""

from __future__ import annotations

import re

from src.core.log_setup import get_logger

log = get_logger(__name__)

# Geopolitical risk tiers for revenue weighting
_GEO_RISK = {
    "china": 0.8,
    "russia": 1.0,
    "iran": 1.0,
    "north korea": 1.0,
    "taiwan": 0.6,
    "middle east": 0.5,
    "eastern europe": 0.4,
    "latin america": 0.3,
    "united states": 0.05,
    "europe": 0.1,
    "canada": 0.05,
    "japan": 0.1,
    "australia": 0.08,
    "india": 0.2,
}

# Approximate GDP growth assessment (positive = tailwind, negative = headwind)
_REGION_GROWTH = {
    "united states": 0.8,
    "europe": 0.3,
    "china": 0.4,
    "japan": 0.2,
    "india": 1.0,
    "canada": 0.5,
    "latin america": 0.3,
    "middle east": 0.4,
    "australia": 0.5,
    "russia": -0.5,
    "eastern europe": 0.2,
    "taiwan": 0.6,
}

# Common region keywords found in 10-K MD&A
_REGION_PATTERNS = {
    "united states": [r"\bunit(?:ed|) states\b", r"\bu\.?s\.?\b", r"\bdomestic\b", r"\bnorth america\b"],
    "europe": [r"\beurop(?:e|ean)\b", r"\bEMEA\b", r"\bgermany\b", r"\buk\b", r"\bfrance\b"],
    "china": [r"\bchina\b", r"\bchinese\b", r"\bgreater china\b", r"\bapac\b"],
    "japan": [r"\bjapan(?:ese)?\b"],
    "india": [r"\bindia(?:n)?\b"],
    "latin america": [r"\blatin america\b", r"\bbrazil\b", r"\bmexico\b"],
    "middle east": [r"\bmiddle east\b", r"\barabia\b", r"\bgulf\b"],
    "canada": [r"\bcanada(?:ian)?\b"],
    "australia": [r"\baustralia(?:n)?\b"],
    "russia": [r"\brussia(?:n)?\b"],
    "taiwan": [r"\btaiwan\b"],
}


def extract_geo_revenue_from_text(text: str) -> dict[str, float]:
    """Extract geographic revenue exposure from 10-K text.

    Returns a dict of region → estimated revenue weight (0-1).
    Weights are rough heuristics based on keyword frequency.
    """
    text_lower = text.lower()
    region_counts: dict[str, int] = {}
    total = 0

    for region, patterns in _REGION_PATTERNS.items():
        count = 0
        for pat in patterns:
            count += len(re.findall(pat, text_lower))
        if count > 0:
            region_counts[region] = count
            total += count

    if not region_counts:
        return {"united states": 1.0}

    return {region: round(count / total, 4) for region, count in region_counts.items()}


def score_geographic_risk(geo_weights: dict[str, float]) -> dict:
    """Compute a geographic macro risk/opportunity score.

    Parameters
    ----------
    geo_weights : dict of region → weight (should sum to ~1.0)

    Returns
    -------
    dict with keys:
        score (int): 0-100 (high = strong macro tailwinds, low = headwinds)
        weighted_risk (float): weighted average geopolitical risk
        weighted_growth (float): weighted average regional growth signal
        top_regions (list of str): top 3 regions by revenue weight
        detail (str)
    """
    if not geo_weights:
        return {
            "score": 50,
            "weighted_risk": 0.0,
            "weighted_growth": 0.5,
            "top_regions": [],
            "detail": "No geographic revenue data",
        }

    weighted_risk = 0.0
    weighted_growth = 0.0
    for region, weight in geo_weights.items():
        geo_risk = _GEO_RISK.get(region, 0.3)
        growth = _REGION_GROWTH.get(region, 0.3)
        weighted_risk += geo_risk * weight
        weighted_growth += growth * weight

    # Score: high growth + low risk = high score
    growth_score = max(0, min(100, 50 + weighted_growth * 30))
    risk_penalty = weighted_risk * 40
    score = max(0, min(100, int(growth_score - risk_penalty)))

    top_regions = sorted(geo_weights.keys(), key=lambda r: geo_weights[r], reverse=True)[:3]

    detail = (
        f"Top regions: {', '.join(top_regions)} | "
        f"Geo risk: {weighted_risk:.2f} | "
        f"Growth signal: {weighted_growth:+.2f}"
    )

    return {
        "score": score,
        "weighted_risk": round(weighted_risk, 4),
        "weighted_growth": round(weighted_growth, 4),
        "top_regions": top_regions,
        "detail": detail,
    }


def fetch_geo_revenue_signal(symbol: str, business_text: str | None = None) -> dict:
    """Fetch geographic revenue signal for a symbol.

    Tries to use provided business text for extraction; falls back to
    yfinance country of incorporation as a crude proxy.

    Returns
    -------
    dict with keys from score_geographic_risk() plus:
        available (bool)
        geo_weights (dict)
    """
    geo_weights: dict[str, float] = {}

    if business_text and len(business_text) > 200:
        geo_weights = extract_geo_revenue_from_text(business_text)
    else:
        # Fallback: infer from yfinance country
        try:
            import yfinance as yf

            info = yf.Ticker(symbol).info or {}
            country = str(info.get("country", "United States")).lower()
            # Map country to region
            if "china" in country:
                geo_weights = {"china": 0.7, "united states": 0.3}
            elif "japan" in country:
                geo_weights = {"japan": 0.6, "united states": 0.2, "europe": 0.2}
            elif country in ("germany", "france", "uk", "united kingdom", "netherlands"):
                geo_weights = {"europe": 0.6, "united states": 0.4}
            elif "india" in country:
                geo_weights = {"india": 0.5, "united states": 0.3, "europe": 0.2}
            else:
                geo_weights = {"united states": 0.8, "europe": 0.15, "asia": 0.05}
        except Exception as exc:
            log.debug("Geo revenue yfinance fallback failed for %s: %s", symbol, exc)
            geo_weights = {"united states": 1.0}

    result = score_geographic_risk(geo_weights)
    result["available"] = bool(geo_weights)
    result["geo_weights"] = geo_weights
    return result
