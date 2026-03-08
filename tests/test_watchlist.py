"""Tests for watchlist.py (P1.2)."""
import json
import pytest
from pathlib import Path


@pytest.fixture(autouse=True)
def clean_watchlist(tmp_path, monkeypatch):
    """Redirect watchlist file to a temp directory."""
    import watchlist as wl
    monkeypatch.setattr(wl, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(wl, "_WATCHLIST_FILE", tmp_path / "watchlist.json")
    yield


def test_empty_watchlist():
    from watchlist import get_watchlist
    assert get_watchlist() == []


def test_add_and_retrieve():
    from watchlist import add_to_watchlist, get_watchlist
    add_to_watchlist("AAPL", name="Apple Inc.", price=150.0, factor_score=72)
    wl = get_watchlist()
    assert len(wl) == 1
    assert wl[0]["symbol"] == "AAPL"
    assert wl[0]["name"] == "Apple Inc."
    assert wl[0]["price"] == 150.0
    assert wl[0]["factor_score"] == 72


def test_add_normalizes_symbol():
    from watchlist import add_to_watchlist, get_watchlist
    add_to_watchlist("aapl")
    wl = get_watchlist()
    assert wl[0]["symbol"] == "AAPL"


def test_is_in_watchlist():
    from watchlist import add_to_watchlist, is_in_watchlist
    add_to_watchlist("MSFT")
    assert is_in_watchlist("MSFT") is True
    assert is_in_watchlist("GOOG") is False


def test_remove_from_watchlist():
    from watchlist import add_to_watchlist, remove_from_watchlist, get_watchlist
    add_to_watchlist("TSLA")
    add_to_watchlist("NVDA")
    remove_from_watchlist("TSLA")
    wl = get_watchlist()
    symbols = [e["symbol"] for e in wl]
    assert "TSLA" not in symbols
    assert "NVDA" in symbols


def test_add_updates_existing():
    """Adding same symbol twice should update, not duplicate."""
    from watchlist import add_to_watchlist, get_watchlist
    add_to_watchlist("AAPL", price=100.0)
    add_to_watchlist("AAPL", price=200.0)
    wl = get_watchlist()
    assert len(wl) == 1
    assert wl[0]["price"] == 200.0


def test_update_entry():
    from watchlist import add_to_watchlist, update_watchlist_entry, get_watchlist
    add_to_watchlist("JPM", price=150.0)
    update_watchlist_entry("JPM", price=165.0, factor_score=68)
    wl = get_watchlist()
    assert wl[0]["price"] == 165.0
    assert wl[0]["factor_score"] == 68
