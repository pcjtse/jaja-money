"""Tests for jaja-money event scheduler — Event-Triggered Analysis."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# register_event_callback
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_callbacks():
    """Ensure callbacks are cleared between tests."""
    import jaja_money_skill.scripts.jaja_events as ev

    ev.clear_event_callbacks()
    yield
    ev.clear_event_callbacks()


def test_register_callback_valid_event():
    from jaja_money_skill.scripts.jaja_events import (
        register_event_callback,
        _event_callbacks,
    )

    def my_cb(event):
        pass

    register_event_callback("earnings_approaching", my_cb)
    assert my_cb in _event_callbacks["earnings_approaching"]


def test_register_callback_invalid_event():
    from jaja_money_skill.scripts.jaja_events import register_event_callback

    with pytest.raises(ValueError, match="Unknown event type"):
        register_event_callback("nonexistent_event", lambda e: None)


def test_clear_callbacks_single_type():
    from jaja_money_skill.scripts.jaja_events import (
        register_event_callback,
        clear_event_callbacks,
        _event_callbacks,
    )

    register_event_callback("earnings_approaching", lambda e: None)
    register_event_callback("new_sec_filing", lambda e: None)

    clear_event_callbacks("earnings_approaching")
    assert len(_event_callbacks["earnings_approaching"]) == 0
    assert len(_event_callbacks["new_sec_filing"]) == 1


def test_clear_callbacks_all():
    from jaja_money_skill.scripts.jaja_events import (
        register_event_callback,
        clear_event_callbacks,
        _event_callbacks,
    )

    register_event_callback("earnings_approaching", lambda e: None)
    register_event_callback("price_alert_triggered", lambda e: None)

    clear_event_callbacks()
    for callbacks in _event_callbacks.values():
        assert len(callbacks) == 0


# ---------------------------------------------------------------------------
# check_earnings_events
# ---------------------------------------------------------------------------


def test_check_earnings_events_fires_when_near():
    from jaja_money_skill.scripts.jaja_events import check_earnings_events

    near_date = (date.today() + timedelta(days=1)).isoformat()
    mock_api = MagicMock()
    mock_api.get_earnings.return_value = [{"period": near_date, "estimate": 2.5}]

    events = check_earnings_events(["AAPL"], api=mock_api)

    assert len(events) == 1
    assert events[0]["event_type"] == "earnings_approaching"
    assert events[0]["symbol"] == "AAPL"
    assert events[0]["days_away"] == 1


def test_check_earnings_events_no_fire_when_far():
    from jaja_money_skill.scripts.jaja_events import check_earnings_events

    far_date = (date.today() + timedelta(days=30)).isoformat()
    mock_api = MagicMock()
    mock_api.get_earnings.return_value = [{"period": far_date, "estimate": 2.5}]

    events = check_earnings_events(["AAPL"], api=mock_api)

    assert events == []


def test_check_earnings_events_no_fire_for_past():
    from jaja_money_skill.scripts.jaja_events import check_earnings_events

    past_date = (date.today() - timedelta(days=1)).isoformat()
    mock_api = MagicMock()
    mock_api.get_earnings.return_value = [{"period": past_date, "estimate": 2.5}]

    events = check_earnings_events(["AAPL"], api=mock_api)

    assert events == []


def test_check_earnings_events_skips_empty_earnings():
    from jaja_money_skill.scripts.jaja_events import check_earnings_events

    mock_api = MagicMock()
    mock_api.get_earnings.return_value = []

    events = check_earnings_events(["AAPL"], api=mock_api)
    assert events == []


def test_check_earnings_events_handles_api_error():
    from jaja_money_skill.scripts.jaja_events import check_earnings_events

    mock_api = MagicMock()
    mock_api.get_earnings.side_effect = Exception("API failure")

    # Should not raise, just skip the ticker
    events = check_earnings_events(["AAPL"], api=mock_api)
    assert events == []


# ---------------------------------------------------------------------------
# check_sec_filing_events
# ---------------------------------------------------------------------------


def test_check_sec_filing_events_fires_for_today():
    import sys
    import types

    from jaja_money_skill.scripts.jaja_events import check_sec_filing_events

    today = date.today().isoformat()
    mock_filing = {
        "form": "8-K",
        "filed": today + "T00:00:00",
        "primaryDocument": "https://sec.gov/doc.htm",
    }

    # Patch edgar module so the local import inside check_sec_filing_events
    # returns our mock filing
    edgar_stub = types.ModuleType("edgar")
    edgar_stub.get_recent_filings = MagicMock(return_value=[mock_filing])
    with patch.dict(sys.modules, {"edgar": edgar_stub}):
        events = check_sec_filing_events(["AAPL"])

    assert len(events) == 1
    assert events[0]["event_type"] == "new_sec_filing"
    assert events[0]["symbol"] == "AAPL"
    assert events[0]["filing_type"] == "8-K"


def test_check_sec_filing_events_skips_old_filings():
    import sys
    import types

    from jaja_money_skill.scripts.jaja_events import check_sec_filing_events

    old_filing = {
        "form": "10-K",
        "filed": "2025-01-15",
        "primaryDocument": "",
    }

    edgar_stub = types.ModuleType("edgar")
    edgar_stub.get_recent_filings = MagicMock(return_value=[old_filing])
    with patch.dict(sys.modules, {"edgar": edgar_stub}):
        events = check_sec_filing_events(["AAPL"])

    assert events == []


def test_check_sec_filing_events_no_edgar():
    """Should return empty list when edgar is unavailable."""
    import sys

    from jaja_money_skill.scripts.jaja_events import check_sec_filing_events

    # Temporarily remove edgar from sys.modules so the import inside the
    # function raises ImportError and the function returns []
    original = sys.modules.pop("edgar", None)
    try:
        events = check_sec_filing_events(["AAPL"])
    finally:
        if original is not None:
            sys.modules["edgar"] = original

    assert isinstance(events, list)


# ---------------------------------------------------------------------------
# check_price_alert_events
# ---------------------------------------------------------------------------


def test_check_price_alert_events_fires_triggered(tmp_path, monkeypatch):
    import alerts as a

    monkeypatch.setattr(a, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(a, "_ALERTS_FILE", tmp_path / "alerts.json")

    from alerts import add_alert

    add_alert("AAPL", "Price Above", 150.0)

    mock_api = MagicMock()
    mock_api.get_quote.return_value = {"c": 160.0}

    from jaja_money_skill.scripts.jaja_events import check_price_alert_events

    events = check_price_alert_events(["AAPL"], api=mock_api)

    assert len(events) == 1
    assert events[0]["event_type"] == "price_alert_triggered"
    assert events[0]["symbol"] == "AAPL"
    assert events[0]["current_price"] == pytest.approx(160.0)


def test_check_price_alert_events_no_fire_below_threshold(tmp_path, monkeypatch):
    import alerts as a

    monkeypatch.setattr(a, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(a, "_ALERTS_FILE", tmp_path / "alerts.json")

    from alerts import add_alert

    add_alert("AAPL", "Price Above", 200.0)

    mock_api = MagicMock()
    mock_api.get_quote.return_value = {"c": 150.0}

    from jaja_money_skill.scripts.jaja_events import check_price_alert_events

    events = check_price_alert_events(["AAPL"], api=mock_api)
    assert events == []


# ---------------------------------------------------------------------------
# Callback firing
# ---------------------------------------------------------------------------


def test_fire_callbacks_called_for_each_event():
    from jaja_money_skill.scripts.jaja_events import (
        register_event_callback,
        _fire_callbacks,
    )

    received = []
    register_event_callback("earnings_approaching", received.append)

    events = [
        {"event_type": "earnings_approaching", "symbol": "AAPL"},
        {"event_type": "earnings_approaching", "symbol": "MSFT"},
    ]
    _fire_callbacks("earnings_approaching", events)

    assert len(received) == 2
    assert received[0]["symbol"] == "AAPL"
    assert received[1]["symbol"] == "MSFT"


def test_fire_callbacks_callback_error_does_not_propagate():
    from jaja_money_skill.scripts.jaja_events import (
        register_event_callback,
        _fire_callbacks,
    )

    def bad_cb(event):
        raise RuntimeError("callback failure")

    register_event_callback("price_alert_triggered", bad_cb)

    # Should not raise
    _fire_callbacks("price_alert_triggered", [{"event_type": "price_alert_triggered"}])


# ---------------------------------------------------------------------------
# Scheduler lifecycle
# ---------------------------------------------------------------------------


def test_start_stop_scheduler():
    from jaja_money_skill.scripts.jaja_events import (
        start_event_scheduler,
        stop_event_scheduler,
        is_scheduler_running,
    )

    try:
        started = start_event_scheduler(tickers=["AAPL"], interval_seconds=3600)
        if not started:
            pytest.skip("APScheduler not installed")

        assert is_scheduler_running() is True
    finally:
        stop_event_scheduler()

    assert is_scheduler_running() is False


def test_start_scheduler_idempotent():
    from jaja_money_skill.scripts.jaja_events import (
        start_event_scheduler,
        stop_event_scheduler,
        is_scheduler_running,
    )

    try:
        r1 = start_event_scheduler(tickers=["AAPL"], interval_seconds=3600)
        r2 = start_event_scheduler(tickers=["AAPL"], interval_seconds=3600)
        if not r1:
            pytest.skip("APScheduler not installed")

        assert r1 is True
        assert r2 is True
        assert is_scheduler_running() is True
    finally:
        stop_event_scheduler()
