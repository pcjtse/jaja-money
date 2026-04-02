"""ML-Trained Adaptive Factor Weights (21.1).

Replaces the static hardcoded factor weights with a logistic-regression model
trained on historical (symbol, date, factor_scores) → forward-return data.

Walk-forward protocol
---------------------
At each quarterly rebalance date, fit on all data before that date and
evaluate on the next quarter's data.  The final live weights are taken from
a model trained on *all* available data.

Fallback
--------
If fewer than MIN_SAMPLES labelled rows exist, or if training raises any
exception, cfg.factor_weights is returned unchanged.

Public API
----------
get_adaptive_weights()       -> dict[str, float]
get_weights_metadata()       -> dict   (for UI display)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_SAMPLES = 30  # minimum labelled rows before ML is attempted
FORWARD_DAYS = 63  # ~3-month forward return horizon
RETRAIN_EVERY_DAYS = 90  # quarterly retraining cadence

# Canonical factor weight key order (must match _get_weight calls in factors.py)
FACTOR_KEYS = [
    "valuation",
    "trend",
    "rsi",
    "macd",
    "sentiment",
    "earnings",
    "analyst",
    "range",
]

# Minimum weight floor so no factor is ever zeroed out
_MIN_WEIGHT = 0.02


# ---------------------------------------------------------------------------
# Dataset construction
# ---------------------------------------------------------------------------


def _parse_factors_json(factors_json: str) -> dict[str, float]:
    """Extract {factor_key: score} from a stored factors_json blob.

    Each element is a dict with at least 'name' and 'score' keys.
    We map the displayed name back to a canonical key using CORE_FACTOR_NAMES
    from factor_attribution.py so the mapping stays in sync.
    """
    from src.analysis.factor_attribution import CORE_FACTOR_NAMES

    name_to_key = CORE_FACTOR_NAMES  # {display_name: col_key}
    scores: dict[str, float] = {}
    try:
        items = (
            json.loads(factors_json) if isinstance(factors_json, str) else factors_json
        )
        for item in items:
            name = item.get("name", "")
            key = name_to_key.get(name)
            if key and "score" in item:
                scores[key] = float(item["score"])
    except Exception:
        pass
    if len(scores) < 4:
        log.debug(
            "_parse_factors_json: only %d factor names matched (expected >= 4); "
            "check display names in factors_json against CORE_FACTOR_NAMES",
            len(scores),
        )
    return scores


def build_training_dataset(
    snapshots: list[dict],
    forward_prices: dict[tuple[str, str], float],
) -> "list[dict]":
    """Build labelled training rows from snapshots + forward price map.

    Parameters
    ----------
    snapshots       : rows from get_all_factor_snapshots()
    forward_prices  : {(symbol, date): forward_price} mapping

    Returns
    -------
    list of dicts, each with FACTOR_KEYS columns + 'target' (0/1) + 'date'.
    Rows where the forward price is unavailable are dropped.
    """
    rows = []
    for snap in snapshots:
        symbol = snap["symbol"]
        date = snap["date"]
        price = snap.get("price")
        if not price or price <= 0:
            continue

        fwd_price = forward_prices.get((symbol, date))
        if fwd_price is None or fwd_price <= 0:
            continue

        factor_scores = _parse_factors_json(snap.get("factors_json", "[]"))
        # Only include rows where we have at least the core factors
        if len(factor_scores) < 6:
            continue

        row = {"date": date, "target": int(fwd_price > price)}
        for key in FACTOR_KEYS:
            val = factor_scores.get(key)
            row[key] = float(val) if val is not None else float("nan")
        rows.append(row)
    return rows


def fetch_forward_prices(
    snapshots: list[dict],
    forward_days: int = FORWARD_DAYS,
) -> "dict[tuple[str, str], float]":
    """Fetch T+forward_days closing prices for each (symbol, date) snapshot.

    Uses yfinance.  Gracefully skips tickers that fail.
    """
    try:
        import yfinance as yf
    except ImportError:
        log.warning("yfinance not installed — ML training unavailable")
        return {}

    # Group by symbol for batched downloads
    from collections import defaultdict
    import pandas as pd

    sym_dates: dict[str, list[str]] = defaultdict(list)
    for snap in snapshots:
        sym = snap["symbol"]
        date = snap["date"]
        sym_dates[sym].append(date)

    result: dict[tuple[str, str], float] = {}
    for sym, dates in sym_dates.items():
        try:
            # Find the date range we need to cover
            base_dates = [datetime.strptime(d, "%Y-%m-%d") for d in dates]
            min_date = min(base_dates)
            max_date = max(base_dates) + timedelta(days=forward_days + 10)
            ticker = yf.Ticker(sym)
            hist = ticker.history(
                start=min_date.strftime("%Y-%m-%d"),
                end=max_date.strftime("%Y-%m-%d"),
            )
            if hist.empty:
                continue
            close_series = hist["Close"]
            close_series.index = pd.to_datetime(close_series.index).tz_localize(None)
            for d in dates:
                target_dt = datetime.strptime(d, "%Y-%m-%d") + timedelta(
                    days=forward_days
                )
                # Find the nearest trading day on or after target_dt
                future = close_series[close_series.index >= target_dt]
                if future.empty:
                    continue
                result[(sym, d)] = float(future.iloc[0])
        except Exception as exc:
            log.debug("Forward price fetch failed for %s: %s", sym, exc)
    return result


# ---------------------------------------------------------------------------
# Walk-forward training
# ---------------------------------------------------------------------------


def _normalize_weights(raw: dict[str, float]) -> dict[str, float]:
    """Clip to minimum floor and normalize to sum=1."""
    clipped = {k: max(_MIN_WEIGHT, v) for k, v in raw.items()}
    total = sum(clipped.values())
    return {k: v / total for k, v in clipped.items()}


def extract_weights_from_model(model, feature_names: list[str]) -> dict[str, float]:
    """Convert logistic regression coefficients to a normalized weight dict.

    Negative coefficients indicate the factor is contrarian; we take the
    absolute value so every factor retains some influence, then normalize.
    """
    coef = model.coef_[0]
    raw = {name: abs(float(c)) for name, c in zip(feature_names, coef)}
    return _normalize_weights(raw)


def walk_forward_train(
    rows: list[dict],
    min_samples: int = MIN_SAMPLES,
) -> dict:
    """Fit a logistic regression walk-forward and return weights + metrics.

    Returns
    -------
    dict with keys:
        weights              – {factor_key: float}
        auc                  – float (mean OOS AUC across folds)
        precision_top_decile – float
        n_samples            – int
        source               – "ml"
    """
    if len(rows) < min_samples:
        raise ValueError(
            f"Insufficient data: {len(rows)} rows < MIN_SAMPLES={min_samples}"
        )

    try:
        import numpy as np
        import pandas as pd
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import roc_auc_score
        from sklearn.preprocessing import StandardScaler
    except ImportError as exc:
        raise RuntimeError(
            f"scikit-learn / numpy required for ML training: {exc}"
        ) from exc

    # Drop rows with NaN in any factor column before training
    df = pd.DataFrame(rows)
    df = df.dropna(subset=FACTOR_KEYS)
    rows = df.to_dict("records")

    if len(rows) < min_samples:
        raise ValueError(
            f"Insufficient data after dropna: {len(rows)} rows < MIN_SAMPLES={min_samples}"
        )

    # Sort chronologically
    rows_sorted = sorted(rows, key=lambda r: r["date"])
    dates = [r["date"] for r in rows_sorted]

    X = np.array([[r[k] for k in FACTOR_KEYS] for r in rows_sorted], dtype=float)
    y = np.array([r["target"] for r in rows_sorted], dtype=int)

    # Walk-forward: quarterly folds
    unique_quarters = sorted(
        {d[:7] for d in dates}  # YYYY-MM
    )

    oos_preds: list[float] = []
    oos_true: list[int] = []

    for i in range(4, len(unique_quarters)):
        train_cutoff = unique_quarters[i - 1]
        test_quarter = unique_quarters[i]

        train_mask = np.array([d[:7] <= train_cutoff for d in dates])
        test_mask = np.array([d[:7] == test_quarter for d in dates])

        if train_mask.sum() < min_samples or test_mask.sum() == 0:
            continue

        scaler = StandardScaler()
        X_train = scaler.fit_transform(X[train_mask])
        X_test = scaler.transform(X[test_mask])

        clf = LogisticRegression(max_iter=1000, random_state=42)
        clf.fit(X_train, y[train_mask])

        probs = clf.predict_proba(X_test)[:, 1]
        oos_preds.extend(probs.tolist())
        oos_true.extend(y[test_mask].tolist())

    # Final model trained on ALL data
    scaler_full = StandardScaler()
    X_scaled = scaler_full.fit_transform(X)
    final_clf = LogisticRegression(max_iter=1000, random_state=42)
    final_clf.fit(X_scaled, y)
    weights = extract_weights_from_model(final_clf, FACTOR_KEYS)

    # OOS metrics
    auc = 0.5
    prec_top = 0.5
    if len(oos_true) >= 10 and len(set(oos_true)) > 1:
        try:
            auc = float(roc_auc_score(oos_true, oos_preds))
            # precision@top-decile
            n_top = max(1, len(oos_preds) // 10)
            sorted_idx = sorted(range(len(oos_preds)), key=lambda i: -oos_preds[i])
            top_true = [oos_true[i] for i in sorted_idx[:n_top]]
            prec_top = float(sum(top_true) / len(top_true))
        except Exception:
            pass

    return {
        "weights": weights,
        "auc": round(auc, 4),
        "precision_top_decile": round(prec_top, 4),
        "n_samples": len(rows),
        "source": "ml",
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _static_weights() -> dict[str, float]:
    """Return static weights from config."""
    from src.core.config import cfg

    return dict(cfg.factor_weights)


def _retrain_and_save() -> dict:
    """Full pipeline: load snapshots → fetch forward prices → train → persist."""
    from src.data.history import get_all_factor_snapshots, save_ml_weights

    snapshots = get_all_factor_snapshots()
    if len(snapshots) < MIN_SAMPLES:
        log.info(
            "Only %d snapshots in history — not enough to train ML weights",
            len(snapshots),
        )
        return {
            "weights": _static_weights(),
            "source": "static",
            "n_samples": len(snapshots),
        }

    forward_prices = fetch_forward_prices(snapshots)
    rows = build_training_dataset(snapshots, forward_prices)

    if len(rows) < MIN_SAMPLES:
        log.info(
            "Only %d labelled rows after forward-price join — using static weights",
            len(rows),
        )
        return {
            "weights": _static_weights(),
            "source": "static",
            "n_samples": len(rows),
        }

    result = walk_forward_train(rows)

    trained_date = datetime.utcnow().strftime("%Y-%m-%d")
    save_ml_weights(
        weights=result["weights"],
        trained_date=trained_date,
        auc=result.get("auc"),
        precision_top_decile=result.get("precision_top_decile"),
        n_samples=result.get("n_samples", 0),
    )
    log.info(
        "ML weights trained: AUC=%.3f prec@top10=%.3f n=%d",
        result["auc"],
        result["precision_top_decile"],
        result["n_samples"],
    )
    return result


def get_adaptive_weights(force_retrain: bool = False) -> dict[str, float]:
    """Return ML-trained weights if available and fresh, else cfg.factor_weights.

    Weights are cached in history.db and refreshed at most every
    RETRAIN_EVERY_DAYS days (quarterly).

    Parameters
    ----------
    force_retrain : bypass cache and retrain immediately
    """
    if not force_retrain:
        try:
            from src.data.history import get_latest_ml_weights

            row = get_latest_ml_weights()
            if row is not None:
                trained_date = datetime.strptime(row["trained_date"], "%Y-%m-%d")
                age_days = (datetime.utcnow() - trained_date).days
                if age_days <= RETRAIN_EVERY_DAYS:
                    return json.loads(row["weights_json"])
        except Exception as exc:
            log.debug("Could not load cached ML weights: %s", exc)

    try:
        result = _retrain_and_save()
        return result["weights"]
    except Exception as exc:
        log.warning("ML weight training failed, using static weights: %s", exc)
        return _static_weights()


def get_weights_metadata() -> dict:
    """Return current weights + training metrics for UI display.

    Returns
    -------
    dict with keys:
        weights              – {factor_key: float}
        source               – "ml" | "static"
        trained_date         – str or None
        auc                  – float or None
        precision_top_decile – float or None
        n_samples            – int or None
        age_days             – int or None
    """
    try:
        from src.data.history import get_latest_ml_weights

        row = get_latest_ml_weights()
        if row is not None:
            trained_date = row["trained_date"]
            age_days = (
                datetime.utcnow() - datetime.strptime(trained_date, "%Y-%m-%d")
            ).days
            if age_days <= RETRAIN_EVERY_DAYS:
                return {
                    "weights": json.loads(row["weights_json"]),
                    "source": "ml",
                    "trained_date": trained_date,
                    "auc": row.get("auc"),
                    "precision_top_decile": row.get("precision_top_decile"),
                    "n_samples": row.get("n_samples"),
                    "age_days": age_days,
                }
    except Exception as exc:
        log.debug("Could not read ML weights metadata: %s", exc)

    return {
        "weights": _static_weights(),
        "source": "static",
        "trained_date": None,
        "auc": None,
        "precision_top_decile": None,
        "n_samples": None,
        "age_days": None,
    }
