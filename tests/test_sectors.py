"""Tests for sectors.py (P3.3)."""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


def _make_close(n=252, drift=0.0002):
    prices = [100.0]
    for _ in range(n - 1):
        prices.append(prices[-1] * (1 + drift + np.random.normal(0, 0.01)))
    return pd.Series(prices)


def test_sector_momentum_score_structure():
    from sectors import sector_momentum_score
    close = _make_close(252)
    result = sector_momentum_score(close)
    assert "score" in result
    assert 0 <= result["score"] <= 100
    assert "perf_1m" in result
    assert "perf_3m" in result
    assert "perf_6m" in result
    assert "rsi" in result
    assert "volatility" in result


def test_sector_momentum_insufficient_data():
    from sectors import sector_momentum_score
    close = pd.Series([100, 101, 102])
    result = sector_momentum_score(close)
    assert result["score"] == 50  # default when insufficient data


def test_uptrending_sector_high_score():
    from sectors import sector_momentum_score
    close = _make_close(252, drift=0.003)  # strong uptrend
    result = sector_momentum_score(close)
    assert result["score"] > 50


def test_downtrending_sector_low_score():
    from sectors import sector_momentum_score
    close = _make_close(252, drift=-0.003)  # strong downtrend
    result = sector_momentum_score(close)
    assert result["score"] < 50


def test_classify_rotation_phase_leading():
    from sectors import classify_rotation_phase
    assert classify_rotation_phase(75, 3.0, 5.0) == "Leading"


def test_classify_rotation_phase_lagging():
    from sectors import classify_rotation_phase
    assert classify_rotation_phase(25, -3.0, -5.0) == "Lagging"


def test_classify_rotation_phase_neutral():
    from sectors import classify_rotation_phase
    assert classify_rotation_phase(50, 0.5, 1.0) == "Neutral"


def test_classify_rotation_phase_improving():
    from sectors import classify_rotation_phase
    # High score, good 1M but weak 3M → Improving
    assert classify_rotation_phase(75, 3.0, -2.0) == "Improving"
