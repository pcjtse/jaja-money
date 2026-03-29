"""Cross-Asset Leading Indicator Layer.

Computes sector-specific leading indicator scores using cross-asset ETFs:
  - Technology  ← DXY inverse, TLT (rates)
  - Energy      ← Oil (USO), DXY
  - Financials  ← HYG-IEF credit spread
  - Industrials ← Copper/Gold ratio (CPER/GLD)
  - Materials   ← Copper/Gold ratio
  - Health Care ← Defensive / VIX-inverse
  - Consumer    ← PCE proxy (XLY-relative to XLP)
  - Utilities   ← TLT direction
  - Real Estate ← TLT direction, mortgage rates
"""

from __future__ import annotations

from src.core.log_setup import get_logger

log = get_logger(__name__)

# Maps sector → list of (etf_ticker, direction, weight)
# direction: +1 = positive correlation, -1 = inverse correlation
_SECTOR_MAP: dict[str, list[tuple[str, int, float]]] = {
    "Technology": [("TLT", +1, 0.4), ("DXY", -1, 0.3), ("QQQ", +1, 0.3)],
    "Energy": [("USO", +1, 0.5), ("DX-Y.NYB", -1, 0.3), ("XLE", +1, 0.2)],
    "Financials": [("HYG", +1, 0.4), ("IEF", -1, 0.3), ("XLF", +1, 0.3)],
    "Industrials": [("CPER", +1, 0.4), ("GLD", -1, 0.3), ("XLI", +1, 0.3)],
    "Materials": [("CPER", +1, 0.4), ("GLD", -1, 0.3), ("GDX", +1, 0.3)],
    "Health Care": [("XLV", +1, 0.5), ("VIX", -1, 0.3), ("TLT", +1, 0.2)],
    "Consumer Disc.": [("XLY", +1, 0.5), ("XLP", -1, 0.3), ("AMZN", +1, 0.2)],
    "Consumer Staples": [("XLP", +1, 0.4), ("VIX", -1, 0.2), ("TLT", +1, 0.4)],
    "Utilities": [("TLT", +1, 0.5), ("VIX", -1, 0.3), ("XLU", +1, 0.2)],
    "Real Estate": [("TLT", +1, 0.5), ("IEF", +1, 0.3), ("XLRE", +1, 0.2)],
    "Communication": [("QQQ", +1, 0.4), ("TLT", +1, 0.3), ("XLC", +1, 0.3)],
}

_FALLBACK_SECTOR = "Technology"


def fetch_cross_asset_signals(sector: str | None = None) -> dict:
    """Fetch and compute cross-asset signal score for a sector.

    Parameters
    ----------
    sector : stock's sector name (matches config.yaml sectors.etfs names)

    Returns
    -------
    dict with keys:
        available (bool)
        sector (str)
        score (int): 0-100 macro tailwind score for this sector
        leading_indicators (list of dict): each with ticker, signal, weight
        detail (str)
    """
    sector_key = _resolve_sector(sector)
    indicators = _SECTOR_MAP.get(sector_key, _SECTOR_MAP[_FALLBACK_SECTOR])

    tickers = [t for t, _, _ in indicators]
    price_changes = _fetch_price_changes(tickers)

    if not price_changes:
        return {
            "available": False,
            "sector": sector_key,
            "score": 50,
            "leading_indicators": [],
            "detail": "Cross-asset data unavailable",
        }

    weighted_score = 50.0
    leading = []
    for ticker, direction, weight in indicators:
        change = price_changes.get(ticker)
        if change is None:
            continue

        # Convert price change to signal: positive = up, negative = down
        # Apply direction: if direction=-1, an up move in this ticker is bearish
        signal_value = change * direction

        # Map to 0-100 contribution
        if signal_value > 1.5:
            contribution = 80
        elif signal_value > 0.5:
            contribution = 65
        elif signal_value > -0.5:
            contribution = 50
        elif signal_value > -1.5:
            contribution = 35
        else:
            contribution = 20

        weighted_score += (contribution - 50) * weight
        leading.append({
            "ticker": ticker,
            "pct_change_5d": round(change, 2),
            "direction": direction,
            "signal_contribution": contribution,
            "weight": weight,
        })

    score = max(0, min(100, int(weighted_score)))

    if score >= 70:
        assessment = "Macro tailwinds"
    elif score >= 55:
        assessment = "Mild tailwinds"
    elif score >= 45:
        assessment = "Neutral macro"
    elif score >= 30:
        assessment = "Mild headwinds"
    else:
        assessment = "Macro headwinds"

    detail = f"Cross-asset score ({sector_key}): {score}/100 — {assessment}"

    return {
        "available": True,
        "sector": sector_key,
        "score": score,
        "leading_indicators": leading,
        "detail": detail,
    }


def _fetch_price_changes(tickers: list[str]) -> dict[str, float]:
    """Fetch 5-day % price change for each ticker."""
    results: dict[str, float] = {}
    try:
        import yfinance as yf

        # Filter out non-yfinance tickers
        yf_tickers = [t for t in tickers if t not in ("VIX",)]
        vix_tickers = [t for t in tickers if t == "VIX"]

        if yf_tickers:
            data = yf.download(
                " ".join(yf_tickers),
                period="10d",
                progress=False,
                auto_adjust=True,
            )
            close = data.get("Close", data) if isinstance(data.columns, object) else data

            if hasattr(close, "columns"):
                for t in yf_tickers:
                    if t in close.columns:
                        col = close[t].dropna()
                        if len(col) >= 2:
                            pct = (float(col.iloc[-1]) - float(col.iloc[-6 if len(col) >= 6 else 0])) / float(col.iloc[-6 if len(col) >= 6 else 0]) * 100
                            results[t] = round(pct, 3)
            elif len(yf_tickers) == 1:
                col = close.dropna() if hasattr(close, "dropna") else close
                if hasattr(col, "__len__") and len(col) >= 2:
                    start = col.iloc[-6 if len(col) >= 6 else 0]
                    end = col.iloc[-1]
                    if float(start) != 0:
                        results[yf_tickers[0]] = round((float(end) - float(start)) / float(start) * 100, 3)

        if vix_tickers:
            vix_data = yf.download("^VIX", period="10d", progress=False, auto_adjust=True)
            if not vix_data.empty and len(vix_data) >= 2:
                vix_close = vix_data["Close"].dropna()
                start = float(vix_close.iloc[-6 if len(vix_close) >= 6 else 0])
                end = float(vix_close.iloc[-1])
                if start != 0:
                    results["VIX"] = round((end - start) / start * 100, 3)

    except Exception as exc:
        log.debug("Cross-asset price fetch failed: %s", exc)

    return results


def _resolve_sector(sector: str | None) -> str:
    if not sector:
        return _FALLBACK_SECTOR
    # Exact match
    if sector in _SECTOR_MAP:
        return sector
    # Partial match
    for key in _SECTOR_MAP:
        if key.lower() in sector.lower() or sector.lower() in key.lower():
            return key
    return _FALLBACK_SECTOR
