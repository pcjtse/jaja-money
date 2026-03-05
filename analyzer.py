import os
import anthropic
from dotenv import load_dotenv

load_dotenv()

_SYSTEM_PROMPT = """\
You are an expert equity research analyst with deep experience in fundamental \
analysis, financial statement interpretation, and investment research. \
Your job is to produce a clear, structured fundamental analysis report based \
on the data provided. Be analytical, balanced, and specific — cite the \
numbers you are given. Do not fabricate data. If a data point is missing or \
unavailable, acknowledge it rather than guessing.

Structure your report with these sections:
1. **Company Snapshot** — brief business description and sector context
2. **Valuation** — P/E, EPS, market cap; cheap/fair/expensive vs. sector norms
3. **Financial Health** — earnings trends, EPS surprises, dividend yield
4. **Technical Posture** — price vs. SMAs, RSI, MACD signal
5. **Analyst Sentiment** — consensus rating breakdown and what it implies
6. **Peer Context** — how the company compares within its peer group
7. **Key Risks & Catalysts** — top 2-3 bullish and bearish factors
8. **Investment Thesis** — concise buy / hold / sell assessment with rationale

Keep the tone professional and the report digestible for a sophisticated \
but non-specialist reader.\
"""


def build_data_prompt(
    symbol: str,
    quote: dict,
    profile: dict | None,
    financials: dict | None,
    technicals: dict,
    recommendations: list,
    earnings: list,
    peers: list,
    news: list,
) -> str:
    """Assemble all available market data into a structured prompt."""
    lines = [f"## Fundamental Analysis Request: {symbol}\n"]

    # --- Quote ---
    lines.append("### Real-Time Quote")
    lines.append(f"- Current Price: ${quote.get('c', 'N/A')}")
    lines.append(f"- Day Change: {quote.get('d', 'N/A')} ({quote.get('dp', 'N/A')}%)")
    lines.append(f"- Day High / Low: ${quote.get('h', 'N/A')} / ${quote.get('l', 'N/A')}")
    lines.append(f"- Previous Close: ${quote.get('pc', 'N/A')}\n")

    # --- Company Profile ---
    if profile:
        lines.append("### Company Profile")
        lines.append(f"- Name: {profile.get('name', 'N/A')}")
        lines.append(f"- Industry: {profile.get('finnhubIndustry', 'N/A')}")
        lines.append(f"- Country: {profile.get('country', 'N/A')}")
        lines.append(f"- Exchange: {profile.get('exchange', 'N/A')}\n")

    # --- Key Financials ---
    if financials:
        mc = financials.get("marketCapitalization")
        if mc is not None:
            mc_f = float(mc)
            if mc_f >= 1_000_000:
                mc_str = f"${mc_f / 1_000_000:.2f}T"
            elif mc_f >= 1_000:
                mc_str = f"${mc_f / 1_000:.2f}B"
            else:
                mc_str = f"${mc_f:.2f}M"
        else:
            mc_str = "N/A"

        pe = financials.get("peBasicExclExtraTTM")
        eps = financials.get("epsBasicExclExtraItemsTTM")
        div = financials.get("dividendYieldIndicatedAnnual")
        hi52 = financials.get("52WeekHigh")
        lo52 = financials.get("52WeekLow")

        lines.append("### Key Financials")
        lines.append(f"- Market Cap: {mc_str}")
        lines.append(f"- P/E Ratio (TTM): {pe if pe is not None else 'N/A'}")
        lines.append(f"- EPS (TTM): {eps if eps is not None else 'N/A'}")
        lines.append(f"- Dividend Yield: {div if div is not None else 'N/A'}%")
        lines.append(f"- 52-Week Range: ${lo52} – ${hi52}\n")

    # --- Technical Indicators ---
    lines.append("### Technical Indicators")
    lines.append(f"- SMA(50): {technicals.get('sma50', 'N/A')}")
    lines.append(f"- SMA(200): {technicals.get('sma200', 'N/A')}")
    lines.append(f"- RSI(14): {technicals.get('rsi', 'N/A')}")
    lines.append(f"- MACD: {technicals.get('macd', 'N/A')}")
    lines.append(f"- MACD Signal: {technicals.get('macd_signal', 'N/A')}")
    lines.append(f"- MACD Histogram: {technicals.get('macd_hist', 'N/A')}\n")

    # --- Analyst Recommendations ---
    if recommendations:
        r = recommendations[0]
        lines.append("### Analyst Recommendations (Most Recent Period)")
        lines.append(f"- Period: {r.get('period', 'N/A')}")
        lines.append(f"- Strong Buy: {r.get('strongBuy', 0)}")
        lines.append(f"- Buy: {r.get('buy', 0)}")
        lines.append(f"- Hold: {r.get('hold', 0)}")
        lines.append(f"- Sell: {r.get('sell', 0)}")
        lines.append(f"- Strong Sell: {r.get('strongSell', 0)}\n")

    # --- Earnings History ---
    if earnings:
        lines.append("### Earnings History (EPS Surprises)")
        for e in earnings:
            actual = e.get("actual")
            estimate = e.get("estimate")
            surprise = e.get("surprisePercent")
            period = e.get("period", "N/A")
            lines.append(
                f"- {period}: Actual={actual}, Estimate={estimate}, "
                f"Surprise={surprise}%"
            )
        lines.append("")

    # --- Peers ---
    if peers:
        peer_list = [p for p in peers if p != symbol]
        lines.append(f"### Peer Companies\n- {', '.join(peer_list)}\n")

    # --- Recent News Headlines ---
    if news:
        lines.append("### Recent News Headlines (last 7 days)")
        for article in news[:5]:
            headline = article.get("headline", "")
            source = article.get("source", "")
            if headline:
                lines.append(f"- [{source}] {headline}")
        lines.append("")

    return "\n".join(lines)


