"""Tests for P7 screener enhancements.

Covers:
- P7.1 Universe loaders (load_sp500, load_russell1000, load_universe)
- P7.2 OR-logic filter groups (apply_filters, _evaluate_group, _evaluate_filter)
- P7.3 Screen templates (save/load/delete), CSV export, sentiment warning
"""
from screener import (
    apply_filters,
    load_sp500,
    load_russell1000,
    load_universe,
    save_screen_template,
    load_screen_templates,
    delete_screen_template,
    results_to_csv,
    sentiment_skipped_warning,
)


# ---------------------------------------------------------------------------
# P7.1: Universe loaders
# ---------------------------------------------------------------------------

def test_load_sp500_returns_list():
    tickers = load_sp500()
    assert isinstance(tickers, list)
    assert len(tickers) > 0


def test_load_sp500_no_comments():
    tickers = load_sp500()
    for t in tickers:
        assert not t.startswith("#")


def test_load_sp500_uppercase():
    tickers = load_sp500()
    for t in tickers:
        assert t == t.upper()


def test_load_russell1000_returns_list():
    tickers = load_russell1000()
    assert isinstance(tickers, list)
    assert len(tickers) > 0


def test_load_russell1000_larger_than_sp500():
    sp = load_sp500()
    r1k = load_russell1000()
    assert len(r1k) >= len(sp)


def test_load_universe_default():
    tickers = load_universe("default")
    assert isinstance(tickers, list)


def test_load_universe_sp500():
    tickers = load_universe("sp500")
    assert len(tickers) > 0


def test_load_universe_russell1000():
    tickers = load_universe("russell1000")
    assert len(tickers) > 0


def test_load_sp500_contains_known_ticker():
    tickers = load_sp500()
    # AAPL should be in any reasonable S&P 500 list
    assert "AAPL" in tickers


# ---------------------------------------------------------------------------
# P7.2: Filter evaluation — plain filters (AND)
# ---------------------------------------------------------------------------

RESULT_HIGH = {
    "factor_score": 80, "risk_score": 25, "pe_ratio": 20.0,
    "rsi": 55.0, "trend": "uptrend", "market_cap_b": 500.0,
}
RESULT_LOW = {
    "factor_score": 30, "risk_score": 75, "pe_ratio": 80.0,
    "rsi": 28.0, "trend": "downtrend", "market_cap_b": 1.0,
}


def test_apply_filters_empty_passes_all():
    assert apply_filters(RESULT_HIGH, []) is True
    assert apply_filters(RESULT_LOW, []) is True


def test_apply_filters_single_passing():
    f = [{"dimension": "factor_score", "operator": ">=", "value": 70}]
    assert apply_filters(RESULT_HIGH, f) is True


def test_apply_filters_single_failing():
    f = [{"dimension": "factor_score", "operator": ">=", "value": 70}]
    assert apply_filters(RESULT_LOW, f) is False


def test_apply_filters_multiple_and_all_pass():
    filters = [
        {"dimension": "factor_score", "operator": ">=", "value": 60},
        {"dimension": "risk_score", "operator": "<=", "value": 40},
    ]
    assert apply_filters(RESULT_HIGH, filters) is True


def test_apply_filters_multiple_and_one_fails():
    filters = [
        {"dimension": "factor_score", "operator": ">=", "value": 60},
        {"dimension": "risk_score", "operator": "<=", "value": 20},  # risk=25 > 20 → fail
    ]
    assert apply_filters(RESULT_HIGH, filters) is False


def test_apply_filters_operator_gt():
    f = [{"dimension": "pe_ratio", "operator": ">", "value": 15.0}]
    assert apply_filters(RESULT_HIGH, f) is True  # pe=20 > 15


def test_apply_filters_operator_lt():
    f = [{"dimension": "pe_ratio", "operator": "<", "value": 30.0}]
    assert apply_filters(RESULT_HIGH, f) is True  # pe=20 < 30


def test_apply_filters_operator_eq():
    f = [{"dimension": "trend", "operator": "==", "value": "uptrend"}]
    assert apply_filters(RESULT_HIGH, f) is True


def test_apply_filters_operator_in():
    f = [{"dimension": "trend", "operator": "in", "value": ["uptrend", "sideways"]}]
    assert apply_filters(RESULT_HIGH, f) is True
    assert apply_filters(RESULT_LOW, f) is False  # downtrend not in list


