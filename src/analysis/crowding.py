"""Factor Crowding Risk Monitor.

Detects when a stock's factor profile is concentrated in factors that are
currently "crowded" — widely held by factor-investing funds. Crowded factors
reverse violently when unwinding occurs.

Method: compare the stock's factor score vector to the cross-sectional
distribution of scores in the ranking history. High similarity to the
"consensus top pick" profile = crowding risk.
"""

from __future__ import annotations

import math
import sqlite3
from pathlib import Path

from src.core.log_setup import get_logger

log = get_logger(__name__)

_DATA_DIR = Path.home() / ".jaja-money"
_DB_FILE = _DATA_DIR / "history.db"


def _connect() -> sqlite3.Connection:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_FILE))
    conn.row_factory = sqlite3.Row
    return conn


def compute_factor_crowding(
    symbol: str,
    current_factors: list[dict],
) -> dict:
    """Compute a crowding risk score for a stock.

    Compares the stock's factor profile to the cross-sectional "top-decile
    consensus" profile stored in the rankings history. High cosine similarity
    = the stock looks like everyone's top pick = crowding risk.

    Parameters
    ----------
    symbol         : stock ticker
    current_factors: list of factor dicts from compute_factors()

    Returns
    -------
    dict with keys:
        crowding_score (float): 0.0-1.0 (1.0 = maximally crowded)
        risk_level (str): "Low" | "Moderate" | "High" | "Extreme"
        penalty (int): suggested score penalty (0-15)
        detail (str)
    """
    factor_vector = _extract_factor_vector(current_factors)
    if not factor_vector:
        return _no_crowding_data()

    centroid = _get_top_decile_centroid()
    if not centroid:
        return _no_crowding_data()

    similarity = _cosine_similarity(factor_vector, centroid)
    return _classify_crowding(similarity)


def _extract_factor_vector(factors: list[dict]) -> list[float] | None:
    """Convert factors list to a normalized score vector."""
    if not factors:
        return None
    scores = [float(f.get("score", 50)) for f in factors]
    if not scores:
        return None
    # Normalize to 0-1
    return [s / 100.0 for s in scores]


def _get_top_decile_centroid() -> list[float] | None:
    """Get the average factor vector of the top-decile stocks from ranking history."""
    try:
        import json

        with _connect() as conn:
            rows = conn.execute(
                """SELECT factors_json FROM analysis_history
                   WHERE factor_score >= 75
                   ORDER BY timestamp DESC
                   LIMIT 100"""
            ).fetchall()

        if not rows:
            return None

        all_vectors: list[list[float]] = []
        for row in rows:
            fj = row.get("factors_json") or row["factors_json"]
            if not fj:
                continue
            try:
                factors = json.loads(fj)
                vec = [float(f.get("score", 50)) / 100.0 for f in factors if f.get("score") is not None]
                if vec:
                    all_vectors.append(vec)
            except (json.JSONDecodeError, TypeError):
                continue

        if not all_vectors:
            return None

        # Truncate/pad to common length
        min_len = min(len(v) for v in all_vectors)
        all_vectors = [v[:min_len] for v in all_vectors]

        # Compute centroid (mean vector)
        centroid = [
            sum(v[i] for v in all_vectors) / len(all_vectors)
            for i in range(min_len)
        ]
        return centroid
    except Exception as exc:
        log.debug("Crowding centroid computation failed: %s", exc)
        return None


def _cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    min_len = min(len(v1), len(v2))
    if min_len == 0:
        return 0.0
    v1, v2 = v1[:min_len], v2[:min_len]

    dot = sum(a * b for a, b in zip(v1, v2))
    mag1 = math.sqrt(sum(a * a for a in v1))
    mag2 = math.sqrt(sum(b * b for b in v2))

    if mag1 == 0 or mag2 == 0:
        return 0.0
    return round(dot / (mag1 * mag2), 4)


def _classify_crowding(similarity: float) -> dict:
    if similarity >= 0.92:
        risk_level = "Extreme"
        penalty = 15
    elif similarity >= 0.82:
        risk_level = "High"
        penalty = 10
    elif similarity >= 0.70:
        risk_level = "Moderate"
        penalty = 5
    else:
        risk_level = "Low"
        penalty = 0

    detail = (
        f"Factor crowding similarity: {similarity:.2f} | "
        f"Risk: {risk_level} | Penalty: -{penalty} pts"
    )

    return {
        "crowding_score": similarity,
        "risk_level": risk_level,
        "penalty": penalty,
        "detail": detail,
    }


def _no_crowding_data() -> dict:
    return {
        "crowding_score": 0.0,
        "risk_level": "Unknown",
        "penalty": 0,
        "detail": "Insufficient history for crowding analysis",
    }
