"""AutoResearch — editable strategy file.

The autoresearch agent modifies THIS file only.

Entry point: ``compute_signal(close, index) -> int``

Rules:
- Only ``math``, ``pandas``, and ``numpy`` may be imported.
- Return 50 when index < 35 (insufficient history).
- Return value must be 0-100.
- No look-ahead: only use ``close.iloc[:index+1]``.
"""

from __future__ import annotations

import math

import pandas as pd


def compute_signal(close: pd.Series, index: int) -> int:  # noqa: C901
    """Return a signal score 0-100 for the bar at *index*.

    Starting strategy: Price Technical v2
    - SMA trend 35% (directional, requires 50+ bars for SMA-50)
    - RSI directional 25% (linear mapping: RSI 70 → score 74, RSI 30 → score 26)
    - MACD histogram 25% (direction + momentum)
    - Bollinger Band position 15% (price within ±2σ of SMA-20)
    """
    if index < 35:
        return 50

    slice_ = close.iloc[: index + 1]
    n = len(slice_)
    price = float(slice_.iloc[-1])

    # --- SMA trend (35%) ---
    sma_score = 50
    if n >= 50:
        sma50 = float(slice_.rolling(50).mean().iloc[-1])
        sma200 = float(slice_.rolling(200).mean().iloc[-1]) if n >= 200 else None
        if sma200 is not None:
            if price > sma50 > sma200:
                sma_score = 90
            elif price < sma50 < sma200:
                sma_score = 10
            else:
                sma_score = 50
        else:
            sma_score = 70 if price > sma50 else 30

    # --- RSI directional (25%) ---
    rsi_score = 50
    if n >= 15:
        delta = slice_.diff()
        avg_gain = delta.clip(lower=0).ewm(alpha=1 / 14, min_periods=14).mean()
        avg_loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, min_periods=14).mean()
        rs = avg_gain / avg_loss
        rsi = float((100 - 100 / (1 + rs)).iloc[-1])
        if not math.isnan(rsi):
            # Linear directional: RSI 50 → 50, amplified 1.2×
            rsi_score = int(max(10, min(90, 50 + (rsi - 50) * 1.2)))

    # --- MACD histogram (25%) ---
    macd_score = 50
    if n >= 36:
        ema12 = slice_.ewm(span=12, adjust=False).mean()
        ema26 = slice_.ewm(span=26, adjust=False).mean()
        hist = (ema12 - ema26) - (ema12 - ema26).ewm(span=9, adjust=False).mean()
        h_now = float(hist.iloc[-1])
        h_prev = float(hist.iloc[-2])
        if h_now > 0 and h_now > h_prev:
            macd_score = 85
        elif h_now > 0:
            macd_score = 65
        elif h_now <= 0 and h_now > h_prev:
            macd_score = 40
        else:
            macd_score = 15

    # --- Bollinger Band position (15%) ---
    bb_score = 50
    if n >= 22:
        sma20 = float(slice_.rolling(20).mean().iloc[-1])
        std20 = float(slice_.rolling(20).std().iloc[-1])
        if std20 > 0:
            bb_range = 4 * std20
            bb_pos = (price - (sma20 - 2 * std20)) / bb_range
            bb_score = int(max(0, min(100, bb_pos * 100)))

    return int(0.35 * sma_score + 0.25 * rsi_score + 0.25 * macd_score + 0.15 * bb_score)
