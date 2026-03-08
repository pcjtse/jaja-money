"""Unit tests for portfolio.py — position sizing, entry strategy, stops, targets."""

import pytest
import pandas as pd

from portfolio import (
    suggest_position,
    RISK_TOLERANCES,
    HORIZONS,
    _hist_vol,
    _rsi,
    _HORIZON_KEY,
    _TOLERANCE_KEY,
)

SHORT  = HORIZONS[0]
MEDIUM = HORIZONS[1]
LONG   = HORIZONS[2]

CONSERVATIVE = RISK_TOLERANCES[0]
MODERATE     = RISK_TOLERANCES[1]
AGGRESSIVE   = RISK_TOLERANCES[2]

QUOTE_100 = {"c": 100.0}
QUOTE_200 = {"c": 200.0}
QUOTE_ZERO = {"c": 0}


def rising_close(n=60, start=100, step=1):
    return pd.Series([float(start + i * step) for i in range(n)])

def falling_close(n=60, start=160, step=1):
    return pd.Series([float(start - i * step) for i in range(n)])

def flat_close(n=30, price=100):
    return pd.Series([float(price)] * n)

def noisy_close(n=250, start=100.0, drift=0.0005, vol=0.015, seed=42):
    """Random-walk series with realistic daily volatility (~24% annualised)."""
    import random
    random.seed(seed)
    prices = [start]
    for _ in range(n - 1):
        r = drift + random.gauss(0, vol)
        prices.append(max(prices[-1] * (1 + r), 0.01))
    return pd.Series(prices)


# ---------------------------------------------------------------------------
# _hist_vol (portfolio version — returns ratio not %)
# ---------------------------------------------------------------------------

def test_hist_vol_none():
    assert _hist_vol(None) is None

def test_hist_vol_insufficient():
    assert _hist_vol(pd.Series([100.0] * 5)) is None

def test_hist_vol_rising_positive():
    result = _hist_vol(rising_close(50))
    assert result is not None
    assert result > 0

def test_hist_vol_flat_zero():
    result = _hist_vol(flat_close(30))
    assert result is not None
    assert result == pytest.approx(0.0)

def test_hist_vol_no_crash_zero_price():
    close = pd.Series([100.0] * 10 + [0.0] + [100.0] * 20)
    result = _hist_vol(close)
    assert result is None or isinstance(result, float)


# ---------------------------------------------------------------------------
# _rsi (portfolio version)
# ---------------------------------------------------------------------------

def test_portfolio_rsi_none():
    assert _rsi(None) is None

def test_portfolio_rsi_insufficient():
    assert _rsi(pd.Series([100.0] * 5)) is None

def test_portfolio_rsi_rising_high():
    result = _rsi(rising_close(50))
    assert result is not None
    assert result > 80

def test_portfolio_rsi_falling_low():
    result = _rsi(falling_close(50))
    assert result is not None
    assert result < 20


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

def test_risk_tolerances_has_three():
    assert len(RISK_TOLERANCES) == 3

def test_horizons_has_three():
    assert len(HORIZONS) == 3

def test_horizon_key_mapping():
    assert _HORIZON_KEY[SHORT] == "short"
    assert _HORIZON_KEY[MEDIUM] == "medium"
    assert _HORIZON_KEY[LONG] == "long"

def test_tolerance_key_mapping():
    assert _TOLERANCE_KEY[CONSERVATIVE] == "conservative"
    assert _TOLERANCE_KEY[MODERATE] == "moderate"
    assert _TOLERANCE_KEY[AGGRESSIVE] == "aggressive"


# ---------------------------------------------------------------------------
# suggest_position — return keys
# ---------------------------------------------------------------------------

def test_suggest_position_return_keys():
    result = suggest_position(MODERATE, MEDIUM, 60, 35, QUOTE_100)
    required = {"action", "action_color", "position_pct", "position_label",
                "entry_strategy", "stop_price", "stop_pct", "target_1",
                "target_2", "risk_reward", "rationale"}
    assert required.issubset(result.keys())

def test_suggest_position_rationale_is_list():
    result = suggest_position(MODERATE, MEDIUM, 60, 35, QUOTE_100)
    assert isinstance(result["rationale"], list)
    assert len(result["rationale"]) > 0


# ---------------------------------------------------------------------------
# Action determination
# ---------------------------------------------------------------------------

def test_action_buy_strong_factor_low_risk():
    result = suggest_position(MODERATE, MEDIUM, 75, 30, QUOTE_100)
    assert result["action"] == "Buy"

def test_action_accumulate_moderate_factor():
    result = suggest_position(MODERATE, MEDIUM, 60, 50, QUOTE_100)
    assert result["action"] == "Accumulate"