def stream_fundamental_analysis(prompt: str):
    """
    Stream a fundamental analysis from Claude Opus 4.6 with adaptive thinking.
    Yields text chunks as they arrive.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key or api_key == "your_anthropic_api_key_here":
        raise ValueError(
            "ANTHROPIC_API_KEY not set. "
            "Add your Anthropic API key to .env."
        )

    client = anthropic.Anthropic(api_key=api_key)

    with client.messages.stream(
        model="claude-opus-4-6",
        max_tokens=4096,
        thinking={"type": "adaptive"},
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for event in stream:
            if (
                event.type == "content_block_delta"
                and event.delta.type == "text_delta"
            ):
                yield event.delta.text


_SENTIMENT_THEMES_SYSTEM = """\
You are a financial news analyst. Your task is to synthesise a batch of \
news articles and their machine-learning sentiment scores into a concise \
thematic briefing for investors.

Structure your response with:
1. **Overall Sentiment Signal** — restate the aggregate (Bullish / Bearish / \
Mixed) and explain what is driving it
2. **Key Bullish Themes** — bullet the main positive narratives (2-4 points)
3. **Key Bearish / Risk Themes** — bullet the main negative narratives \
(2-4 points)
4. **Neutral / Background Noise** — brief note on articles that are \
informational but not price-moving
5. **Investor Takeaway** — one paragraph: what should investors watch for \
in the near term based on this news flow?

Be specific — reference actual headlines where relevant. Be concise.\
"""


def stream_sentiment_themes(
    symbol: str,
    articles: list,
    scores: list,
    aggregate: dict,
) -> object:
    """Stream a Claude sentiment-themes briefing.

    Yields text chunks.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key or api_key == "your_anthropic_api_key_here":
        raise ValueError(
            "ANTHROPIC_API_KEY not set. "
            "Add your Anthropic API key to .env."
        )

    # Build the user message
    lines = [
        f"## News Sentiment Briefing: {symbol}\n",
        f"**Aggregate signal:** {aggregate['signal']} "
        f"(net score: {aggregate['net_score']:+.2f}, "
        f"positive: {aggregate['counts']['positive']}, "
        f"negative: {aggregate['counts']['negative']}, "
        f"neutral: {aggregate['counts']['neutral']})\n",
        "### Scored Articles\n",
    ]

    for article, score in zip(articles, scores):
        headline = article.get("headline", "")
        source = article.get("source", "")
        label = score.get("label", "neutral").upper()
        conf = score.get("score", 0.0)
        if headline:
            lines.append(
                f"- **[{label} {conf:.0%}]** [{source}] {headline}"
            )

    prompt = "\n".join(lines)

    client = anthropic.Anthropic(api_key=api_key)

    with client.messages.stream(
        model="claude-opus-4-6",
        max_tokens=1024,
        system=_SENTIMENT_THEMES_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for event in stream:
            if (
                event.type == "content_block_delta"
                and event.delta.type == "text_delta"
            ):
                yield event.delta.text
