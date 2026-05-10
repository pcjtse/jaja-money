"""Named strategy signal functions for the backtesting engine.

Each strategy has the signature::

    (close: pd.Series, index: int) -> int

Returns a score 0-100 where the default thresholds are:
- ``>= 65``  →  Buy
- ``<= 40``  →  Sell
- ``41-64``  →  Hold

``STRATEGY_REGISTRY`` maps display names to callables so the backtest
page and the autoresearch harness can look them up by name.
"""

from __future__ import annotations

import math

import pandas as pd


# ---------------------------------------------------------------------------
# v1 — Original baseline (SMA 40% + symmetric RSI 30% + MACD 30%)
# ---------------------------------------------------------------------------


def price_technical_v1(close: pd.Series, index: int) -> int:
    """Original 3-indicator price signal.

    Kept as the baseline so walk-forward and sweep results are comparable
    against the improved variants.

    RSI scoring is *symmetric* — peaks at RSI=50 and treats overbought
    and oversold identically.  That is the known weakness this module fixes.
    """
    if index < 35:
        return 50

    slice_ = close.iloc[: index + 1]
    n = len(slice_)

    # SMA trend (40%)
    sma_score = 50
    if n >= 50:
        sma50 = float(slice_.rolling(50).mean().iloc[-1])
        sma200 = float(slice_.rolling(200).mean().iloc[-1]) if n >= 200 else None
        price = float(slice_.iloc[-1])
        if sma200 is not None:
            if price > sma50 > sma200:
                sma_score = 90
            elif price < sma50 < sma200:
                sma_score = 10
            else:
                sma_score = 50
        else:
            sma_score = 70 if price > sma50 else 30

    # RSI (30%) — symmetric: peaks at RSI=50
    rsi_score = 50
    if n >= 15:
        delta = slice_.diff()
        avg_gain = delta.clip(lower=0).ewm(alpha=1 / 14, min_periods=14).mean()
        avg_loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, min_periods=14).mean()
        rs = avg_gain / avg_loss
        rsi = float((100 - 100 / (1 + rs)).iloc[-1])
        if not math.isnan(rsi):
            rsi_score = int(max(0, min(100, 100 - abs(rsi - 50) * 0.5)))

    # MACD (30%)
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

    return int(0.40 * sma_score + 0.30 * rsi_score + 0.30 * macd_score)


# ---------------------------------------------------------------------------
# v2 — Improved: directional RSI + Bollinger Band filter
# ---------------------------------------------------------------------------


def price_technical_v2(close: pd.Series, index: int) -> int:
    """Improved momentum strategy with directional RSI and Bollinger Band filter.

    Key changes over v1:

    * **RSI is directional** — RSI=70 (bullish momentum) scores high, RSI=30
      (bearish momentum) scores low.  v1 treated them identically (both scored
      ~90) because it used ``abs(rsi - 50)``.

    * **Bollinger Band position** replaces some SMA weight — price at the upper
      band in an expanding-width regime confirms trend strength.

    Weights: SMA 35% | RSI 25% | MACD 25% | Bollinger Band 15%
    """
    if index < 35:
        return 50

    slice_ = close.iloc[: index + 1]
    n = len(slice_)
    price = float(slice_.iloc[-1])

    # SMA trend (35%)
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

    # RSI (25%) — directional: RSI 70 → score 74, RSI 30 → score 26
    rsi_score = 50
    if n >= 15:
        delta = slice_.diff()
        avg_gain = delta.clip(lower=0).ewm(alpha=1 / 14, min_periods=14).mean()
        avg_loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, min_periods=14).mean()
        rs = avg_gain / avg_loss
        rsi = float((100 - 100 / (1 + rs)).iloc[-1])
        if not math.isnan(rsi):
            # Linear directional mapping: RSI 50 → 50, amplified 1.2×
            rsi_score = int(max(10, min(90, 50 + (rsi - 50) * 1.2)))

    # MACD (25%)
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

    # Bollinger Band position (15%)
    bb_score = 50
    if n >= 22:
        sma20 = float(slice_.rolling(20).mean().iloc[-1])
        std20 = float(slice_.rolling(20).std().iloc[-1])
        if std20 > 0:
            bb_range = 4 * std20  # upper - lower = 4σ
            bb_pos = (price - (sma20 - 2 * std20)) / bb_range
            bb_score = int(max(0, min(100, bb_pos * 100)))

    return int(0.35 * sma_score + 0.25 * rsi_score + 0.25 * macd_score + 0.15 * bb_score)