def test_action_hold_neutral_factor():
    result = suggest_position(MODERATE, MEDIUM, 50, 60, QUOTE_100)
    assert result["action"] == "Hold"

def test_action_reduce_weak_factor():
    result = suggest_position(MODERATE, MEDIUM, 35, 70, QUOTE_100)
    assert result["action"] == "Reduce"

def test_action_avoid_very_weak_factor_high_risk():
    result = suggest_position(MODERATE, MEDIUM, 20, 85, QUOTE_100)
    assert result["action"] == "Avoid"

def test_action_avoid_has_zero_or_minimal_position():
    result = suggest_position(CONSERVATIVE, SHORT, 15, 90, QUOTE_100)
    assert result["action"] == "Avoid"
    # position_pct should be very small for avoid
    assert result["position_pct"] < 2.0


# ---------------------------------------------------------------------------
# Position sizing bounds
# ---------------------------------------------------------------------------

def test_position_pct_in_bounds_conservative():
    result = suggest_position(CONSERVATIVE, MEDIUM, 70, 20, QUOTE_100)
    assert 0.0 <= result["position_pct"] <= 5.0

def test_position_pct_in_bounds_moderate():
    result = suggest_position(MODERATE, MEDIUM, 70, 20, QUOTE_100)
    assert 0.0 <= result["position_pct"] <= 10.0

def test_position_pct_in_bounds_aggressive():
    result = suggest_position(AGGRESSIVE, LONG, 80, 15, QUOTE_100)
    assert 0.0 <= result["position_pct"] <= 20.0

def test_position_label_format():
    result = suggest_position(MODERATE, MEDIUM, 60, 35, QUOTE_100)
    label = result["position_label"]
    assert "–" in label or "-" in label
    assert "%" in label

def test_position_label_hi_capped_at_base_max():
    # Aggressive + strong factor + low risk → should be near base_max (20%)
    result = suggest_position(AGGRESSIVE, LONG, 80, 10, QUOTE_100)
    hi_str = result["position_label"].split("–")[1].replace("%", "").strip()
    hi = float(hi_str)
    assert hi <= 20.0  # capped at base_max

def test_position_pct_higher_for_aggressive():
    conservative = suggest_position(CONSERVATIVE, MEDIUM, 70, 20, QUOTE_100)
    aggressive   = suggest_position(AGGRESSIVE,   MEDIUM, 70, 20, QUOTE_100)
    assert aggressive["position_pct"] >= conservative["position_pct"]

def test_position_pct_higher_for_long_horizon():
    short  = suggest_position(MODERATE, SHORT,  70, 20, QUOTE_100)
    long_h = suggest_position(MODERATE, LONG,   70, 20, QUOTE_100)
    assert long_h["position_pct"] >= short["position_pct"]

def test_position_pct_lower_for_high_risk():
    low_risk  = suggest_position(MODERATE, MEDIUM, 65, 20,  QUOTE_100)
    high_risk = suggest_position(MODERATE, MEDIUM, 65, 75,  QUOTE_100)
    assert low_risk["position_pct"] >= high_risk["position_pct"]


# ---------------------------------------------------------------------------
# Stop-loss
# ---------------------------------------------------------------------------

def test_stop_price_below_current():
    # Use a noisy series so HV > 0 and stop is meaningfully below entry
    close = noisy_close()
    result = suggest_position(MODERATE, MEDIUM, 65, 30, QUOTE_100, close=close)
    if result["stop_price"] is not None:
        assert result["stop_price"] < 100.0

def test_stop_pct_positive():
    close = noisy_close()
    result = suggest_position(MODERATE, MEDIUM, 65, 30, QUOTE_100, close=close)
    if result["stop_pct"] is not None:
        assert result["stop_pct"] > 0

def test_stop_pct_conservative_tighter():
    close = noisy_close()
    r_con = suggest_position(CONSERVATIVE, MEDIUM, 65, 30, QUOTE_100, close=close)
    r_agg = suggest_position(AGGRESSIVE,   MEDIUM, 65, 30, QUOTE_100, close=close)
    # Conservative uses z_mult=1.5, Aggressive uses 2.5 → conservative stop is tighter
    if r_con["stop_pct"] and r_agg["stop_pct"]:
        assert r_con["stop_pct"] < r_agg["stop_pct"]

def test_stop_fallback_no_close():
    # Without close data, falls back to fixed % stop
    result = suggest_position(MODERATE, MEDIUM, 65, 30, QUOTE_100, close=None)
    assert result["stop_price"] is not None
    assert result["stop_pct"] == pytest.approx(10.0)  # moderate fixed = 10%
    assert result["stop_price"] == pytest.approx(90.0)

