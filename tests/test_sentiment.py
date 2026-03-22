"""Unit tests for sentiment.py — aggregate_sentiment and label validation.

score_articles() requires a live FinBERT model and is tested via integration;
only the pure-logic helpers are covered here.
"""

import pytest
from src.data.sentiment import aggregate_sentiment


# ---------------------------------------------------------------------------
# aggregate_sentiment — counts
# ---------------------------------------------------------------------------


def test_aggregate_empty_list():
    result = aggregate_sentiment([])
    assert result["total"] == 0
    assert result["net_score"] == 0.0
    assert result["signal"] == "Mixed / Neutral"
    assert result["counts"] == {"positive": 0, "negative": 0, "neutral": 0}


def test_aggregate_all_positive():
    scores = [{"label": "positive", "score": 0.9}] * 5
    result = aggregate_sentiment(scores)
    assert result["counts"]["positive"] == 5
    assert result["counts"]["negative"] == 0
    assert result["counts"]["neutral"] == 0
    assert result["total"] == 5
    assert result["net_score"] == pytest.approx(1.0)
    assert result["signal"] == "Bullish"


def test_aggregate_all_negative():
    scores = [{"label": "negative", "score": 0.85}] * 4
    result = aggregate_sentiment(scores)
    assert result["counts"]["negative"] == 4
    assert result["net_score"] == pytest.approx(-1.0)
    assert result["signal"] == "Bearish"


def test_aggregate_all_neutral():
    scores = [{"label": "neutral", "score": 0.7}] * 3
    result = aggregate_sentiment(scores)
    assert result["counts"]["neutral"] == 3
    assert result["net_score"] == pytest.approx(0.0)
    assert result["signal"] == "Mixed / Neutral"


def test_aggregate_mixed_bullish():
    # 6 positive, 1 negative → net = 5/7 ≈ 0.71 > 0.2 → Bullish
    scores = [{"label": "positive", "score": 0.9}] * 6 + [
        {"label": "negative", "score": 0.8}
    ] * 1
    result = aggregate_sentiment(scores)
    assert result["signal"] == "Bullish"
    assert result["net_score"] == pytest.approx(5 / 7)


def test_aggregate_mixed_bearish():
    # 1 positive, 6 negative → net = -5/7 ≈ -0.71 < -0.2 → Bearish
    scores = [{"label": "positive", "score": 0.8}] * 1 + [
        {"label": "negative", "score": 0.9}
    ] * 6
    result = aggregate_sentiment(scores)
    assert result["signal"] == "Bearish"
    assert result["net_score"] == pytest.approx(-5 / 7)


def test_aggregate_near_neutral_boundary():
    # 3 positive, 2 negative, 5 neutral → net = 1/10 = 0.1 → Mixed
    scores = (
        [{"label": "positive", "score": 0.8}] * 3
        + [{"label": "negative", "score": 0.8}] * 2
        + [{"label": "neutral", "score": 0.9}] * 5
    )
    result = aggregate_sentiment(scores)
    assert result["signal"] == "Mixed / Neutral"
    assert result["net_score"] == pytest.approx(0.1)


# ---------------------------------------------------------------------------
# Label validation — unknown labels must fall back to "neutral"
# ---------------------------------------------------------------------------


def test_aggregate_unknown_label_falls_back():
    scores = [{"label": "unknown_label", "score": 0.9}]
    result = aggregate_sentiment(scores)
    # Must not create a new key in counts
    assert set(result["counts"].keys()) == {"positive", "negative", "neutral"}
    assert result["counts"]["neutral"] == 1


def test_aggregate_mixed_with_unknown_label():
    scores = [
        {"label": "positive", "score": 0.9},
        {"label": "GARBAGE", "score": 0.5},
        {"label": "negative", "score": 0.8},
    ]
    result = aggregate_sentiment(scores)
    assert result["counts"]["positive"] == 1
    assert result["counts"]["negative"] == 1
    assert result["counts"]["neutral"] == 1  # GARBAGE → neutral
    assert set(result["counts"].keys()) == {"positive", "negative", "neutral"}


def test_aggregate_uppercase_labels_normalised():
    # Labels from the model might come in various cases
    scores = [{"label": "Positive", "score": 0.9}]
    result = aggregate_sentiment(scores)
    assert result["counts"]["positive"] == 1


# ---------------------------------------------------------------------------
# net_score bounds
# ---------------------------------------------------------------------------


def test_net_score_single_positive():
    result = aggregate_sentiment([{"label": "positive", "score": 0.9}])
    assert result["net_score"] == pytest.approx(1.0)


def test_net_score_single_negative():
    result = aggregate_sentiment([{"label": "negative", "score": 0.9}])
    assert result["net_score"] == pytest.approx(-1.0)


def test_net_score_single_neutral():
    result = aggregate_sentiment([{"label": "neutral", "score": 0.9}])
    assert result["net_score"] == pytest.approx(0.0)
