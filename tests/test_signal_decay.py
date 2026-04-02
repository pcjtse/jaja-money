"""Tests for src/analysis/signal_decay.py — per-factor win rate analysis."""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# get_leading_factor
# ---------------------------------------------------------------------------


def test_leading_factor_highest_above_50():
    from src.analysis.signal_decay import get_leading_factor

    scores = {
        "Valuation (P/E)": 80.0,   # above 50 by 30
        "Trend (SMA)": 90.0,        # above 50 by 40 — winner
        "Momentum (RSI)": 60.0,     # above 50 by 10
    }
    assert get_leading_factor(scores) == "Trend (SMA)"


def test_leading_factor_all_below_50():
    from src.analysis.signal_decay import get_leading_factor

    scores = {"Valuation (P/E)": 40.0, "MACD Signal": 30.0}
    assert get_leading_factor(scores) == "none"


def test_leading_factor_exactly_50_is_not_leading():
    from src.analysis.signal_decay import get_leading_factor

    scores = {"Valuation (P/E)": 50.0, "Trend (SMA)": 51.0}
    assert get_leading_factor(scores) == "Trend (SMA)"


def test_leading_factor_empty():
    from src.analysis.signal_decay import get_leading_factor

    assert get_leading_factor({}) == "none"


# ---------------------------------------------------------------------------
# get_signal_decay_table — no closed positions
# ---------------------------------------------------------------------------


def test_decay_table_empty_when_no_closed(tmp_path, monkeypatch):
    import src.analysis.ledger as L

    monkeypatch.setattr(L, "_LEDGER_PATH", tmp_path / "ledger.json")
    monkeypatch.setattr(L, "_TMP_PATH", tmp_path / "ledger.json.tmp")

    from src.analysis.signal_decay import get_signal_decay_table

    df = get_signal_decay_table()
    assert not df.empty
    assert df["n"].sum() == 0
    assert not df["sufficient"].any()
    assert "win_t5" in df.columns


# ---------------------------------------------------------------------------
# get_signal_decay_table — with closed positions
# ---------------------------------------------------------------------------


def test_decay_table_win_rate(tmp_path, monkeypatch):
    """Two wins (exit > entry) for Trend (SMA) as leading factor."""
    import src.analysis.ledger as L

    monkeypatch.setattr(L, "_LEDGER_PATH", tmp_path / "ledger.json")
    monkeypatch.setattr(L, "_TMP_PATH", tmp_path / "ledger.json.tmp")

    from src.analysis.ledger import add_signal, close_position

    # Create 5 closed positions where Trend (SMA) is the leading factor
    for i in range(5):
        entry = 100.0 + i
        # Trend (SMA) at 90 is highest above 50
        sig = add_signal(
            ticker=f"T{i}",
            composite_score=78.0,
            factor_scores={"Trend (SMA)": 90.0, "Valuation (P/E)": 60.0},
            price=entry,
            spy_price=500.0,
        )
        # First 4 wins, 1 loss
        exit_price = entry + 10.0 if i < 4 else entry - 5.0
        close_position(sig, exit_price, 505.0, entry + 2, entry + 5, exit_price)

    from src.analysis.signal_decay import get_signal_decay_table

    df = get_signal_decay_table(min_n=5)
    trend_row = df[df["factor"] == "Trend (SMA)"].iloc[0]

    assert trend_row["n"] == 5
    assert bool(trend_row["sufficient"]) is True
    # 4 wins out of 5 = 0.8
    assert trend_row["win_t30"] == pytest.approx(0.8, abs=1e-9)


def test_decay_table_insufficient_below_min_n(tmp_path, monkeypatch):
    """Factor with n < min_n should have win_t5/t10/t30 = None."""
    import src.analysis.ledger as L

    monkeypatch.setattr(L, "_LEDGER_PATH", tmp_path / "ledger.json")
    monkeypatch.setattr(L, "_TMP_PATH", tmp_path / "ledger.json.tmp")

    from src.analysis.ledger import add_signal, close_position

    # Only 3 positions, min_n=5
    for i in range(3):
        sig = add_signal(
            ticker=f"X{i}",
            composite_score=76.0,
            factor_scores={"MACD Signal": 85.0},
            price=100.0,
            spy_price=500.0,
        )
        close_position(sig, 110.0, 505.0, 102.0, 105.0, 110.0)

    from src.analysis.signal_decay import get_signal_decay_table

    df = get_signal_decay_table(min_n=5)
    macd_row = df[df["factor"] == "MACD Signal"].iloc[0]

    assert macd_row["n"] == 3
    assert bool(macd_row["sufficient"]) is False
    assert macd_row["win_t30"] is None
