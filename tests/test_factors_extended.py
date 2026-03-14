"""Extended tests for factors.py new indicators (P1.4)."""

import pytest
import pandas as pd
import numpy as np


def _make_ohlcv(n=100, start=100.0):
    np.random.seed(42)
    closes = [start]
    for _ in range(n - 1):
        closes.append(closes[-1] * (1 + np.random.normal(0, 0.01)))
    opens = [c * 0.999 for c in closes]
    highs = [c * 1.01 for c in closes]
    lows = [c * 0.99 for c in closes]
    volumes = [1_000_000 + int(np.random.normal(0, 50_000)) for _ in range(n)]
    return pd.DataFrame(
        {
            "Date": pd.date_range("2023-01-01", periods=n),
            "Open": opens,
            "High": highs,
            "Low": lows,
            "Close": closes,
            "Volume": volumes,
        }
    )


# ---------------------------------------------------------------------------
# Bollinger Bands
# ---------------------------------------------------------------------------


def test_bollinger_bands_structure():
    from factors import calc_bollinger_bands

    df = _make_ohlcv(100)
    result = calc_bollinger_bands(df["Close"], window=20)
    assert result is not None
    assert "upper" in result
    assert "middle" in result
    assert "lower" in result
    assert "pct_b" in result
    assert "bandwidth" in result


def test_bollinger_upper_above_lower():
    from factors import calc_bollinger_bands

    df = _make_ohlcv(100)
    bb = calc_bollinger_bands(df["Close"])
    assert bb["upper"] > bb["lower"]
    assert bb["upper"] > bb["middle"]
    assert bb["middle"] > bb["lower"]


def test_bollinger_insufficient_data():
    from factors import calc_bollinger_bands

    close = pd.Series([100, 101, 102])
    assert calc_bollinger_bands(close, window=20) is None


def test_bollinger_pct_b_range():
    from factors import calc_bollinger_bands

    df = _make_ohlcv(200)
    bb = calc_bollinger_bands(df["Close"])
    # pct_b can be outside 0-1 when price is beyond bands
    assert isinstance(bb["pct_b"], float)


def test_bollinger_series_length():
    from factors import calc_bollinger_bands

    df = _make_ohlcv(100)
    bb = calc_bollinger_bands(df["Close"], window=20)
    assert len(bb["upper_series"]) == 100
    assert len(bb["lower_series"]) == 100
    assert len(bb["middle_series"]) == 100


# ---------------------------------------------------------------------------
# OBV
# ---------------------------------------------------------------------------


def test_obv_returns_series():
    from factors import calc_obv

    df = _make_ohlcv(100)
    obv = calc_obv(df["Close"], df["Volume"])
    assert obv is not None
    assert isinstance(obv, pd.Series)
    assert len(obv) == 100


def test_obv_none_when_no_volume():
    from factors import calc_obv

    close = pd.Series([100, 101, 102])
    assert calc_obv(close, None) is None


def test_obv_none_when_length_mismatch():
    from factors import calc_obv

    close = pd.Series([100, 101, 102])
    vol = pd.Series([1000, 2000])  # different length
    assert calc_obv(close, vol) is None


def test_obv_rising_on_updays():
    from factors import calc_obv

    # All up days → OBV should be monotonically increasing
    close = pd.Series([100, 101, 102, 103, 104])
    vol = pd.Series([1000, 1000, 1000, 1000, 1000])
    obv = calc_obv(close, vol)
    assert all(obv.diff().dropna() >= 0)


# ---------------------------------------------------------------------------
# VWAP
# ---------------------------------------------------------------------------


def test_vwap_returns_float():
    from factors import calc_vwap

    df = _make_ohlcv(100)
    vwap = calc_vwap(df)
    assert vwap is not None
    assert isinstance(vwap, float)
    assert vwap > 0


def test_vwap_none_on_empty():
    from factors import calc_vwap

    assert calc_vwap(None) is None
    assert calc_vwap(pd.DataFrame()) is None


def test_vwap_none_on_missing_columns():
    from factors import calc_vwap

    df = pd.DataFrame({"Close": [100, 101]})
    assert calc_vwap(df) is None


def test_vwap_near_typical_price():
    from factors import calc_vwap

    # Flat OHLCV → VWAP should be close to the price
    n = 20
    df = pd.DataFrame(
        {
            "High": [100.0] * n,
            "Low": [100.0] * n,
            "Close": [100.0] * n,
            "Volume": [1000] * n,
        }
    )
    vwap = calc_vwap(df)
    assert vwap == pytest.approx(100.0, abs=0.01)
