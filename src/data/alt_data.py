"""Alternative Data Signals — Feature 21.5.

Provides Google Trends search-interest and job-posting velocity signals
as leading indicators that complement the core financial factor model.

Both signals are optional: if the required libraries or APIs are
unavailable, each function returns ``{"available": False}`` so the
caller can degrade gracefully (factor scored as neutral 50).
"""

from __future__ import annotations

import time

import numpy as np

from src.core.log_setup import get_logger

log = get_logger(__name__)

# Cache TTL: 6 hours — alt data changes slowly
_ALT_DATA_TTL = 6 * 3600


# ---------------------------------------------------------------------------
# Google Trends
# ---------------------------------------------------------------------------


def fetch_google_trends(keyword: str, timeframe: str = "today 3-m") -> dict:
    """Fetch Google Trends interest-over-time for *keyword*.

    Parameters
    ----------
    keyword:
        Search term, e.g. ``"Apple Inc"`` or ``"iPhone"``.
    timeframe:
        pytrends timeframe string.  Defaults to last 3 months weekly.

    Returns
    -------
    dict with keys:
        available (bool)
        values (list[int])   – weekly relative interest 0-100
        slope (float)        – linear trend slope (positive = accelerating)
        score (int)          – normalised 0-100 factor score
        detail (str)
    """
    try:
        from pytrends.request import TrendReq  # optional dep
    except ImportError:
        log.debug("pytrends not installed — Google Trends signal unavailable")
        return {"available": False, "detail": "pytrends not installed"}

    try:
        pt = TrendReq(hl="en-US", tz=0, timeout=(10, 25))
        pt.build_payload([keyword], timeframe=timeframe)
        df = pt.interest_over_time()

        if df is None or df.empty or keyword not in df.columns:
            return {"available": False, "detail": "No Trends data returned"}

        values = [int(v) for v in df[keyword].tolist()]
        if not values:
            return {"available": False, "detail": "Empty Trends series"}

        # Linear slope over the series (normalised by mean to get % change / period)
        x = np.arange(len(values), dtype=float)
        mean_val = float(np.mean(values)) or 1.0
        slope = (
            float(np.polyfit(x, values, 1)[0]) / mean_val
        )  # slope as fraction of mean

        # Score: neutral=50, each 1% per-period slope adds/subtracts ~10 pts (capped)
        raw_score = 50.0 + slope * 1000.0
        score = int(max(0, min(100, raw_score)))

        if slope > 0.02:
            direction, label = "accelerating", "Accelerating interest"
        elif slope < -0.02:
            direction, label = "decelerating", "Decelerating interest"
        else:
            direction, label = "stable", "Stable interest"

        recent = values[-1] if values else 0
        detail = (
            f"Google Trends: {direction} | "
            f"Recent interest: {recent}/100 | "
            f"90-day slope: {slope:+.3f}"
        )

        return {
            "available": True,
            "values": values,
            "slope": slope,
            "score": score,
            "label": label,
            "detail": detail,
        }

    except Exception as exc:
        log.warning("Google Trends fetch failed for '%s': %s", keyword, exc)
        return {"available": False, "detail": f"Trends fetch error: {exc}"}


# ---------------------------------------------------------------------------
# Job Posting Velocity (Adzuna free-tier)
# ---------------------------------------------------------------------------


