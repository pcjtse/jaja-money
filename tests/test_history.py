"""Tests for history.py (P2.2)."""

import pytest


@pytest.fixture(autouse=True)
def clean_history(tmp_path, monkeypatch):
    """Redirect history DB to a temp directory."""
    import src.data.history as h

    monkeypatch.setattr(h, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(h, "_DB_FILE", tmp_path / "history.db")
    h._ensure_table()
    yield


def test_save_and_retrieve():
    from src.data.history import save_analysis, get_history

    save_analysis(
        symbol="AAPL",
        price=150.0,
        factor_score=70,
        risk_score=30,
        composite_label="Strong Buy",
        risk_level="Low",
    )
    rows = get_history("AAPL")
    assert len(rows) == 1
    assert rows[0]["symbol"] == "AAPL"
    assert rows[0]["factor_score"] == 70
    assert rows[0]["risk_score"] == 30


def test_symbol_normalization():
    from src.data.history import save_analysis, get_history

    save_analysis("aapl", price=100.0, factor_score=60, risk_score=40)
    assert len(get_history("AAPL")) == 1


def test_upsert_same_day():
    """Two saves on the same day should result in only one record."""
    from src.data.history import save_analysis, get_history

    save_analysis("MSFT", price=300.0, factor_score=65, risk_score=35)
    save_analysis("MSFT", price=305.0, factor_score=68, risk_score=32)
    rows = get_history("MSFT")
    assert len(rows) == 1
    assert rows[0]["factor_score"] == 68  # latest value


def test_score_trend_structure():
    from src.data.history import save_analysis, get_score_trend

    save_analysis("TSLA", price=200.0, factor_score=55, risk_score=60)
    trend = get_score_trend("TSLA")
    assert "dates" in trend
    assert "factor_scores" in trend
    assert "risk_scores" in trend
    assert "prices" in trend
    assert len(trend["dates"]) == 1
    assert trend["factor_scores"][0] == 55


def test_get_tracked_symbols():
    from src.data.history import save_analysis, get_tracked_symbols

    save_analysis("AAPL", price=150.0, factor_score=70, risk_score=30)
    save_analysis("NVDA", price=500.0, factor_score=80, risk_score=40)
    symbols = get_tracked_symbols()
    assert "AAPL" in symbols
    assert "NVDA" in symbols


def test_empty_history():
    from src.data.history import get_history

    assert get_history("UNKNOWN") == []
