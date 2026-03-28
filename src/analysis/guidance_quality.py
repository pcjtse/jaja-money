"""Earnings Guidance Quality Scorecard.

Scores management's guidance quality based on:
  1. Historical accuracy: did prior guidance match actual results?
  2. Conservatism: does management tend to under-promise and over-deliver?
  3. Specificity: precise numbers vs. vague ranges?

Data comes from the earnings history already tracked in the system.
"""

from __future__ import annotations

from src.core.log_setup import get_logger

log = get_logger(__name__)


def compute_guidance_quality_score(
    earnings: list,
    financials: dict | None = None,
) -> dict:
    """Score guidance quality from earnings surprise history.

    Uses the pattern of earnings beats/misses as a proxy for
    management's track record of conservative vs. aggressive guidance.

    Parameters
    ----------
    earnings  : list of earnings dicts from FinnhubAPI.get_earnings()
                Each has: actual, estimate, period, surprise, surprisePercent
    financials: optional dict with revenueGrowthTTMYoy or other guidance metrics

    Returns
    -------
    dict with keys:
        score (int): 0-100 guidance quality score
        label (str)
        beat_rate (float): fraction of periods with positive surprise
        avg_surprise_pct (float): average earnings surprise %
        consecutive_beats (int): current streak of beats
        detail (str)
    """
    if not earnings:
        return {
            "score": 50,
            "label": "No guidance history",
            "beat_rate": 0.5,
            "avg_surprise_pct": 0.0,
            "consecutive_beats": 0,
            "detail": "Insufficient earnings history for guidance quality scoring",
        }

    # Filter to records with actual vs estimate data
    valid = []
    for e in earnings:
        actual = e.get("actual")
        estimate = e.get("estimate")
        if actual is not None and estimate is not None:
            try:
                valid.append({
                    "actual": float(actual),
                    "estimate": float(estimate),
                    "surprise_pct": e.get("surprisePercent"),
                })
            except (TypeError, ValueError):
                continue

    if not valid:
        return {
            "score": 50,
            "label": "No valid earnings data",
            "beat_rate": 0.5,
            "avg_surprise_pct": 0.0,
            "consecutive_beats": 0,
            "detail": "No actual vs. estimate data available",
        }

    beats = [v for v in valid if v["actual"] >= v["estimate"]]
    beat_rate = len(beats) / len(valid)

    surprise_pcts = [
        v["surprise_pct"] for v in valid if v.get("surprise_pct") is not None
    ]
    avg_surprise = round(sum(surprise_pcts) / len(surprise_pcts), 2) if surprise_pcts else 0.0

    # Consecutive beats from most recent
    consecutive_beats = 0
    for v in valid:
        if v["actual"] >= v["estimate"]:
            consecutive_beats += 1
        else:
            break

    consecutive_misses = 0
    for v in valid:
        if v["actual"] < v["estimate"]:
            consecutive_misses += 1
        else:
            break

    # Score: beat rate + avg surprise magnitude
    base = int(beat_rate * 70)  # 0-70 from beat rate

    if avg_surprise > 5:
        base += 20
    elif avg_surprise > 2:
        base += 12
    elif avg_surprise > 0:
        base += 6
    elif avg_surprise < -5:
        base -= 20
    elif avg_surprise < -2:
        base -= 12

    # Streak bonus / penalty
    if consecutive_beats >= 4:
        base += 10
    elif consecutive_beats >= 2:
        base += 5
    if consecutive_misses >= 3:
        base -= 10
    elif consecutive_misses >= 2:
        base -= 5

    score = max(0, min(100, base))

    if score >= 80:
        label = "Excellent — consistent beat & raise"
    elif score >= 65:
        label = "Good — mostly beats consensus"
    elif score >= 45:
        label = "Average guidance quality"
    elif score >= 30:
        label = "Below average — frequent misses"
    else:
        label = "Poor — persistent guide-down pattern"

    detail = (
        f"Beat rate: {beat_rate:.0%} ({len(beats)}/{len(valid)}) | "
        f"Avg surprise: {avg_surprise:+.1f}% | "
        f"Current streak: {consecutive_beats} beats"
    )

    return {
        "score": score,
        "label": label,
        "beat_rate": round(beat_rate, 4),
        "avg_surprise_pct": avg_surprise,
        "consecutive_beats": consecutive_beats,
        "detail": detail,
    }
