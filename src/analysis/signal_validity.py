"""Signal Validity — forward-return analysis for the composite factor score.

Implements todo 21.3: show users whether the composite score has historically
correlated with forward returns.

Key functions
-------------
compute_forward_return        — fetch actual return N days after a signal date
backfill_all_forward_returns  — process all history rows not yet computed
compute_quartile_analysis     — median return per score quartile
compute_spearman_correlations — rank correlation between score and returns
compute_ic_trend              — rolling IC (information coefficient) over time
get_signal_quality_summary    — compact summary dict for the dashboard badge
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta

from src.core.log_setup import get_logger
from src.data.history import (
    get_all_analysis_signals,
    get_signal_returns,
    upsert_signal_return,
)

log = get_logger(__name__)

_PERIODS = (21, 63, 126)  # trading-day-equivalent calendar days


# ---------------------------------------------------------------------------
# Price helpers
# ---------------------------------------------------------------------------


def _fetch_close_prices(symbol: str, years: int = 2) -> dict[str, float]:
    """Return {date_str: close_price} for the last `years` years via yfinance.

    Falls back to an empty dict if yfinance is unavailable or the ticker
    doesn't exist, so callers can handle gracefully.
    """
    try:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=f"{years}y", interval="1d")
        if hist.empty:
            return {}
        # DatetimeIndex → string keys
        return {
            dt.strftime("%Y-%m-%d"): float(close)
            for dt, close in zip(hist.index, hist["Close"])
        }
    except Exception as exc:
        log.debug("Failed to fetch prices for %s: %s", symbol, exc)
        return {}


def _closest_price(
    prices: dict[str, float], target_date: datetime
) -> float | None:
    """Return the close price on or just after `target_date` (±5 calendar days)."""
    for offset in range(6):
        key = (target_date + timedelta(days=offset)).strftime("%Y-%m-%d")
        if key in prices:
            return prices[key]
    return None


# ---------------------------------------------------------------------------
# Forward return computation
# ---------------------------------------------------------------------------


def compute_forward_return(
    symbol: str,
    signal_date: str,
    price_at_signal: float,
    prices: dict[str, float] | None = None,
) -> dict[str, float | None]:
    """Compute calendar-day forward returns at 21, 63, and 126 days.

    Parameters
    ----------
    symbol        : ticker (used to fetch prices if not provided)
    signal_date   : YYYY-MM-DD string
    price_at_signal : closing price on the signal date
    prices        : optional pre-fetched {date: close} dict (avoids redundant API calls)

    Returns
    -------
    dict with keys return_21d, return_63d, return_126d (each float % or None)
    """
    if price_at_signal is None or price_at_signal <= 0:
        return {f"return_{p}d": None for p in _PERIODS}

    if prices is None:
        prices = _fetch_close_prices(symbol)

    base = datetime.strptime(signal_date, "%Y-%m-%d")
    result: dict[str, float | None] = {}
    for period in _PERIODS:
        target = base + timedelta(days=period)
        future_price = _closest_price(prices, target)
        if future_price is not None:
            ret = (future_price - price_at_signal) / price_at_signal * 100.0
            result[f"return_{period}d"] = round(ret, 4)
        else:
            result[f"return_{period}d"] = None
    return result


# ---------------------------------------------------------------------------
# Backfill
# ---------------------------------------------------------------------------


def backfill_all_forward_returns(max_symbols: int = 200) -> dict:
    """Compute and cache forward returns for all historical analysis signals.

    Skips rows that are already cached in signal_returns.  Fetches price
    history per symbol (one yfinance call per symbol) to minimise API calls.

    Returns a summary dict: {processed, skipped, errors}.
    """
    signals = get_all_analysis_signals()
    cached = {(r["symbol"], r["signal_date"]) for r in get_signal_returns()}

    # Group signals by symbol to fetch prices once per symbol
    by_symbol: dict[str, list[dict]] = {}
    for row in signals:
        sym = row["symbol"]
        if len(by_symbol) >= max_symbols and sym not in by_symbol:
            continue
        by_symbol.setdefault(sym, []).append(row)

    processed = 0
    skipped = 0
    errors = 0
    today_str = datetime.utcnow().strftime("%Y-%m-%d")

    for sym, rows in by_symbol.items():
        # Only fetch prices if there are uncached rows that need future data
        uncached = [r for r in rows if (sym, r["date"]) not in cached]
        if not uncached:
            skipped += len(rows)
            continue

        prices = _fetch_close_prices(sym)
        if not prices:
            errors += len(uncached)
            continue

        for row in uncached:
            signal_date = row["date"]
            # Skip signals from the last 126 days — forward window not yet closed
            try:
                sig_dt = datetime.strptime(signal_date, "%Y-%m-%d")
            except ValueError:
                errors += 1
                continue
            days_since = (datetime.strptime(today_str, "%Y-%m-%d") - sig_dt).days
            price_at_signal = row.get("price")

            rets = compute_forward_return(sym, signal_date, price_at_signal or 0, prices)
            # Only store if we have at least one return value, or the signal is
            # old enough that we expect data (>126 days ago)
            if days_since > 21 or any(v is not None for v in rets.values()):
                upsert_signal_return(
                    symbol=sym,
                    signal_date=signal_date,
                    signal_score=row.get("factor_score"),
                    price_at_signal=price_at_signal,
                    return_21d=rets.get("return_21d"),
                    return_63d=rets.get("return_63d"),
                    return_126d=rets.get("return_126d"),
                )
                processed += 1
            else:
                skipped += 1

        time.sleep(0.1)  # gentle rate limit between symbols

    log.info(
        "backfill_all_forward_returns: processed=%d skipped=%d errors=%d",
        processed,
        skipped,
        errors,
    )
    return {"processed": processed, "skipped": skipped, "errors": errors}


# ---------------------------------------------------------------------------
# Quartile analysis
# ---------------------------------------------------------------------------


def compute_quartile_analysis(horizon_days: int = 63) -> dict:
    """Bucket factor scores into quartiles and return median return per quartile.

    Parameters
    ----------
    horizon_days : one of 21, 63, 126

    Returns
    -------
    dict with keys:
        quartiles    — list of 4 dicts: {label, median_return, mean_return, count, score_range}
        sample_size  — total rows used
        horizon_days — echoed back
    """
    col = f"return_{horizon_days}d"
    rows = [
        r for r in get_signal_returns() if r.get("signal_score") is not None and r.get(col) is not None
    ]

    if len(rows) < 4:
        return {"quartiles": [], "sample_size": len(rows), "horizon_days": horizon_days}

    try:
        import numpy as np

        scores = np.array([r["signal_score"] for r in rows], dtype=float)
        returns = np.array([r[col] for r in rows], dtype=float)

        q25, q50, q75 = np.percentile(scores, [25, 50, 75])
        boundaries = [scores.min(), q25, q50, q75, scores.max()]
        labels = ["Q1 (Lowest)", "Q2", "Q3", "Q4 (Highest)"]
        quartiles = []
        for i, label in enumerate(labels):
            lo, hi = boundaries[i], boundaries[i + 1]
            if i == len(labels) - 1:
                mask = (scores >= lo) & (scores <= hi)
            else:
                mask = (scores >= lo) & (scores < hi)
            q_returns = returns[mask]
            q_scores = scores[mask]
            if len(q_returns) == 0:
                quartiles.append(
                    {
                        "label": label,
                        "median_return": None,
                        "mean_return": None,
                        "count": 0,
                        "score_range": f"{lo:.0f}–{hi:.0f}",
                    }
                )
            else:
                quartiles.append(
                    {
                        "label": label,
                        "median_return": round(float(np.median(q_returns)), 2),
                        "mean_return": round(float(np.mean(q_returns)), 2),
                        "count": int(len(q_returns)),
                        "score_range": f"{q_scores.min():.0f}–{q_scores.max():.0f}",
                    }
                )
        return {
            "quartiles": quartiles,
            "sample_size": len(rows),
            "horizon_days": horizon_days,
        }
    except Exception as exc:
        log.warning("compute_quartile_analysis failed: %s", exc)
        return {"quartiles": [], "sample_size": 0, "horizon_days": horizon_days}


# ---------------------------------------------------------------------------
# Spearman correlations
# ---------------------------------------------------------------------------


def compute_spearman_correlations() -> list[dict]:
    """Compute Spearman rank correlation between factor_score and forward return.

    Returns a list of dicts, one per horizon:
        [{horizon_days, correlation, p_value, sample_size, significant}, ...]
    """
    rows = get_signal_returns()
    results = []

    try:
        from scipy.stats import spearmanr
        import numpy as np

        for period in _PERIODS:
            col = f"return_{period}d"
            valid = [
                (r["signal_score"], r[col])
                for r in rows
                if r.get("signal_score") is not None and r.get(col) is not None
            ]
            if len(valid) < 5:
                results.append(
                    {
                        "horizon_days": period,
                        "correlation": None,
                        "p_value": None,
                        "sample_size": len(valid),
                        "significant": False,
                    }
                )
                continue

            s = np.array([v[0] for v in valid], dtype=float)
            r = np.array([v[1] for v in valid], dtype=float)
            corr, pval = spearmanr(s, r)
            results.append(
                {
                    "horizon_days": period,
                    "correlation": round(float(corr), 4),
                    "p_value": round(float(pval), 4),
                    "sample_size": len(valid),
                    "significant": float(pval) < 0.05,
                }
            )
    except Exception as exc:
        log.warning("compute_spearman_correlations failed: %s", exc)
        for period in _PERIODS:
            results.append(
                {
                    "horizon_days": period,
                    "correlation": None,
                    "p_value": None,
                    "sample_size": 0,
                    "significant": False,
                }
            )

    return results


# ---------------------------------------------------------------------------
# IC trend (rolling information coefficient)
# ---------------------------------------------------------------------------


def compute_ic_trend(horizon_days: int = 63, window_months: int = 12) -> dict:
    """Compute rolling monthly IC between factor_score and forward returns.

    Returns
    -------
    dict with:
        months      — list of YYYY-MM strings
        ic_values   — list of IC floats (None where insufficient data)
        trend       — "Improving" | "Stable" | "Degrading" | "Insufficient data"
        latest_ic   — most recent IC value or None
    """
    col = f"return_{horizon_days}d"
    rows = [
        r
        for r in get_signal_returns()
        if r.get("signal_score") is not None and r.get(col) is not None
    ]

    if len(rows) < 10:
        return {
            "months": [],
            "ic_values": [],
            "trend": "Insufficient data",
            "latest_ic": None,
        }

    try:
        from scipy.stats import spearmanr
        import numpy as np

        # Group rows by year-month
        monthly: dict[str, list[tuple[float, float]]] = {}
        for r in rows:
            ym = r["signal_date"][:7]  # YYYY-MM
            monthly.setdefault(ym, []).append((float(r["signal_score"]), float(r[col])))

        sorted_months = sorted(monthly.keys())
        months_out: list[str] = []
        ic_out: list[float | None] = []

        for ym in sorted_months:
            pairs = monthly[ym]
            if len(pairs) < 3:
                months_out.append(ym)
                ic_out.append(None)
                continue
            s = np.array([p[0] for p in pairs])
            r_arr = np.array([p[1] for p in pairs])
            try:
                corr, _ = spearmanr(s, r_arr)
                ic_out.append(round(float(corr), 4))
            except Exception:
                ic_out.append(None)
            months_out.append(ym)

        # Determine trend from last 6 valid IC values
        valid_ics = [v for v in ic_out if v is not None]
        latest_ic = valid_ics[-1] if valid_ics else None
        trend = "Insufficient data"
        if len(valid_ics) >= 6:
            recent = valid_ics[-6:]
            first_half = sum(recent[:3]) / 3
            second_half = sum(recent[3:]) / 3
            diff = second_half - first_half
            if diff > 0.05:
                trend = "Improving"
            elif diff < -0.05:
                trend = "Degrading"
            else:
                trend = "Stable"

        return {
            "months": months_out,
            "ic_values": ic_out,
            "trend": trend,
            "latest_ic": latest_ic,
        }
    except Exception as exc:
        log.warning("compute_ic_trend failed: %s", exc)
        return {
            "months": [],
            "ic_values": [],
            "trend": "Insufficient data",
            "latest_ic": None,
        }


# ---------------------------------------------------------------------------
# Summary badge
# ---------------------------------------------------------------------------


def get_signal_quality_summary() -> dict:
    """Return a compact summary suitable for the main dashboard badge.

    Keys: sample_size, latest_ic_63d, ic_trend, top_quartile_return_63d,
          spearman_63d, spearman_63d_significant, has_data
    """
    rows = get_signal_returns()
    if not rows:
        return {"has_data": False}

    ic = compute_ic_trend(horizon_days=63)
    corrs = compute_spearman_correlations()
    q = compute_quartile_analysis(horizon_days=63)

    corr_63 = next((c for c in corrs if c["horizon_days"] == 63), {})

    top_quartile_return = None
    if q.get("quartiles") and len(q["quartiles"]) == 4:
        top_quartile_return = q["quartiles"][-1].get("median_return")

    return {
        "has_data": True,
        "sample_size": len(rows),
        "latest_ic_63d": ic.get("latest_ic"),
        "ic_trend": ic.get("trend", "Insufficient data"),
        "top_quartile_return_63d": top_quartile_return,
        "spearman_63d": corr_63.get("correlation"),
        "spearman_63d_significant": corr_63.get("significant", False),
    }
