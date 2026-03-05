import streamlit as st
from transformers import pipeline


@st.cache_resource(show_spinner=False)
def _load_finbert():
    """Load FinBERT once and reuse across all Streamlit reruns."""
    return pipeline(
        "text-classification",
        model="ProsusAI/finbert",
        top_k=None,  # return all three label scores
        truncation=True,
        max_length=512,
    )


def score_articles(articles: list) -> list[dict]:
    """Score each article headline with FinBERT.

    Returns a list parallel to `articles`, each entry:
        {"label": "positive"|"negative"|"neutral", "score": float}
    """
    if not articles:
        return []

    pipe = _load_finbert()
    results = []
    for article in articles:
        headline = article.get("headline", "").strip()
        if not headline:
            results.append({"label": "neutral", "score": 1.0})
            continue

        # pipe returns a list of all label scores, sorted by score desc
        preds = pipe(headline)  # [[{label, score}, ...]]
        # preds is a list-of-lists when top_k=None; first element is best
        top = preds[0] if isinstance(preds[0], dict) else preds[0][0]
        # Normalise label to lowercase
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
        counts[label] = counts.get(label, 0) + 1

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
    "neutral":  "#888888",
}

SENTIMENT_EMOJI = {
    "positive": "🟢",
    "negative": "🔴",
    "neutral":  "⚪",
}
