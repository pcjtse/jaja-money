"""Reddit and StockTwits social sentiment aggregation (P16.1)."""

from __future__ import annotations

from log_setup import get_logger

log = get_logger(__name__)


def fetch_reddit_mentions(symbol: str, limit: int = 25) -> list[dict]:
    """Fetch posts mentioning the symbol from Reddit's public search API.

    Uses the unauthenticated JSON API endpoint; no credentials required.
    Searches across r/wallstreetbets and r/stocks (and any other subreddit
    that appears in results).

    Parameters
    ----------
    symbol:
        Stock ticker symbol (e.g. "AAPL").
    limit:
        Maximum number of posts to return.

    Returns
    -------
    List of dicts, each with keys:
        title (str), score (int), num_comments (int),
        created_utc (float), subreddit (str).
    Returns empty list on any connection or parsing error.
    """
    import urllib.request
    import json

    url = (
        f"https://www.reddit.com/search.json"
        f"?q={symbol}&sort=new&limit={limit}&restrict_sr=false"
    )
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "jaja-money/1.0 (stock analysis app)"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
        data = json.loads(raw)
        children = data.get("data", {}).get("children", [])
        posts = []
        for child in children:
            post_data = child.get("data", {})
            posts.append(
                {
                    "title": post_data.get("title", ""),
                    "score": int(post_data.get("score", 0) or 0),
                    "num_comments": int(post_data.get("num_comments", 0) or 0),
                    "created_utc": float(post_data.get("created_utc", 0) or 0),
                    "subreddit": post_data.get("subreddit", ""),
                }
            )
        log.debug("Reddit: fetched %d posts for %s", len(posts), symbol)
        return posts
    except Exception as exc:
        log.warning("Reddit fetch failed for %s: %s", symbol, exc)
        return []


def fetch_stocktwits_messages(symbol: str, limit: int = 30) -> list[dict]:
    """Fetch recent messages from StockTwits for the given symbol.

    Uses the public StockTwits API (no authentication required for public streams).

    Parameters
    ----------
    symbol:
        Stock ticker symbol (e.g. "AAPL").
    limit:
        Maximum number of messages to return.

    Returns
    -------
    List of dicts, each with keys:
        body (str), sentiment (str|None: "bullish", "bearish", or None),
        created_at (str).
    Returns empty list on any error.
    """
    import urllib.request
    import json

    url = f"https://api.stocktwits.com/api/2/streams/symbol/{symbol}.json"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "jaja-money/1.0 (stock analysis app)"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
        data = json.loads(raw)
        messages_raw = data.get("messages", [])
        messages = []
        for msg in messages_raw[:limit]:
            entities = msg.get("entities", {})
            sentiment_data = entities.get("sentiment", None)
            sentiment = None
            if sentiment_data and isinstance(sentiment_data, dict):
                basic = sentiment_data.get("basic", "")
                if basic:
                    sentiment = basic.lower()  # "bullish" or "bearish"
            messages.append(
                {
                    "body": msg.get("body", ""),
                    "sentiment": sentiment,
                    "created_at": msg.get("created_at", ""),
                }
            )
        log.debug("StockTwits: fetched %d messages for %s", len(messages), symbol)
        return messages
    except Exception as exc:
        log.warning("StockTwits fetch failed for %s: %s", symbol, exc)
        return []


def compute_social_sentiment(
    reddit_posts: list,
    st_messages: list,
    finbert_pipe=None,
) -> dict:
    """Aggregate social sentiment from Reddit and StockTwits data.

    Parameters
    ----------
    reddit_posts:
        List of dicts as returned by fetch_reddit_mentions().
    st_messages:
        List of dicts as returned by fetch_stocktwits_messages().
    finbert_pipe:
        Optional HuggingFace transformers pipeline for FinBERT sentiment
        classification. If None, Reddit titles are scored as neutral.

    Returns
    -------
    dict with keys:
        reddit_mentions (int): Number of Reddit posts found.
        reddit_avg_score (float): Average upvote score across Reddit posts.
        st_bullish (int): StockTwits messages tagged bullish.
        st_bearish (int): StockTwits messages tagged bearish.
        st_neutral (int): StockTwits messages with no sentiment tag.
        overall_signal (str): "Bullish", "Bearish", or "Mixed".
        mention_count (int): Total mentions across both sources.
        available (bool): True if any data was found.
    """
    reddit_mentions = len(reddit_posts)
    reddit_avg_score = 0.0
    if reddit_posts:
        scores = [p.get("score", 0) or 0 for p in reddit_posts]
        reddit_avg_score = round(sum(scores) / len(scores), 1) if scores else 0.0

    # StockTwits sentiment counts
    st_bullish = 0
    st_bearish = 0
    st_neutral = 0
    for msg in st_messages:
        sentiment = msg.get("sentiment")
        if sentiment == "bullish":
            st_bullish += 1
        elif sentiment == "bearish":
            st_bearish += 1
        else:
            st_neutral += 1

    # Score Reddit titles with FinBERT if pipe provided
    reddit_bullish = 0
    reddit_bearish = 0
    if finbert_pipe is not None and reddit_posts:
        try:
            titles = [p.get("title", "") for p in reddit_posts if p.get("title")]
            if titles:
                results = finbert_pipe(titles, truncation=True, max_length=512)
                for res in results:
                    label = (res.get("label") or "").lower()
                    if "positive" in label or "bullish" in label:
                        reddit_bullish += 1
                    elif "negative" in label or "bearish" in label:
                        reddit_bearish += 1
        except Exception as exc:
            log.warning("FinBERT scoring failed: %s", exc)

    # Determine overall signal
    total_bullish = st_bullish + reddit_bullish
    total_bearish = st_bearish + reddit_bearish
    mention_count = reddit_mentions + len(st_messages)

    if mention_count == 0:
        overall_signal = "Mixed"
    elif total_bullish > total_bearish * 1.5:
        overall_signal = "Bullish"
    elif total_bearish > total_bullish * 1.5:
        overall_signal = "Bearish"
    else:
        overall_signal = "Mixed"

    return {
        "reddit_mentions": reddit_mentions,
        "reddit_avg_score": reddit_avg_score,
        "st_bullish": st_bullish,
        "st_bearish": st_bearish,
        "st_neutral": st_neutral,
        "overall_signal": overall_signal,
        "mention_count": mention_count,
        "available": mention_count > 0,
    }