def test_apply_filters_missing_dimension_passes():
    # dimension not in result → op returns False → filter fails
    f = [{"dimension": "nonexistent_dim", "operator": ">=", "value": 10}]
    assert apply_filters(RESULT_HIGH, f) is False


def test_apply_filters_none_value_fails():
    result = {"factor_score": None}
    f = [{"dimension": "factor_score", "operator": ">=", "value": 50}]
    assert apply_filters(result, f) is False


# ---------------------------------------------------------------------------
# P7.2: OR-logic filter groups
# ---------------------------------------------------------------------------

def test_apply_filters_or_group_one_passes():
    """OR group where only one sub-filter passes → overall passes."""
    or_group = {
        "connector": "OR",
        "filters": [
            {"dimension": "factor_score", "operator": ">=", "value": 75},   # RESULT_HIGH passes
            {"dimension": "risk_score", "operator": "<=", "value": 10},     # fails (risk=25)
        ],
    }
    assert apply_filters(RESULT_HIGH, [or_group]) is True


def test_apply_filters_or_group_none_passes():
    """OR group where no sub-filter passes → overall fails."""
    or_group = {
        "connector": "OR",
        "filters": [
            {"dimension": "factor_score", "operator": ">=", "value": 90},   # fails (80 < 90)
            {"dimension": "risk_score", "operator": "<=", "value": 10},     # fails (25 > 10)
        ],
    }
    assert apply_filters(RESULT_HIGH, [or_group]) is False


def test_apply_filters_or_group_all_pass():
    or_group = {
        "connector": "OR",
        "filters": [
            {"dimension": "factor_score", "operator": ">=", "value": 70},
            {"dimension": "risk_score", "operator": "<=", "value": 30},
        ],
    }
    assert apply_filters(RESULT_HIGH, [or_group]) is True


def test_apply_filters_mixed_and_or():
    """AND filter + OR group — both must pass."""
    and_filter = {"dimension": "factor_score", "operator": ">=", "value": 70}
    or_group = {
        "connector": "OR",
        "filters": [
            {"dimension": "pe_ratio", "operator": "<=", "value": 25.0},
            {"dimension": "rsi", "operator": ">=", "value": 50.0},
        ],
    }
    # RESULT_HIGH: factor=80 ✓, pe=20≤25 ✓ (OR passes)
    assert apply_filters(RESULT_HIGH, [and_filter, or_group]) is True


def test_apply_filters_and_or_combo_fails_on_and():
    """AND filter fails → overall result fails even if OR group passes."""
    and_filter = {"dimension": "factor_score", "operator": ">=", "value": 90}  # 80 < 90 → fail
    or_group = {
        "connector": "OR",
        "filters": [
            {"dimension": "risk_score", "operator": "<=", "value": 30},
        ],
    }
    assert apply_filters(RESULT_HIGH, [and_filter, or_group]) is False


def test_apply_filters_empty_or_group_passes():
    """OR group with no sub-filters should pass (vacuously true)."""
    or_group = {"connector": "OR", "filters": []}
    assert apply_filters(RESULT_HIGH, [or_group]) is True


# ---------------------------------------------------------------------------
# P7.3: Screen templates
# ---------------------------------------------------------------------------

def test_save_and_load_template(tmp_path, monkeypatch):
    """Save a template and retrieve it."""
    monkeypatch.setattr("screener._TEMPLATES_FILE", tmp_path / "templates.json")
    filters = [{"dimension": "factor_score", "operator": ">=", "value": 70, "label": "High factor"}]
    save_screen_template("my_screen", filters)
    templates = load_screen_templates()
    assert "my_screen" in templates
    assert templates["my_screen"] == filters


def test_load_templates_empty_when_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr("screener._TEMPLATES_FILE", tmp_path / "nonexistent.json")
    templates = load_screen_templates()
    assert templates == {}


def test_delete_template(tmp_path, monkeypatch):
    monkeypatch.setattr("screener._TEMPLATES_FILE", tmp_path / "templates.json")
    filters = [{"dimension": "risk_score", "operator": "<=", "value": 40}]
    save_screen_template("to_delete", filters)
    delete_screen_template("to_delete")
    templates = load_screen_templates()
    assert "to_delete" not in templates


