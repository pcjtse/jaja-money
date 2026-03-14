"""Multi-Stock Comparison helpers (P1.1).

Provides a function to run full analysis on multiple tickers
and return a side-by-side comparison dict.
"""

from __future__ import annotations

import pandas as pd

from factors import compute_factors, composite_score, composite_label_color
from guardrails import compute_risk
from log_setup import get_logger

log = get_logger(__name__)


def analyze_ticker(symbol: str, api) -> dict | None:
    """Run a full quick analysis for a single ticker.

    Returns a flat dict of all key metrics, or None on failure.
    """
    try:
        quote = api.get_quote(symbol)
        price = float(quote.get("c") or 0)
        change_pct = float(quote.get("dp") or 0)

        try:
            profile = api.get_profile(symbol)
            name = profile.get("name", symbol)
            sector = profile.get("finnhubIndustry", "N/A")
        except Exception:
            profile = None
            name = symbol
            sector = "N/A"

        try:
            financials = api.get_financials(symbol)
        except Exception:
            financials = None

        try:
            daily = api.get_daily(symbol, years=1)
            df = (
                pd.DataFrame(
                    {
                        "Date": pd.to_datetime(daily["t"], unit="s"),
                        "Close": daily["c"],
                        "Volume": daily["v"],
                    }
                )
                .sort_values("Date")
                .reset_index(drop=True)
            )
            close = df["Close"]
        except Exception:
            close = None
            df = None

        try:
            recs = api.get_recommendations(symbol)
        except Exception:
            recs = []

        try:
            earnings = api.get_earnings(symbol, limit=4)
        except Exception:
            earnings = []

        factors = compute_factors(
            quote=quote,
            financials=financials,
            close=close,
            earnings=earnings,
            recommendations=recs,
            sentiment_agg=None,
        )
        factor_sc = composite_score(factors)
        label, color = composite_label_color(factor_sc)

        risk = compute_risk(
            quote=quote,
            financials=financials,
            close=close,
            earnings=earnings,
            recommendations=recs,
            sentiment_agg=None,
            composite_factor_score=factor_sc,
        )

        pe = (financials or {}).get("peBasicExclExtraTTM")
        mc = (financials or {}).get("marketCapitalization")
        eps = (financials or {}).get("epsBasicExclExtraItemsTTM")
        high52 = (financials or {}).get("52WeekHigh")
        low52 = (financials or {}).get("52WeekLow")

        # Per-factor scores (for radar overlay)
        factor_detail = {f["name"]: f["score"] for f in factors}

        return {
            "symbol": symbol,
            "name": name,
            "sector": sector,
            "price": price,
            "change_pct": change_pct,
            "factor_score": factor_sc,
            "composite_label": label,
            "composite_color": color,
            "risk_score": risk["risk_score"],
            "risk_level": risk["risk_level"],
            "risk_color": risk["risk_color"],
            "flag_count": len(risk["flags"]),
            "hv": risk.get("hv"),
            "drawdown_pct": risk.get("drawdown_pct"),
            "pe": float(pe) if pe is not None else None,
            "eps": float(eps) if eps is not None else None,
            "mc_m": float(mc) if mc is not None else None,  # in millions
            "high52": float(high52) if high52 is not None else None,
            "low52": float(low52) if low52 is not None else None,
            "factor_detail": factor_detail,
            "factors": factors,
            "risk": risk,
            "close": close,
        }

    except Exception as exc:
        log.warning("Comparison: failed to analyze %s — %s", symbol, exc)
        return None


def compare_tickers(symbols: list[str], api) -> list[dict]:
    """Return analysis dicts for each symbol (None entries for failed ones)."""
    results = []
    for sym in symbols:
        log.info("Comparison: analyzing %s", sym)
        result = analyze_ticker(sym.strip().upper(), api)
        if result:
            results.append(result)
    return results


