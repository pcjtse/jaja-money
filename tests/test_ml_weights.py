"""Tests for 21.1 ML-Trained Adaptive Factor Weights."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from src.analysis.ml_weights import (
    FACTOR_KEYS,
    MIN_SAMPLES,
    _normalize_weights,
    _parse_factors_json,
    _static_weights,
    build_training_dataset,
    extract_weights_from_model,
    get_adaptive_weights,
    get_weights_metadata,
    walk_forward_train,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_snapshot(symbol: str, date: str, price: float, scores: dict) -> dict:
    """Build a fake analysis_history row."""
    factors = [
        {
            "name": _key_to_name(k),
            "score": v,
            "weight": 0.1,
            "label": "ok",
            "detail": "",
        }
        for k, v in scores.items()
    ]
    return {
        "symbol": symbol,
        "date": date,
        "price": price,
        "factors_json": json.dumps(factors),
    }


def _key_to_name(key: str) -> str:
    # Names must match CORE_FACTOR_NAMES in factor_attribution.py
    return {
        "valuation": "Valuation (P/E)",
        "trend": "Trend (SMA)",
        "rsi": "Momentum (RSI)",
        "macd": "MACD Signal",
        "sentiment": "News Sentiment",
        "earnings": "Earnings Quality",
        "analyst": "Analyst Consensus",
        "range": "52-Wk Strength",
    }.get(key, key)


def _make_full_scores(base: int = 50) -> dict:
    return {k: base for k in FACTOR_KEYS}


def _make_rows(n: int = MIN_SAMPLES + 10) -> list[dict]:
    """Build n synthetic training rows spread across quarters."""
    import datetime

    rows = []
    start = datetime.date(2023, 1, 1)
    for i in range(n):
        d = start + datetime.timedelta(days=i * 3)
        row = {"date": d.strftime("%Y-%m-%d"), "target": i % 2}
        for k in FACTOR_KEYS:
            row[k] = float(50 + (i % 30) - 15)
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# _parse_factors_json
# ---------------------------------------------------------------------------


def test_parse_factors_json_known_names():
    factors = [
        {"name": "Valuation (P/E)", "score": 70, "weight": 0.15},
        {"name": "Trend (SMA)", "score": 80, "weight": 0.20},
        {"name": "Momentum (RSI)", "score": 60, "weight": 0.10},
    ]
    result = _parse_factors_json(json.dumps(factors))
    assert result["valuation"] == 70.0
    assert result["trend"] == 80.0
    assert result["rsi"] == 60.0


def test_parse_factors_json_unknown_names_ignored():
    factors = [{"name": "Unknown Factor", "score": 99, "weight": 0.1}]
    result = _parse_factors_json(json.dumps(factors))
    assert len(result) == 0


def test_parse_factors_json_empty():
    assert _parse_factors_json("[]") == {}


def test_parse_factors_json_invalid_json():
    assert _parse_factors_json("not-json") == {}


# ---------------------------------------------------------------------------
# _normalize_weights
# ---------------------------------------------------------------------------


def test_normalize_weights_sums_to_one():
    raw = {"a": 0.4, "b": 0.6}
    result = _normalize_weights(raw)
    assert abs(sum(result.values()) - 1.0) < 1e-6


def test_normalize_weights_clips_negatives():
    raw = {"a": -0.5, "b": 1.0}
    result = _normalize_weights(raw)
    assert result["a"] > 0


def test_normalize_weights_equal_inputs():
    raw = {k: 1.0 for k in FACTOR_KEYS}
    result = _normalize_weights(raw)
    assert abs(sum(result.values()) - 1.0) < 1e-6
    for v in result.values():
        assert v > 0


# ---------------------------------------------------------------------------
# build_training_dataset
# ---------------------------------------------------------------------------


def test_build_training_dataset_basic():
    snaps = [
        _make_snapshot("AAPL", "2024-01-01", 100.0, _make_full_scores(60)),
        _make_snapshot("AAPL", "2024-02-01", 110.0, _make_full_scores(70)),
    ]
    fwd = {
        ("AAPL", "2024-01-01"): 120.0,  # went up → target=1
        ("AAPL", "2024-02-01"): 105.0,  # went down → target=0
    }
    rows = build_training_dataset(snaps, fwd)
    assert len(rows) == 2
    assert rows[0]["target"] == 1
    assert rows[1]["target"] == 0
    for k in FACTOR_KEYS:
        assert k in rows[0]


def test_build_training_dataset_drops_missing_forward():
    snaps = [_make_snapshot("AAPL", "2024-01-01", 100.0, _make_full_scores())]
    rows = build_training_dataset(snaps, {})
    assert len(rows) == 0


def test_build_training_dataset_drops_zero_price():
    snaps = [_make_snapshot("AAPL", "2024-01-01", 0.0, _make_full_scores())]
    fwd = {("AAPL", "2024-01-01"): 110.0}
    rows = build_training_dataset(snaps, fwd)
    assert len(rows) == 0


def test_build_training_dataset_drops_sparse_factors():
    snap = {
        "symbol": "AAPL",
        "date": "2024-01-01",
        "price": 100.0,
        "factors_json": json.dumps(
            [{"name": "Momentum (RSI)", "score": 60, "weight": 0.1}]
        ),
    }
    fwd = {("AAPL", "2024-01-01"): 110.0}
    rows = build_training_dataset([snap], fwd)
    assert len(rows) == 0


# ---------------------------------------------------------------------------
# extract_weights_from_model
# ---------------------------------------------------------------------------


def test_extract_weights_from_model():
    model = MagicMock()
    model.coef_ = [[0.5, -0.2, 0.3, 0.1, 0.4, 0.15, 0.25, 0.05]]
    result = extract_weights_from_model(model, FACTOR_KEYS)
    assert set(result.keys()) == set(FACTOR_KEYS)
    assert abs(sum(result.values()) - 1.0) < 1e-6
    for v in result.values():
        assert v > 0


# ---------------------------------------------------------------------------
# walk_forward_train
# ---------------------------------------------------------------------------


def test_walk_forward_train_raises_on_small_data():
    rows = _make_rows(5)  # well below MIN_SAMPLES
    with pytest.raises(ValueError, match="Insufficient data"):
        walk_forward_train(rows)


def test_walk_forward_train_returns_weights():
    pytest.importorskip("sklearn")
    rows = _make_rows(MIN_SAMPLES + 20)
    result = walk_forward_train(rows)
    assert "weights" in result
    assert set(result["weights"].keys()) == set(FACTOR_KEYS)
    assert abs(sum(result["weights"].values()) - 1.0) < 1e-6
    assert result["source"] == "ml"
    assert 0.0 <= result["auc"] <= 1.0


# ---------------------------------------------------------------------------
# get_adaptive_weights
# ---------------------------------------------------------------------------


def test_get_adaptive_weights_returns_cached_fresh_weights():
    """Fresh cached weights should be returned without retraining."""
    import json

    cached_weights = {k: 1.0 / len(FACTOR_KEYS) for k in FACTOR_KEYS}
    fake_row = {
        "trained_date": "2026-03-20",
        "weights_json": json.dumps(cached_weights),
        "auc": 0.62,
        "precision_top_decile": 0.58,
        "n_samples": 100,
    }
    with patch("src.data.history.get_latest_ml_weights", return_value=fake_row):
        result = get_adaptive_weights()
    assert result == cached_weights


def test_get_adaptive_weights_falls_back_on_stale_and_training_error():
    """If cached weights are stale and retraining fails, return static weights."""
    stale_row = {
        "trained_date": "2025-01-01",  # > RETRAIN_EVERY_DAYS old
        "weights_json": json.dumps({k: 0.125 for k in FACTOR_KEYS}),
        "auc": 0.55,
        "precision_top_decile": 0.5,
        "n_samples": 50,
    }
    with (
        patch("src.data.history.get_latest_ml_weights", return_value=stale_row),
        patch(
            "src.analysis.ml_weights._retrain_and_save",
            side_effect=RuntimeError("fail"),
        ),
    ):
        result = get_adaptive_weights()
    # Should fall back to static config weights
    static = _static_weights()
    assert result == static


def test_get_adaptive_weights_no_cache_falls_back_on_error():
    """No cache + training error → static weights."""
    with (
        patch("src.data.history.get_latest_ml_weights", return_value=None),
        patch(
            "src.analysis.ml_weights._retrain_and_save",
            side_effect=RuntimeError("fail"),
        ),
    ):
        result = get_adaptive_weights()
    assert result == _static_weights()


# ---------------------------------------------------------------------------
# get_weights_metadata
# ---------------------------------------------------------------------------


def test_get_weights_metadata_ml_source():
    import json

    cached_weights = {k: 1.0 / len(FACTOR_KEYS) for k in FACTOR_KEYS}
    fake_row = {
        "trained_date": "2026-03-20",
        "weights_json": json.dumps(cached_weights),
        "auc": 0.63,
        "precision_top_decile": 0.59,
        "n_samples": 150,
    }
    with patch("src.data.history.get_latest_ml_weights", return_value=fake_row):
        meta = get_weights_metadata()
    assert meta["source"] == "ml"
    assert meta["auc"] == 0.63
    assert meta["n_samples"] == 150
    assert meta["weights"] == cached_weights


def test_get_weights_metadata_static_fallback():
    with patch("src.data.history.get_latest_ml_weights", return_value=None):
        meta = get_weights_metadata()
    assert meta["source"] == "static"
    assert meta["trained_date"] is None
    assert meta["weights"] == _static_weights()
