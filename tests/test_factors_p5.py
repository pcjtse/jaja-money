"""Tests for new P5 factor additions in factors.py.

Covers:
- P5.1 Sector-adjusted P/E valuation (_get_sector_pe_median, _factor_valuation_sector_adjusted)
- P5.7 Dividend yield factor (_factor_dividend_yield)
- P5.2 Estimate revision momentum (_factor_estimate_revisions)
- compute_factors() with new optional params (sector, revisions)
"""

import pytest
import pandas as pd

from src.analysis.factors import (
    _get_sector_pe_median,
    _factor_valuation_sector_adjusted,
    _factor_dividend_yield,
    _factor_estimate_revisions,
    compute_factors,
)


# ---------------------------------------------------------------------------
# _get_sector_pe_median (P5.1)
# ---------------------------------------------------------------------------


def test_sector_pe_exact_match_technology():
    assert _get_sector_pe_median("Technology") == pytest.approx(28.0)


def test_sector_pe_exact_match_banks():
    assert _get_sector_pe_median("Banks") == pytest.approx(11.0)


def test_sector_pe_case_insensitive():
    assert _get_sector_pe_median("technology") == pytest.approx(28.0)


def test_sector_pe_fuzzy_partial_match():
    # "Biotech" substring matches "Biotechnology" key
    result = _get_sector_pe_median("Biotech")
    assert result > 0


def test_sector_pe_none_returns_default():
    assert _get_sector_pe_median(None) == pytest.approx(20.0)


def test_sector_pe_unknown_returns_default():
    assert _get_sector_pe_median("Underwater Basket Weaving") == pytest.approx(20.0)


def test_sector_pe_empty_string_returns_default():
    assert _get_sector_pe_median("") == pytest.approx(20.0)


# ---------------------------------------------------------------------------
# _factor_valuation_sector_adjusted (P5.1)
# ---------------------------------------------------------------------------


def test_sector_adj_val_no_financials():
    f = _factor_valuation_sector_adjusted(None, None)
    assert f["score"] == 50
    assert f["label"] == "No data"


def test_sector_adj_val_negative_pe():
    f = _factor_valuation_sector_adjusted({"peBasicExclExtraTTM": -5}, "Technology")
    assert f["score"] == 25
    assert "Negative" in f["label"]


def test_sector_adj_val_deep_value():
    # P/E 10 vs Technology median 28 → relative ~0.36 < 0.6 → deep value
    f = _factor_valuation_sector_adjusted({"peBasicExclExtraTTM": 10}, "Technology")
    assert f["score"] == 92
    assert "Deep value" in f["label"]


def test_sector_adj_val_discounted():
    # P/E 20 vs Technology median 28 → relative ~0.71 → discounted
    f = _factor_valuation_sector_adjusted({"peBasicExclExtraTTM": 20}, "Technology")
    assert f["score"] == 80
    assert "Discounted" in f["label"]


def test_sector_adj_val_slight_discount():
    # P/E 25 vs Technology median 28 → relative ~0.89 → slight discount
    f = _factor_valuation_sector_adjusted({"peBasicExclExtraTTM": 25}, "Technology")
    assert f["score"] == 68


def test_sector_adj_val_near_median():
    # P/E 30 vs Technology median 28 → relative ~1.07 → near median
    f = _factor_valuation_sector_adjusted({"peBasicExclExtraTTM": 30}, "Technology")
    assert f["score"] == 55
    assert "Near sector median" in f["label"]


def test_sector_adj_val_premium():
    # P/E 36 vs Technology median 28 → relative ~1.29 → premium
    f = _factor_valuation_sector_adjusted({"peBasicExclExtraTTM": 36}, "Technology")
    assert f["score"] == 40


def test_sector_adj_val_significant_premium():
    # P/E 48 vs Technology median 28 → relative ~1.71 → significant premium
    f = _factor_valuation_sector_adjusted({"peBasicExclExtraTTM": 48}, "Technology")
    assert f["score"] == 26


def test_sector_adj_val_extreme_premium():
    # P/E 80 vs Technology median 28 → relative ~2.86 → extreme premium
    f = _factor_valuation_sector_adjusted({"peBasicExclExtraTTM": 80}, "Technology")
    assert f["score"] == 12


def test_sector_adj_val_detail_contains_relative():
    f = _factor_valuation_sector_adjusted({"peBasicExclExtraTTM": 28}, "Technology")
    assert "Relative" in f["detail"]


def test_sector_adj_val_weight():
    f = _factor_valuation_sector_adjusted(None, None)
    assert f["weight"] == pytest.approx(0.15, abs=0.01)


# ---------------------------------------------------------------------------
# _factor_dividend_yield (P5.7)
# ---------------------------------------------------------------------------


def test_div_yield_no_data():
    f = _factor_dividend_yield(None)
    assert f["score"] == 50
    assert f["label"] == "No data"


def test_div_yield_no_dividend_key():
    f = _factor_dividend_yield({})
    assert f["score"] == 50


def test_div_yield_zero():
    f = _factor_dividend_yield({"dividendYieldIndicatedAnnual": 0.0})
    assert f["score"] == 48
    assert "No dividend" in f["label"]


