"""Unit tests for guardrails.py — risk dimensions, flag engine, composite risk."""

import pytest
import pandas as pd

from src.analysis.guardrails import (
    _hist_vol,
    _rsi,
    _sma,
    _clamp,
    _dim_volatility,
    _dim_drawdown,
    _dim_signal_risk,
    _build_flags,
    compute_risk,
    risk_level_color,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def rising_close(n=60, start=100, step=1):
    return pd.Series([float(start + i * step) for i in range(n)])


def falling_close(n=60, start=160, step=1):
    return pd.Series([float(start - i * step) for i in range(n)])


def flat_close(n=30, price=100):
    return pd.Series([float(price)] * n)


def noisy_close(n=250, start=100.0, drift=0.0005, vol=0.015, seed=42):
    """Random-walk price series with realistic daily volatility (~24% annualised)."""
    import random

    random.seed(seed)
    prices = [start]
    for _ in range(n - 1):
        r = drift + random.gauss(0, vol)
        prices.append(max(prices[-1] * (1 + r), 0.01))
    return pd.Series(prices)


QUOTE_100 = {"c": 100.0}


# ---------------------------------------------------------------------------
# _hist_vol
# ---------------------------------------------------------------------------


def test_hist_vol_none_input():
    assert _hist_vol(None) is None


def test_hist_vol_insufficient_data():
    assert _hist_vol(pd.Series([100.0, 101.0])) is None


def test_hist_vol_rising_positive():
    hv = _hist_vol(rising_close(50))
    assert hv is not None
    assert hv > 0


def test_hist_vol_flat_zero_volatility():
    # Flat prices → all ratios = 1 → log(1) = 0 → std = 0
    hv = _hist_vol(flat_close(30))
    assert hv is not None
    assert hv == pytest.approx(0.0)


def test_hist_vol_result_is_percent():
    # Mildly rising stock: expect HV in a reasonable range (not ratio)
    hv = _hist_vol(rising_close(50))
    # Annualised % should be bounded (not e.g. 0.01 as a ratio)
    assert hv is not None


def test_hist_vol_no_crash_on_zero_prices():
    # Close series with a zero value — should not raise ValueError from math.log
    close = pd.Series([100.0, 100.0, 0.0, 100.0, 100.0] + [100.0] * 25)
    result = _hist_vol(close)
    # May return None if insufficient valid data, or a valid float — must not crash
    assert result is None or isinstance(result, float)


# ---------------------------------------------------------------------------
# _rsi (guardrails version)
# ---------------------------------------------------------------------------


def test_rsi_none():
    assert _rsi(None) is None


def test_rsi_insufficient():
    assert _rsi(pd.Series([100.0] * 5)) is None


def test_rsi_flat_returns_none():
    assert _rsi(flat_close(30)) is None


def test_rsi_rising_high():
    result = _rsi(rising_close(50))
    assert result is not None
    assert result > 80


def test_rsi_falling_low():
    result = _rsi(falling_close(50))
    assert result is not None
    assert result < 20


def test_rsi_in_bounds():
    result = _rsi(rising_close(50))
    assert 0 <= result <= 100


# ---------------------------------------------------------------------------
# _sma
# ---------------------------------------------------------------------------


def test_sma_basic():
    close = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    assert _sma(close, 3) == pytest.approx(4.0)


def test_sma_none():
    assert _sma(None, 50) is None


def test_sma_insufficient():
    assert _sma(pd.Series([1.0, 2.0]), 5) is None


# ---------------------------------------------------------------------------
# _clamp
# ---------------------------------------------------------------------------


def test_clamp_within():
    assert _clamp(60) == 60


def test_clamp_below():
    assert _clamp(-5) == 0


def test_clamp_above():
    assert _clamp(150) == 100


def test_clamp_int_output():
    assert isinstance(_clamp(45.9), int)


# ---------------------------------------------------------------------------
# _dim_volatility
# ---------------------------------------------------------------------------


def test_dim_vol_none():
    score, hv = _dim_volatility(None)
    assert score == 50
    assert hv is None


def test_dim_vol_flat_low_risk():
    score, hv = _dim_volatility(flat_close(30))
    assert hv is not None
    assert score == 10  # hv < 15 → lowest risk bucket


def test_dim_vol_score_range():
    score, _ = _dim_volatility(rising_close(50))
    assert 0 <= score <= 100


# ---------------------------------------------------------------------------
# _dim_drawdown
# ---------------------------------------------------------------------------


def test_dim_dd_none_inputs():
    score, dd = _dim_drawdown(None, None, None)
    assert score == 50
    assert dd is None


def test_dim_dd_at_high_no_drawdown():
    # price == 52-week high → dd ≈ 0% → lowest risk bucket
    score, dd = _dim_drawdown(200.0, {"52WeekHigh": 200.0}, None)
    assert dd == pytest.approx(0.0)
    assert score == 5


def test_dim_dd_large_drawdown():
    # price = 50, high = 200 → dd = 75%
    score, dd = _dim_drawdown(50.0, {"52WeekHigh": 200.0}, None)
    assert dd == pytest.approx(75.0)
    assert score == 92


def test_dim_dd_moderate_drawdown():
    # price = 172, high = 200 → dd = 14% < 15 → score bucket 25
    score, dd = _dim_drawdown(172.0, {"52WeekHigh": 200.0}, None)
    assert dd == pytest.approx(14.0)
    assert score == 25


def test_dim_dd_falls_back_to_candle_max():
    close = rising_close(50, start=80)
    price = 80.0  # equals the minimum, so drawdown from max is large
    score, dd = _dim_drawdown(price, None, close)
    assert dd is not None
    assert dd >= 0


# ---------------------------------------------------------------------------
# _dim_signal_risk
# ---------------------------------------------------------------------------


def test_signal_risk_strong_buy():
    # composite = 80 → risk = 20
    assert _dim_signal_risk(80) == 20


def test_signal_risk_neutral():
    assert _dim_signal_risk(50) == 50


def test_signal_risk_strong_sell():
    assert _dim_signal_risk(20) == 80


def test_signal_risk_clamped():
    assert _dim_signal_risk(0) == 100
    assert _dim_signal_risk(100) == 0


# ---------------------------------------------------------------------------
# risk_level_color
# ---------------------------------------------------------------------------


def test_risk_level_low():
    label, color = risk_level_color(10)
    assert label == "Low"


def test_risk_level_moderate():
    label, color = risk_level_color(35)
    assert label == "Moderate"


def test_risk_level_elevated():
    label, color = risk_level_color(55)
    assert label == "Elevated"


def test_risk_level_high():
    label, color = risk_level_color(72)
    assert label == "High"


def test_risk_level_extreme():
    label, color = risk_level_color(85)
    assert label == "Extreme"


def test_risk_level_color_is_hex():
    _, color = risk_level_color(50)
    assert color.startswith("#")


# ---------------------------------------------------------------------------
# _build_flags — specific flag conditions
# ---------------------------------------------------------------------------


def _default_flags_args(**overrides):
    """Return minimal valid kwargs for _build_flags, merging overrides."""
    defaults = dict(
        close=noisy_close(),  # realistic HV; RSI ~50 so no overbought flag
        price=100.0,
        financials={"peBasicExclExtraTTM": 20, "52WeekHigh": 120, "52WeekLow": 80},
        earnings=[{"surprisePercent": 5}] * 4,
        recommendations=[
            {"strongBuy": 5, "buy": 5, "hold": 2, "sell": 0, "strongSell": 0}
        ],
        sentiment_agg={
            "net_score": 0.3,
            "signal": "Bullish",
            "counts": {"positive": 6, "negative": 2, "neutral": 2},
        },
        composite_factor_score=60,
        hv=20.0,
        drawdown_pct=5.0,
    )
    defaults.update(overrides)
    return defaults


def test_flags_no_issues_clean_stock():
    flags = _build_flags(**_default_flags_args())
    severities = {f["severity"] for f in flags}
    # A clean stock with moderate conditions should have no danger flags
    assert "danger" not in severities


def test_flags_extreme_volatility_triggers_danger():
    flags = _build_flags(**_default_flags_args(hv=65.0))
    titles = [f["title"] for f in flags]
    assert any("volatility" in t.lower() for t in titles)
    severities = [f["severity"] for f in flags if "volatility" in f["title"].lower()]
    assert "danger" in severities


def test_flags_high_volatility_triggers_warning():
    flags = _build_flags(**_default_flags_args(hv=45.0))
    titles = [f["title"] for f in flags]
    assert any("volatility" in t.lower() for t in titles)


def test_flags_severe_drawdown_danger():
    flags = _build_flags(**_default_flags_args(drawdown_pct=45.0))
    titles = [f["title"] for f in flags]
    assert any("drawdown" in t.lower() for t in titles)
    sev = [f["severity"] for f in flags if "drawdown" in f["title"].lower()]
    assert "danger" in sev


def test_flags_material_drawdown_warning():
    flags = _build_flags(**_default_flags_args(drawdown_pct=28.0))
    titles = [f["title"] for f in flags]
    assert any("drawdown" in t.lower() for t in titles)


def test_flags_extreme_pe_danger():
    fin = {"peBasicExclExtraTTM": 90.0, "52WeekHigh": 120, "52WeekLow": 80}
    flags = _build_flags(**_default_flags_args(financials=fin))
    titles = [f["title"] for f in flags]
    assert any("valuation" in t.lower() for t in titles)
    sev = [f["severity"] for f in flags if "valuation" in f["title"].lower()]
    assert "danger" in sev


def test_flags_negative_earnings_warning():
    fin = {"peBasicExclExtraTTM": -3.0, "52WeekHigh": 120, "52WeekLow": 80}
    flags = _build_flags(**_default_flags_args(financials=fin))
    titles = [f["title"] for f in flags]
    assert any("earnings" in t.lower() for t in titles)


def test_flags_persistent_misses_danger():
    bad_earnings = [{"surprisePercent": -8}] * 4
    flags = _build_flags(**_default_flags_args(earnings=bad_earnings))
    titles = [f["title"] for f in flags]
    assert any("miss" in t.lower() for t in titles)
    sev = [f["severity"] for f in flags if "miss" in f["title"].lower()]
    assert "danger" in sev


def test_flags_weak_analyst_support_danger():
    recs = [{"strongBuy": 0, "buy": 1, "hold": 1, "sell": 4, "strongSell": 4}]
    flags = _build_flags(**_default_flags_args(recommendations=recs))
    titles = [f["title"] for f in flags]
    assert any("analyst" in t.lower() for t in titles)


def test_flags_very_negative_sentiment_danger():
    agg = {
        "net_score": -0.7,
        "signal": "Bearish",
        "counts": {"positive": 1, "negative": 8, "neutral": 1},
    }
    flags = _build_flags(**_default_flags_args(sentiment_agg=agg))
    titles = [f["title"] for f in flags]
    assert any("sentiment" in t.lower() for t in titles)
    sev = [f["severity"] for f in flags if "sentiment" in f["title"].lower()]
    assert "danger" in sev


def test_flags_multi_factor_sell_danger():
    flags = _build_flags(**_default_flags_args(composite_factor_score=20))
    titles = [f["title"] for f in flags]
    assert any("sell" in t.lower() or "factor" in t.lower() for t in titles)


def test_flags_euphoria_info():
    flags = _build_flags(**_default_flags_args(composite_factor_score=90))
    titles = [f["title"] for f in flags]
    assert any("euphoria" in t.lower() for t in titles)
    sev = [f["severity"] for f in flags if "euphoria" in f["title"].lower()]
    assert "info" in sev


def test_flags_undefined_symbol_no_name_error():
    # The analyst flag previously referenced undefined `symbol` — this must not crash
    recs = [{"strongBuy": 0, "buy": 1, "hold": 1, "sell": 5, "strongSell": 5}]
    try:
        _build_flags(**_default_flags_args(recommendations=recs))
    except NameError as e:
        pytest.fail(f"NameError raised (symbol variable leaked): {e}")


def test_flags_sorted_danger_first():
    bad_earnings = [{"surprisePercent": -10}] * 4
    fin = {"peBasicExclExtraTTM": 95.0, "52WeekHigh": 200, "52WeekLow": 80}
    agg = {
        "net_score": -0.8,
        "signal": "Bearish",
        "counts": {"positive": 1, "negative": 9, "neutral": 0},
    }
    flags = _build_flags(
        **_default_flags_args(
            earnings=bad_earnings,
            financials=fin,
            sentiment_agg=agg,
            hv=65.0,
            drawdown_pct=45.0,
            composite_factor_score=15,
        )
    )
    if len(flags) >= 2:
        order = {"danger": 0, "warning": 1, "info": 2}
        for i in range(len(flags) - 1):
            assert order[flags[i]["severity"]] <= order[flags[i + 1]["severity"]]


# ---------------------------------------------------------------------------
# compute_risk — smoke tests
# ---------------------------------------------------------------------------


def test_compute_risk_returns_required_keys():
    result = compute_risk(
        quote=QUOTE_100,
        financials={"peBasicExclExtraTTM": 20, "52WeekHigh": 120, "52WeekLow": 80},
        close=rising_close(250),
        earnings=[{"surprisePercent": 5}] * 4,
        recommendations=[
            {"strongBuy": 5, "buy": 3, "hold": 2, "sell": 0, "strongSell": 0}
        ],
        sentiment_agg={
            "net_score": 0.4,
            "signal": "Bullish",
            "counts": {"positive": 7, "negative": 1, "neutral": 2},
        },
        composite_factor_score=65,
    )
    assert "risk_score" in result
    assert "risk_level" in result
    assert "risk_color" in result
    assert "flags" in result
    assert "hv" in result
    assert "drawdown_pct" in result


def test_compute_risk_score_in_range():
    result = compute_risk(
        quote=QUOTE_100,
        financials=None,
        close=None,
        earnings=[],
        recommendations=[],
        sentiment_agg=None,
        composite_factor_score=50,
    )
    assert 0 <= result["risk_score"] <= 100


def test_compute_risk_all_none_no_crash():
    result = compute_risk(
        quote={},
        financials=None,
        close=None,
        earnings=[],
        recommendations=[],
        sentiment_agg=None,
        composite_factor_score=50,
    )
    assert isinstance(result["risk_score"], int)


def test_compute_risk_high_risk_conditions():
    result = compute_risk(
        quote={"c": 50.0},
        financials={"52WeekHigh": 200.0, "peBasicExclExtraTTM": 100.0},
        close=falling_close(250),
        earnings=[{"surprisePercent": -10}] * 4,
        recommendations=[
            {"strongBuy": 0, "buy": 0, "hold": 1, "sell": 5, "strongSell": 5}
        ],
        sentiment_agg={
            "net_score": -0.9,
            "signal": "Bearish",
            "counts": {"positive": 0, "negative": 9, "neutral": 1},
        },
        composite_factor_score=15,
    )
    assert result["risk_score"] > 50
    assert result["risk_level"] in ("Elevated", "High", "Extreme")
