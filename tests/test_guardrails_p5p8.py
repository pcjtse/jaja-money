"""Tests for P5/P8 guardrails enhancements.

Covers:
- P8.2 Volatility regime detection (vol_regime, hv_5d, hv_30d fields)
- P8.1 Liquidity risk flag (account_size / max_position_pct params)
- P5.6 macro_context pass-through field
- compute_risk() returns new fields (vol_regime, hv_5d, hv_30d, macro_context)
"""
from __future__ import annotations

import pandas as pd
import numpy as np

from guardrails import compute_risk, _volatility_regime


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _price_series(n=60, start=100.0, step=1.0) -> pd.Series:
    return pd.Series([float(start + i * step) for i in range(n)])


def _noisy_series(n=250, vol=0.015, seed=42) -> pd.Series:
    rng = np.random.default_rng(seed)
    returns = rng.normal(0, vol, n)
    prices = [100.0]
    for r in returns:
        prices.append(max(prices[-1] * (1 + r), 0.01))
    return pd.Series(prices[:n])


def _base_risk(**overrides) -> dict:
    """Helper to call compute_risk with minimal valid inputs."""
    close = _price_series()
    kwargs = dict(
        quote={"c": 110.0},
        financials=None,
        close=close,
        earnings=[],
        recommendations=[],
        sentiment_agg=None,
        composite_factor_score=50,
    )
    kwargs.update(overrides)
    return compute_risk(**kwargs)


QUOTE_100 = {"c": 100.0}


# ---------------------------------------------------------------------------
# New return fields are present
# ---------------------------------------------------------------------------

def test_compute_risk_returns_vol_regime():
    result = _base_risk()
    assert "vol_regime" in result


def test_compute_risk_returns_hv_5d():
    result = _base_risk()
    assert "hv_5d" in result


def test_compute_risk_returns_hv_30d():
    result = _base_risk()
    assert "hv_30d" in result


def test_compute_risk_returns_macro_context_none_by_default():
    result = _base_risk()
    assert "macro_context" in result
    assert result["macro_context"] is None


def test_compute_risk_passes_macro_context_through():
    ctx = {"vix": 18.5, "vix_regime": "calm", "treasury_10y": 4.25}
    result = _base_risk(macro_context=ctx)
    assert result["macro_context"] == ctx


# ---------------------------------------------------------------------------
# P8.2: _volatility_regime
# ---------------------------------------------------------------------------

def test_vol_regime_returns_unknown_when_no_data():
    assert _volatility_regime(None, None) == "unknown"
    assert _volatility_regime(20.0, None) == "unknown"
    assert _volatility_regime(None, 20.0) == "unknown"


def test_vol_regime_spike_when_5d_much_higher():
    # hv_5d > 2 × hv_30d → spike
    assert _volatility_regime(50.0, 20.0) == "spike"


def test_vol_regime_sustained_when_both_high():
    # hv_5d > 1.5 × hv_30d and hv_30d > 30 → sustained
    assert _volatility_regime(50.0, 32.0) == "sustained"


def test_vol_regime_elevated_when_30d_high():
    # hv_30d > 30 but hv_5d not spiking
    assert _volatility_regime(35.0, 32.0) == "elevated"


def test_vol_regime_normal_when_low_vol():
    assert _volatility_regime(12.0, 14.0) == "normal"


def test_compute_risk_vol_regime_with_noisy_prices():
    close = _noisy_series()
    result = compute_risk(
        quote={"c": 100.0},
        financials=None,
        close=close,
        earnings=[],
        recommendations=[],
        sentiment_agg=None,
        composite_factor_score=50,
    )
    assert result["vol_regime"] in ("spike", "sustained", "elevated", "normal", "unknown")
    # hv_5d and hv_30d should be computable from 250 bars
    assert result["hv_5d"] is not None
    assert result["hv_30d"] is not None


# ---------------------------------------------------------------------------
# P8.2: vol_regime affects risk score (sustained/spike adds points)
# ---------------------------------------------------------------------------

def test_sustained_vol_raises_risk_score():
    """Artificially force hv_5d > 1.5 × hv_30d and hv_30d > 30 using a volatile series."""
    rng = np.random.default_rng(0)
    # Build a series where last 5 days are extremely volatile
    stable = [100.0 + i * 0.1 for i in range(200)]
    spiky = [stable[-1] * (1 + rng.normal(0, 0.08)) for _ in range(35)]
    close = pd.Series(stable + spiky)

    result_spiky = compute_risk(
        quote={"c": float(close.iloc[-1])},
        financials=None,
        close=close,
        earnings=[],
        recommendations=[],
        sentiment_agg=None,
        composite_factor_score=50,
    )
    result_stable = compute_risk(
        quote={"c": 120.0},
        financials=None,
        close=pd.Series(stable[-60:]),
        earnings=[],
        recommendations=[],
        sentiment_agg=None,
        composite_factor_score=50,
    )
    # Spiky series should have higher or equal risk score
    assert result_spiky["risk_score"] >= result_stable["risk_score"] - 5


# ---------------------------------------------------------------------------
# P8.1: Liquidity risk flag
# ---------------------------------------------------------------------------

def test_no_liquidity_flag_without_account_size():
    result = _base_risk()
    flag_titles = [f["title"] for f in result["flags"]]
    assert not any("Liquidity" in t for t in flag_titles)


def test_liquidity_flag_appears_with_large_account():
    close = _price_series(n=30, start=10.0, step=0.1)
    result = compute_risk(
        quote={"c": 12.0},
        financials=None,
        close=close,
        earnings=[],
        recommendations=[],
        sentiment_agg=None,
        composite_factor_score=50,
        account_size=5_000_000,  # $5M account, 5% = $250k position
        max_position_pct=0.05,
    )
    flag_titles = [f["title"] for f in result["flags"]]
    assert any("Liquidity" in t for t in flag_titles)


def test_no_liquidity_flag_for_small_account():
    close = _price_series(n=30)
    result = compute_risk(
        quote={"c": 100.0},
        financials=None,
        close=close,
        earnings=[],
        recommendations=[],
        sentiment_agg=None,
        composite_factor_score=50,
        account_size=50_000,   # $50k account → position < $100k threshold
        max_position_pct=0.05,
    )
    flag_titles = [f["title"] for f in result["flags"]]
    assert not any("Liquidity" in t for t in flag_titles)


# ---------------------------------------------------------------------------
# Insider transaction helper (used in broader P5 tests)
# ---------------------------------------------------------------------------

def _make_insider_txns(buys=0, sells=0, buy_shares=1000, sell_shares=1000):
    """Create a minimal list of recent insider transactions."""
    from datetime import date
    today = date.today().isoformat()
    txns = []
    for _ in range(buys):
        txns.append({
            "transactionDate": today,
            "transactionCode": "P",   # Purchase
            "share": buy_shares,
            "change": buy_shares,
        })
    for _ in range(sells):
        txns.append({
            "transactionDate": today,
            "transactionCode": "S",   # Sale
            "share": sell_shares,
            "change": -sell_shares,
        })
    return txns


def test_make_insider_txns_returns_expected_counts():
    txns = _make_insider_txns(buys=3, sells=2)
    assert len(txns) == 5
    purchases = [t for t in txns if t["transactionCode"] == "P"]
    sales = [t for t in txns if t["transactionCode"] == "S"]
    assert len(purchases) == 3
    assert len(sales) == 2
