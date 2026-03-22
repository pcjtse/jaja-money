"""Stock Screener engine (P2.1 + P3.1 + P7.1 + P7.2 + P7.3).

Runs factor + risk computation for a list of tickers and applies
structured filter criteria.  Supports both rule-based filters and
Claude-parsed natural language queries.

Enhancements:
- P7.1: Larger screener universe (S&P 500, Russell 1000 from CSV files)
- P7.2: OR-logic filter support with filter groups
- P7.3: Sentiment warning and CSV export

Usage:
    from src.trading.screener import run_screen, apply_filters, load_universe
"""

from __future__ import annotations

import json
from pathlib import Path

from src.core.config import cfg
from src.core.log_setup import get_logger

log = get_logger(__name__)

# Path to bundled ticker universe CSV files
_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

# ---------------------------------------------------------------------------
# P16.4: Short squeeze preset
# ---------------------------------------------------------------------------

SHORT_SQUEEZE_PRESET: dict = {
    "short_pct_float_min": 15.0,
    "days_to_cover_min": 5.0,
    "momentum_min": 55,
}


# ---------------------------------------------------------------------------
# P7.1: Universe loaders
# ---------------------------------------------------------------------------


def load_sp500() -> list[str]:
    """Load S&P 500 tickers from data/sp500.csv."""
    csv_path = _DATA_DIR / "sp500.csv"
    if not csv_path.exists():
        log.warning("sp500.csv not found, using config default")
        return cfg.screener_universe
    try:
        tickers = []
        with open(csv_path) as f:
            for line in f:
                t = line.strip().upper()
                if t and not t.startswith("#"):
                    tickers.append(t)
        log.info("Loaded %d S&P 500 tickers from CSV", len(tickers))
        return tickers
    except Exception as exc:
        log.warning("Failed to load sp500.csv: %s", exc)
        return cfg.screener_universe


def load_russell1000() -> list[str]:
    """Load Russell 1000 tickers from data/russell1000.csv."""
    csv_path = _DATA_DIR / "russell1000.csv"
    if not csv_path.exists():
        log.warning("russell1000.csv not found, falling back to S&P 500")
        return load_sp500()
    try:
        tickers = []
        with open(csv_path) as f:
            for line in f:
                t = line.strip().upper()
                if t and not t.startswith("#"):
                    tickers.append(t)
        log.info("Loaded %d Russell 1000 tickers from CSV", len(tickers))
        return tickers
    except Exception as exc:
        log.warning("Failed to load russell1000.csv: %s", exc)
        return load_sp500()


def load_universe(name: str = "default", sector_filter: str | None = None) -> list[str]:
    """Load a named ticker universe, with optional sector pre-filter.

    name: 'default' | 'sp500' | 'russell1000'
    sector_filter: if provided, filter to tickers where known sector matches.
    """
    if name == "sp500":
        tickers = load_sp500()
    elif name == "russell1000":
        tickers = load_russell1000()
    else:
        tickers = cfg.screener_universe

    # Sector filter is applied during screening since we don't have sector metadata in CSV
    return tickers


# ---------------------------------------------------------------------------
# P7.2: Filter application with AND/OR group support
# ---------------------------------------------------------------------------

_OP_MAP = {
    ">": lambda v, t: v is not None and v > t,
    "<": lambda v, t: v is not None and v < t,
    ">=": lambda v, t: v is not None and v >= t,
    "<=": lambda v, t: v is not None and v <= t,
    "==": lambda v, t: v is not None and v == t,
    "in": lambda v, t: v is not None and v in t,
}


def _evaluate_filter(result: dict, filt: dict) -> bool:
    """Evaluate a single filter against a result."""
    dim = filt.get("dimension", "")
    op = filt.get("operator", ">")
    thresh = filt.get("value")
    fn = _OP_MAP.get(op)
    if fn is None:
        return True
    val = result.get(dim)
    return fn(val, thresh)


def _evaluate_group(result: dict, group: dict) -> bool:
    """Evaluate a filter group (AND or OR connector)."""
    connector = group.get("connector", "AND").upper()
    filters = group.get("filters", [])
    if not filters:
        return True
    if connector == "OR":
        return any(_evaluate_filter(result, f) for f in filters)
    else:  # AND
        return all(_evaluate_filter(result, f) for f in filters)


