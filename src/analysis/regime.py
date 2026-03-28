"""Market Regime Detector — 5-State Classifier.

Classifies the current market environment into one of five states:
  1. Risk-On Growth    — bull market, strong breadth, falling VIX
  2. Risk-On Momentum  — momentum-driven, elevated VIX but rising prices
  3. Sideways          — range-bound, unclear direction
  4. Risk-Off Defensive — defensive rotation, rising VIX, yields falling
  5. Risk-Off Panic    — crash/crisis state, VIX spike, credit stress

Each state maps to a composite score multiplier and factor weight tilts.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from src.core.log_setup import get_logger

log = get_logger(__name__)

_DATA_DIR = Path.home() / ".jaja-money"
_DB_FILE = _DATA_DIR / "history.db"

REGIME_RISK_ON_GROWTH = "Risk-On Growth"
REGIME_RISK_ON_MOMENTUM = "Risk-On Momentum"
REGIME_SIDEWAYS = "Sideways"
REGIME_RISK_OFF_DEFENSIVE = "Risk-Off Defensive"
REGIME_RISK_OFF_PANIC = "Risk-Off Panic"

# Score multiplier for composite factor score by regime
REGIME_MULTIPLIERS = {
    REGIME_RISK_ON_GROWTH:    +8,
    REGIME_RISK_ON_MOMENTUM:  +4,
    REGIME_SIDEWAYS:           0,
    REGIME_RISK_OFF_DEFENSIVE: -5,
    REGIME_RISK_OFF_PANIC:    -12,
}


def _connect() -> sqlite3.Connection:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_FILE))
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_regime_table() -> None:
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS regime_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                date        TEXT NOT NULL UNIQUE,
                regime      TEXT NOT NULL,
                confidence  REAL,
                vix         REAL,
                spy_vs_200d REAL,
                hyg_ief     REAL,
                fetched_at  INTEGER
            )
        """)


_ensure_regime_table()


def detect_market_regime(macro_context: dict | None = None) -> dict:
    """Detect the current market regime using cross-asset signals.

    Parameters
    ----------
    macro_context : output of FinnhubAPI.get_macro_context() or equivalent.
                   Expected keys: vix, yield_curve_spread, spy_vs_200sma.
                   Additional optional keys: hyg_ief_ratio, dxy.

    Returns
    -------
    dict with keys:
        regime (str): one of the REGIME_* constants
        confidence (float): 0.0-1.0
        multiplier (int): score adjustment to apply to composite
        signals (dict): individual indicator values
        detail (str)
    """
    signals = _fetch_regime_signals(macro_context)
    regime, confidence = _classify_regime(signals)

    multiplier = REGIME_MULTIPLIERS.get(regime, 0)

    _save_regime(regime, confidence, signals)

    detail = (
        f"Regime: {regime} | Confidence: {confidence:.0%} | "
        f"VIX: {signals.get('vix', 'N/A')} | "
        f"SPY vs 200d: {signals.get('spy_above_200d')}"
    )

    return {
        "regime": regime,
        "confidence": round(confidence, 3),
        "multiplier": multiplier,
        "signals": signals,
        "detail": detail,
    }


def _fetch_regime_signals(macro_context: dict | None) -> dict:
    """Extract and augment regime signals from macro context."""
    ctx = macro_context or {}
    signals: dict = {}

    signals["vix"] = _safe_float(ctx.get("vix"))
    signals["yield_spread"] = _safe_float(ctx.get("yield_curve_spread"))
    signals["spy_above_200d"] = ctx.get("spy_above_200sma", ctx.get("spy_vs_200sma"))

    # Try to fetch additional cross-asset signals
    try:
        import yfinance as yf

        hyg = yf.download("HYG", period="5d", progress=False, auto_adjust=True)
        ief = yf.download("IEF", period="5d", progress=False, auto_adjust=True)
        if not hyg.empty and not ief.empty:
            hyg_price = float(hyg["Close"].iloc[-1])
            ief_price = float(ief["Close"].iloc[-1])
            if ief_price > 0:
                signals["hyg_ief_ratio"] = round(hyg_price / ief_price, 4)

        spy = yf.download("SPY", period="252d", progress=False, auto_adjust=True)
        if not spy.empty and len(spy) >= 200:
            spy_close = spy["Close"].iloc[-1]
            spy_200 = spy["Close"].rolling(200).mean().iloc[-1]
            if spy_200 > 0:
                signals["spy_vs_200_pct"] = round((float(spy_close) - float(spy_200)) / float(spy_200) * 100, 2)
                signals["spy_above_200d"] = float(spy_close) > float(spy_200)
    except Exception as exc:
        log.debug("Regime cross-asset fetch failed: %s", exc)

    return signals


