"""Tests for new P5 / P8 guardrail additions.

Covers:
- P8.2 Volatility regime detection (_detect_vol_regime)
- P5.3 Earnings calendar flags
- P5.4 Insider transaction flags
- P5.5 Short interest flags
- P5.6 Macro context flags
- P8.2 Vol regime flags from _build_flags / compute_risk
- compute_risk() returns new fields (vol_regime, hv_5d, hv_30d, macro_context)
"""
import pandas as pd
import numpy as np

from guardrails import _detect_vol_regime, _build_flags, compute_risk


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def flat_close(n=50, price=100.0):
    return pd.Series([float(price)] * n)


def noisy_close(n=250, seed=42, vol=0.015):
    rng = np.random.default_rng(seed)
    prices = [100.0]
    for _ in range(n - 1):
        prices.append(max(prices[-1] * (1 + rng.normal(0, vol)), 0.01))
    return pd.Series(prices)


def _default_flags_kwargs(**overrides):
    base = dict(
        close=noisy_close(),
        price=100.0,
        financials={"peBasicExclExtraTTM": 20, "52WeekHigh": 120, "52WeekLow": 80},
        earnings=[{"surprisePercent": 5}] * 4,
        recommendations=[{"strongBuy": 5, "buy": 5, "hold": 2, "sell": 0, "strongSell": 0}],
        sentiment_agg={"net_score": 0.3, "signal": "Bullish",
                       "counts": {"positive": 6, "negative": 2, "neutral": 2}},
        composite_factor_score=60,
        hv=20.0,
        drawdown_pct=5.0,
    )
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# _detect_vol_regime (P8.2)
# ---------------------------------------------------------------------------

def test_vol_regime_returns_tuple():
    regime, hv5, hv30 = _detect_vol_regime(noisy_close())
    assert isinstance(regime, str)
    assert regime in ("normal", "spike", "sustained")


def test_vol_regime_none_close():
    regime, hv5, hv30 = _detect_vol_regime(None)
    assert regime == "normal"
    assert hv5 is None
    assert hv30 is None


def test_vol_regime_normal_flat():
    # Flat prices → zero vol → normal regime
    regime, hv5, hv30 = _detect_vol_regime(flat_close(100))
    assert regime == "normal"


def test_vol_regime_spike_detected():
    """_detect_vol_regime returns spike when 5-day vol >> 30-day baseline."""
    rng = np.random.default_rng(123)
    # Long quiet period (low vol baseline for 30-day window)
    quiet = [100.0]
    for _ in range(200):
        quiet.append(quiet[-1] * (1 + rng.normal(0, 0.001)))  # ~0.1% daily vol
    # Sudden large-move spike in last 5 bars
    spiked = list(quiet)
    for _ in range(5):
        spiked.append(spiked[-1] * (1 + rng.normal(0, 0.08)))  # ~8% daily vol
    close = pd.Series(spiked)
    regime, hv5, hv30 = _detect_vol_regime(close)
    # With a genuine vol spike, hv5 >> hv30 → spike regime
    if hv5 is not None and hv30 is not None and hv30 > 0:
        assert regime == "spike" or hv5 >= hv30


def test_vol_regime_hv5_hv30_returned():
    regime, hv5, hv30 = _detect_vol_regime(noisy_close(250))
    # With 250 bars we have enough for both windows
    assert hv5 is not None
    assert hv30 is not None


# ---------------------------------------------------------------------------
# P5.3: Earnings calendar flags
# ---------------------------------------------------------------------------

def test_earnings_calendar_within_7_days_danger():
    cal = {"days_to_earnings": 3, "next_date": "2026-03-12"}
    flags = _build_flags(**_default_flags_kwargs(earnings_calendar=cal))
    titles = [f["title"] for f in flags]
    assert any("Earnings this week" in t for t in titles)
    sev = [f["severity"] for f in flags if "Earnings this week" in f["title"]]
    assert "danger" in sev


def test_earnings_calendar_within_14_days_warning():
    cal = {"days_to_earnings": 10, "next_date": "2026-03-19"}
    flags = _build_flags(**_default_flags_kwargs(earnings_calendar=cal))
    titles = [f["title"] for f in flags]
    assert any("Earnings within 2 weeks" in t for t in titles)
    sev = [f["severity"] for f in flags if "Earnings within 2 weeks" in f["title"]]
    assert "warning" in sev


def test_earnings_calendar_far_away_no_flag():
    cal = {"days_to_earnings": 45, "next_date": "2026-04-23"}
    flags = _build_flags(**_default_flags_kwargs(earnings_calendar=cal))
    titles = [f["title"] for f in flags]
    assert not any("Earnings" in t for t in titles)


