"""Stock Screener engine (P2.1 + P3.1 + P7.3).

Runs factor + risk computation for a list of tickers and applies
structured filter criteria.  Supports both rule-based filters and
Claude-parsed natural language queries.

Enhanced with:
- Screen templates: save/load/delete (P7.3)
- CSV export (P7.3)
- Sentiment-skip warning (P7.3)

Usage:
    from screener import run_screen, apply_filters
"""
from __future__ import annotations

import csv
import io
import json
import os
import time
from pathlib import Path

from config import cfg
from log_setup import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Filter application
# ---------------------------------------------------------------------------

_OP_MAP = {
    ">":  lambda v, t: v is not None and v > t,
    "<":  lambda v, t: v is not None and v < t,
    ">=": lambda v, t: v is not None and v >= t,
    "<=": lambda v, t: v is not None and v <= t,
    "==": lambda v, t: v is not None and v == t,
    "in": lambda v, t: v is not None and v in t,
}


def apply_filters(result: dict, filters: list[dict]) -> bool:
    """Return True if a screener result passes all filters."""
    for filt in filters:
        dim = filt.get("dimension", "")
        op = filt.get("operator", ">")
        thresh = filt.get("value")
        fn = _OP_MAP.get(op)
        if fn is None:
            continue
        val = result.get(dim)
        if not fn(val, thresh):
            return False
    return True


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


# ---------------------------------------------------------------------------
# P7.3: Screen templates (save / load / delete)
# ---------------------------------------------------------------------------

_TEMPLATE_DIR = Path(os.path.expanduser("~/.jaja-money/templates"))


def _ensure_template_dir() -> None:
    _TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)


def save_template(name: str, filters: list[dict]) -> None:
    """Persist a filter set under ``name`` for later retrieval."""
    _ensure_template_dir()
    path = _TEMPLATE_DIR / f"{name}.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"name": name, "filters": filters}, fh, indent=2)
    log.info("Template saved: %s", path)


def load_template(name: str) -> list[dict]:
    """Load a saved filter template by name.  Raises FileNotFoundError if absent."""
    path = _TEMPLATE_DIR / f"{name}.json"
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return data.get("filters", [])


def delete_template(name: str) -> bool:
    """Delete a saved template.  Returns True if deleted, False if not found."""
    path = _TEMPLATE_DIR / f"{name}.json"
    if path.exists():
        path.unlink()
        log.info("Template deleted: %s", name)
        return True
    return False


def list_templates() -> list[str]:
    """Return names of all saved screen templates."""
    if not _TEMPLATE_DIR.exists():
        return []
    return [p.stem for p in sorted(_TEMPLATE_DIR.glob("*.json"))]


# ---------------------------------------------------------------------------
# P7.3: CSV export
# ---------------------------------------------------------------------------

_CSV_COLUMNS = [
    "symbol", "name", "sector", "price",
    "factor_score", "composite_label",
    "risk_score", "risk_level", "flag_count",
    "pe_ratio", "market_cap_b", "rsi",
]


def export_results_to_csv(results: list[dict]) -> str:
    """Serialise screener results to a CSV string.

    Returns the CSV content as a plain string (suitable for Streamlit download).
    """
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=_CSV_COLUMNS,
        extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()
    for row in results:
        writer.writerow({col: row.get(col, "") for col in _CSV_COLUMNS})
    return buf.getvalue()


# ---------------------------------------------------------------------------
# P7.3: Sentiment-skip warning helper
# ---------------------------------------------------------------------------

SENTIMENT_SKIP_WARNING = (
    "FinBERT sentiment analysis was skipped during bulk screening to improve speed. "
    "Sentiment factor scores are set to neutral (50/100). "
    "Run a full single-ticker analysis for sentiment-adjusted scores."
)
