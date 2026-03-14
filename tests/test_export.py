"""Tests for export.py (P1.3)."""

import pandas as pd


SAMPLE_FACTORS = [
    {
        "name": "Valuation (P/E)",
        "score": 75,
        "weight": 0.15,
        "label": "Fairly valued",
        "detail": "P/E 18x",
    },
    {
        "name": "Trend (SMA)",
        "score": 85,
        "weight": 0.20,
        "label": "Strong uptrend",
        "detail": "Price > SMA50 > SMA200",
    },
    {
        "name": "Momentum (RSI)",
        "score": 65,
        "weight": 0.10,
        "label": "Healthy zone",
        "detail": "RSI 52.3",
    },
]

SAMPLE_QUOTE = {"c": 150.0, "d": 2.5, "dp": 1.7, "h": 152.0, "l": 148.0, "pc": 147.5}

SAMPLE_RISK = {
    "risk_score": 28,
    "risk_level": "Moderate",
    "risk_color": "#4CAF50",
    "hv": 22.5,
    "drawdown_pct": 12.3,
    "flags": [
        {
            "severity": "warning",
            "icon": "⚡",
            "title": "High Vol",
            "message": "HV elevated",
        },
    ],
}

SAMPLE_FINANCIALS = {
    "peBasicExclExtraTTM": 18.5,
    "epsBasicExclExtraItemsTTM": 6.20,
    "marketCapitalization": 2_500_000,
    "dividendYieldIndicatedAnnual": 0.52,
    "52WeekHigh": 182.0,
    "52WeekLow": 124.0,
}


def test_factors_to_csv_returns_bytes():
    from export import factors_to_csv

    result = factors_to_csv(
        "AAPL", SAMPLE_FACTORS, SAMPLE_RISK, SAMPLE_QUOTE, SAMPLE_FINANCIALS
    )
    assert isinstance(result, bytes)
    assert len(result) > 0


def test_factors_to_csv_contains_symbol():
    from export import factors_to_csv

    result = factors_to_csv(
        "AAPL", SAMPLE_FACTORS, SAMPLE_RISK, SAMPLE_QUOTE, SAMPLE_FINANCIALS
    )
    assert b"AAPL" in result


def test_factors_to_csv_contains_factor_names():
    from export import factors_to_csv

    result = factors_to_csv("TSLA", SAMPLE_FACTORS, SAMPLE_RISK, SAMPLE_QUOTE)
    decoded = result.decode("utf-8")
    assert "Valuation (P/E)" in decoded
    assert "Trend (SMA)" in decoded


def test_factors_to_csv_contains_flags():
    from export import factors_to_csv

    result = factors_to_csv("AAPL", SAMPLE_FACTORS, SAMPLE_RISK, SAMPLE_QUOTE)
    assert b"High Vol" in result


def test_price_history_to_csv():
    from export import price_history_to_csv

    df = pd.DataFrame(
        {"Open": [100, 101], "Close": [102, 103]},
        index=pd.date_range("2024-01-01", periods=2),
    )
    result = price_history_to_csv("AAPL", df)
    assert isinstance(result, bytes)
    assert b"AAPL" in result
    assert b"Close" in result


def test_analysis_to_html_returns_bytes():
    from export import analysis_to_html

    result = analysis_to_html(
        symbol="AAPL",
        quote=SAMPLE_QUOTE,
        profile={"name": "Apple Inc.", "finnhubIndustry": "Technology"},
        financials=SAMPLE_FINANCIALS,
        factors=SAMPLE_FACTORS,
        risk=SAMPLE_RISK,
        composite_score=72,
        composite_label="Strong Buy",
    )
    assert isinstance(result, bytes)
    assert b"AAPL" in result
    assert b"Apple Inc." in result


def test_analysis_to_html_valid_html():
    from export import analysis_to_html

    result = analysis_to_html(
        symbol="MSFT",
        quote=SAMPLE_QUOTE,
        profile=None,
        financials=None,
        factors=SAMPLE_FACTORS,
        risk=SAMPLE_RISK,
        composite_score=65,
        composite_label="Buy",
    )
    html = result.decode("utf-8")
    assert "<!DOCTYPE html>" in html
    assert "<table>" in html
    assert "Strong Buy" in html or "Buy" in html
