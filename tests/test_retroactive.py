"""Tests for src/analysis/retroactive.py — retroactive ledger seeding."""

from __future__ import annotations

import time

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def patched_ledger(tmp_path, monkeypatch):
    """Redirect ledger paths to tmp_path for isolation."""
    import src.analysis.ledger as L

    monkeypatch.setattr(L, "_LEDGER_PATH", tmp_path / "ledger.json")
    monkeypatch.setattr(L, "_TMP_PATH", tmp_path / "ledger.json.tmp")
    return tmp_path


@pytest.fixture
def patched_history(tmp_path, monkeypatch):
    """Redirect history DB to tmp_path for isolation."""
    import src.data.history as h

    monkeypatch.setattr(h, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(h, "_DB_FILE", tmp_path / "history.db")
    h._ensure_table()
    return h


def _insert_history_row(h, symbol, date_str, price, factor_score, factors_json="[]"):
    with h._connect() as conn:
        conn.execute(
            """INSERT INTO analysis_history
               (symbol, date, timestamp, price, factor_score, risk_score,
                composite_label, risk_level, factors_json, flags_json)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                symbol,
                date_str,
                int(time.time()),
                price,
                factor_score,
                20,
                "Buy",
                "Low",
                factors_json,
                "[]",
            ),
        )


# ---------------------------------------------------------------------------
# test_empty_history_noop
# ---------------------------------------------------------------------------


def test_empty_history_noop(patched_ledger, patched_history, monkeypatch):
    """Empty analysis_history → no entries written, no crash."""
    import src.analysis.retroactive as R
    import src.data.providers as P

    monkeypatch.setattr(P, "get_price_on_date", lambda *a, **k: None)

    result = R.seed_from_history(buy_threshold=75)
    assert result["seeded"] == 0
    assert result["skipped"] == 0

    from src.analysis.ledger import get_all_signals

    assert get_all_signals() == []


# ---------------------------------------------------------------------------
# test_low_score_skipped
# ---------------------------------------------------------------------------


def test_low_score_skipped(patched_ledger, patched_history, monkeypatch):
    """Rows with factor_score < buy_threshold are not seeded."""
    import src.analysis.retroactive as R
    import src.data.providers as P

    monkeypatch.setattr(P, "get_price_on_date", lambda *a, **k: None)
    _insert_history_row(patched_history, "AAPL", "2025-01-10", 180.0, 70)

    result = R.seed_from_history(buy_threshold=75)
    assert result["seeded"] == 0

    from src.analysis.ledger import get_all_signals

    assert get_all_signals() == []


# ---------------------------------------------------------------------------
# test_high_score_written
# ---------------------------------------------------------------------------


def test_high_score_written(patched_ledger, patched_history, monkeypatch):
    """Row with factor_score >= threshold → entry written with source='retroactive'."""
    import src.analysis.retroactive as R
    import src.data.providers as P

    # Patch get_price_on_date to return None (past dates, won't close)
    monkeypatch.setattr(P, "get_price_on_date", lambda *a, **k: None)

    # Use a future date so T+30 hasn't passed and position stays open
    from datetime import date, timedelta

    future_date = (date.today() + timedelta(days=5)).isoformat()
    _insert_history_row(patched_history, "MSFT", future_date, 400.0, 80)

    result = R.seed_from_history(buy_threshold=75)
    assert result["seeded"] == 1

    from src.analysis.ledger import get_all_signals

    signals = get_all_signals()
    assert len(signals) == 1
    assert signals[0]["ticker"] == "MSFT"
    assert signals[0].get("source") == "retroactive"


# ---------------------------------------------------------------------------
# test_duplicate_guard_retroactive
# ---------------------------------------------------------------------------


def test_duplicate_guard_retroactive(patched_ledger, patched_history, monkeypatch):
    """Running seed_from_history twice skips already-seeded entries."""
    import src.analysis.retroactive as R
    import src.data.providers as P

    monkeypatch.setattr(P, "get_price_on_date", lambda *a, **k: None)

    from datetime import date, timedelta

    future_date = (date.today() + timedelta(days=5)).isoformat()
    _insert_history_row(patched_history, "NVDA", future_date, 500.0, 82)

    result1 = R.seed_from_history(buy_threshold=75)
    assert result1["seeded"] == 1

    result2 = R.seed_from_history(buy_threshold=75)
    assert result2["seeded"] == 0
    assert result2["skipped"] == 1

    from src.analysis.ledger import get_all_signals

    assert len(get_all_signals()) == 1


# ---------------------------------------------------------------------------
# test_past_signal_auto_closed
# ---------------------------------------------------------------------------


def test_past_signal_auto_closed(patched_ledger, patched_history, monkeypatch):
    """Signal > 30 days old is automatically closed at seed time."""
    import src.analysis.retroactive as R
    import src.data.providers as P

    # Return 105.0 for all price lookups
    monkeypatch.setattr(P, "get_price_on_date", lambda *a, **k: 105.0)

    _insert_history_row(patched_history, "TSLA", "2024-01-15", 200.0, 78)

    result = R.seed_from_history(buy_threshold=75)
    assert result["seeded"] == 1

    from src.analysis.ledger import get_closed_positions

    closed = get_closed_positions()
    assert len(closed) == 1
    assert closed[0]["ticker"] == "TSLA"
    assert closed[0]["status"] == "closed"


# ---------------------------------------------------------------------------
# test_dry_run_no_write
# ---------------------------------------------------------------------------


def test_dry_run_no_write(patched_ledger, patched_history, monkeypatch):
    """dry_run=True computes counts but writes nothing."""
    import src.analysis.retroactive as R
    import src.data.providers as P

    monkeypatch.setattr(P, "get_price_on_date", lambda *a, **k: None)

    from datetime import date, timedelta

    future_date = (date.today() + timedelta(days=5)).isoformat()
    _insert_history_row(patched_history, "AMZN", future_date, 180.0, 85)

    result = R.seed_from_history(buy_threshold=75, dry_run=True)
    assert result["dry_run"] is True
    assert result["seeded"] == 1

    from src.analysis.ledger import get_all_signals

    assert get_all_signals() == []


# ---------------------------------------------------------------------------
# test_atomic_write (ledger)
# ---------------------------------------------------------------------------


def test_atomic_write_no_tmp_persists(patched_ledger):
    """After add_signal(), the .tmp file must not remain on disk."""
    from src.analysis.ledger import add_signal
    import src.analysis.ledger as L

    add_signal("GOOG", 76.0, {}, 150.0, 510.0)

    tmp = L._TMP_PATH
    assert not tmp.exists(), ".tmp file should be renamed away after write"


# ---------------------------------------------------------------------------
# test_source_field_distinguishes_retroactive
# ---------------------------------------------------------------------------


def test_source_field_distinguishes_retroactive(patched_ledger, patched_history, monkeypatch):
    """source='retroactive' is set; live signals have no source field."""
    import src.analysis.retroactive as R
    import src.data.providers as P

    monkeypatch.setattr(P, "get_price_on_date", lambda *a, **k: None)

    from datetime import date, timedelta

    future_date = (date.today() + timedelta(days=5)).isoformat()
    _insert_history_row(patched_history, "META", future_date, 300.0, 80)

    # Add a live signal first
    from src.analysis.ledger import add_signal, get_all_signals

    add_signal("AAPL", 77.0, {}, 175.0, 510.0)

    R.seed_from_history(buy_threshold=75)

    signals = get_all_signals()
    assert len(signals) == 2

    sources = {s["ticker"]: s.get("source") for s in signals}
    assert sources["META"] == "retroactive"
    assert sources["AAPL"] == "forward"  # live signals have source="forward"
