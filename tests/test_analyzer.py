"""Tests for analyzer.py — mocks the Anthropic SDK (P4.4)."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("ANTHROPIC_API_KEY", "test_key_ci")

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

SAMPLE_QUOTE = {"c": 150.0, "d": 1.5, "dp": 1.0, "h": 152.0, "l": 148.0, "pc": 148.5}

SAMPLE_PROFILE = {
    "name": "Apple Inc.",
    "finnhubIndustry": "Technology",
    "country": "US",
    "exchange": "NASDAQ",
}

SAMPLE_FINANCIALS = {
    "peBasicExclExtraTTM": 28.5,
    "epsBasicExclExtraItemsTTM": 6.05,
    "marketCapitalization": 2_500_000,
    "dividendYieldIndicatedAnnual": 0.52,
    "52WeekHigh": 182.0,
    "52WeekLow": 124.0,
}

SAMPLE_TECHNICALS = {
    "sma50": "$145.00",
    "sma200": "$138.00",
    "rsi": "54.20",
    "macd": "0.8500",
    "macd_signal": "0.7800",
    "macd_hist": "+0.0700",
}

SAMPLE_RECS = [
    {
        "period": "2024-01",
        "strongBuy": 20,
        "buy": 10,
        "hold": 5,
        "sell": 2,
        "strongSell": 1,
    }
]
SAMPLE_EARNINGS = [
    {"period": "2024-Q1", "actual": 2.5, "estimate": 2.3, "surprisePercent": 8.7}
]
SAMPLE_PEERS = ["MSFT", "GOOGL", "AMZN"]
SAMPLE_NEWS = [{"headline": "Apple surges on earnings", "source": "Reuters"}]

SAMPLE_FACTORS = [
    {
        "name": "Valuation (P/E)",
        "score": 63,
        "weight": 0.15,
        "label": "Moderately valued",
        "detail": "P/E 28.5x",
    },
    {
        "name": "Trend (SMA)",
        "score": 90,
        "weight": 0.20,
        "label": "Strong uptrend",
        "detail": "Price > SMA50 > SMA200",
    },
]

SAMPLE_RISK = {
    "risk_score": 30,
    "risk_level": "Moderate",
    "hv": 22.0,
    "drawdown_pct": 10.5,
    "flags": [],
}


# ---------------------------------------------------------------------------
# build_data_prompt
# ---------------------------------------------------------------------------


def test_build_data_prompt_contains_symbol():
    from src.analysis.analyzer import build_data_prompt

    prompt = build_data_prompt(
        symbol="AAPL",
        quote=SAMPLE_QUOTE,
        profile=SAMPLE_PROFILE,
        financials=SAMPLE_FINANCIALS,
        technicals=SAMPLE_TECHNICALS,
        recommendations=SAMPLE_RECS,
        earnings=SAMPLE_EARNINGS,
        peers=SAMPLE_PEERS,
        news=SAMPLE_NEWS,
    )
    assert "AAPL" in prompt


def test_build_data_prompt_contains_price():
    from src.analysis.analyzer import build_data_prompt

    prompt = build_data_prompt(
        symbol="AAPL",
        quote=SAMPLE_QUOTE,
        profile=None,
        financials=None,
        technicals={},
        recommendations=[],
        earnings=[],
        peers=[],
        news=[],
    )
    assert "150.0" in prompt


def test_build_data_prompt_handles_missing_profile():
    from src.analysis.analyzer import build_data_prompt

    prompt = build_data_prompt(
        symbol="AAPL",
        quote=SAMPLE_QUOTE,
        profile=None,
        financials=None,
        technicals={},
        recommendations=[],
        earnings=[],
        peers=[],
        news=[],
    )
    assert isinstance(prompt, str)
    assert len(prompt) > 0


def test_build_data_prompt_includes_peers():
    from src.analysis.analyzer import build_data_prompt

    prompt = build_data_prompt(
        symbol="AAPL",
        quote=SAMPLE_QUOTE,
        profile=SAMPLE_PROFILE,
        financials=None,
        technicals={},
        recommendations=[],
        earnings=[],
        peers=SAMPLE_PEERS,
        news=[],
    )
    assert "MSFT" in prompt


def test_build_data_prompt_includes_news_headline():
    from src.analysis.analyzer import build_data_prompt

    prompt = build_data_prompt(
        symbol="AAPL",
        quote=SAMPLE_QUOTE,
        profile=None,
        financials=None,
        technicals={},
        recommendations=[],
        earnings=[],
        peers=[],
        news=SAMPLE_NEWS,
    )
    assert "Apple surges" in prompt


# ---------------------------------------------------------------------------
# build_chat_system_prompt
# ---------------------------------------------------------------------------


def test_build_chat_system_prompt_contains_symbol():
    from src.analysis.analyzer import build_chat_system_prompt

    prompt = build_chat_system_prompt(
        symbol="AAPL",
        profile=SAMPLE_PROFILE,
        quote=SAMPLE_QUOTE,
        financials=SAMPLE_FINANCIALS,
        factors=SAMPLE_FACTORS,
        risk=SAMPLE_RISK,
        composite_score=72,
        composite_label="Strong Buy",
    )
    assert "AAPL" in prompt
    assert "Apple Inc." in prompt


def test_build_chat_system_prompt_contains_score():
    from src.analysis.analyzer import build_chat_system_prompt

    prompt = build_chat_system_prompt(
        symbol="AAPL",
        profile=None,
        quote=SAMPLE_QUOTE,
        financials=None,
        factors=SAMPLE_FACTORS,
        risk=SAMPLE_RISK,
        composite_score=72,
        composite_label="Buy",
    )
    assert "72" in prompt
    assert "Buy" in prompt


def test_build_chat_system_prompt_handles_no_profile():
    from src.analysis.analyzer import build_chat_system_prompt

    prompt = build_chat_system_prompt(
        symbol="TSLA",
        profile=None,
        quote=SAMPLE_QUOTE,
        financials=None,
        factors=[],
        risk={"risk_score": 50, "risk_level": "Moderate", "flags": []},
        composite_score=50,
        composite_label="Neutral",
    )
    assert isinstance(prompt, str)


# ---------------------------------------------------------------------------
# stream_fundamental_analysis — mocked stream
# ---------------------------------------------------------------------------


def _mock_stream_event(text: str):
    event = MagicMock()
    event.type = "content_block_delta"
    event.delta.type = "text_delta"
    event.delta.text = text
    return event


def _make_mock_stream(chunks: list[str]):
    """Return a context-manager mock whose stream object exposes text_stream."""
    stream_obj = MagicMock()
    stream_obj.text_stream = iter(chunks)
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=stream_obj)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


def test_stream_fundamental_analysis_yields_chunks():
    from src.analysis.analyzer import stream_fundamental_analysis

    mock_client = MagicMock()
    mock_client.messages.stream.return_value = _make_mock_stream(["Hello ", "world!"])
    with patch("src.analysis.analyzer._get_client", return_value=mock_client):
        chunks = list(stream_fundamental_analysis("test prompt", use_cache=False))
    assert chunks == ["Hello ", "world!"]


def test_stream_fundamental_analysis_skips_non_text_events():
    from src.analysis.analyzer import stream_fundamental_analysis

    # text_stream already filters out non-text events at the SDK level;
    # verify that only the text yielded by text_stream reaches callers.
    mock_client = MagicMock()
    mock_client.messages.stream.return_value = _make_mock_stream(["Some text"])

    with patch("src.analysis.analyzer._get_client", return_value=mock_client):
        chunks = list(stream_fundamental_analysis("prompt"))
    assert chunks == ["Some text"]


# ---------------------------------------------------------------------------
# parse_nl_screen
# ---------------------------------------------------------------------------


def test_parse_nl_screen_returns_filters():
    from src.analysis.analyzer import parse_nl_screen

    response_text = '{"filters": [{"dimension": "factor_score", "operator": ">", "value": 65, "label": "Strong factor"}], "description": "High factor scores"}'
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=response_text)]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    with patch("src.analysis.analyzer._get_client", return_value=mock_client):
        result = parse_nl_screen("find strong stocks")

    assert "filters" in result
    assert result["filters"][0]["dimension"] == "factor_score"


def test_parse_nl_screen_handles_invalid_json():
    from src.analysis.analyzer import parse_nl_screen

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="not valid json at all")]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    with patch("src.analysis.analyzer._get_client", return_value=mock_client):
        result = parse_nl_screen("anything")

    assert result["filters"] == []


def test_parse_nl_screen_handles_empty_response():
    from src.analysis.analyzer import parse_nl_screen

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="")]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    with patch("src.analysis.analyzer._get_client", return_value=mock_client):
        result = parse_nl_screen("anything")

    assert result["filters"] == []


# ---------------------------------------------------------------------------
# stream_forward_looking_analysis
# ---------------------------------------------------------------------------


def test_stream_forward_looking_analysis_yields_chunks():
    from src.analysis.analyzer import stream_forward_looking_analysis

    mock_client = MagicMock()
    mock_client.messages.stream.return_value = _make_mock_stream(
        ["Forward ", "guidance."]
    )
    with patch("src.analysis.analyzer._get_client", return_value=mock_client):
        chunks = list(
            stream_forward_looking_analysis("AAPL", "We expect revenue to grow 10%...")
        )
    assert "".join(chunks) == "Forward guidance."


# ---------------------------------------------------------------------------
# _get_client — key validation
# ---------------------------------------------------------------------------


def test_get_client_raises_without_key(monkeypatch):
    import src.data.api as _api
    from src.analysis.analyzer import _get_client

    monkeypatch.setattr(_api, "MOCK_MODE", False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        _get_client()


def test_get_client_raises_on_placeholder(monkeypatch):
    import src.data.api as _api
    from src.analysis.analyzer import _get_client

    monkeypatch.setattr(_api, "MOCK_MODE", False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "your_anthropic_api_key_here")
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        _get_client()
