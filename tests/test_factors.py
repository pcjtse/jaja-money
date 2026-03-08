"""Unit tests for factors.py — all internal helpers and public API."""

import pytest
import pandas as pd

from factors import (
    _clamp,
    _macd_histograms,
    _sma,
    _rsi,
    _factor_valuation,
    _factor_trend,
    _factor_rsi,
    _factor_macd,
    _factor_sentiment,
    _factor_earnings,
    _factor_analyst,
    _factor_range_position,
    compute_factors,
    composite_score,
    composite_label_color,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def rising_close(n=60, start=100, step=1):
    """Strictly increasing close prices — RSI → 100, SMA trend = up."""
    return pd.Series([float(start + i * step) for i in range(n)])


def falling_close(n=60, start=160, step=1):
    """Strictly decreasing close prices — RSI → 0, SMA trend = down."""
    return pd.Series([float(start - i * step) for i in range(n)])


def flat_close(n=30, price=100):
    """Constant prices — RSI gain=loss=0, should return NaN → None."""
    return pd.Series([float(price)] * n)


QUOTE_100 = {"c": 100.0}
QUOTE_ZERO = {"c": 0}
QUOTE_NONE = {}


# ---------------------------------------------------------------------------
# _clamp
# ---------------------------------------------------------------------------

def test_clamp_within_bounds():
    assert _clamp(50) == 50

def test_clamp_below_lo():
    assert _clamp(-10) == 0

def test_clamp_above_hi():
    assert _clamp(120) == 100

def test_clamp_custom_bounds():
    assert _clamp(25, lo=10, hi=20) == 20

def test_clamp_returns_int():
    assert isinstance(_clamp(55.7), int)


# ---------------------------------------------------------------------------
# _sma
# ---------------------------------------------------------------------------

def test_sma_basic():
    close = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    assert _sma(close, 3) == pytest.approx(4.0)  # mean of [3,4,5]

def test_sma_insufficient_data():
    assert _sma(pd.Series([1.0, 2.0]), 5) is None

def test_sma_none_input():
    assert _sma(None, 50) is None


# ---------------------------------------------------------------------------
# _rsi
# ---------------------------------------------------------------------------

def test_rsi_none_input():
    assert _rsi(None) is None

def test_rsi_insufficient_data():
    assert _rsi(pd.Series([100.0] * 5)) is None

def test_rsi_flat_prices_returns_none():
    # All diffs = 0 → gain=loss=0 → 0/0 = NaN → should return None
    result = _rsi(flat_close(30))
    assert result is None

def test_rsi_rising_prices_high():
    # All gains, no losses → RSI near 100
    result = _rsi(rising_close(50))
    assert result is not None
    assert result > 80

def test_rsi_falling_prices_low():
    # All losses, no gains → RSI near 0
    result = _rsi(falling_close(50))
    assert result is not None
    assert result < 20

def test_rsi_bounds():
    result = _rsi(rising_close(50))
    assert 0 <= result <= 100


# ---------------------------------------------------------------------------
# _macd_histograms
# ---------------------------------------------------------------------------

def test_macd_none_input():
    h, hp = _macd_histograms(None)
    assert h is None and hp is None

def test_macd_insufficient_data():
    h, hp = _macd_histograms(pd.Series([100.0] * 10))
    assert h is None and hp is None

def test_macd_rising_bullish():
    close = rising_close(100, step=2)
    h, hp = _macd_histograms(close)
    assert h is not None
    # Rising prices: fast EMA > slow EMA → positive MACD; histogram sign can vary
    assert isinstance(h, float)
    assert isinstance(hp, float)


# ---------------------------------------------------------------------------
# _factor_valuation
# ---------------------------------------------------------------------------

def test_valuation_no_financials():
    f = _factor_valuation(None)
    assert f["score"] == 50
    assert f["label"] == "No data"

def test_valuation_pe_negative():
    f = _factor_valuation({"peBasicExclExtraTTM": -5})
    assert f["score"] == 25
    assert "Negative" in f["label"]

def test_valuation_pe_below_15():
    f = _factor_valuation({"peBasicExclExtraTTM": 12})
    assert f["score"] == 88
    assert "Attractively" in f["label"]

def test_valuation_pe_15_to_20():
    f = _factor_valuation({"peBasicExclExtraTTM": 17})
    assert f["score"] == 75

def test_valuation_pe_20_to_25():
    f = _factor_valuation({"peBasicExclExtraTTM": 22})
    assert f["score"] == 63

def test_valuation_pe_25_to_35():
    f = _factor_valuation({"peBasicExclExtraTTM": 30})
    assert f["score"] == 48

def test_valuation_pe_35_to_50():
    f = _factor_valuation({"peBasicExclExtraTTM": 42})
    assert f["score"] == 32

def test_valuation_pe_above_50():
    f = _factor_valuation({"peBasicExclExtraTTM": 80})
    assert f["score"] == 16

def test_valuation_weight():
    f = _factor_valuation({"peBasicExclExtraTTM": 20})
    assert f["weight"] == pytest.approx(0.15)


# ---------------------------------------------------------------------------
# _factor_trend
# ---------------------------------------------------------------------------

def test_trend_no_data():
    f = _factor_trend(None, None)
    assert f["score"] == 50

def test_trend_strong_uptrend():
    # price > sma50 > sma200: score 90
    close = rising_close(250)
    price = float(close.iloc[-1])
    f = _factor_trend(close, price)
    assert f["score"] == 90
    assert "uptrend" in f["label"].lower()

def test_trend_strong_downtrend():
    # price < sma50 < sma200: score 14
    close = falling_close(250)
    price = float(close.iloc[-1])
    f = _factor_trend(close, price)
    assert f["score"] == 14
    assert "downtrend" in f["label"].lower()

def test_trend_weight():
    f = _factor_trend(None, None)
    assert f["weight"] == pytest.approx(0.20)


# ---------------------------------------------------------------------------
# _factor_rsi
# ---------------------------------------------------------------------------

def test_factor_rsi_no_data():
    f = _factor_rsi(None)
    assert f["score"] == 50
    assert f["label"] == "No data"

def test_factor_rsi_rising_strong_momentum():
    f = _factor_rsi(rising_close(50))
    # RSI near 100 → "Extreme overbought" zone
    assert f["score"] < 50  # Extremely overbought → low score (risky to buy)

def test_factor_rsi_flat_no_data():
    # Flat prices → RSI NaN → falls back to "Insufficient data"
    f = _factor_rsi(flat_close(30))
    assert f["score"] == 50

def test_factor_rsi_weight():
    f = _factor_rsi(None)
    assert f["weight"] == pytest.approx(0.10)


# ---------------------------------------------------------------------------
# _factor_macd
# ---------------------------------------------------------------------------

def test_factor_macd_no_data():
    f = _factor_macd(None)
    assert f["score"] == 50

def test_factor_macd_insufficient_data():
    f = _factor_macd(pd.Series([100.0] * 10))
    assert f["score"] == 50

def test_factor_macd_score_in_range():
    f = _factor_macd(rising_close(100, step=2))
    assert 0 <= f["score"] <= 100

def test_factor_macd_weight():
    f = _factor_macd(None)
    assert f["weight"] == pytest.approx(0.10)


# ---------------------------------------------------------------------------
# _factor_sentiment
# ---------------------------------------------------------------------------

def test_sentiment_factor_no_data():
    f = _factor_sentiment(None)
    assert f["score"] == 50
    assert f["label"] == "No data"

def test_sentiment_factor_bullish():
    agg = {"net_score": 0.8, "signal": "Bullish",
           "counts": {"positive": 8, "negative": 1, "neutral": 1}}
    f = _factor_sentiment(agg)
    assert f["score"] > 70
    assert f["label"] == "Bullish"

def test_sentiment_factor_bearish():
    agg = {"net_score": -0.8, "signal": "Bearish",
           "counts": {"positive": 1, "negative": 8, "neutral": 1}}
    f = _factor_sentiment(agg)
    assert f["score"] < 30

def test_sentiment_factor_neutral():
    agg = {"net_score": 0.0, "signal": "Mixed / Neutral",
           "counts": {"positive": 3, "negative": 3, "neutral": 4}}
    f = _factor_sentiment(agg)
    assert f["score"] == 50

def test_sentiment_factor_net_score_mapping():
    # net_score = -1 → score = 0
    agg = {"net_score": -1.0, "signal": "Bearish",
           "counts": {"positive": 0, "negative": 10, "neutral": 0}}
    f = _factor_sentiment(agg)
    assert f["score"] == 0

def test_sentiment_factor_weight():
    f = _factor_sentiment(None)
    assert f["weight"] == pytest.approx(0.15)


# ---------------------------------------------------------------------------
# _factor_earnings
# ---------------------------------------------------------------------------

def test_earnings_no_data():
    f = _factor_earnings([])
    assert f["score"] == 50
    assert f["label"] == "No data"

def test_earnings_consistent_beats():
    earnings = [{"surprisePercent": 12}, {"surprisePercent": 15},
                {"surprisePercent": 11}, {"surprisePercent": 14}]
    f = _factor_earnings(earnings)
    assert f["score"] == 90
    assert "Consistently" in f["label"]

def test_earnings_solid_beats():
    earnings = [{"surprisePercent": 6}, {"surprisePercent": 7},
                {"surprisePercent": 8}, {"surprisePercent": 5.5}]
    f = _factor_earnings(earnings)
    assert f["score"] == 78

def test_earnings_significant_misses():
    earnings = [{"surprisePercent": -8}, {"surprisePercent": -12},
                {"surprisePercent": -6}, {"surprisePercent": -9}]
    f = _factor_earnings(earnings)
    assert f["score"] == 18

def test_earnings_skips_none_surprises():
    # avg = (12 + 12) / 2 = 12 > 10 → score 90
    earnings = [{"surprisePercent": 12}, {"surprisePercent": None},
                {"surprisePercent": 12}]
    f = _factor_earnings(earnings)
    assert f["score"] == 90  # only the two valid surprises count

def test_earnings_weight():
    f = _factor_earnings([])
    assert f["weight"] == pytest.approx(0.15)


# ---------------------------------------------------------------------------
# _factor_analyst
# ---------------------------------------------------------------------------

def test_analyst_no_data():
    f = _factor_analyst([])
    assert f["score"] == 50

def test_analyst_all_zeros():
    f = _factor_analyst([{"strongBuy": 0, "buy": 0, "hold": 0,
                           "sell": 0, "strongSell": 0}])
    assert f["score"] == 50
    assert f["label"] == "No coverage"

def test_analyst_overwhelmingly_bullish():
    f = _factor_analyst([{"strongBuy": 10, "buy": 8, "hold": 2,
                           "sell": 0, "strongSell": 0}])
    assert f["score"] == 90
    assert "bullish" in f["label"].lower()

def test_analyst_bearish():
    f = _factor_analyst([{"strongBuy": 0, "buy": 1, "hold": 2,
                           "sell": 5, "strongSell": 4}])
    assert f["score"] == 20
    assert f["label"] == "Bearish"

def test_analyst_weight():
    f = _factor_analyst([])
    assert f["weight"] == pytest.approx(0.10)


# ---------------------------------------------------------------------------
# _factor_range_position
# ---------------------------------------------------------------------------

def test_range_position_no_data():
    f = _factor_range_position(None, None)
    assert f["score"] == 50

def test_range_position_at_52w_low():
    financials = {"52WeekHigh": 200.0, "52WeekLow": 100.0}
    f = _factor_range_position(financials, 100.0)
    assert f["score"] == 0
    assert "low" in f["label"].lower()

def test_range_position_at_52w_high():
    financials = {"52WeekHigh": 200.0, "52WeekLow": 100.0}
    f = _factor_range_position(financials, 200.0)
    assert f["score"] == 100

def test_range_position_midpoint():
    financials = {"52WeekHigh": 200.0, "52WeekLow": 100.0}
    f = _factor_range_position(financials, 150.0)
    assert f["score"] == 50

def test_range_position_equal_high_low():
    financials = {"52WeekHigh": 100.0, "52WeekLow": 100.0}
    f = _factor_range_position(financials, 100.0)
    assert f["score"] == 50  # flat range fallback

def test_range_position_weight():
    f = _factor_range_position(None, None)
    assert f["weight"] == pytest.approx(0.05)


# ---------------------------------------------------------------------------
# composite_score
# ---------------------------------------------------------------------------

def test_composite_score_equal_weights():
    factors = [
        {"score": 80, "weight": 0.5},
        {"score": 60, "weight": 0.5},
    ]
    assert composite_score(factors) == 70

def test_composite_score_weighted():
    factors = [
        {"score": 100, "weight": 0.9},
        {"score": 0,   "weight": 0.1},
    ]
    assert composite_score(factors) == 90

def test_composite_score_empty():
    assert composite_score([]) == 50

def test_composite_score_clamps_to_100():
    factors = [{"score": 100, "weight": 1.0}]
    assert composite_score(factors) == 100

def test_composite_score_clamps_to_0():
    factors = [{"score": 0, "weight": 1.0}]
    assert composite_score(factors) == 0


# ---------------------------------------------------------------------------
# composite_label_color
# ---------------------------------------------------------------------------

def test_label_strong_buy():
    label, color = composite_label_color(75)
    assert label == "Strong Buy"

def test_label_buy():
    label, color = composite_label_color(62)
    assert label == "Buy"

def test_label_neutral():
    label, color = composite_label_color(50)
    assert label == "Neutral"

def test_label_sell():
    label, color = composite_label_color(37)
    assert label == "Sell"

def test_label_strong_sell():
    label, color = composite_label_color(10)
    assert label == "Strong Sell"

def test_label_boundary_70():
    label, _ = composite_label_color(70)
    assert label == "Strong Buy"

def test_label_boundary_55():
    label, _ = composite_label_color(55)
    assert label == "Buy"

def test_label_boundary_45():
    label, _ = composite_label_color(45)
    assert label == "Neutral"

def test_label_boundary_30():
    label, _ = composite_label_color(30)
    assert label == "Sell"

def test_label_color_is_hex():
    _, color = composite_label_color(75)
    assert color.startswith("#")
    assert len(color) == 7


# ---------------------------------------------------------------------------
# compute_factors — smoke test (all 8 factors returned)
# ---------------------------------------------------------------------------

def test_compute_factors_returns_8():
    result = compute_factors(
        quote=QUOTE_100,
        financials={"peBasicExclExtraTTM": 20, "52WeekHigh": 120, "52WeekLow": 80},
        close=rising_close(250),
        earnings=[{"surprisePercent": 5}] * 4,
        recommendations=[{"strongBuy": 5, "buy": 3, "hold": 2,
                           "sell": 0, "strongSell": 0}],
        sentiment_agg={"net_score": 0.4, "signal": "Bullish",
                       "counts": {"positive": 7, "negative": 2, "neutral": 1}},
    )
    assert len(result) == 8

def test_compute_factors_keys():
    result = compute_factors(
        quote=QUOTE_100,
        financials=None,
        close=None,
        earnings=[],
        recommendations=[],
        sentiment_agg=None,
    )
    for f in result:
        assert "name" in f
        assert "score" in f
        assert "label" in f
        assert "detail" in f
        assert "weight" in f
        assert 0 <= f["score"] <= 100

def test_compute_factors_zero_price_handled():
    # price = 0 → _factor_trend / _factor_range_position must not crash
    result = compute_factors(
        quote=QUOTE_ZERO,
        financials={"peBasicExclExtraTTM": 25, "52WeekHigh": 110, "52WeekLow": 90},
        close=rising_close(50),
        earnings=[],
        recommendations=[],
        sentiment_agg=None,
    )
    assert len(result) == 8

def test_compute_factors_all_none():
    result = compute_factors(
        quote=QUOTE_NONE,
        financials=None,
        close=None,
        earnings=[],
        recommendations=[],
        sentiment_agg=None,
    )
    # All factors should fall back gracefully to 50 or similar defaults
    assert all(0 <= f["score"] <= 100 for f in result)
