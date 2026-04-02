"""Tests for src/analysis/ledger.py — tamper-evident JSON signal ledger."""

from __future__ import annotations

import json

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def ledger_dir(tmp_path, monkeypatch):
    """Redirect ledger paths to a temp directory for isolation."""
    import src.analysis.ledger as L

    monkeypatch.setattr(L, "_LEDGER_PATH", tmp_path / "ledger.json")
    monkeypatch.setattr(L, "_TMP_PATH", tmp_path / "ledger.json.tmp")
    return tmp_path


# ---------------------------------------------------------------------------
# add_signal
# ---------------------------------------------------------------------------


def test_add_signal_creates_file(ledger_dir):
    from src.analysis.ledger import add_signal

    sig_id = add_signal(
        ticker="AAPL",
        composite_score=82.0,
        factor_scores={"Valuation (P/E)": 80.0, "Trend (SMA)": 85.0},
        price=175.0,
        spy_price=510.0,
    )
    assert sig_id
    ledger_file = ledger_dir / "ledger.json"
    assert ledger_file.exists()
    signals = json.loads(ledger_file.read_text())
    assert len(signals) == 1
    assert signals[0]["ticker"] == "AAPL"
    assert signals[0]["status"] == "open"
    assert signals[0]["composite_score"] == pytest.approx(82.0)
    assert signals[0]["price_at_signal"] == pytest.approx(175.0)
    assert signals[0]["price_t5"] is None


def test_add_signal_returns_uuid(ledger_dir):
    from src.analysis.ledger import add_signal
    import uuid

    sig_id = add_signal("MSFT", 70.0, {}, 400.0, 510.0)
    # Should be parseable as UUID
    parsed = uuid.UUID(sig_id)
    assert str(parsed) == sig_id


def test_add_signal_duplicate_raises(ledger_dir):
    from src.analysis.ledger import add_signal

    add_signal("NVDA", 80.0, {}, 500.0, 510.0)
    with pytest.raises(ValueError, match="already has an open position"):
        add_signal("NVDA", 82.0, {}, 510.0, 512.0)


def test_add_signal_different_tickers_ok(ledger_dir):
    from src.analysis.ledger import add_signal

    add_signal("AAPL", 75.0, {}, 175.0, 510.0)
    add_signal("MSFT", 78.0, {}, 400.0, 510.0)
    from src.analysis.ledger import get_open_positions

    assert len(get_open_positions()) == 2


# ---------------------------------------------------------------------------
# close_position
# ---------------------------------------------------------------------------


def test_close_position_updates_status(ledger_dir):
    from src.analysis.ledger import add_signal, close_position, get_closed_positions

    sig_id = add_signal("TSLA", 77.0, {"Trend (SMA)": 85.0}, 250.0, 510.0)
    close_position(
        signal_id=sig_id,
        exit_price=270.0,
        spy_exit_price=520.0,
        price_t5=255.0,
        price_t10=262.0,
        price_t30=270.0,
    )
    closed = get_closed_positions()
    assert len(closed) == 1
    pos = closed[0]
    assert pos["status"] == "closed"
    assert pos["exit_price"] == pytest.approx(270.0)
    # P&L = (270 - 250) / 250 * 100 = 8.0%
    assert pos["pnl_pct"] == pytest.approx(8.0, abs=0.01)
    assert pos["price_t5"] == pytest.approx(255.0)
    assert pos["price_t10"] == pytest.approx(262.0)
    assert pos["price_t30"] == pytest.approx(270.0)


def test_close_position_none_prices_ok(ledger_dir):
    """Closing with None T+5/T+10/T+30 is allowed (API failure tolerance)."""
    from src.analysis.ledger import add_signal, close_position, get_closed_positions

    sig_id = add_signal("AMZN", 76.0, {}, 180.0, 510.0)
    close_position(sig_id, 170.0, 505.0, None, None, None)
    pos = get_closed_positions()[0]
    assert pos["price_t5"] is None
    assert pos["pnl_pct"] == pytest.approx(-100 * 10 / 180, abs=0.01)


def test_close_already_closed_raises(ledger_dir):
    from src.analysis.ledger import add_signal, close_position

    sig_id = add_signal("GOOG", 80.0, {}, 160.0, 510.0)
    close_position(sig_id, 165.0, 512.0, None, None, None)
    with pytest.raises(ValueError, match="already closed"):
        close_position(sig_id, 165.0, 512.0, None, None, None)


def test_close_unknown_signal_raises(ledger_dir):
    from src.analysis.ledger import close_position

    with pytest.raises(ValueError, match="not found in ledger"):
        close_position("nonexistent-id", 100.0, 100.0, None, None, None)


# ---------------------------------------------------------------------------
# get_* accessors
# ---------------------------------------------------------------------------


def test_get_open_positions_empty(ledger_dir):
    from src.analysis.ledger import get_open_positions

    assert get_open_positions() == []


def test_get_closed_positions_empty(ledger_dir):
    from src.analysis.ledger import get_closed_positions

    assert get_closed_positions() == []


def test_get_all_signals_mixed(ledger_dir):
    from src.analysis.ledger import add_signal, close_position, get_all_signals

    s1 = add_signal("A", 75.0, {}, 100.0, 510.0)
    add_signal("B", 78.0, {}, 200.0, 510.0)
    close_position(s1, 105.0, 512.0, None, None, None)
    all_sigs = get_all_signals()
    assert len(all_sigs) == 2
    statuses = {s["status"] for s in all_sigs}
    assert statuses == {"open", "closed"}


def test_load_returns_empty_when_no_file(ledger_dir):
    from src.analysis.ledger import get_all_signals

    assert get_all_signals() == []