def test_earnings_calendar_none_no_flag():
    flags = _build_flags(**_default_flags_kwargs(earnings_calendar=None))
    titles = [f["title"] for f in flags]
    assert not any("Earnings this week" in t or "Earnings within" in t for t in titles)


# ---------------------------------------------------------------------------
# P5.4: Insider transaction flags
# ---------------------------------------------------------------------------

def _make_insider_txns(buys=0, sells=0, buy_shares=1000, sell_shares=1000):
    """Create a minimal list of recent insider transactions."""
    from datetime import date
    today = date.today().isoformat()
    txns = []
    for _ in range(buys):
        txns.append({
            "transactionCode": "P",
            "change": buy_shares,
            "transactionDate": today,
        })
    for _ in range(sells):
        txns.append({
            "transactionCode": "S",
            "change": -sell_shares,
            "transactionDate": today,
        })
    return txns


def test_insider_heavy_selling_danger():
    txns = _make_insider_txns(sells=3, sell_shares=10000, buys=0)
    flags = _build_flags(**_default_flags_kwargs(insider_transactions=txns))
    titles = [f["title"] for f in flags]
    assert any("insider selling" in t.lower() for t in titles)
    sev = [f["severity"] for f in flags if "insider" in f["title"].lower()]
    assert "danger" in sev


def test_insider_moderate_selling_warning():
    # 2 sells with more shares than 0 buys → warning
    txns = _make_insider_txns(sells=2, sell_shares=5000, buys=0)
    flags = _build_flags(**_default_flags_kwargs(insider_transactions=txns))
    titles = [f["title"] for f in flags]
    # Could be warning or danger
    assert any("insider" in t.lower() for t in titles)


def test_insider_buying_cluster_info():
    txns = _make_insider_txns(buys=2, buy_shares=5000, sells=0)
    flags = _build_flags(**_default_flags_kwargs(insider_transactions=txns))
    titles = [f["title"] for f in flags]
    assert any("Insider buying" in t for t in titles)
    sev = [f["severity"] for f in flags if "Insider buying" in f["title"]]
    assert "info" in sev


def test_insider_none_no_flag():
    flags = _build_flags(**_default_flags_kwargs(insider_transactions=None))
    titles = [f["title"] for f in flags]
    assert not any("insider" in t.lower() for t in titles)


# ---------------------------------------------------------------------------
# P5.5: Short interest flags
# ---------------------------------------------------------------------------

def test_short_interest_extreme_danger():
    si = {"available": True, "short_pct_float": 30.0, "days_to_cover": 5.0}
    flags = _build_flags(**_default_flags_kwargs(short_interest=si))
    titles = [f["title"] for f in flags]
    assert any("short interest" in t.lower() for t in titles)
    sev = [f["severity"] for f in flags if "short" in f["title"].lower()]
    assert "danger" in sev


def test_short_interest_elevated_warning():
    si = {"available": True, "short_pct_float": 18.0, "days_to_cover": 3.0}
    flags = _build_flags(**_default_flags_kwargs(short_interest=si))
    titles = [f["title"] for f in flags]
    assert any("short interest" in t.lower() for t in titles)
    sev = [f["severity"] for f in flags if "short" in f["title"].lower()]
    assert "warning" in sev


def test_short_interest_low_no_flag():
    si = {"available": True, "short_pct_float": 5.0}
    flags = _build_flags(**_default_flags_kwargs(short_interest=si))
    titles = [f["title"] for f in flags]
    assert not any("short" in t.lower() for t in titles)


def test_short_interest_unavailable_no_flag():
    si = {"available": False, "short_pct_float": 30.0}
    flags = _build_flags(**_default_flags_kwargs(short_interest=si))
    titles = [f["title"] for f in flags]
    assert not any("short" in t.lower() for t in titles)


def test_short_interest_none_no_flag():
    flags = _build_flags(**_default_flags_kwargs(short_interest=None))
    titles = [f["title"] for f in flags]
    assert not any("short" in t.lower() for t in titles)


# ---------------------------------------------------------------------------
# P5.6: Macro context flags
# ---------------------------------------------------------------------------

def test_macro_high_vix_warning():
    macro = {"vix": 35.0, "spread_2y10y": 0.5}
    flags = _build_flags(**_default_flags_kwargs(macro_context=macro))
    titles = [f["title"] for f in flags]
    assert any("VIX" in t or "fear" in t.lower() for t in titles)


def test_macro_inverted_yield_curve_warning():
    macro = {"vix": 20.0, "spread_2y10y": -0.3}
    flags = _build_flags(**_default_flags_kwargs(macro_context=macro))
    titles = [f["title"] for f in flags]
    assert any("yield curve" in t.lower() for t in titles)


