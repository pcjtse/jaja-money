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
    # Mock _fetch_t_prices (replaces get_price_on_date; uses get_daily() internally)
    monkeypatch.setattr(
        LC, "_fetch_t_prices", lambda ticker, fired_date: (102.0, 102.0, 102.0, 522.0)
    )

    LC.run_ledger_check(["AAPL"])

    closed = get_closed_positions()
    assert len(closed) == 1
    assert closed[0]["ticker"] == "AAPL"
    assert closed[0]["status"] == "closed"


def test_signal_source_field_forward(isolated_ledger, monkeypatch):
    """Signals fired by cron should have source='forward'."""
    import src.analysis.ledger_check as LC
    from src.analysis.ledger import get_all_signals

    monkeypatch.setattr(LC, "_score_ticker", lambda t: (80, {}, 100.0))

    LC.run_ledger_check(["AAPL"])

    real_signals = [s for s in get_all_signals() if not s.get("is_baseline")]
    assert len(real_signals) == 1
    assert real_signals[0]["source"] == "forward"


def test_regime_threshold_one_percent(monkeypatch):
    """Regime uses ±1% thresholds (not ±2%)."""
    import src.analysis.ledger_check as LC
    import src.data.api as _api_mod
    import time as _t

    # SPY gained +1.5% over 20 days: bull at ±1%, would be flat at ±2%
    base = 100.0
    closes = [base] * 20 + [base * 1.015]
    now_ts = int(_t.time())
    timestamps = [now_ts - (20 - i) * 86400 for i in range(21)]
    mock_daily = {"s": "ok", "c": closes, "t": timestamps}

    class _MockAPI:
        def get_daily(self, sym, years=1):
            return mock_daily

    monkeypatch.setattr(_api_mod, "get_api", lambda: _MockAPI())

    assert LC._get_market_regime(spy_price=None) == "bull"

    # Also verify bear at -1.5%
    closes_bear = [base * 1.015] * 20 + [base]
    mock_daily_bear = {"s": "ok", "c": closes_bear, "t": timestamps}

    class _MockAPIBear:
        def get_daily(self, sym, years=1):
            return mock_daily_bear

    monkeypatch.setattr(_api_mod, "get_api", lambda: _MockAPIBear())
    assert LC._get_market_regime(spy_price=None) == "bear"


def test_baseline_one_per_day(isolated_ledger, monkeypatch):
    """Only one baseline signal should fire per day, even with multiple real signals."""
    import src.analysis.ledger_check as LC
    from src.analysis.ledger import get_all_signals

    monkeypatch.setattr(LC, "_score_ticker", lambda t: (80, {}, 100.0))

    # Two tickers qualify — should produce 2 real signals but only 1 baseline
    LC.run_ledger_check(["AAPL", "MSFT"])

    all_sigs = get_all_signals()
    baseline_sigs = [s for s in all_sigs if s.get("source") == "baseline"]
    assert len(baseline_sigs) <= 1


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