def apply_filters(result: dict, filters: list[dict]) -> bool:
    """Return True if a screener result passes all filters.

    Supports both flat lists (all AND) and grouped filters with AND/OR.
    A group has the structure: {"connector": "AND"|"OR", "filters": [...]}
    A flat filter has: {"dimension": ..., "operator": ..., "value": ...}
    """
    for filt in filters:
        if "connector" in filt:
            # This is a filter group
            if not _evaluate_group(result, filt):
                return False
        else:
            # Plain filter — treat as AND
            if not _evaluate_filter(result, filt):
                return False
    return True


# ---------------------------------------------------------------------------
# P7.3: Screen template persistence
# ---------------------------------------------------------------------------

_TEMPLATES_FILE = Path.home() / ".jaja-money" / "screen_templates.json"


def save_screen_template(name: str, filters: list[dict]) -> None:
    """Save a screen template to disk."""
    _TEMPLATES_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        templates = load_screen_templates()
        templates[name] = filters
        with open(_TEMPLATES_FILE, "w") as f:
            json.dump(templates, f, indent=2)
        log.info("Saved screen template: %s", name)
    except Exception as exc:
        log.warning("Could not save screen template: %s", exc)


def load_screen_templates() -> dict[str, list]:
    """Load all saved screen templates."""
    if not _TEMPLATES_FILE.exists():
        return {}
    try:
        with open(_TEMPLATES_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def delete_screen_template(name: str) -> None:
    """Delete a saved screen template."""
    templates = load_screen_templates()
    templates.pop(name, None)
    try:
        with open(_TEMPLATES_FILE, "w") as f:
            json.dump(templates, f, indent=2)
    except Exception as exc:
        log.warning("Could not delete screen template: %s", exc)


# ---------------------------------------------------------------------------
# Single-ticker quick analysis (lightweight version for bulk screening)
# ---------------------------------------------------------------------------


def _quick_analyze(symbol: str, api=None) -> dict | None:
    """Fetch minimal data and compute factor + risk score for one ticker.

    Returns a dict or None on failure.  Uses a shorter TTL for caching
    to allow fresh screening runs.

    Parameters
    ----------
    symbol : stock ticker symbol
    api    : shared FinnhubAPI instance (avoids creating one per ticker)
    """
    from src.analysis.factors import (
        compute_factors,
        composite_score,
        composite_label_color,
    )
    from src.analysis.guardrails import compute_risk
    import pandas as pd

    try:
        if api is None:
            from src.data.api import get_api

            api = get_api()

        quote = api.get_quote(symbol)
        price = float(quote.get("c") or 0)

        # Fetch what we can; gracefully handle missing data
        try:
            financials = api.get_financials(symbol)
        except Exception:
            financials = None

        try:
            daily = api.get_daily(symbol, years=1)
            df = (
                pd.DataFrame(
                    {
                        "Close": daily["c"],
                        "Volume": daily["v"],
                        "Date": pd.to_datetime(daily["t"], unit="s"),
                    }
                )
                .sort_values("Date")
                .reset_index(drop=True)
            )
            close = df["Close"]
        except Exception:
            close = None

        try:
            recs = api.get_recommendations(symbol)
        except Exception:
            recs = []

        try:
            earnings = api.get_earnings(symbol, limit=4)
        except Exception:
            earnings = []

        try:
            profile = api.get_profile(symbol)
            name = profile.get("name", symbol)
            sector = profile.get("finnhubIndustry", "N/A")
        except Exception:
            name = symbol
            sector = "N/A"

        factors = compute_factors(
            quote=quote,
            financials=financials,
            close=close,
            earnings=earnings,
            recommendations=recs,
            sentiment_agg=None,  # skip FinBERT for bulk screening speed
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

        # RSI for filter dimension
        rsi = None
        if close is not None and len(close) >= 15:
            import math

            delta = close.diff()
            gain = delta.clip(lower=0)
            loss = -delta.clip(upper=0)
            avg_gain = gain.ewm(alpha=1 / 14, min_periods=14).mean()
            avg_loss = loss.ewm(alpha=1 / 14, min_periods=14).mean()
            rs = avg_gain / avg_loss
            rsi_val = float((100 - 100 / (1 + rs)).iloc[-1])
            rsi = None if math.isnan(rsi_val) else rsi_val

        return {
            "symbol": symbol,
            "name": name,
            "sector": sector,
            "price": price,
            "factor_score": factor_sc,
            "composite_label": label,
            "composite_color": color,
            "risk_score": risk["risk_score"],
            "risk_level": risk["risk_level"],
            "flag_count": len(risk["flags"]),
            "pe_ratio": float(pe) if pe is not None else None,
            "market_cap_b": float(mc) / 1000 if mc is not None else None,
            "rsi": rsi,
            "trend": _classify_trend(factors),
        }

    except Exception as exc:
        log.debug("Screener: skipped %s — %s", symbol, exc)
        return None


def _classify_trend(factors: list[dict]) -> str:
    for f in factors:
        if f["name"] == "Trend (SMA)":
            lbl = f["label"].lower()
            if "uptrend" in lbl or "recovering" in lbl or "above" in lbl:
                return "uptrend"
            elif "downtrend" in lbl or "below" in lbl:
                return "downtrend"
    return "sideways"


# ---------------------------------------------------------------------------
# Bulk screening
# ---------------------------------------------------------------------------


def run_screen(
    tickers: list[str],
    filters: list[dict] | None = None,
    max_workers: int = 4,
    delay_between: float = 0.2,
) -> list[dict]:
    """Run a screen over `tickers`, return filtered + sorted results.

    Rate limiting is handled by the centralized token-bucket limiter
    inside FinnhubAPI._cached(), so per-worker sleeps are unnecessary.
    A single shared FinnhubAPI instance is used across all workers.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from src.data.api import get_api

    results = []
    log.info(
        "Starting screen: %d tickers, %d filters", len(tickers), len(filters or [])
    )

    # Share a single API instance so all workers share the rate limiter
    shared_api = get_api()

    def _worker(sym):
        return _quick_analyze(sym, api=shared_api)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_worker, t): t for t in tickers}
        for fut in as_completed(futures):
            r = fut.result()
            if r is None:
                continue
            if not filters or apply_filters(r, filters):
                results.append(r)

    # Sort by factor score descending
    results.sort(key=lambda x: x.get("factor_score", 0), reverse=True)
    log.info("Screen complete: %d/%d passed filters", len(results), len(tickers))
    return results


def default_universe() -> list[str]:
    """Return the configured default ticker universe for screening."""
    return cfg.screener_universe


def is_short_squeeze_candidate(short_data: dict, factor_score: int) -> bool:
    """Return True if a ticker meets the short-squeeze setup criteria (P16.4).

    A candidate must have high short interest (>= 15% of float), sufficient
    days-to-cover (>= 5), and a factor score indicating positive momentum
    (>= 50).  All three conditions must be met.

    Parameters
    ----------
    short_data   : dict with keys short_pct_float (float) and
                   days_to_cover (float).  Missing values are treated as
                   failing the threshold.
    factor_score : composite factor score (0-100).

    Returns
    -------
    bool
    """
    short_pct = short_data.get("short_pct_float")
    days_to_cover = short_data.get("days_to_cover")

    if short_pct is None or days_to_cover is None:
        return False

    meets_short = float(short_pct) >= SHORT_SQUEEZE_PRESET["short_pct_float_min"]
    meets_cover = float(days_to_cover) >= SHORT_SQUEEZE_PRESET["days_to_cover_min"]
    meets_momentum = int(factor_score) >= SHORT_SQUEEZE_PRESET["momentum_min"]

    return meets_short and meets_cover and meets_momentum


def apply_esg_filter(
    results: list[dict], min_esg_score: float | None = None
) -> list[dict]:
    """Filter screener results by minimum ESG score (P19.3).

    Tickers without ESG data (esg_score key absent or None) are kept, since
    absence of data should not penalise a ticker.  Only tickers with an
    explicit ESG score below min_esg_score are excluded.

    Parameters
    ----------
    results       : list of screener result dicts
    min_esg_score : minimum acceptable ESG score (0-100), or None to skip
                    filtering entirely

    Returns
    -------
    Filtered list of result dicts
    """
    if min_esg_score is None:
        return results

    filtered = []
    for r in results:
        esg = r.get("esg_score")
        if esg is None:
            # No ESG data — pass through
            filtered.append(r)
        elif float(esg) >= min_esg_score:
            filtered.append(r)
        else:
            log.debug(
                "ESG filter: excluded %s (esg_score=%.1f < min=%.1f)",
                r.get("symbol", "?"),
                esg,
                min_esg_score,
            )

    log.info(
        "ESG filter (min=%.1f): %d/%d results passed",
        min_esg_score,
        len(filtered),
        len(results),
    )
    return filtered


def results_to_csv(results: list[dict]) -> str:
    """Convert screener results to CSV string for download (P7.3)."""
    import io
    import csv

    if not results:
        return ""
    fieldnames = [
        "symbol",
        "name",
        "sector",
        "price",
        "factor_score",
        "composite_label",
        "risk_score",
        "risk_level",
        "pe_ratio",
        "market_cap_b",
        "rsi",
        "trend",
        "flag_count",
    ]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(results)
    return buf.getvalue()


def sentiment_skipped_warning() -> str:
    """Return a human-readable warning about FinBERT being skipped (P7.3)."""
    return (
        "⚠️ **Note:** FinBERT sentiment analysis is skipped during bulk screening "
        "for performance reasons. Factor scores may be slightly lower than in the "
        "full single-stock analysis, which includes news sentiment scoring."
    )


# ---------------------------------------------------------------------------
# 21.3: Dividend Growth screen preset and qualifier
# ---------------------------------------------------------------------------

DIVIDEND_GROWTH_PRESET: dict = {
    "min_yield_pct": 2.0,
    "max_payout_ratio": 75.0,
    "min_div_growth_rate_5y": 5.0,  # % CAGR
    "max_risk_score": 55,
    "min_factor_score": 45,
}


def is_dividend_growth_candidate(
    result: dict,
    financials: dict | None = None,
) -> bool:
    """Return True if a screener result meets dividend growth criteria (21.3).

    Checks: yield ≥ 2%, payout ≤ 75%, risk score ≤ 55, factor score ≥ 45.
    If financials are provided, also checks 5-year dividend growth rate ≥ 5%.
    """
    p = DIVIDEND_GROWTH_PRESET

    # Risk and factor gates
    if result.get("risk_score", 100) > p["max_risk_score"]:
        return False
    if result.get("factor_score", 0) < p["min_factor_score"]:
        return False

    metrics = financials or {}
    div_yield = metrics.get("dividendYieldIndicatedAnnual") or result.get("div_yield")
    payout = metrics.get("payoutRatioTTM") or result.get("payout_ratio")
    div_growth = metrics.get("dividendGrowthRate5Y") or result.get("div_growth_rate_5y")

    if div_yield is None or float(div_yield) < p["min_yield_pct"]:
        return False
    if payout is not None and float(payout) > p["max_payout_ratio"]:
        return False
    if div_growth is not None and float(div_growth) < p["min_div_growth_rate_5y"]:
        return False

    return True


# ---------------------------------------------------------------------------
# 21.4: Graham Number / Deep Value preset and filter
# ---------------------------------------------------------------------------

DEEP_VALUE_PRESET: dict = {
    "min_margin_of_safety": 0.10,  # 10% minimum
    "max_pe_ratio": 22.0,
    "max_risk_score": 60,
}


def compute_graham_filter(result: dict, financials: dict | None = None) -> dict:
    """Compute Graham Number metrics for a screener result (21.4).

    Returns dict with: graham_number, margin_of_safety, is_deep_value.
    """
    from src.analysis.factors import compute_graham_number as _cgn

    metrics = financials or {}
    eps = metrics.get("epsTTM") or metrics.get("epsBasicExclExtraItemsTTM")
    bvps = metrics.get("bookValuePerShareAnnual") or metrics.get(
        "bookValuePerShareQuarterly"
    )
    price = result.get("price")

    if eps is None or bvps is None or price is None or float(price) <= 0:
        return {"graham_number": None, "margin_of_safety": None, "is_deep_value": False}

    graham = _cgn(float(eps), float(bvps))
    if graham is None:
        return {"graham_number": None, "margin_of_safety": None, "is_deep_value": False}

    margin = (graham - float(price)) / graham
    p = DEEP_VALUE_PRESET
    is_deep = (
        margin >= p["min_margin_of_safety"]
        and (
            result.get("pe_ratio") is None
            or float(result["pe_ratio"]) <= p["max_pe_ratio"]
        )
        and result.get("risk_score", 100) <= p["max_risk_score"]
    )

    return {
        "graham_number": round(graham, 2),
        "margin_of_safety": round(margin, 4),
        "is_deep_value": is_deep,
    }


# ---------------------------------------------------------------------------
# 21.5: Cross-Sectional Momentum (Relative Strength)
# ---------------------------------------------------------------------------

MOMENTUM_LEADERS_PRESET: dict = {
    "top_decile_pct": 0.10,
    "lookback_6m_days": 126,
    "lookback_12m_days": 252,
    "min_factor_score": 45,
}


def compute_cross_sectional_momentum(
    tickers: list[str],
    api,
    max_workers: int = 4,
    delay_between: float = 0.2,
) -> list[dict]:
    """Rank a ticker universe by 6-month and 12-month price momentum (21.5).

    Returns list of dicts sorted by composite momentum rank (ascending rank = stronger).
    Each dict includes: symbol, return_6m_pct, return_12m_pct, momentum_rank,
    decile (1=top, 10=bottom).
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import pandas as _pd

    def _fetch_returns(symbol: str) -> dict | None:
        try:
            daily = api.get_daily(symbol, years=1.5)
            close = _pd.Series(daily["c"])
            n = len(close)
            p = MOMENTUM_LEADERS_PRESET

            ret_6m = ret_12m = None
            if n >= p["lookback_6m_days"] + 1:
                ret_6m = round(
                    (
                        float(close.iloc[-1])
                        / float(close.iloc[-p["lookback_6m_days"]])
                        - 1
                    )
                    * 100,
                    2,
                )
            if n >= p["lookback_12m_days"] + 1:
                ret_12m = round(
                    (
                        float(close.iloc[-1])
                        / float(close.iloc[-p["lookback_12m_days"]])
                        - 1
                    )
                    * 100,
                    2,
                )
            return {
                "symbol": symbol,
                "return_6m_pct": ret_6m,
                "return_12m_pct": ret_12m,
            }
        except Exception as exc:
            log.debug("Momentum fetch skipped %s: %s", symbol, exc)
            return None

    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_fetch_returns, t): t for t in tickers}
        for fut in as_completed(futures):
            r = fut.result()
            if r and (
                r["return_6m_pct"] is not None or r["return_12m_pct"] is not None
            ):
                results.append(r)

    if not results:
        return []

    # Composite momentum score: 40% 6M + 60% 12M (skip-1-month convention omitted for simplicity)
    def _composite(r: dict) -> float:
        r6 = r.get("return_6m_pct") or 0.0
        r12 = r.get("return_12m_pct") or r6
        return 0.4 * r6 + 0.6 * r12

    results.sort(key=_composite, reverse=True)

    # Assign rank and decile
    n_total = len(results)
    for rank, r in enumerate(results, start=1):
        r["momentum_rank"] = rank
        r["decile"] = min(10, int((rank - 1) / n_total * 10) + 1)
        r["composite_momentum_pct"] = round(_composite(r), 2)

    log.info("Cross-sectional momentum: ranked %d tickers", n_total)
    return results