def comparison_dataframe(results: list[dict]) -> pd.DataFrame:
    """Build a summary DataFrame suitable for display."""
    rows = []
    for r in results:
        mc = r.get("mc_m")
        if mc is not None:
            mc_str = (
                f"${mc / 1000:.1f}B" if mc < 1_000_000 else f"${mc / 1_000_000:.1f}T"
            )
        else:
            mc_str = "N/A"

        rows.append(
            {
                "Symbol": r["symbol"],
                "Name": r["name"][:25],
                "Sector": r["sector"],
                "Price": f"${r['price']:,.2f}" if r["price"] else "N/A",
                "Day %": f"{r['change_pct']:+.2f}%"
                if r.get("change_pct") is not None
                else "N/A",
                "Factor Score": r["factor_score"],
                "Signal": r["composite_label"],
                "Risk Score": r["risk_score"],
                "Risk Level": r["risk_level"],
                "P/E": f"{r['pe']:.1f}×" if r.get("pe") else "N/A",
                "Market Cap": mc_str,
                "Flags": r["flag_count"],
                "Volatility": f"{r['hv']:.1f}%" if r.get("hv") is not None else "N/A",
                "Drawdown": f"{r['drawdown_pct']:.1f}%"
                if r.get("drawdown_pct") is not None
                else "N/A",
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# P11.4: Peer Group Automatic Comparison
# ---------------------------------------------------------------------------


def fetch_peer_metrics(symbol: str, api) -> dict:
    """Fetch sector peers and compare key metrics vs. the target stock.

    Parameters
    ----------
    symbol : target ticker
    api : FinnhubAPI instance

    Returns
    -------
    dict with: target_metrics, peers (list), percentile_ranks, peer_tickers
    """
    from log_setup import get_logger

    log = get_logger(__name__)

    peer_tickers = []
    try:
        peer_tickers = api.get_peers(symbol)
        # Limit to 8 peers for performance
        peer_tickers = [p for p in peer_tickers if p != symbol][:8]
    except Exception as exc:
        log.warning("Peer fetch failed for %s: %s", symbol, exc)

    all_tickers = [symbol] + peer_tickers

    # Fetch financials for each
    metrics_by_ticker: dict[str, dict] = {}
    for ticker in all_tickers:
        try:
            fin = api.get_financials(ticker)
            quote = api.get_quote(ticker)
            profile = api.get_profile(ticker)
            metrics_by_ticker[ticker] = {
                "pe": fin.get("peBasicExclExtraTTM") or fin.get("peNormalizedAnnual"),
                "roe": fin.get("roeTTM"),
                "revenue_growth": fin.get("revenueGrowthTTMYoy"),
                "gross_margin": fin.get("grossMarginTTM"),
                "price": quote.get("c"),
                "market_cap": fin.get("marketCapitalization"),
                "name": profile.get("name", ticker)[:25],
                "sector": profile.get("finnhubIndustry", ""),
            }
        except Exception as exc:
            log.debug("Could not fetch metrics for peer %s: %s", ticker, exc)

    if symbol not in metrics_by_ticker:
        return {"error": "No data for target symbol", "peer_tickers": peer_tickers}

    # Compute percentile ranks for the target vs peers
    metric_keys = ["pe", "roe", "revenue_growth", "gross_margin"]
    percentile_ranks: dict[str, float | None] = {}

    for key in metric_keys:
        values = []
        for t, m in metrics_by_ticker.items():
            val = m.get(key)
            if val is not None:
                values.append((t, float(val)))

        if len(values) < 2:
            percentile_ranks[key] = None
            continue

        values_sorted = sorted(values, key=lambda x: x[1])
        target_val = metrics_by_ticker[symbol].get(key)
        if target_val is None:
            percentile_ranks[key] = None
            continue

        below = sum(1 for _, v in values_sorted if v < float(target_val))
        percentile_ranks[key] = round(below / len(values_sorted) * 100, 0)

    # Build comparison table
    peer_table = []
    for ticker in all_tickers:
        m = metrics_by_ticker.get(ticker, {})
        peer_table.append(
            {
                "ticker": ticker,
                "name": m.get("name", ticker),
                "pe": m.get("pe"),
                "roe": m.get("roe"),
                "revenue_growth": m.get("revenue_growth"),
                "gross_margin": m.get("gross_margin"),
                "market_cap": m.get("market_cap"),
                "is_target": ticker == symbol,
            }
        )

    return {
        "target": symbol,
        "target_metrics": metrics_by_ticker.get(symbol, {}),
        "peer_tickers": peer_tickers,
        "peer_table": peer_table,
        "percentile_ranks": percentile_ranks,
        "metrics_by_ticker": metrics_by_ticker,
    }
