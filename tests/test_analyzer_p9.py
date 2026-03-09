"""Tests for P9 AI & Claude integration features in analyzer.py.

Covers:
- P9.1 Response caching (_compute_context_hash, _store_cached_response, _get_cached_response)
- P9.2 Adaptive system prompts (stream_fundamental_analysis stock_type param)
- P9.3 Claude Backtest Narrative (stream_backtest_narrative)
- P9.5 Chat History Trim (trim_chat_history, _estimate_tokens)
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

os.environ.setdefault("ANTHROPIC_API_KEY", "test_key_ci")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

from analyzer import (
    _compute_context_hash,
    _estimate_tokens,
    trim_chat_history,
    _DEFAULT_SYSTEM_PROMPT,
    _STOCK_TYPE_SYSTEM_PROMPTS,
)


# ---------------------------------------------------------------------------
# P9.5: _estimate_tokens
# ---------------------------------------------------------------------------

def test_estimate_tokens_empty_string():
    assert _estimate_tokens("") == 0.0


def test_estimate_tokens_proportional_to_words():
    short = _estimate_tokens("hello world")
    long = _estimate_tokens("hello world foo bar baz qux")
    assert long > short


def test_estimate_tokens_scales_by_1_3():
    text = "one two three four"   # 4 words
    assert abs(_estimate_tokens(text) - 4 * 1.3) < 0.01


# ---------------------------------------------------------------------------
# P9.5: trim_chat_history
# ---------------------------------------------------------------------------

def _make_history(n: int, words_per_msg: int = 50) -> list[dict]:
    content = " ".join(["word"] * words_per_msg)
    roles = ["user", "assistant"]
    return [{"role": roles[i % 2], "content": content} for i in range(n)]


def test_trim_chat_history_short_history_unchanged():
    history = _make_history(4, words_per_msg=10)
    trimmed, was_trimmed = trim_chat_history("System.", history, max_budget_tokens=100_000)
    assert not was_trimmed
    assert trimmed == history


def test_trim_chat_history_truncates_long_history():
    history = _make_history(200, words_per_msg=100)
    trimmed, was_trimmed = trim_chat_history(
        "System.", history, max_budget_tokens=50000, budget_ratio=0.8
    )
    assert was_trimmed
    assert len(trimmed) < len(history)
    assert _estimate_tokens(" ".join(m["content"] for m in trimmed)) <= 50000 * 0.8 + 200


def test_trim_chat_history_preserves_newest_messages():
    history = _make_history(100, words_per_msg=200)
    trimmed, _ = trim_chat_history("S", history, max_budget_tokens=10_000)
    # Newest message should always be kept
    assert trimmed[-1] == history[-1]


def test_trim_chat_history_returns_tuple():
    history = _make_history(2)
    result = trim_chat_history("S", history)
    assert isinstance(result, tuple) and len(result) == 2


# ---------------------------------------------------------------------------
# P9.1: _compute_context_hash
# ---------------------------------------------------------------------------

def test_compute_context_hash_deterministic():
    prompt = "Analyze AAPL fundamentals."
    assert _compute_context_hash(prompt) == _compute_context_hash(prompt)


def test_compute_context_hash_different_prompts():
    h1 = _compute_context_hash("prompt A")
    h2 = _compute_context_hash("prompt B")
    assert h1 != h2


def test_compute_context_hash_is_hex_string():
    h = _compute_context_hash("test")
    assert isinstance(h, str)
    assert all(c in "0123456789abcdef" for c in h)
    assert len(h) == 64   # SHA-256 hex digest


# ---------------------------------------------------------------------------
# P9.1: cache round-trip via stream_backtest_narrative
# ---------------------------------------------------------------------------

def test_stream_backtest_narrative_uses_cache_on_second_call():
    """Second call with identical inputs should be served from cache."""
    mock_stream = MagicMock()
    mock_event = MagicMock()
    mock_event.type = "content_block_delta"
    mock_event.delta.type = "text_delta"
    mock_event.delta.text = "narrative chunk"
    mock_stream.__enter__ = MagicMock(return_value=iter([mock_event]))
    mock_stream.__exit__ = MagicMock(return_value=False)

    metrics = {"total_return_pct": 15.3, "sharpe": 1.2, "max_drawdown_pct": -8.0,
               "win_rate_pct": 55.0, "num_trades": 12}

    with (
        patch("analyzer._get_client") as mock_get_client,
        patch("analyzer._get_cached_response", return_value=None) as mock_get_cache,
        patch("analyzer._store_cached_response") as mock_store,
    ):
        mock_client = MagicMock()
        mock_client.messages.stream.return_value = mock_stream
        mock_get_client.return_value = mock_client

        from analyzer import stream_backtest_narrative
        result = list(stream_backtest_narrative(metrics, []))

        assert len(result) > 0
        mock_get_cache.assert_called_once()
        mock_store.assert_called_once()


def test_stream_backtest_narrative_cache_hit_skips_api():
    """When cache returns a result, the Anthropic API should not be called."""
    cached_text = "Cached narrative text."
    metrics = {"total_return_pct": 10.0}

    with (
        patch("analyzer._get_client") as mock_get_client,
        patch("analyzer._get_cached_response", return_value=cached_text),
    ):
        from analyzer import stream_backtest_narrative
        result = list(stream_backtest_narrative(metrics, []))

        assert result == [cached_text]
        mock_get_client.assert_not_called()


def test_stream_backtest_narrative_hash_uses_compute_context_hash():
    cached_text = "cached"
    metrics = {"total_return_pct": 5.0}

    with (
        patch("analyzer._get_client"),
        patch("analyzer._get_cached_response", return_value=cached_text),
        patch("analyzer._compute_context_hash", wraps=_compute_context_hash) as mock_hash,
    ):
        from analyzer import stream_backtest_narrative
        list(stream_backtest_narrative(metrics, []))
        mock_hash.assert_called_once()


# ---------------------------------------------------------------------------
# P9.2: Adaptive system prompts
# ---------------------------------------------------------------------------

def test_stream_fundamental_analysis_uses_stock_type_prompt():
    from analyzer import stream_fundamental_analysis

    mock_stream = MagicMock()
    mock_event = MagicMock()
    mock_event.type = "content_block_delta"
    mock_event.delta.type = "text_delta"
    mock_event.delta.text = "chunk"
    mock_stream.__enter__ = MagicMock(return_value=iter([mock_event]))
    mock_stream.__exit__ = MagicMock(return_value=False)

    mock_client = MagicMock()
    mock_client.messages.stream.return_value = mock_stream

    with patch("analyzer._get_client", return_value=mock_client):
        list(stream_fundamental_analysis("test prompt", stock_type="growth"))

    call_kwargs = mock_client.messages.stream.call_args[1]
    system_used = call_kwargs.get("system", "")
    assert "growth" in system_used.lower() or "growth equity" in system_used.lower()


def test_stream_fundamental_analysis_default_prompt_when_no_type():
    from analyzer import _DEFAULT_SYSTEM_PROMPT

    mock_stream = MagicMock()
    mock_event = MagicMock()
    mock_event.type = "content_block_delta"
    mock_event.delta.type = "text_delta"
    mock_event.delta.text = "chunk"
    mock_stream.__enter__ = MagicMock(return_value=iter([mock_event]))
    mock_stream.__exit__ = MagicMock(return_value=False)

    mock_client = MagicMock()
    mock_client.messages.stream.return_value = mock_stream

    from analyzer import stream_fundamental_analysis
    with patch("analyzer._get_client", return_value=mock_client):
        list(stream_fundamental_analysis("test prompt", stock_type=None))

    call_kwargs = mock_client.messages.stream.call_args[1]
    assert call_kwargs.get("system") == _DEFAULT_SYSTEM_PROMPT


def test_stock_type_prompts_all_types_present():
    for key in ("growth", "value", "dividend", "cyclical", "defensive"):
        assert key in _STOCK_TYPE_SYSTEM_PROMPTS
        assert isinstance(_STOCK_TYPE_SYSTEM_PROMPTS[key], str)
        assert len(_STOCK_TYPE_SYSTEM_PROMPTS[key]) > 50


def test_default_system_prompt_is_string():
    assert isinstance(_DEFAULT_SYSTEM_PROMPT, str)
    assert len(_DEFAULT_SYSTEM_PROMPT) > 50
