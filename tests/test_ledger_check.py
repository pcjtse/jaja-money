"""Tests for src/analysis/ledger_check.py orchestrator."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_ledger(tmp_path, monkeypatch):
    """Redirect ledger paths and monkeypatch ledger_check dependencies."""
    import src.analysis.ledger as L
    import src.analysis.ledger_check as LC

    monkeypatch.setattr(L, "_LEDGER_PATH", tmp_path / "ledger.json")
    monkeypatch.setattr(L, "_TMP_PATH", tmp_path / "ledger.json.tmp")

    # Default: _get_spy_price returns a fixed value
    monkeypatch.setattr(LC, "_get_spy_price", lambda: 500.0)
    # Default: _get_market_regime returns "flat" to avoid API calls
    monkeypatch.setattr(LC, "_get_market_regime", lambda spy_price: "flat")

    return tmp_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_signal_fires_at_threshold(isolated_ledger, monkeypatch):
    """A score >= buy_threshold should add 1 open position for AAPL."""
    import src.analysis.ledger_check as LC
    from src.analysis.ledger import get_open_positions

    monkeypatch.setattr(
        LC, "_score_ticker", lambda t: (76, {"Trend (SMA)": 80.0}, 100.0)
    )

    result = LC.run_ledger_check(["AAPL"])

    open_pos = get_open_positions()
    assert len(open_pos) == 1
    assert open_pos[0]["ticker"] == "AAPL"
    assert "AAPL" in result["signals_fired"]


def test_no_signal_below_threshold(isolated_ledger, monkeypatch):
    """A score below buy_threshold should not create any signal."""
    import src.analysis.ledger_check as LC
    from src.analysis.ledger import get_all_signals

    monkeypatch.setattr(LC, "_score_ticker", lambda t: (74, {}, 100.0))

    LC.run_ledger_check(["AAPL"])

    assert get_all_signals() == []


def test_skips_existing_open_position(isolated_ledger, monkeypatch):
    """Ticker with an existing open position should not fire a duplicate signal."""
    import src.analysis.ledger_check as LC
    from src.analysis.ledger import add_signal, get_open_positions

    # Pre-add AAPL open position
    add_signal("AAPL", 80.0, {}, 100.0, 500.0)

    monkeypatch.setattr(LC, "_score_ticker", lambda t: (80, {}, 110.0))

    LC.run_ledger_check(["AAPL"])

    # Still only 1 open position
    open_pos = get_open_positions()
    assert len(open_pos) == 1


def test_closes_expired_position(isolated_ledger, monkeypatch):
    """Position older than hold_days should be closed."""
    import src.analysis.ledger as L
    import src.analysis.ledger_check as LC
    from src.analysis.ledger import add_signal, get_closed_positions

    # Add AAPL position then backdate fired_at to 31 days ago
    sig_id = add_signal("AAPL", 80.0, {}, 100.0, 500.0)
    signals = L._load()
    past_date = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
    for s in signals:
        if s["signal_id"] == sig_id:
            s["fired_at"] = past_date
    L._save(signals)

    monkeypatch.setattr(LC, "_score_ticker", lambda t: (50, {}, 105.0))
    monkeypatch.setattr(LC, "_get_spy_price", lambda: 520.0)
    monkeypatch.setattr(
        "src.data.providers.get_price_on_date", lambda ticker, date: 102.0
    )

    LC.run_ledger_check(["AAPL"])

    closed = get_closed_positions()
    assert len(closed) == 1
    assert closed[0]["ticker"] == "AAPL"
    assert closed[0]["status"] == "closed"


def test_api_failure_graceful(isolated_ledger, monkeypatch):
    """API failure for one ticker should not block processing of the next."""
    import src.analysis.ledger_check as LC

    call_count = {"n": 0}

    def _mock_score(ticker):
        call_count["n"] += 1
        if ticker == "AAPL":
            return None  # simulated failure
        return (80, {}, 100.0)

    monkeypatch.setattr(LC, "_score_ticker", _mock_score)

    result = LC.run_ledger_check(["AAPL", "MSFT"])

    assert "AAPL" in result["errors"]
    assert len(result["errors"]) == 1
    # MSFT should have been processed and fired a signal
    assert "MSFT" in result["signals_fired"]


def test_baseline_co_fired(isolated_ledger, monkeypatch):
    """After a real signal fires, a baseline signal should also be present."""
    import src.analysis.ledger_check as LC
    from src.analysis.ledger import get_all_signals

    monkeypatch.setattr(LC, "_score_ticker", lambda t: (80, {}, 100.0))
    monkeypatch.setattr(LC, "_get_spy_price", lambda: 500.0)

    LC.run_ledger_check(["AAPL"])

    all_sigs = get_all_signals()
    # Should have at least 2 entries: 1 real + 1 baseline
    assert len(all_sigs) >= 2

    baseline_sigs = [s for s in all_sigs if s.get("is_baseline") is True]
    assert len(baseline_sigs) >= 1