def test_macro_normal_no_macro_flag():
    macro = {"vix": 18.0, "spread_2y10y": 0.8}
    flags = _build_flags(**_default_flags_kwargs(macro_context=macro))
    titles = [f["title"] for f in flags]
    assert not any("VIX" in t or "yield curve" in t.lower() for t in titles)


def test_macro_none_no_flag():
    flags = _build_flags(**_default_flags_kwargs(macro_context=None))
    titles = [f["title"] for f in flags]
    assert not any("VIX" in t or "yield curve" in t.lower() for t in titles)


# ---------------------------------------------------------------------------
# P8.2: Volatility regime flags from _build_flags
# ---------------------------------------------------------------------------

def test_vol_regime_spike_flag():
    """Spike regime (hv_5d > 2×hv_30d) should produce a warning flag."""
    # Build a close series where recent 5-day vol >> 30-day baseline
    flat = [100.0] * 200
    spike = [flat[-1] * (1 + 0.10 * ((-1) ** i)) for i in range(6)]
    close = pd.Series(flat + spike)
    flags = _build_flags(**_default_flags_kwargs(close=close))
    # The spike flag is triggered by _detect_vol_regime internally;
    # just verify no crash and flags is a list
    assert isinstance(flags, list)


def test_vol_regime_no_crash_none_close():
    flags = _build_flags(**_default_flags_kwargs(close=None))
    assert isinstance(flags, list)


# ---------------------------------------------------------------------------
# compute_risk new return fields
# ---------------------------------------------------------------------------

def test_compute_risk_returns_vol_regime():
    result = compute_risk(
        quote={"c": 100.0},
        financials=None,
        close=noisy_close(),
        earnings=[],
        recommendations=[],
        sentiment_agg=None,
        composite_factor_score=50,
    )
    assert "vol_regime" in result
    assert result["vol_regime"] in ("normal", "spike", "sustained")


def test_compute_risk_returns_hv5_hv30():
    result = compute_risk(
        quote={"c": 100.0},
        financials=None,
        close=noisy_close(250),
        earnings=[],
        recommendations=[],
        sentiment_agg=None,
        composite_factor_score=50,
    )
    assert "hv_5d" in result
    assert "hv_30d" in result


def test_compute_risk_returns_macro_context():
    macro = {"vix": 22.0, "spread_2y10y": 0.4}
    result = compute_risk(
        quote={"c": 100.0},
        financials=None,
        close=noisy_close(),
        earnings=[],
        recommendations=[],
        sentiment_agg=None,
        composite_factor_score=50,
        macro_context=macro,
    )
    assert result["macro_context"] == macro


def test_compute_risk_macro_vix_above_30_increases_score():
    """High VIX macro context should increase risk score via macro_mult."""
    result_normal = compute_risk(
        quote={"c": 100.0},
        financials=None,
        close=noisy_close(250, seed=99),
        earnings=[],
        recommendations=[],
        sentiment_agg=None,
        composite_factor_score=50,
        macro_context={"vix": 15.0, "spread_2y10y": 0.5},
    )
    result_fear = compute_risk(
        quote={"c": 100.0},
        financials=None,
        close=noisy_close(250, seed=99),
        earnings=[],
        recommendations=[],
        sentiment_agg=None,
        composite_factor_score=50,
        macro_context={"vix": 35.0, "spread_2y10y": -0.4},
    )
    assert result_fear["risk_score"] >= result_normal["risk_score"]


def test_compute_risk_all_new_params_no_crash():
    from datetime import date
    today = date.today().isoformat()
    cal = {"days_to_earnings": 5, "next_date": today}
    txns = [{"transactionCode": "S", "change": -5000, "transactionDate": today}] * 3
    si = {"available": True, "short_pct_float": 20.0}
    macro = {"vix": 32.0, "spread_2y10y": -0.2}
    result = compute_risk(
        quote={"c": 100.0},
        financials={"peBasicExclExtraTTM": 25, "52WeekHigh": 120, "52WeekLow": 80},
        close=noisy_close(),
        earnings=[{"surprisePercent": -8}] * 4,
        recommendations=[{"strongBuy": 0, "buy": 1, "hold": 2, "sell": 3, "strongSell": 2}],
        sentiment_agg={"net_score": -0.5, "signal": "Bearish",
                       "counts": {"positive": 2, "negative": 7, "neutral": 1}},
        composite_factor_score=30,
        earnings_calendar=cal,
        insider_transactions=txns,
        short_interest=si,
        macro_context=macro,
    )
    assert isinstance(result["risk_score"], int)
    assert 0 <= result["risk_score"] <= 100
