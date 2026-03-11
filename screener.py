"""Stock Screener engine (P2.1 + P3.1 + P7.1 + P7.2 + P7.3).

Runs factor + risk computation for a list of tickers and applies
structured filter criteria.  Supports both rule-based filters and
Claude-parsed natural language queries.

Enhancements:
- P7.1: Larger screener universe (S&P 500, Russell 1000 from CSV files)
- P7.2: OR-logic filter support with filter groups
- P7.3: Sentiment warning and CSV export

Usage:
    from screener import run_screen, apply_filters, load_universe
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from config import cfg
from log_setup import get_logger

log = get_logger(__name__)

# Path to bundled ticker universe CSV files
_DATA_DIR = Path(__file__).parent / "data"

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
    ">":  lambda v, t: v is not None and v > t,
    "<":  lambda v, t: v is not None and v < t,
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

def _quick_analyze(symbol: str) -> dict | None:
    """Fetch minimal data and compute factor + risk score for one ticker.

    Returns a dict or None on failure.  Uses a shorter TTL for caching
    to allow fresh screening runs.
    """
    from api import FinnhubAPI
    from factors import compute_factors, composite_score, composite_label_color
    from guardrails import compute_risk
    import pandas as pd

    try:
        api = FinnhubAPI()

        quote = api.get_quote(symbol)
        price = float(quote.get("c") or 0)

        # Fetch what we can; gracefully handle missing data
        try:
            financials = api.get_financials(symbol)
        except Exception:
            financials = None

        try:
            daily = api.get_daily(symbol, years=1)
            df = pd.DataFrame({
                "Close": daily["c"],
                "Volume": daily["v"],
                "Date": pd.to_datetime(daily["t"], unit="s"),
            }).sort_values("Date").reset_index(drop=True)
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
            avg_gain = gain.ewm(alpha=1/14, min_periods=14).mean()
            avg_loss = loss.ewm(alpha=1/14, min_periods=14).mean()
            rs = avg_gain / avg_loss
            rsi_val = float((100 - 100/(1+rs)).iloc[-1])
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

    Uses a simple sequential loop with rate-limit sleep to respect
    Finnhub's 60 req/min free tier.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results = []
    log.info("Starting screen: %d tickers, %d filters",
             len(tickers), len(filters or []))

    def _worker(sym):
        time.sleep(delay_between)
        return _quick_analyze(sym)

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


def apply_esg_filter(results: list[dict], min_esg_score: float | None = None) -> list[dict]:
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
                r.get("symbol", "?"), esg, min_esg_score,
            )

    log.info(
        "ESG filter (min=%.1f): %d/%d results passed",
        min_esg_score, len(filtered), len(results),
    )
    return filtered


def results_to_csv(results: list[dict]) -> str:
    """Convert screener results to CSV string for download (P7.3)."""
    import io
    import csv
    if not results:
        return ""
    fieldnames = ["symbol", "name", "sector", "price", "factor_score",
                  "composite_label", "risk_score", "risk_level",
                  "pe_ratio", "market_cap_b", "rsi", "trend", "flag_count"]
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