def momentum_leaders(results: list[dict], top_pct: float = 0.10) -> list[dict]:
    """Return the top-decile momentum leaders from a ranked list (21.5)."""
    n = max(1, int(len(results) * top_pct))
    return [r for r in results if r.get("decile", 10) == 1][:n]


def momentum_laggards(results: list[dict], bottom_pct: float = 0.10) -> list[dict]:
    """Return the bottom-decile momentum laggards from a ranked list (21.5)."""
    return [r for r in results if r.get("decile", 1) == 10]


# ---------------------------------------------------------------------------
# 21.10: Short Selling screen preset and qualifier
# ---------------------------------------------------------------------------

SHORT_SELLING_PRESET: dict = {
    "min_short_pct_float": 10.0,  # % of float sold short
    "min_days_to_cover": 3.0,
    "max_factor_score": 38,  # weak fundamentals required
    "insider_signal": "Selling",  # insider selling activity
    "max_earnings_beat_rate": 0.40,  # < 40% beat rate
}


def is_short_selling_candidate(
    result: dict,
    insider_summary: dict | None = None,
    short_data: dict | None = None,
) -> bool:
    """Return True if a ticker meets short-selling screening criteria (21.10).

    Combines weak factor score + high short interest + insider selling.
    All three groups are individually weighted; at least two must be met.

    Parameters
    ----------
    result         : screener result dict (factor_score, risk_score, etc.)
    insider_summary: output of ownership.fetch_insider_summary()
    short_data     : dict with short_pct_float and days_to_cover

    Returns
    -------
    bool
    """
    p = SHORT_SELLING_PRESET
    signals_met = 0

    # Signal 1: Weak fundamentals
    if result.get("factor_score", 100) <= p["max_factor_score"]:
        signals_met += 1

    # Signal 2: High short interest
    if short_data:
        short_pct = short_data.get("short_pct_float")
        days_cover = short_data.get("days_to_cover")
        if (
            short_pct is not None
            and float(short_pct) >= p["min_short_pct_float"]
            and days_cover is not None
            and float(days_cover) >= p["min_days_to_cover"]
        ):
            signals_met += 1

    # Signal 3: Insider selling
    if insider_summary and insider_summary.get("signal") == p["insider_signal"]:
        signals_met += 1

    return signals_met >= 2