def fetch_job_posting_velocity(company_name: str) -> dict:
    """Fetch job posting velocity for *company_name* via Adzuna free API.

    Counts listings in the last 30 days vs. the prior 30 days (days 31-60)
    to compute a velocity (% change).  Falls back gracefully if the API is
    unreachable or returns no results.

    Returns
    -------
    dict with keys:
        available (bool)
        recent_count (int)    – postings in last 30 days
        prior_count (int)     – postings in days 31-60
        velocity_pct (float)  – % change (positive = hiring acceleration)
        score (int)           – normalised 0-100 factor score
        detail (str)
    """
    try:
        import requests  # always available in requirements
    except ImportError:
        return {"available": False, "detail": "requests not installed"}

    base_url = "https://api.adzuna.com/v1/api/jobs/us/search/1"
    # Adzuna allows anonymous access with app_id/app_key from env; fall back
    # to a public demo key if absent.
    import os

    app_id = os.getenv("ADZUNA_APP_ID", "")
    app_key = os.getenv("ADZUNA_APP_KEY", "")

    if not app_id or not app_key:
        log.debug("ADZUNA_APP_ID/KEY not set — job posting signal unavailable")
        return {"available": False, "detail": "Adzuna API credentials not configured"}

    def _count(days_from: int, days_to: int) -> int:
        """Return posting count in a date window relative to today."""
        now = int(time.time())
        date_from = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - days_to * 86400)
        )
        date_to = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - days_from * 86400)
        )
        params = {
            "app_id": app_id,
            "app_key": app_key,
            "what_company": company_name,
            "date_from": date_from,
            "date_to": date_to,
            "results_per_page": 1,  # we only need the count header
        }
        resp = requests.get(base_url, params=params, timeout=10)
        resp.raise_for_status()
        return int(resp.json().get("count", 0))

    try:
        recent = _count(0, 30)
        prior = _count(30, 60)

        if prior == 0 and recent == 0:
            return {"available": False, "detail": "No job postings found"}

        velocity = (recent - prior) / max(prior, 1) * 100.0  # % change

        # Score: neutral=50, ±1% velocity → ±0.5 pts (capped)
        raw_score = 50.0 + velocity * 0.5
        score = int(max(0, min(100, raw_score)))

        if velocity > 20:
            label = "Rapid hiring"
        elif velocity > 5:
            label = "Hiring growth"
        elif velocity < -20:
            label = "Significant layoffs"
        elif velocity < -5:
            label = "Hiring slowdown"
        else:
            label = "Stable headcount"

        detail = (
            f"Job postings: {recent} (last 30d) vs {prior} (prior 30d) | "
            f"Velocity: {velocity:+.1f}%"
        )

        return {
            "available": True,
            "recent_count": recent,
            "prior_count": prior,
            "velocity_pct": velocity,
            "score": score,
            "label": label,
            "detail": detail,
        }

    except Exception as exc:
        log.warning("Job posting fetch failed for '%s': %s", company_name, exc)
        return {"available": False, "detail": f"Job posting fetch error: {exc}"}


# ---------------------------------------------------------------------------
# Combined signal
# ---------------------------------------------------------------------------


def compute_alt_data_signals(
    symbol: str,
    company_name: str,
    trends_weight: float = 0.5,
    jobs_weight: float = 0.5,
) -> dict:
    """Compute combined alternative data signal for *symbol*.

    Fetches Google Trends and job posting velocity, normalises each to 0-100,
    then combines them with *trends_weight* / *jobs_weight*.  If only one
    source is available it is used at full weight.

    Parameters
    ----------
    symbol:
        Ticker symbol (used as a search hint and cache key).
    company_name:
        Human-readable company name for job posting and Trends searches.
    trends_weight, jobs_weight:
        Relative weights for each sub-signal (will be normalised).

    Returns
    -------
    dict with keys:
        available (bool)
        score (int)       – combined 0-100 factor score
        label (str)
        detail (str)
        trends (dict)     – raw Google Trends result
        jobs (dict)       – raw job posting result
    """
    trends = fetch_google_trends(company_name)
    jobs = fetch_job_posting_velocity(company_name)

    t_avail = trends.get("available", False)
    j_avail = jobs.get("available", False)

    if not t_avail and not j_avail:
        return {
            "available": False,
            "score": 50,
            "label": "No data",
            "detail": "Alternative data unavailable — scored as neutral",
            "trends": trends,
            "jobs": jobs,
        }

    # Weighted average of whichever signals are available
    total_w = 0.0
    weighted_sum = 0.0
    if t_avail:
        total_w += trends_weight
        weighted_sum += trends["score"] * trends_weight
    if j_avail:
        total_w += jobs_weight
        weighted_sum += jobs["score"] * jobs_weight

    combined_score = int(weighted_sum / total_w) if total_w > 0 else 50

    parts = []
    if t_avail:
        parts.append(f"Trends: {trends.get('label', '—')} ({trends['score']}/100)")
    if j_avail:
        parts.append(f"Jobs: {jobs.get('label', '—')} ({jobs['score']}/100)")

    if combined_score >= 65:
        label = "Positive alt signal"
    elif combined_score <= 35:
        label = "Negative alt signal"
    else:
        label = "Neutral alt signal"

    return {
        "available": True,
        "score": combined_score,
        "label": label,
        "detail": " | ".join(parts),
        "trends": trends,
        "jobs": jobs,
    }