def test_stop_conservative_fallback():
    result = suggest_position(CONSERVATIVE, MEDIUM, 65, 30, QUOTE_100, close=None)
    assert result["stop_pct"] == pytest.approx(7.0)

def test_stop_aggressive_fallback():
    result = suggest_position(AGGRESSIVE, MEDIUM, 65, 30, QUOTE_100, close=None)
    assert result["stop_pct"] == pytest.approx(14.0)

def test_no_stop_for_zero_price():
    result = suggest_position(MODERATE, MEDIUM, 65, 30, QUOTE_ZERO, close=None)
    assert result["stop_price"] is None


# ---------------------------------------------------------------------------
# Price targets
# ---------------------------------------------------------------------------

def test_targets_above_price():
    result = suggest_position(MODERATE, MEDIUM, 65, 30, QUOTE_100)
    assert result["target_1"] > 100.0
    assert result["target_2"] > result["target_1"]

def test_targets_long_horizon_higher():
    r_short = suggest_position(MODERATE, SHORT,  65, 30, QUOTE_100)
    r_long  = suggest_position(MODERATE, LONG,   65, 30, QUOTE_100)
    assert r_long["target_1"] > r_short["target_1"]
    assert r_long["target_2"] > r_short["target_2"]

def test_targets_strong_factor_higher():
    r_weak   = suggest_position(MODERATE, MEDIUM, 40, 30, QUOTE_100)
    r_strong = suggest_position(MODERATE, MEDIUM, 80, 30, QUOTE_100)
    if r_strong["target_1"] and r_weak["target_1"]:
        assert r_strong["target_1"] >= r_weak["target_1"]

def test_targets_none_for_zero_price():
    result = suggest_position(MODERATE, MEDIUM, 65, 30, QUOTE_ZERO)
    assert result["target_1"] is None
    assert result["target_2"] is None

def test_targets_reflect_price():
    result = suggest_position(MODERATE, MEDIUM, 65, 30, QUOTE_200)
    assert result["target_1"] > 200.0


# ---------------------------------------------------------------------------
# Risk / reward
# ---------------------------------------------------------------------------

def test_rr_positive_for_buy():
    result = suggest_position(MODERATE, MEDIUM, 70, 25, QUOTE_100, close=None)
    if result["risk_reward"] is not None:
        assert result["risk_reward"] > 0

def test_rr_none_for_zero_price():
    result = suggest_position(MODERATE, MEDIUM, 70, 25, QUOTE_ZERO)
    assert result["risk_reward"] is None

def test_rr_not_unrealistically_large():
    # stop_pct must be >= 0.1 to compute R/R — prevents absurd ratios
    close = flat_close(250)   # HV ≈ 0 → very small stop
    result = suggest_position(MODERATE, MEDIUM, 70, 25, QUOTE_100, close=close)
    # With near-zero stop, R/R should be None (guard kicks in)
    # OR if fixed fallback is used, R/R should be finite and reasonable
    if result["risk_reward"] is not None:
        assert result["risk_reward"] < 1000


# ---------------------------------------------------------------------------
# Entry strategy
# ---------------------------------------------------------------------------

def test_entry_strategy_avoid():
    result = suggest_position(CONSERVATIVE, SHORT, 15, 90, QUOTE_100)
    assert "Do not initiate" in result["entry_strategy"]

def test_entry_strategy_reduce():
    result = suggest_position(MODERATE, MEDIUM, 35, 70, QUOTE_100)
    assert "Trim" in result["entry_strategy"]

def test_entry_strategy_overbought():
    close = rising_close(50)  # RSI → near 100 → overbought
    result = suggest_position(MODERATE, LONG, 70, 20, QUOTE_100, close=close)
    assert "RSI" in result["entry_strategy"] or "overbought" in result["entry_strategy"].lower() or "Wait" in result["entry_strategy"]

def test_entry_strategy_is_string():
    result = suggest_position(MODERATE, MEDIUM, 60, 35, QUOTE_100)
    assert isinstance(result["entry_strategy"], str)
    assert len(result["entry_strategy"]) > 0


# ---------------------------------------------------------------------------
# Action color
# ---------------------------------------------------------------------------

def test_action_color_is_hex():
    result = suggest_position(MODERATE, MEDIUM, 60, 35, QUOTE_100)
    assert result["action_color"].startswith("#")

def test_action_color_green_for_buy():
    result = suggest_position(MODERATE, MEDIUM, 75, 20, QUOTE_100)
    assert result["action"] == "Buy"
    # Green hex for buy
    assert result["action_color"] in ("#2da44e", "#4CAF50")

def test_action_color_red_for_avoid():
    result = suggest_position(MODERATE, MEDIUM, 15, 90, QUOTE_100)
    assert result["action"] == "Avoid"
    assert result["action_color"] in ("#cf2929", "#e05252")