def test_div_yield_low():
    f = _factor_dividend_yield({"dividendYieldIndicatedAnnual": 1.0})
    assert f["score"] == 55
    assert "Low" in f["label"]


def test_div_yield_moderate():
    f = _factor_dividend_yield({"dividendYieldIndicatedAnnual": 2.0})
    assert f["score"] == 70
    assert "Moderate" in f["label"]


def test_div_yield_attractive():
    f = _factor_dividend_yield({"dividendYieldIndicatedAnnual": 4.0})
    assert f["score"] == 82
    assert "Attractive" in f["label"]


def test_div_yield_high():
    f = _factor_dividend_yield({"dividendYieldIndicatedAnnual": 6.0})
    assert f["score"] == 75
    assert "High" in f["label"]


def test_div_yield_unsustainable_payout():
    f = _factor_dividend_yield(
        {
            "dividendYieldIndicatedAnnual": 4.0,
            "payoutRatioTTM": 120.0,  # > 100% = unsustainable
        }
    )
    assert f["score"] <= 57  # penalized from 82
    assert "Unsustainable" in f["label"]


def test_div_yield_elevated_payout_penalized():
    f = _factor_dividend_yield(
        {
            "dividendYieldIndicatedAnnual": 4.0,
            "payoutRatioTTM": 85.0,  # > 80 = elevated
        }
    )
    # Score should be reduced (82 - 10 = 72 min-clamped to 35)
    base_score = 82
    assert f["score"] <= base_score


def test_div_yield_healthy_payout_unchanged():
    f_no_payout = _factor_dividend_yield({"dividendYieldIndicatedAnnual": 4.0})
    f_healthy = _factor_dividend_yield(
        {
            "dividendYieldIndicatedAnnual": 4.0,
            "payoutRatioTTM": 50.0,
        }
    )
    assert f_healthy["score"] == f_no_payout["score"]


def test_div_yield_weight():
    f = _factor_dividend_yield(None)
    assert f["weight"] > 0


# ---------------------------------------------------------------------------
# _factor_estimate_revisions (P5.2)
# ---------------------------------------------------------------------------


def test_est_revisions_no_data_none():
    f = _factor_estimate_revisions(None)
    assert f["score"] == 50
    assert f["label"] == "No data"


def test_est_revisions_not_available():
    f = _factor_estimate_revisions({"available": False})
    assert f["score"] == 50


def test_est_revisions_up():
    f = _factor_estimate_revisions(
        {
            "available": True,
            "revision_direction": "up",
            "analyst_count": 20,
            "forward_eps": 5.50,
        }
    )
    assert f["score"] == 78
    assert "Upward" in f["label"]


def test_est_revisions_down():
    f = _factor_estimate_revisions(
        {
            "available": True,
            "revision_direction": "down",
            "analyst_count": 15,
            "forward_eps": 3.20,
        }
    )
    assert f["score"] == 28
    assert "Downward" in f["label"]


def test_est_revisions_flat():
    f = _factor_estimate_revisions(
        {
            "available": True,
            "revision_direction": "flat",
        }
    )
    assert f["score"] == 52
    assert "Stable" in f["label"]


def test_est_revisions_detail_includes_direction():
    f = _factor_estimate_revisions(
        {
            "available": True,
            "revision_direction": "up",
            "analyst_count": 10,
        }
    )
    assert "up" in f["detail"]


def test_est_revisions_weight():
    f = _factor_estimate_revisions(None)
    assert f["weight"] > 0


# ---------------------------------------------------------------------------
# compute_factors with sector and revisions params
# ---------------------------------------------------------------------------


def _rising_close(n=250):
    return pd.Series([float(100 + i) for i in range(n)])


def test_compute_factors_with_sector():
    result = compute_factors(
        quote={"c": 150.0},
        financials={"peBasicExclExtraTTM": 20, "52WeekHigh": 160, "52WeekLow": 100},
        close=_rising_close(),
        earnings=[{"surprisePercent": 5}] * 4,
        recommendations=[
            {"strongBuy": 5, "buy": 3, "hold": 2, "sell": 0, "strongSell": 0}
        ],
        sentiment_agg=None,
        sector="Technology",
    )
    assert len(result) == 11
    val_factor = next(f for f in result if f["name"] == "Valuation (P/E)")
    # P/E 20 vs Technology median 28 → discounted
    assert (
        "Discounted" in val_factor["label"] or "discount" in val_factor["label"].lower()
    )


def test_compute_factors_with_revisions():
    revisions = {
        "available": True,
        "revision_direction": "up",
        "analyst_count": 12,
        "forward_eps": 6.0,
    }
    result = compute_factors(
        quote={"c": 100.0},
        financials={"peBasicExclExtraTTM": 15},
        close=_rising_close(),
        earnings=[],
        recommendations=[],
        sentiment_agg=None,
        revisions=revisions,
    )
    assert len(result) == 11
    rev_factor = next(f for f in result if f["name"] == "Estimate Revisions")
    assert rev_factor["score"] == 78


def test_compute_factors_all_none_still_10():
    result = compute_factors(
        quote={},
        financials=None,
        close=None,
        earnings=[],
        recommendations=[],
        sentiment_agg=None,
        sector=None,
        revisions=None,
    )
    assert len(result) == 11
    assert all(0 <= f["score"] <= 100 for f in result)