def test_delete_nonexistent_template_no_crash(tmp_path, monkeypatch):
    monkeypatch.setattr("screener._TEMPLATES_FILE", tmp_path / "templates.json")
    delete_screen_template("ghost_template")  # should not raise


def test_save_multiple_templates(tmp_path, monkeypatch):
    monkeypatch.setattr("screener._TEMPLATES_FILE", tmp_path / "templates.json")
    save_screen_template("screen_a", [{"dimension": "factor_score", "operator": ">=", "value": 60}])
    save_screen_template("screen_b", [{"dimension": "risk_score", "operator": "<=", "value": 50}])
    templates = load_screen_templates()
    assert "screen_a" in templates
    assert "screen_b" in templates


def test_overwrite_existing_template(tmp_path, monkeypatch):
    monkeypatch.setattr("screener._TEMPLATES_FILE", tmp_path / "templates.json")
    save_screen_template("screen", [{"dimension": "factor_score", "operator": ">=", "value": 60}])
    save_screen_template("screen", [{"dimension": "factor_score", "operator": ">=", "value": 80}])
    templates = load_screen_templates()
    assert templates["screen"][0]["value"] == 80


# ---------------------------------------------------------------------------
# P7.3: CSV export
# ---------------------------------------------------------------------------

def test_results_to_csv_empty():
    assert results_to_csv([]) == ""


def test_results_to_csv_header_present():
    results = [{"symbol": "AAPL", "name": "Apple Inc.", "sector": "Technology",
                "price": 150.0, "factor_score": 75, "composite_label": "Buy",
                "risk_score": 30, "risk_level": "Moderate",
                "pe_ratio": 28.5, "market_cap_b": 2500.0, "rsi": 54.0,
                "trend": "uptrend", "flag_count": 1}]
    csv = results_to_csv(results)
    assert "symbol" in csv
    assert "factor_score" in csv


def test_results_to_csv_data_row():
    results = [{"symbol": "MSFT", "name": "Microsoft", "sector": "Technology",
                "price": 380.0, "factor_score": 80, "composite_label": "Strong Buy",
                "risk_score": 25, "risk_level": "Low",
                "pe_ratio": 35.0, "market_cap_b": 2800.0, "rsi": 58.0,
                "trend": "uptrend", "flag_count": 0}]
    csv = results_to_csv(results)
    assert "MSFT" in csv
    assert "80" in csv


def test_results_to_csv_multiple_rows():
    results = [
        {"symbol": "AAPL", "name": "Apple", "sector": "Tech", "price": 150.0,
         "factor_score": 75, "composite_label": "Buy", "risk_score": 30,
         "risk_level": "Moderate", "pe_ratio": 28.0, "market_cap_b": 2500.0,
         "rsi": 55.0, "trend": "uptrend", "flag_count": 0},
        {"symbol": "NVDA", "name": "NVIDIA", "sector": "Tech", "price": 800.0,
         "factor_score": 85, "composite_label": "Strong Buy", "risk_score": 40,
         "risk_level": "Elevated", "pe_ratio": 60.0, "market_cap_b": 2000.0,
         "rsi": 68.0, "trend": "uptrend", "flag_count": 1},
    ]
    csv = results_to_csv(results)
    assert "AAPL" in csv
    assert "NVDA" in csv


def test_results_to_csv_newlines():
    results = [{"symbol": "TEST", "name": "Test Co", "sector": "Other",
                "price": 50.0, "factor_score": 60, "composite_label": "Neutral",
                "risk_score": 45, "risk_level": "Elevated", "pe_ratio": 15.0,
                "market_cap_b": 5.0, "rsi": 50.0, "trend": "sideways", "flag_count": 0}]
    csv = results_to_csv(results)
    lines = csv.strip().split("\n")
    assert len(lines) == 2  # header + 1 data row


# ---------------------------------------------------------------------------
# P7.3: Sentiment warning
# ---------------------------------------------------------------------------

def test_sentiment_warning_returns_string():
    msg = sentiment_skipped_warning()
    assert isinstance(msg, str)
    assert len(msg) > 0


def test_sentiment_warning_mentions_finbert():
    msg = sentiment_skipped_warning()
    assert "FinBERT" in msg or "sentiment" in msg.lower()
