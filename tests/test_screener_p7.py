"""Tests for P7 screener improvements.

Covers:
- P7.3 Screen templates (save/load/delete), CSV export, sentiment warning
"""
from __future__ import annotations

import tempfile

from screener import (
    export_results_to_csv,
    SENTIMENT_SKIP_WARNING,
)

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

_SAMPLE_FILTERS = [
    {"dimension": "factor_score", "operator": ">", "value": 65},
    {"dimension": "risk_score", "operator": "<", "value": 40},
]

_SAMPLE_RESULTS = [
    {
        "symbol": "AAPL",
        "name": "Apple Inc.",
        "sector": "Technology",
        "price": 175.0,
        "factor_score": 78,
        "composite_label": "Strong Buy",
        "risk_score": 32,
        "risk_level": "Moderate",
        "flag_count": 0,
        "pe_ratio": 28.5,
        "market_cap_b": 2700.0,
        "rsi": 55.0,
    },
    {
        "symbol": "MSFT",
        "name": "Microsoft Corp.",
        "sector": "Technology",
        "price": 380.0,
        "factor_score": 72,
        "composite_label": "Buy",
        "risk_score": 28,
        "risk_level": "Moderate",
        "flag_count": 1,
        "pe_ratio": 35.0,
        "market_cap_b": 2800.0,
        "rsi": 58.0,
    },
]


# ---------------------------------------------------------------------------
# P7.3: Screen template save / load / delete
# ---------------------------------------------------------------------------

def _with_temp_template_dir(fn):
    """Run fn with _TEMPLATE_DIR pointing to a temp directory."""
    import screener as _screener_mod
    original = _screener_mod._TEMPLATE_DIR
    with tempfile.TemporaryDirectory() as tmp:
        from pathlib import Path
        _screener_mod._TEMPLATE_DIR = Path(tmp) / "templates"
        try:
            fn(_screener_mod)
        finally:
            _screener_mod._TEMPLATE_DIR = original


def test_save_and_load_template():
    def _run(mod):
        mod.save_template("test_screen", _SAMPLE_FILTERS)
        loaded = mod.load_template("test_screen")
        assert loaded == _SAMPLE_FILTERS

    _with_temp_template_dir(_run)


def test_load_template_raises_for_missing():
    import pytest

    def _run(mod):
        with pytest.raises(FileNotFoundError):
            mod.load_template("nonexistent_template")

    _with_temp_template_dir(_run)


def test_delete_template_returns_true_when_found():
    def _run(mod):
        mod.save_template("to_delete", _SAMPLE_FILTERS)
        result = mod.delete_template("to_delete")
        assert result is True

    _with_temp_template_dir(_run)


def test_delete_template_returns_false_when_not_found():
    def _run(mod):
        result = mod.delete_template("ghost_template")
        assert result is False

    _with_temp_template_dir(_run)


def test_deleted_template_no_longer_loadable():
    import pytest

    def _run(mod):
        mod.save_template("ephemeral", _SAMPLE_FILTERS)
        mod.delete_template("ephemeral")
        with pytest.raises(FileNotFoundError):
            mod.load_template("ephemeral")

    _with_temp_template_dir(_run)


def test_list_templates_returns_saved_names():
    def _run(mod):
        mod.save_template("alpha", _SAMPLE_FILTERS)
        mod.save_template("beta", _SAMPLE_FILTERS[:1])
        names = mod.list_templates()
        assert "alpha" in names
        assert "beta" in names

    _with_temp_template_dir(_run)


def test_list_templates_empty_when_none_saved():
    def _run(mod):
        names = mod.list_templates()
        assert names == []

    _with_temp_template_dir(_run)


def test_saved_template_preserves_filter_values():
    filters = [
        {"dimension": "rsi", "operator": "<", "value": 30},
        {"dimension": "market_cap_b", "operator": ">", "value": 10.0},
    ]

    def _run(mod):
        mod.save_template("rsi_screen", filters)
        loaded = mod.load_template("rsi_screen")
        assert loaded[0]["value"] == 30
        assert loaded[1]["dimension"] == "market_cap_b"

    _with_temp_template_dir(_run)


# ---------------------------------------------------------------------------
# P7.3: CSV export
# ---------------------------------------------------------------------------

def test_export_results_to_csv_returns_string():
    csv_str = export_results_to_csv(_SAMPLE_RESULTS)
    assert isinstance(csv_str, str)
    assert len(csv_str) > 0


def test_export_results_to_csv_contains_header():
    csv_str = export_results_to_csv(_SAMPLE_RESULTS)
    first_line = csv_str.splitlines()[0]
    assert "symbol" in first_line
    assert "factor_score" in first_line
    assert "risk_score" in first_line


def test_export_results_to_csv_contains_all_rows():
    csv_str = export_results_to_csv(_SAMPLE_RESULTS)
    lines = [ln for ln in csv_str.splitlines() if ln.strip()]
    assert len(lines) == len(_SAMPLE_RESULTS) + 1  # header + data rows


def test_export_results_to_csv_contains_ticker_symbols():
    csv_str = export_results_to_csv(_SAMPLE_RESULTS)
    assert "AAPL" in csv_str
    assert "MSFT" in csv_str


def test_export_empty_results():
    csv_str = export_results_to_csv([])
    lines = [ln for ln in csv_str.splitlines() if ln.strip()]
    assert len(lines) == 1  # header only


# ---------------------------------------------------------------------------
# P7.3: Sentiment-skip warning
# ---------------------------------------------------------------------------

def test_sentiment_skip_warning_is_string():
    assert isinstance(SENTIMENT_SKIP_WARNING, str)
    assert len(SENTIMENT_SKIP_WARNING) > 20


def test_sentiment_skip_warning_mentions_finbert():
    assert "FinBERT" in SENTIMENT_SKIP_WARNING or "sentiment" in SENTIMENT_SKIP_WARNING.lower()


def test_sentiment_skip_warning_mentions_speed():
    lower = SENTIMENT_SKIP_WARNING.lower()
    assert "speed" in lower or "fast" in lower or "bulk" in lower or "skip" in lower


# ---------------------------------------------------------------------------
# Integration: round-trip template with real file I/O
# ---------------------------------------------------------------------------

def test_template_round_trip_real_fs():
    import screener as _mod
    from pathlib import Path
    original = _mod._TEMPLATE_DIR
    with tempfile.TemporaryDirectory() as tmp:
        _mod._TEMPLATE_DIR = Path(tmp) / "tpl"
        try:
            _mod.save_template("integration_test", _SAMPLE_FILTERS)
            assert "integration_test" in _mod.list_templates()
            loaded = _mod.load_template("integration_test")
            assert len(loaded) == len(_SAMPLE_FILTERS)
            deleted = _mod.delete_template("integration_test")
            assert deleted is True
            assert "integration_test" not in _mod.list_templates()
        finally:
            _mod._TEMPLATE_DIR = original