def _classify_regime(signals: dict) -> tuple[str, float]:
    """Classify regime from signals using a rule-based approach."""
    vix = signals.get("vix")
    spy_above_200 = signals.get("spy_above_200d")
    hyg_ief = signals.get("hyg_ief_ratio")
    spy_vs_200_pct = signals.get("spy_vs_200_pct")
    yield_spread = signals.get("yield_spread")

    score_by_regime: dict[str, float] = {
        REGIME_RISK_ON_GROWTH: 0.0,
        REGIME_RISK_ON_MOMENTUM: 0.0,
        REGIME_SIDEWAYS: 0.0,
        REGIME_RISK_OFF_DEFENSIVE: 0.0,
        REGIME_RISK_OFF_PANIC: 0.0,
    }

    # VIX signals
    if vix is not None:
        if vix < 15:
            score_by_regime[REGIME_RISK_ON_GROWTH] += 2
        elif vix < 20:
            score_by_regime[REGIME_RISK_ON_GROWTH] += 1
            score_by_regime[REGIME_RISK_ON_MOMENTUM] += 1
        elif vix < 25:
            score_by_regime[REGIME_SIDEWAYS] += 1
            score_by_regime[REGIME_RISK_ON_MOMENTUM] += 1
        elif vix < 35:
            score_by_regime[REGIME_RISK_OFF_DEFENSIVE] += 2
        else:
            score_by_regime[REGIME_RISK_OFF_PANIC] += 3

    # SPY vs 200 SMA
    if spy_above_200 is True:
        score_by_regime[REGIME_RISK_ON_GROWTH] += 1.5
        score_by_regime[REGIME_RISK_ON_MOMENTUM] += 1
    elif spy_above_200 is False:
        score_by_regime[REGIME_RISK_OFF_DEFENSIVE] += 1.5
        score_by_regime[REGIME_RISK_OFF_PANIC] += 0.5

    if spy_vs_200_pct is not None:
        if spy_vs_200_pct > 10:
            score_by_regime[REGIME_RISK_ON_GROWTH] += 1
        elif spy_vs_200_pct > 3:
            score_by_regime[REGIME_RISK_ON_MOMENTUM] += 0.5
        elif spy_vs_200_pct < -10:
            score_by_regime[REGIME_RISK_OFF_PANIC] += 1

    # HYG/IEF ratio (credit health)
    if hyg_ief is not None:
        if hyg_ief > 0.85:
            score_by_regime[REGIME_RISK_ON_GROWTH] += 1
        elif hyg_ief > 0.75:
            score_by_regime[REGIME_RISK_ON_MOMENTUM] += 0.5
        elif hyg_ief < 0.65:
            score_by_regime[REGIME_RISK_OFF_PANIC] += 1.5
        else:
            score_by_regime[REGIME_RISK_OFF_DEFENSIVE] += 0.5

    # Yield spread (inverted = recession risk)
    if yield_spread is not None:
        if yield_spread < 0:
            score_by_regime[REGIME_RISK_OFF_DEFENSIVE] += 1.5
        elif yield_spread < 0.5:
            score_by_regime[REGIME_SIDEWAYS] += 0.5

    # Default to sideways if no data
    total = sum(score_by_regime.values())
    if total == 0:
        return REGIME_SIDEWAYS, 0.4

    best_regime = max(score_by_regime, key=score_by_regime.__getitem__)  # type: ignore[arg-type]
    best_score = score_by_regime[best_regime]
    confidence = min(0.95, best_score / total)

    return best_regime, round(confidence, 3)


def _save_regime(regime: str, confidence: float, signals: dict) -> None:
    from datetime import datetime

    today = datetime.utcnow().strftime("%Y-%m-%d")
    try:
        with _connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO regime_history
                   (date, regime, confidence, vix, spy_vs_200d, hyg_ief, fetched_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    today,
                    regime,
                    confidence,
                    signals.get("vix"),
                    signals.get("spy_vs_200_pct"),
                    signals.get("hyg_ief_ratio"),
                    int(time.time()),
                ),
            )
    except Exception as exc:
        log.debug("Failed to save regime history: %s", exc)


def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def apply_regime_multiplier(composite_score: int, regime_result: dict) -> int:
    """Apply regime multiplier to composite score, clamped to 0-100."""
    multiplier = regime_result.get("multiplier", 0)
    return max(0, min(100, composite_score + multiplier))
