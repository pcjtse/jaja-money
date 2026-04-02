"""Per-factor IC Attribution Module.

Computes Spearman Information Coefficient (IC) for each of the 23 factors
against T+21/T+63/T+126 trading-day forward returns stored in signal_returns.

Usage:
    from src.analysis.factor_attribution import build_attribution_dataset, get_attribution_report

    base_df, oldest_date = build_attribution_dataset()
    report = get_attribution_report(base_df, "return_63d")
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from src.core.log_setup import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# 8 always-present core factors.
# Names must EXACTLY match the `name` field returned by each _factor_*()
# function in factors.py. Verified against factors.py source (commit c9c2461).
CORE_FACTOR_NAMES: dict[str, str] = {
    "Valuation (P/E)": "valuation",
    "Trend (SMA)": "trend",
    "Momentum (RSI)": "rsi",
    "MACD Signal": "macd",
    "News Sentiment": "sentiment",
    "Earnings Quality": "earnings",
    "Analyst Consensus": "analyst",
    "52-Wk Strength": "range",
}

# 15 alpha signals — sparse, vary per ticker.
# Names verified against factors.py source (commit c9c2461).
# KNOWN BUG: ml_weights.py uses stale names that don't match these.
# See TODOS.md TODO-001 for the fix.
ALPHA_FACTOR_NAMES: dict[str, str] = {
    "Dividend Yield": "dividend_yield",
    "Estimate Revisions": "estimate_revisions",
    "Alt Data Signal": "alt_data",  # NOT "Alternative Data"
    "Congress Signal": "congressional",  # NOT "Congressional Trading"
    "Institutional Flow": "institutional_flow",
    "Estimate Velocity": "estimate_velocity",
    "Buyback Effectiveness": "buyback",  # NOT "Buyback Signal"
    "Guidance Quality": "guidance_quality",
    "Options Flow": "options_flow",
    "Dark Pool Signal": "dark_pool",  # NOT "Dark Pool Activity"
    "Supply Chain Risk": "supply_chain",
    "Special Situation": "special_situation",
    "Cross-Asset Signal": "cross_asset",
    "Geo Revenue Macro": "geo_revenue",  # NOT "Geographic Revenue"
    "Market Regime": "regime",
}

ALL_FACTOR_NAMES: dict[str, str] = {**CORE_FACTOR_NAMES, **ALPHA_FACTOR_NAMES}

# Absence detection: factor functions return score=50 with label="No data"
# when data is unavailable. Do NOT use score==50 as the absence signal —
# a genuine neutral score of 50 is valid. See TODOS.md TODO-003 for plan
# to enforce this convention with a FACTOR_ABSENT_LABEL constant in factors.py.
ABSENT_LABEL: str = "No data"

VALID_HORIZONS: frozenset[str] = frozenset({"return_21d", "return_63d", "return_126d"})


# ---------------------------------------------------------------------------
# Internal parser
# ---------------------------------------------------------------------------


def _parse_all_factor_scores(factors_json: str | list) -> dict[str, float | None]:
    """Parse factors_json and return {col_key: score_or_None} for all 23 factors.

    Returns {} on malformed JSON — the row will be all-NaN in the DataFrame.
    Returns None for a factor when label == ABSENT_LABEL, meaning the data
    source was genuinely unavailable, not that the score happened to be 50.
    """
    result: dict[str, float | None] = {}
    try:
        items = (
            json.loads(factors_json) if isinstance(factors_json, str) else factors_json
        )
        for item in items:
            name = item.get("name", "")
            key = ALL_FACTOR_NAMES.get(name)
            if key is None:
                continue
            label = item.get("label", "")
            score = item.get("score")
            if label == ABSENT_LABEL or score is None:
                result[key] = None
            else:
                result[key] = float(score)
    except Exception:
        pass
    return result


# ---------------------------------------------------------------------------
# Dataset builder
# ---------------------------------------------------------------------------


def build_attribution_dataset() -> tuple[pd.DataFrame, str | None]:
    """Load and join analysis_history + signal_returns into a single DataFrame.

    Returns (base_df, oldest_analysis_date).
    base_df has 23 factor columns (NaN for absent sparse signals) + 3 return columns.
    Returns (empty DataFrame, None) when no joined rows exist.
    """
    from src.data.history import get_attributed_analysis_rows

    raw_rows = get_attributed_analysis_rows()
    if not raw_rows:
        return pd.DataFrame(), None

    records = []
    oldest_date: str | None = None

    for row in raw_rows:
        scores = _parse_all_factor_scores(row["factors_json"])
        record: dict = {
            "symbol": row["symbol"],
            "date": row["date"],
            "return_21d": row["return_21d"],
            "return_63d": row["return_63d"],
            "return_126d": row["return_126d"],
        }
        for key in ALL_FACTOR_NAMES.values():
            record[key] = scores.get(key)  # None if absent
        records.append(record)
        if oldest_date is None or row["date"] < oldest_date:
            oldest_date = row["date"]

    base_df = pd.DataFrame(records)
    return base_df, oldest_date


# ---------------------------------------------------------------------------
# IC computation
# ---------------------------------------------------------------------------


def compute_factor_ic(df: pd.DataFrame, factor_col: str, return_col: str) -> dict:
    """Compute Spearman IC for a single factor vs a single return horizon.

    Parameters
    ----------
    df : base DataFrame from build_attribution_dataset()
    factor_col : column name (e.g. "valuation") — must be in df
    return_col : must be one of VALID_HORIZONS

    Returns a dict with: ic, n, ci_lo, ci_hi, sufficient, pval, warning.
    Raises ValueError if return_col is not in VALID_HORIZONS.
    """
    if return_col not in VALID_HORIZONS:
        raise ValueError(
            f"return_col must be one of {VALID_HORIZONS}, got {return_col!r}"
        )

    if factor_col not in df.columns or return_col not in df.columns:
        return {
            "ic": None,
            "n": 0,
            "ci_lo": None,
            "ci_hi": None,
            "sufficient": False,
            "pval": None,
            "warning": "n < 10 — no IC computed",
        }

    valid = df[[factor_col, return_col]].dropna()
    n = len(valid)

    if n < 10:
        return {
            "ic": None,
            "n": n,
            "ci_lo": None,
            "ci_hi": None,
            "sufficient": False,
            "pval": None,
            "warning": "n < 10 — no IC computed",
        }

    ic, pval = spearmanr(valid[factor_col], valid[return_col])

    # Perfect rank correlation makes arctanh undefined
    if abs(ic) >= 1.0:
        return {
            "ic": float(ic),
            "n": n,
            "ci_lo": None,
            "ci_hi": None,
            "sufficient": n >= 30,
            "pval": float(pval),
            "warning": "perfect rank correlation — CI undefined",
        }

    # Fisher z-transform 95% CI for Spearman. n >= 10 ensures n - 3 >= 7.
    z = np.arctanh(ic)
    se = 1.0 / np.sqrt(n - 3)
    ci_lo = float(np.tanh(z - 1.96 * se))
    ci_hi = float(np.tanh(z + 1.96 * se))

    warning = "n < 30 — interpret with caution" if n < 30 else None
    return {
        "ic": float(ic),
        "n": n,
        "ci_lo": ci_lo,
        "ci_hi": ci_hi,
        "sufficient": n >= 30,
        "pval": float(pval),
        "warning": warning,
    }


# ---------------------------------------------------------------------------
# Attribution report
# ---------------------------------------------------------------------------


def get_attribution_report(base_df: pd.DataFrame, horizon: str = "return_63d") -> dict:
    """Build the full IC attribution report for a given return horizon.

    Parameters
    ----------
    base_df : output of build_attribution_dataset()
    horizon : one of VALID_HORIZONS

    Returns a dict with keys: horizon, core, alpha, total_rows,
    oldest_analysis_date, generated_at. Raises ValueError for invalid horizon.

    BH p-value correction is applied across all sufficient factors.
    Requires scipy >= 1.11; falls back to unadjusted p-values on older scipy.
    """
    if horizon not in VALID_HORIZONS:
        raise ValueError(f"horizon must be one of {VALID_HORIZONS}, got {horizon!r}")

    total_rows = len(base_df)
    oldest_date: str | None = None
    if total_rows > 0 and "date" in base_df.columns:
        oldest_date = str(base_df["date"].min())

    # Compute IC for all 23 factors
    all_results: dict[str, dict] = {}
    for col_key in ALL_FACTOR_NAMES.values():
        all_results[col_key] = compute_factor_ic(base_df, col_key, horizon)

    # Benjamini-Hochberg p-value adjustment across sufficient factors
    sufficient_keys = [
        k for k, r in all_results.items() if r["sufficient"] and r["pval"] is not None
    ]
    if len(sufficient_keys) >= 2:
        try:
            from scipy.stats import false_discovery_control

            pvals = [all_results[k]["pval"] for k in sufficient_keys]
            adjusted = false_discovery_control(pvals, method="bh")
            for k, adj_p in zip(sufficient_keys, adjusted):
                all_results[k]["pval_adjusted"] = float(adj_p)
        except AttributeError:
            pass  # scipy < 1.11 — unadjusted p-values remain

    core = {col_key: all_results[col_key] for col_key in CORE_FACTOR_NAMES.values()}
    alpha = {col_key: all_results[col_key] for col_key in ALPHA_FACTOR_NAMES.values()}

    return {
        "horizon": horizon,
        "core": core,
        "alpha": alpha,
        "total_rows": total_rows,
        "oldest_analysis_date": oldest_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
