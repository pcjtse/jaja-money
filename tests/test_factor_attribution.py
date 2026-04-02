"""Tests for factor_attribution.py — per-factor IC attribution module."""

from __future__ import annotations

import json
import time

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def patched_history(tmp_path, monkeypatch):
    """Redirect history DB to a temp directory for isolation."""
    import src.data.history as h

    monkeypatch.setattr(h, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(h, "_DB_FILE", tmp_path / "history.db")
    h._ensure_table()
    h._ensure_signal_returns_table()
    return h


# ---------------------------------------------------------------------------
# compute_factor_ic
# ---------------------------------------------------------------------------


def test_compute_factor_ic_random_50_rows():
    from src.analysis.factor_attribution import compute_factor_ic

    rng = np.random.default_rng(42)
    df = pd.DataFrame(
        {
            "valuation": rng.uniform(0, 100, 50),
            "return_63d": rng.uniform(-20, 20, 50),
        }
    )
    result = compute_factor_ic(df, "valuation", "return_63d")
    assert result["n"] == 50
    assert result["sufficient"] is True
    assert result["ic"] is not None
    assert -1.0 <= result["ic"] <= 1.0
    assert result["ci_lo"] is not None
    assert result["ci_hi"] is not None


def test_compute_factor_ic_8_rows():
    from src.analysis.factor_attribution import compute_factor_ic

    rng = np.random.default_rng(1)
    df = pd.DataFrame(
        {
            "trend": rng.uniform(0, 100, 8),
            "return_21d": rng.uniform(-10, 10, 8),
        }
    )
    result = compute_factor_ic(df, "trend", "return_21d")
    assert result["n"] == 8
    assert result["ic"] is None
    assert result["sufficient"] is False
    assert "n < 10" in result["warning"]


def test_compute_factor_ic_perfect_correlation():
    from src.analysis.factor_attribution import compute_factor_ic

    x = list(range(1, 13))
    df = pd.DataFrame({"rsi": x, "return_126d": x})
    result = compute_factor_ic(df, "rsi", "return_126d")
    assert result["ic"] == pytest.approx(1.0, abs=1e-9)
    assert result["ci_lo"] is None
    assert result["ci_hi"] is None
    assert "perfect rank correlation" in result["warning"]


def test_compute_factor_ic_invalid_horizon():
    from src.analysis.factor_attribution import compute_factor_ic

    df = pd.DataFrame({"valuation": [1.0, 2.0], "return_7d": [0.5, 0.6]})
    with pytest.raises(ValueError, match="return_col must be one of"):
        compute_factor_ic(df, "valuation", "return_7d")


def test_compute_factor_ic_missing_column():
    from src.analysis.factor_attribution import compute_factor_ic

    result = compute_factor_ic(pd.DataFrame(), "valuation", "return_63d")
    assert result["n"] == 0
    assert result["ic"] is None
    assert result["sufficient"] is False


# ---------------------------------------------------------------------------
# _parse_all_factor_scores
# ---------------------------------------------------------------------------


def test_parse_no_data_label():
    from src.analysis.factor_attribution import ABSENT_LABEL, _parse_all_factor_scores

    factors_json = json.dumps(
        [{"name": "Congress Signal", "score": 50, "label": ABSENT_LABEL, "detail": ""}]
    )
    result = _parse_all_factor_scores(factors_json)
    assert result["congressional"] is None


def test_parse_neutral_score_50():
    from src.analysis.factor_attribution import _parse_all_factor_scores

    factors_json = json.dumps(
        [{"name": "Market Regime", "score": 50, "label": "Neutral", "detail": ""}]
    )
    result = _parse_all_factor_scores(factors_json)
    assert result["regime"] == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# get_attribution_report
# ---------------------------------------------------------------------------


def test_get_attribution_report_invalid_horizon():
    from src.analysis.factor_attribution import get_attribution_report

    with pytest.raises(ValueError, match="horizon must be one of"):
        get_attribution_report(pd.DataFrame(), "return_7d")


def test_get_attribution_report_empty_dataframes():
    from src.analysis.factor_attribution import (
        ALPHA_FACTOR_NAMES,
        CORE_FACTOR_NAMES,
        get_attribution_report,
    )

    report = get_attribution_report(pd.DataFrame(), "return_63d")
    assert report["horizon"] == "return_63d"
    assert report["total_rows"] == 0
    assert report["oldest_analysis_date"] is None
    for col_key in CORE_FACTOR_NAMES.values():
        assert report["core"][col_key]["ic"] is None
        assert report["core"][col_key]["n"] == 0
    for col_key in ALPHA_FACTOR_NAMES.values():
        assert report["alpha"][col_key]["ic"] is None
        assert report["alpha"][col_key]["n"] == 0


# ---------------------------------------------------------------------------
# build_attribution_dataset
# ---------------------------------------------------------------------------


def test_build_attribution_dataset_empty(patched_history):
    from src.analysis.factor_attribution import build_attribution_dataset

    base_df, oldest_date = build_attribution_dataset()
    assert isinstance(base_df, pd.DataFrame)
    assert base_df.empty
    assert oldest_date is None


def test_build_attribution_dataset_join(patched_history):
    from src.analysis.factor_attribution import (
        ALL_FACTOR_NAMES,
        build_attribution_dataset,
    )

    h = patched_history
    signal_date = "2026-01-15"

    factors_list = [
        {"name": "Valuation (P/E)", "score": 72, "label": "Strong", "detail": ""},
        {"name": "Trend (SMA)", "score": 60, "label": "Bullish", "detail": ""},
        {"name": "Congress Signal", "score": 50, "label": "No data", "detail": ""},
    ]

    with h._connect() as conn:
        conn.execute(
            """INSERT INTO analysis_history
               (symbol, date, timestamp, price, factor_score, risk_score,
                composite_label, risk_level, factors_json, flags_json)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                "AAPL",
                signal_date,
                int(time.time()),
                180.0,
                72,
                25,
                "Buy",
                "Low",
                json.dumps(factors_list),
                "[]",
            ),
        )
        conn.execute(
            """INSERT INTO signal_returns
               (symbol, signal_date, signal_score, price_at_signal,
                return_21d, return_63d, return_126d, fetched_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            ("AAPL", signal_date, 72, 180.0, 2.5, 5.1, 8.3, int(time.time())),
        )

    base_df, oldest_date = build_attribution_dataset()

    assert not base_df.empty
    assert len(base_df) == 1
    assert oldest_date == signal_date

    # All 23 factor columns present
    for col_key in ALL_FACTOR_NAMES.values():
        assert col_key in base_df.columns

    # Return columns present and correct
    assert base_df["return_63d"].iloc[0] == pytest.approx(5.1)
    assert base_df["return_21d"].iloc[0] == pytest.approx(2.5)

    # Absent Congress Signal → NaN, not 50.0
    assert pd.isna(base_df["congressional"].iloc[0])

    # Present factors have correct scores
    assert base_df["valuation"].iloc[0] == pytest.approx(72.0)
    assert base_df["trend"].iloc[0] == pytest.approx(60.0)


# ---------------------------------------------------------------------------
# Factor name consistency
# ---------------------------------------------------------------------------


def test_factor_names_match_factors_py():
    """Ensure ALL_FACTOR_NAMES display names exactly match factors.py output."""
    from src.analysis.factor_attribution import ALL_FACTOR_NAMES
    from src.analysis.factors import compute_factors

    factors = compute_factors(
        quote={"c": "100"},
        financials=None,
        close=None,
        earnings=[],
        recommendations=[],
        sentiment_agg=None,
    )
    actual_names = {f["name"] for f in factors}
    expected_names = set(ALL_FACTOR_NAMES.keys())
    assert actual_names == expected_names, (
        f"Name mismatch.\n"
        f"In factors.py but not attribution: {actual_names - expected_names}\n"
        f"In attribution but not factors.py: {expected_names - actual_names}"
    )