# ---------------------------------------------------------------------------
# MA Crossover — pure golden/death cross
# ---------------------------------------------------------------------------


def ma_crossover(close: pd.Series, index: int) -> int:
    """Pure SMA golden/death cross strategy.

    * Golden cross (SMA-50 rises above SMA-200, price above both) → 88
    * Death cross (SMA-50 falls below SMA-200, price below both) → 12
    * Mixed / insufficient history → 50

    Produces fewer, longer-duration trades than technical v1/v2.  Works
    best on index ETFs and large-cap trending stocks.
    """
    if index < 200:
        return 50

    slice_ = close.iloc[: index + 1]
    n = len(slice_)

    if n < 202:
        return 50

    sma50_now = float(slice_.rolling(50).mean().iloc[-1])
    sma200_now = float(slice_.rolling(200).mean().iloc[-1])
    sma50_prev = float(slice_.rolling(50).mean().iloc[-2])
    sma200_prev = float(slice_.rolling(200).mean().iloc[-2])
    price = float(slice_.iloc[-1])

    # Fresh golden cross: SMA-50 just crossed above SMA-200
    if sma50_now > sma200_now and sma50_prev <= sma200_prev:
        return 92
    # Established uptrend
    if sma50_now > sma200_now and price > sma50_now:
        return 80
    # SMA-50 above SMA-200 but price lagging
    if sma50_now > sma200_now:
        return 60
    # Fresh death cross: SMA-50 just crossed below SMA-200
    if sma50_now < sma200_now and sma50_prev >= sma200_prev:
        return 8
    # Established downtrend
    if sma50_now < sma200_now and price < sma50_now:
        return 20
    # SMA-50 below SMA-200 but price recovering
    if sma50_now < sma200_now:
        return 40
    return 50


# ---------------------------------------------------------------------------
# Momentum Breakout — 52-week high proximity + RSI confirmation
# ---------------------------------------------------------------------------


def momentum_breakout(close: pd.Series, index: int) -> int:
    """Momentum breakout strategy: buy strength, sell weakness.

    Entry signal is high when:
    - Price is near or above its rolling 252-day (1-year) high
    - RSI confirms bullish momentum (55-80)
    - Price is above SMA-50

    This is a trend-following strategy that performs well in strong bull
    markets but gives back gains during sideways/bear periods.

    Weights: 52-week high proximity 40% | RSI directional 35% | SMA filter 25%
    """
    if index < 35:
        return 50

    slice_ = close.iloc[: index + 1]
    n = len(slice_)
    price = float(slice_.iloc[-1])

    # 52-week high proximity (40%)
    lookback = min(n, 252)
    high_52w = float(slice_.iloc[-lookback:].max())
    proximity_score = 50
    if high_52w > 0:
        # score = 100 when at 52-week high, 0 when 30%+ below
        pct_from_high = (price - high_52w) / high_52w  # negative when below high
        proximity_score = int(max(0, min(100, 100 + pct_from_high * 333)))

    # RSI directional (35%)
    rsi_score = 50
    if n >= 15:
        delta = slice_.diff()
        avg_gain = delta.clip(lower=0).ewm(alpha=1 / 14, min_periods=14).mean()
        avg_loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, min_periods=14).mean()
        rs = avg_gain / avg_loss
        rsi = float((100 - 100 / (1 + rs)).iloc[-1])
        if not math.isnan(rsi):
            rsi_score = int(max(10, min(90, 50 + (rsi - 50) * 1.2)))

    # SMA-50 filter (25%)
    sma_score = 50
    if n >= 50:
        sma50 = float(slice_.rolling(50).mean().iloc[-1])
        if price > sma50 * 1.02:
            sma_score = 80
        elif price > sma50:
            sma_score = 65
        elif price > sma50 * 0.97:
            sma_score = 35
        else:
            sma_score = 15

    return int(0.40 * proximity_score + 0.35 * rsi_score + 0.25 * sma_score)


# ---------------------------------------------------------------------------
# Strategy registry — used by backtest page and autoresearch harness
# ---------------------------------------------------------------------------

STRATEGY_REGISTRY: dict[str, object] = {
    "Price Technical v1 (baseline)": price_technical_v1,
    "Price Technical v2 (improved)": price_technical_v2,
    "MA Crossover": ma_crossover,
    "Momentum Breakout": momentum_breakout,
}

DEFAULT_STRATEGY = "Price Technical v2 (improved)"
