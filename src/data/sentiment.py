import os
import random

import streamlit as st

from src.core.log_setup import get_logger

try:
    from transformers import pipeline as _transformers_pipeline
except ImportError:
    _transformers_pipeline = None  # type: ignore[assignment]

log = get_logger(__name__)

_MOCK_MODE = os.getenv("MOCK_DATA", "").strip().lower() in ("1", "true", "yes")


@st.cache_resource(show_spinner=False)
def _load_finbert():
    """Load FinBERT once and reuse across all Streamlit reruns."""
    if _transformers_pipeline is None:
        raise ImportError(
            "The `transformers` package is not installed. "
            "Run `pip install transformers torch` or set MOCK_DATA=1."
        )
    return _transformers_pipeline(
        "text-classification",
        model="ProsusAI/finbert",
        top_k=None,  # return all three label scores
        truncation=True,
        max_length=512,
    )


def _mock_score_articles(articles: list) -> list[dict]:
    """Return plausible mock sentiment scores for local testing."""
    rng = random.Random(42)
    results = []
    positive_keywords = {"strong", "beat", "upgrade", "bull", "high", "grow", "expan"}
    negative_keywords = {"weak", "miss", "downgrad", "bear", "low", "declin", "risk"}
    for article in articles:
        headline = article.get("headline", "").lower()
        if any(kw in headline for kw in positive_keywords):
            label = "positive"
        elif any(kw in headline for kw in negative_keywords):
            label = "negative"
        else:
            label = rng.choice(
                ["positive", "positive", "neutral", "neutral", "negative"]
            )
        results.append({"label": label, "score": round(rng.uniform(0.7, 0.98), 4)})
    return results


def score_articles(articles: list) -> list[dict]:
    """Score each article headline with FinBERT.

    Returns a list parallel to `articles`, each entry:
        {"label": "positive"|"negative"|"neutral", "score": float}

    In mock mode (MOCK_DATA=1), returns plausible synthetic scores.
    """
    if not articles:
        return []

    if _MOCK_MODE:
        return _mock_score_articles(articles)

    pipe = _load_finbert()
    results = []
    for article in articles:
        headline = article.get("headline", "").strip()
        if not headline:
            results.append({"label": "neutral", "score": 1.0})
            continue

        # With top_k=None, pipeline returns a list of dicts sorted by score desc
        preds = pipe(headline)
        top = preds[0]  # highest-confidence prediction
        results.append({"label": top["label"].lower(), "score": top["score"]})

    return results


def aggregate_sentiment(scores: list[dict]) -> dict:
    """Compute aggregate counts, net score, and overall signal.

    Returns:
        counts   – dict with keys positive/negative/neutral
        total    – int
        net_score – float in [-1, +1]
        signal   – "Bullish" | "Bearish" | "Mixed / Neutral"
    """
    counts = {"positive": 0, "negative": 0, "neutral": 0}
    for s in scores:
        label = s.get("label", "neutral").lower()
        if label not in counts:
            label = "neutral"
        counts[label] += 1

    total = len(scores)
    net = (counts["positive"] - counts["negative"]) / total if total else 0.0

    if net > 0.2:
        signal = "Bullish"
    elif net < -0.2:
        signal = "Bearish"
    else:
        signal = "Mixed / Neutral"

    return {"counts": counts, "total": total, "net_score": net, "signal": signal}


# Colour constants reused in app.py
SENTIMENT_COLOR = {
    "positive": "#2da44e",
    "negative": "#e05252",
    "neutral": "#888888",
}

SENTIMENT_EMOJI = {
    "positive": "🟢",
    "negative": "🔴",
    "neutral": "⚪",
}

# ---------------------------------------------------------------------------
# P20.2: News impact-weighted sentiment scoring
# ---------------------------------------------------------------------------

_IMPACT_WEIGHTS: dict[str, float] = {
    "High": 3.0,
    "Medium": 2.0,
    "Low": 1.0,
    "Negligible": 0.5,
}


def compute_impact_weighted_sentiment(
    articles: list[dict],
    sentiment_scores: list[dict],
    impact_scores: list[dict],
) -> dict:
    """Compute sentiment weighted by article impact level (P20.2).

    Each article is weighted by its impact level before contributing to the
    net sentiment signal.  If impact_scores is empty or mismatched, falls
    back to equal-weight aggregation (matching aggregate_sentiment behaviour).

    Parameters
    ----------
    articles        : list of article dicts (used for length reference only).
    sentiment_scores : list of dicts parallel to articles, each with:
                       {label: "positive"|"negative"|"neutral", score: float}
    impact_scores   : list of dicts parallel to articles, each with:
                       {level: "High"|"Medium"|"Low"|"Negligible"}
                       Pass an empty list to use equal weighting.

    Returns
    -------
    dict with:
        weighted_net_score   – float in [-1, +1], positive = more bullish
        weighted_signal      – "Bullish" | "Bearish" | "Mixed / Neutral"
        impact_distribution  – dict mapping level -> count of articles
    """
    if not sentiment_scores:
        log.debug(
            "compute_impact_weighted_sentiment: no sentiment scores, returning neutral"
        )
        return {
            "weighted_net_score": 0.0,
            "weighted_signal": "Mixed / Neutral",
            "impact_distribution": {},
        }

    # Fall back to equal weights if impact_scores is empty or length mismatch
    use_equal_weights = not impact_scores or len(impact_scores) != len(sentiment_scores)

    if use_equal_weights:
        log.debug(
            "compute_impact_weighted_sentiment: falling back to equal-weight aggregation"
        )
        agg = aggregate_sentiment(sentiment_scores)
        return {
            "weighted_net_score": round(agg["net_score"], 4),
            "weighted_signal": agg["signal"],
            "impact_distribution": {},
        }

    impact_distribution: dict[str, int] = {
        "High": 0,
        "Medium": 0,
        "Low": 0,
        "Negligible": 0,
    }
    weighted_positive = 0.0
    weighted_negative = 0.0
    total_weight = 0.0

    for sent, imp in zip(sentiment_scores, impact_scores):
        label = (sent.get("label") or "neutral").lower()
        level = imp.get("level", "Low")
        weight = _IMPACT_WEIGHTS.get(level, 1.0)

        # Track distribution
        if level in impact_distribution:
            impact_distribution[level] += 1
        else:
            impact_distribution[level] = 1

        if label == "positive":
            weighted_positive += weight
        elif label == "negative":
            weighted_negative += weight

        total_weight += weight

    if total_weight == 0:
        weighted_net = 0.0
    else:
        weighted_net = (weighted_positive - weighted_negative) / total_weight

    if weighted_net > 0.2:
        signal = "Bullish"
    elif weighted_net < -0.2:
        signal = "Bearish"
    else:
        signal = "Mixed / Neutral"

    log.debug(
        "Impact-weighted sentiment: net=%.3f signal=%s (total_weight=%.1f)",
        weighted_net,
        signal,
        total_weight,
    )

    return {
        "weighted_net_score": round(weighted_net, 4),
        "weighted_signal": signal,
        "impact_distribution": impact_distribution,
    }
