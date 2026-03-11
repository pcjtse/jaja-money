"""Claude-powered analysis functions.

Enhanced with:
- Earnings call transcript analysis (P2.3)
- AI natural language screener parsing (P3.1)
- Interactive stock Q&A chat (P3.4)
- Structured logging (P4.3)
- Claude response caching (P9.1)
- Adaptive system prompts by stock type (P9.2)
- Backtest narrative (P9.3)
- Sector rotation narrative (P9.4)
- Chat history trimming (P9.5)
"""
from __future__ import annotations

import hashlib
import os
from typing import Generator
import anthropic
from dotenv import load_dotenv

from cache import get_cache
from log_setup import get_logger

load_dotenv()

log = get_logger(__name__)
_disk_cache = get_cache()

# ---------------------------------------------------------------------------
# P9.1: Claude response caching helpers
# ---------------------------------------------------------------------------

_CLAUDE_CACHE_TTL = 1800  # 30 minutes


def _compute_context_hash(context: str) -> str:
    """Compute a stable hash of the Claude input context."""
    return hashlib.sha256(context.encode("utf-8")).hexdigest()[:16]


def _get_cached_response(cache_key: str) -> str | None:
    """Return cached Claude text response or None."""
    result = _disk_cache.get(f"claude:{cache_key}")
    if result is not None:
        log.info("Claude cache hit for key=%s", cache_key[:12])
    return result


def _store_cached_response(cache_key: str, text: str) -> None:
    """Store Claude text response in disk cache."""
    _disk_cache.set(f"claude:{cache_key}", text, ttl=_CLAUDE_CACHE_TTL)
    log.info("Claude response cached for key=%s", cache_key[:12])


# ---------------------------------------------------------------------------
# P9.2: Adaptive system prompts — stock type classification
# ---------------------------------------------------------------------------

def classify_stock_type(
    sector: str | None,
    pe_ratio: float | None,
    div_yield: float | None,
    revenue_growth: float | None = None,
) -> str:
    """Classify stock type for adaptive prompt selection.

    Returns: 'Growth' | 'Value' | 'Dividend' | 'Cyclical' | 'Defensive'
    """
    sector_lower = (sector or "").lower()

    # Dividend income stocks
    if div_yield is not None and div_yield >= 3.0:
        return "Dividend"

    # Defensive sectors
    defensive_sectors = {"utilities", "consumer staples", "healthcare"}
    if any(d in sector_lower for d in defensive_sectors):
        return "Defensive"

    # Cyclical sectors
    cyclical_sectors = {"energy", "materials", "industrials", "consumer discretionary", "financials"}
    if any(c in sector_lower for c in cyclical_sectors):
        return "Cyclical"

    # Growth (high P/E or tech/biotech sectors)
    growth_sectors = {"technology", "software", "semiconductor", "biotech", "communication"}
    if any(g in sector_lower for g in growth_sectors):
        return "Growth"
    if pe_ratio is not None and pe_ratio > 30:
        return "Growth"

    # Value (low P/E, no strong sector signal)
    if pe_ratio is not None and pe_ratio < 15:
        return "Value"

    return "Value"  # default fallback


_STOCK_TYPE_SYSTEM_PROMPTS: dict[str, str] = {
    "Growth": """\
You are an expert growth equity analyst specializing in high-growth companies,
technology disruption, and innovation-driven investment theses. You evaluate
stocks through the lens of revenue growth rates, total addressable market,
competitive moats, and path to profitability.

Structure your report:
1. **Company Snapshot** — business model, growth vectors, and TAM
2. **Growth Metrics** — revenue growth, gross margin trajectory, unit economics
3. **Competitive Position** — moat, product differentiation, customer retention
4. **Valuation** — P/S, PEG ratio, price-to-FCF; is growth priced in?
5. **Technical Posture** — price vs. SMAs, RSI, MACD signal
6. **Key Risks & Catalysts** — top growth vs. deceleration risks
7. **Investment Thesis** — buy/hold/sell with growth-specific rationale

Be analytical, cite numbers, and don't fabricate data.\
""",
    "Value": """\
You are an expert value investor and equity analyst focused on identifying
undervalued companies with strong fundamentals, reasonable valuations, and
margin of safety.

Structure your report:
1. **Company Snapshot** — business description and value proposition
2. **Valuation** — P/E, P/B, EV/EBITDA; discount to intrinsic value estimate
3. **Financial Health** — earnings trends, FCF, debt levels, balance sheet
4. **Catalyst for Re-rating** — what would unlock value (buybacks, management, cycle)
5. **Technical Posture** — price vs. SMAs, RSI, MACD signal
6. **Key Risks** — value traps, structural decline risks
7. **Investment Thesis** — buy/hold/sell with margin of safety rationale

Be specific, cite numbers, and maintain a contrarian but disciplined lens.\
""",
    "Dividend": """\
You are an expert income equity analyst specializing in dividend-paying stocks,
yield sustainability, and income generation strategies for conservative investors.

Structure your report:
1. **Company Snapshot** — business model and dividend history
2. **Income Analysis** — yield, payout ratio, dividend growth rate, coverage ratio
3. **Financial Sustainability** — FCF vs. dividend, debt levels, earnings stability
4. **Dividend Safety** — probability of dividend cut/raise; key triggers to watch
5. **Technical Posture** — price vs. SMAs, RSI, MACD signal
6. **Risk Factors** — interest rate sensitivity, sector-specific income risks
7. **Investment Thesis** — income-focused buy/hold/sell recommendation

Prioritize dividend sustainability over price appreciation. Cite actual numbers.\
""",
    "Cyclical": """\
You are an expert cyclical equity analyst specializing in economically sensitive
sectors including energy, materials, industrials, and consumer discretionary.

Structure your report:
1. **Company Snapshot** — business model and cycle sensitivity
2. **Cycle Positioning** — where are we in the industry/economic cycle?
3. **Commodity/Macro Drivers** — key inputs/outputs and their current trend
4. **Valuation** — cycle-adjusted P/E, EV/EBITDA vs. trough vs. peak
5. **Technical Posture** — price vs. SMAs, RSI, MACD signal
6. **Key Risks & Catalysts** — cycle turn signals, supply/demand dynamics
7. **Investment Thesis** — cycle-aware buy/hold/sell recommendation

Account for where we are in the cycle. Cite actual numbers.\
""",
    "Defensive": """\
You are an expert defensive equity analyst specializing in utilities, healthcare,
and consumer staples — companies known for earnings stability and recession resilience.

Structure your report:
1. **Company Snapshot** — business model and defensive characteristics
2. **Earnings Stability** — revenue predictability, regulated vs. unregulated
3. **Valuation vs. Safety Premium** — is the defensive premium justified?
4. **Financial Health** — debt, FCF, regulatory environment
5. **Technical Posture** — price vs. SMAs, RSI, MACD signal
6. **Key Risks** — regulatory changes, disruption risk, rising rate sensitivity
7. **Investment Thesis** — buy/hold/sell for defensive allocation

Balance income safety vs. growth potential. Cite actual numbers.\
""",
}

# Fallback to original system prompt
_DEFAULT_SYSTEM_PROMPT = """\
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

def _get_client() -> anthropic.Anthropic:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key or api_key == "your_anthropic_api_key_here":
        raise ValueError(
            "ANTHROPIC_API_KEY not set. "
            "Add your Anthropic API key to .env."
        )
    return anthropic.Anthropic(api_key=api_key)


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
    lines.append(f"- MACD Histogram: {technicals.get('macd_hist', 'N/A')}")
    if technicals.get("bb_upper"):
        lines.append(f"- Bollinger Upper: {technicals.get('bb_upper', 'N/A')}")
        lines.append(f"- Bollinger Lower: {technicals.get('bb_lower', 'N/A')}")
        lines.append(f"- BB %B: {technicals.get('bb_pct_b', 'N/A')}")
    lines.append("")

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


def stream_fundamental_analysis(
    prompt: str,
    stock_type: str | None = None,
    use_cache: bool = True,
):
    """Stream a fundamental analysis from Claude Opus 4.6 with adaptive thinking.

    Parameters
    ----------
    prompt     : The assembled data prompt
    stock_type : Optional stock type for adaptive system prompt selection
    use_cache  : If True, return cached response if available (P9.1)
    """
    system = _STOCK_TYPE_SYSTEM_PROMPTS.get(stock_type or "", _DEFAULT_SYSTEM_PROMPT)
    client = _get_client()

    # P9.1: Check cache
    if use_cache:
        cache_key = _compute_context_hash(system + prompt)
        cached = _get_cached_response(cache_key)
        if cached:
            yield cached
            return

    log.info("Starting fundamental analysis stream (stock_type=%s)", stock_type)
    full_text = ""
    with client.messages.stream(
        model="claude-opus-4-6",
        max_tokens=4096,
        thinking={"type": "adaptive"},
        system=system,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for event in stream:
            if (
                event.type == "content_block_delta"
                and event.delta.type == "text_delta"
            ):
                full_text += event.delta.text
                yield event.delta.text

    # P9.1: Cache the full response
    if use_cache and full_text:
        cache_key = _compute_context_hash(system + prompt)
        _store_cached_response(cache_key, full_text)


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
):
    """Stream a Claude sentiment-themes briefing. Yields text chunks."""
    client = _get_client()

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
            lines.append(f"- **[{label} {conf:.0%}]** [{source}] {headline}")

    prompt = "\n".join(lines)
    log.info("Starting sentiment themes stream for %s", symbol)

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


_PORTFOLIO_MEMO_SYSTEM = """\
You are a senior portfolio manager writing a concise investment memo for a
private client. You have been given quantitative analysis outputs — a factor
score, a risk score, and a rule-based position suggestion — alongside the
client's stated risk tolerance and investment horizon.

Write a portfolio construction memo with the following sections:

1. **Investment Stance** — one sentence summary of the recommended action and why
2. **Position Construction** — how to build the position (size, tranches, timing),
   referencing the client's risk profile and horizon
3. **Risk Management** — stop-loss rationale, what would invalidate the thesis,
   and specific conditions to monitor
4. **Upside Scenario** — what has to go right to hit the price targets; key catalysts
5. **Downside Scenario** — what could go wrong; asymmetric risks specific to this stock
6. **Portfolio Fit** — one paragraph on how this position fits within a diversified
   portfolio given the client's stated risk tolerance

Be specific — reference actual numbers (factor score, risk score, position %, stop %,
targets). Be direct and avoid boilerplate. Write for a sophisticated investor.\
"""


def stream_portfolio_memo(
    symbol: str,
    suggestion: dict,
    factors: list,
    risk: dict,
    profile: dict | None,
    risk_tolerance: str,
    horizon: str,
):
    """Stream a Claude portfolio construction memo. Yields text chunks."""
    client = _get_client()

    name = (profile or {}).get("name", symbol)
    sector = (profile or {}).get("finnhubIndustry", "Unknown sector")

    lines = [
        f"## Portfolio Memo Request: {symbol} ({name})",
        f"**Sector:** {sector}",
        f"**Client profile:** {risk_tolerance} risk tolerance, {horizon}\n",
        "### Quantitative Summary",
        f"- Composite factor score: "
        f"{int(sum(f['score'] * f['weight'] for f in factors) / sum(f['weight'] for f in factors)) if factors else 'N/A'}"
        f"/100 ({suggestion.get('action')} signal)",
        f"- Risk score: {risk.get('risk_score')}/100 ({risk.get('risk_level')})",
        (f"- Annualised volatility (20d): {risk['hv']:.1f}%"
         if risk.get("hv") is not None else "- Annualised volatility: N/A"),
        (f"- Drawdown from 52-wk high: {risk['drawdown_pct']:.1f}%"
         if risk.get("drawdown_pct") is not None else "- Drawdown: N/A"),
        "",
        "### Rule-Based Suggestion",
        f"- Action: {suggestion.get('action')}",
        f"- Suggested allocation: {suggestion.get('position_label')} of portfolio",
        f"- Entry strategy: {suggestion.get('entry_strategy')}",
    ]
    if suggestion.get("stop_price"):
        lines.append(
            f"- Stop-loss: ${suggestion['stop_price']} "
            f"({suggestion.get('stop_pct')}% below entry)"
        )
    if suggestion.get("target_1"):
        lines.append(f"- Target 1: ${suggestion['target_1']}")
    if suggestion.get("target_2"):
        lines.append(f"- Target 2: ${suggestion['target_2']}")
    if suggestion.get("risk_reward"):
        lines.append(f"- Risk/reward (to T1): {suggestion['risk_reward']}×")

    lines += ["", "### Factor Breakdown"]
    for f in factors:
        lines.append(f"- {f['name']}: {f['score']}/100 — {f['label']} ({f['detail']})")

    lines += ["", "### Active Risk Flags"]
    flags = risk.get("flags", [])
    if flags:
        for fl in flags:
            lines.append(f"- [{fl['severity'].upper()}] {fl['title']}: {fl['message']}")
    else:
        lines.append("- No active risk flags")

    lines += ["", "### Rule-engine rationale"]
    for r in suggestion.get("rationale", []):
        lines.append(f"- {r}")

    log.info("Starting portfolio memo stream for %s", symbol)
    with client.messages.stream(
        model="claude-opus-4-6",
        max_tokens=1500,
        system=_PORTFOLIO_MEMO_SYSTEM,
        messages=[{"role": "user", "content": "\n".join(lines)}],
    ) as stream:
        for event in stream:
            if (
                event.type == "content_block_delta"
                and event.delta.type == "text_delta"
            ):
                yield event.delta.text


# ---------------------------------------------------------------------------
# P2.3: Earnings Call Transcript Analysis
# ---------------------------------------------------------------------------

_TRANSCRIPT_SYSTEM = """\
You are an expert financial analyst specializing in earnings call analysis.
Analyze the provided earnings call transcript and produce a structured briefing.

Structure your analysis with:
1. **Management Tone** — assess the overall tone: confident / cautious / defensive
2. **Key Guidance Points** — bullet 3-5 specific forward-looking statements with numbers
3. **Revenue & Earnings Commentary** — what management said about results vs. expectations
4. **Growth Drivers** — bullish factors management highlighted (products, markets, etc.)
5. **Risk Acknowledgements** — headwinds, challenges, or uncertainties they mentioned
6. **Q&A Insights** — notable analyst questions and management responses
7. **Investor Takeaway** — one paragraph: what does this call signal for the next quarter?

Be specific — quote actual phrases from management where impactful. Flag any hedging
language, unusual caution, or notable confidence. Write for a sophisticated investor.\
"""


def stream_transcript_analysis(symbol: str, transcript_text: str):
    """Stream an earnings call transcript analysis. Yields text chunks."""
    client = _get_client()

    prompt = f"""## Earnings Call Transcript Analysis: {symbol}

{transcript_text[:8000]}  <!-- truncated to fit context if needed -->
"""
    log.info("Starting transcript analysis stream for %s", symbol)
    with client.messages.stream(
        model="claude-opus-4-6",
        max_tokens=2000,
        system=_TRANSCRIPT_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for event in stream:
            if (
                event.type == "content_block_delta"
                and event.delta.type == "text_delta"
            ):
                yield event.delta.text


# ---------------------------------------------------------------------------
# P2.3 extension: Forward-looking statement extraction
# ---------------------------------------------------------------------------

_FORWARD_LOOKING_SYSTEM = """\
You are a financial analyst specializing in extracting and evaluating \
forward-looking statements from corporate earnings calls.

Your tasks:
1. **Forward-Looking Statements** — extract explicit guidance, forecasts, \
   projections, and expectations management mentioned (quote exact phrases)
2. **Cautionary Language** — flag hedging qualifiers: "may", "could", \
   "subject to", "if", "approximately", "expect", "anticipate", etc.
3. **Guidance Confidence** — rate each statement: Confident / Cautious / Hedged
4. **Risks Flagged by Management** — specific risks they acknowledged
5. **Unspoken Concerns** — what management seemed reluctant to address or omitted

Format as structured markdown with clear headings. Be concise and specific.\
"""


def stream_forward_looking_analysis(symbol: str, transcript_text: str):
    """Stream a forward-looking statement extraction analysis. Yields text chunks."""
    client = _get_client()

    prompt = f"""## Forward-Looking Statement Analysis: {symbol}

Analyze the following earnings call transcript excerpt and extract all \
forward-looking statements, guidance, and cautionary language:

{transcript_text[:6000]}
"""
    log.info("Starting forward-looking analysis stream for %s", symbol)
    with client.messages.stream(
        model="claude-opus-4-6",
        max_tokens=1500,
        system=_FORWARD_LOOKING_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for event in stream:
            if (
                event.type == "content_block_delta"
                and event.delta.type == "text_delta"
            ):
                yield event.delta.text


# ---------------------------------------------------------------------------
# P3.1: AI Natural Language Screener
# ---------------------------------------------------------------------------

_NL_SCREENER_SYSTEM = """\
You are a quantitative stock analyst. The user will describe a stock screening
criteria in natural language. Your job is to:
1. Parse the intent into structured filter criteria
2. Map each criterion to one of these measurable dimensions:
   - factor_score (0-100): composite quantitative score
   - risk_score (0-100): risk level
   - pe_ratio: price/earnings
   - rsi: RSI(14) value
   - market_cap_b: market cap in billions
   - sentiment: "positive" | "negative" | "neutral"
   - trend: "uptrend" | "downtrend" | "sideways"
3. Output ONLY valid JSON in this format (no extra text):
{
  "filters": [
    {"dimension": "factor_score", "operator": ">", "value": 65, "label": "Strong factor score"},
    ...
  ],
  "description": "One sentence description of what the screen is looking for"
}

Operators: ">", "<", ">=", "<=", "==", "in" (value is then a list).
If a criterion can't be mapped, skip it.
"""


def parse_nl_screen(query: str) -> dict:
    """Parse a natural language screening query into structured filters.

    Returns dict with 'filters' list and 'description' string.
    Raises ValueError if Claude can't be reached.
    """
    import json as _json
    client = _get_client()

    log.info("Parsing NL screen query: %s", query[:100])
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=512,
        system=_NL_SCREENER_SYSTEM,
        messages=[{"role": "user", "content": query}],
    )
    text = response.content[0].text.strip()

    # Extract JSON from the response
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        return {"filters": [], "description": query}

    try:
        return _json.loads(text[start:end])
    except _json.JSONDecodeError:
        return {"filters": [], "description": query}


def stream_screener_summary(results: list[dict], query: str):
    """Stream a Claude narrative explaining the top screener results."""
    client = _get_client()

    rows = "\n".join(
        f"- {r['symbol']}: factor={r.get('factor_score','?')}/100, "
        f"risk={r.get('risk_score','?')}/100, "
        f"price=${r.get('price','?')}, sector={r.get('sector','?')}"
        for r in results[:10]
    )

    prompt = f"""## Stock Screener Results

**Query:** {query}

**Top Matches:**
{rows}

Briefly explain why these stocks match the criteria and highlight 2-3 of the most
compelling candidates with specific reasons. Be concise and actionable."""

    log.info("Streaming screener summary for query: %s", query[:60])
    with client.messages.stream(
        model="claude-opus-4-6",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for event in stream:
            if (
                event.type == "content_block_delta"
                and event.delta.type == "text_delta"
            ):
                yield event.delta.text


# ---------------------------------------------------------------------------
# P3.4: Interactive AI Chat for Stock Q&A
# ---------------------------------------------------------------------------

_CHAT_SYSTEM_TEMPLATE = """\
You are a knowledgeable stock analyst assistant for {symbol} ({name}).
You have access to the following current analysis data for this stock:

{data_context}

Answer the user's questions about this stock concisely and accurately.
Reference the specific data above when relevant. If asked about something
outside the provided data, acknowledge the limitation honestly.
Do not make up data points. Keep responses focused and actionable.\
"""


def build_chat_system_prompt(
    symbol: str,
    profile: dict | None,
    quote: dict,
    financials: dict | None,
    factors: list,
    risk: dict,
    composite_score: int,
    composite_label: str,
) -> str:
    """Build the system prompt for the chat interface."""
    name = (profile or {}).get("name", symbol)
    sector = (profile or {}).get("finnhubIndustry", "N/A")
    price = quote.get("c", 0)
    change_pct = quote.get("dp", 0)

    pe = (financials or {}).get("peBasicExclExtraTTM")
    mc = (financials or {}).get("marketCapitalization")
    mc_str = f"${float(mc)/1000:.1f}B" if mc and float(mc) < 1_000_000 else \
             f"${float(mc)/1_000_000:.1f}T" if mc else "N/A"

    factor_lines = "\n".join(
        f"  - {f['name']}: {f['score']}/100 ({f['label']})"
        for f in factors
    )
    flag_lines = "\n".join(
        f"  - [{fl['severity'].upper()}] {fl['title']}"
        for fl in risk.get("flags", [])
    ) or "  - None"

    data_context = f"""
**Company:** {name} ({symbol}) | Sector: {sector}
**Price:** ${price:,.2f} ({change_pct:+.2f}% today)
**Market Cap:** {mc_str} | P/E: {f"{pe:.1f}x" if pe else "N/A"}
**Composite Factor Score:** {composite_score}/100 — {composite_label}
**Risk Score:** {risk.get('risk_score')}/100 — {risk.get('risk_level')}
**Factor Breakdown:**
{factor_lines}
**Active Risk Flags:**
{flag_lines}"""

    return _CHAT_SYSTEM_TEMPLATE.format(
        symbol=symbol, name=name, data_context=data_context
    )


def stream_chat_response(
    system_prompt: str,
    conversation_history: list[dict],
    user_message: str,
):
    """Stream a chat response. Yields text chunks.

    conversation_history: list of {"role": "user"|"assistant", "content": str}
    """
    client = _get_client()

    messages = conversation_history + [{"role": "user", "content": user_message}]

    log.info("Chat response stream (turns=%d)", len(messages))
    with client.messages.stream(
        model="claude-opus-4-6",
        max_tokens=1024,
        system=system_prompt,
        messages=messages,
    ) as stream:
        for event in stream:
            if (
                event.type == "content_block_delta"
                and event.delta.type == "text_delta"
            ):
                yield event.delta.text


# ---------------------------------------------------------------------------
# P9.3: Claude Backtest Narrative
# ---------------------------------------------------------------------------

_BACKTEST_NARRATIVE_SYSTEM = """\
You are a quantitative analyst reviewing backtesting results for a trading strategy.
Analyze the provided backtest metrics and provide an honest, nuanced assessment.

Cover:
1. **Performance Assessment** — is the strategy adding value over buy-and-hold?
2. **Risk-Adjusted Returns** — Sharpe ratio interpretation, drawdown risk
3. **Strategy Robustness** — could this be genuine alpha or overfitting/luck?
4. **Regime Analysis** — what market environments might this strategy favor or suffer in?
5. **Weaknesses & Limitations** — look-ahead bias risks, transaction costs, sample size
6. **Actionable Improvements** — 2-3 concrete suggestions to improve the signal

Be honest about limitations. Reference actual numbers. Write for a sophisticated investor.\
"""


def stream_backtest_narrative(result, use_cache: bool = True):
    """Stream a Claude backtest analysis. Yields text chunks.

    Parameters
    ----------
    result : BacktestResult dataclass
    use_cache : Cache the response (P9.1)
    """
    client = _get_client()

    prompt = f"""## Backtest Analysis: {result.symbol}

**Strategy:** Price-based factor signal (SMA trend 40% + RSI 30% + MACD 30%)
**Entry threshold:** {result.entry_threshold} | **Exit threshold:** {result.exit_threshold}
**Period:** {result.start_date} to {result.end_date}
**In-sample:** {result.is_insample}

**Performance Results:**
- Gross return: {result.gross_return_pct:+.1f}%
- Net return (after costs): {result.total_return_pct:+.1f}%
- Total transaction costs: {result.total_cost_pct:.2f}%
- Buy-and-hold return: {result.benchmark_return_pct:+.1f}%
- Alpha vs. buy-and-hold: {result.total_return_pct - result.benchmark_return_pct:+.1f}%
- CAGR: {result.cagr_pct:+.1f}%
- Sharpe ratio: {result.sharpe_ratio}
- Max drawdown: {result.max_drawdown_pct:.1f}%
- Win rate: {result.win_rate_pct:.1f}% ({result.total_trades} trades)

Analyze this strategy comprehensively."""

    if use_cache:
        cache_key = _compute_context_hash(prompt)
        cached = _get_cached_response(cache_key)
        if cached:
            yield cached
            return

    log.info("Starting backtest narrative stream for %s", result.symbol)
    full_text = ""
    with client.messages.stream(
        model="claude-opus-4-6",
        max_tokens=1200,
        system=_BACKTEST_NARRATIVE_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for event in stream:
            if (event.type == "content_block_delta" and
                    event.delta.type == "text_delta"):
                full_text += event.delta.text
                yield event.delta.text

    if use_cache and full_text:
        _store_cached_response(_compute_context_hash(prompt), full_text)


# ---------------------------------------------------------------------------
# P9.4: Claude Sector Rotation Narrative
# ---------------------------------------------------------------------------

_SECTOR_ROTATION_SYSTEM = """\
You are a macro equity strategist specializing in sector rotation analysis.
Analyze the provided sector momentum data and provide a market-cycle interpretation.

Structure your analysis:
1. **Leading Sectors** — what's driving them and the macro narrative
2. **Lagging Sectors** — key headwinds and potential turning points
3. **Rotation Signals** — notable rotation patterns (defensive/cyclical, value/growth)
4. **Macro Cycle Interpretation** — where are we in the economic cycle?
5. **Tactical Positioning** — 2-3 actionable sector allocation ideas

Be specific and data-driven. Reference actual performance numbers from the data.\
"""


def stream_sector_rotation_narrative(sector_data: list[dict], use_cache: bool = True):
    """Stream a Claude sector rotation analysis. Yields text chunks."""
    client = _get_client()

    sector_summary = "\n".join(
        f"- {d['ticker']} ({d['name']}): score={d.get('score', 'N/A')}, "
        f"phase={d.get('phase', 'N/A')}, "
        f"1M={d['perf_1m']:+.1f}%, 3M={d['perf_3m']:+.1f}%, RSI={d.get('rsi', 'N/A')}"
        if d.get('perf_1m') is not None and d.get('perf_3m') is not None
        else f"- {d['ticker']} ({d['name']}): data unavailable"
        for d in sector_data
    )

    prompt = f"""## Sector Rotation Analysis

**Current Sector Momentum Scores (sorted by score):**
{sector_summary}

Provide a comprehensive sector rotation analysis with actionable insights."""

    if use_cache:
        cache_key = _compute_context_hash(prompt)
        cached = _get_cached_response(cache_key)
        if cached:
            yield cached
            return

    log.info("Starting sector rotation narrative stream")
    full_text = ""
    with client.messages.stream(
        model="claude-opus-4-6",
        max_tokens=1200,
        system=_SECTOR_ROTATION_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for event in stream:
            if (event.type == "content_block_delta" and
                    event.delta.type == "text_delta"):
                full_text += event.delta.text
                yield event.delta.text

    if use_cache and full_text:
        _store_cached_response(_compute_context_hash(prompt), full_text)


# ---------------------------------------------------------------------------
# P9.5: Chat history trimming
# ---------------------------------------------------------------------------

_CONTEXT_BUDGET_TOKENS = 180_000  # Claude Opus 4.6 context window
_CHAT_BUDGET_RATIO = 0.80  # trim when history exceeds 80%


def _estimate_tokens(text: str) -> int:
    """Rough token count estimate: words × 1.3."""
    return int(len(text.split()) * 1.3)


def trim_chat_history(
    system_prompt: str,
    conversation_history: list[dict],
    max_budget_tokens: int = _CONTEXT_BUDGET_TOKENS,
    budget_ratio: float = _CHAT_BUDGET_RATIO,
) -> tuple[list[dict], bool]:
    """Trim chat history to fit within context budget.

    Keeps system prompt + most recent exchanges.
    Returns (trimmed_history, was_trimmed).
    """
    system_tokens = _estimate_tokens(system_prompt)
    budget = int(max_budget_tokens * budget_ratio) - system_tokens

    total_tokens = sum(
        _estimate_tokens(m.get("content", "")) for m in conversation_history
    )

    if total_tokens <= budget:
        return conversation_history, False

    # Drop oldest turns (preserve pairs: user+assistant) from front
    trimmed = list(conversation_history)
    while trimmed and _estimate_tokens(
        " ".join(m.get("content", "") for m in trimmed)
    ) > budget:
        # Drop oldest user+assistant pair
        if len(trimmed) >= 2:
            trimmed = trimmed[2:]
        else:
            trimmed = trimmed[1:]

    log.info(
        "Chat history trimmed: %d → %d messages (est. tokens: %d → %d)",
        len(conversation_history), len(trimmed),
        total_tokens, _estimate_tokens(" ".join(m.get("content", "") for m in trimmed)),
    )
    return trimmed, True


# ---------------------------------------------------------------------------
# P11.4: Peer Group Narrative
# ---------------------------------------------------------------------------


def stream_peer_comparison_narrative(
    symbol: str, peer_data: dict, use_cache: bool = True
) -> "Generator[str, None, None]":
    """Stream Claude commentary on peer group comparison.

    Parameters
    ----------
    symbol : target ticker
    peer_data : dict from comparison.fetch_peer_metrics
    use_cache : whether to use/store cached response
    """

    percentiles = peer_data.get("percentile_ranks", {})
    target_metrics = peer_data.get("target_metrics", {})
    peer_tickers = peer_data.get("peer_tickers", [])

    context = f"""Stock: {symbol}
Peer group: {', '.join(peer_tickers) if peer_tickers else 'N/A'}

Target metrics:
- P/E Ratio: {target_metrics.get('pe', 'N/A')}
- ROE: {target_metrics.get('roe', 'N/A')}%
- Revenue Growth (YoY): {target_metrics.get('revenue_growth', 'N/A')}%
- Gross Margin: {target_metrics.get('gross_margin', 'N/A')}%

Percentile ranks vs. peers (0 = lowest, 100 = highest):
- P/E: {percentiles.get('pe', 'N/A')}th percentile
- ROE: {percentiles.get('roe', 'N/A')}th percentile
- Revenue Growth: {percentiles.get('revenue_growth', 'N/A')}th percentile
- Gross Margin: {percentiles.get('gross_margin', 'N/A')}th percentile"""

    cache_key = _compute_context_hash(context)
    if use_cache:
        cached = _get_cached_response(f"peer_narrative:{cache_key}")
        if cached:
            yield cached
            return

    prompt = f"""You are an equity analyst providing a peer group benchmarking commentary.

{context}

Write a concise 3-4 sentence commentary comparing {symbol} to its sector peers. Highlight:
1. Where the stock trades at a premium or discount vs peers (valuation)
2. Where it leads or lags on quality metrics (ROE, margins)
3. The overall investment implication of its peer positioning

Example: "{symbol} trades at a premium to peers on valuation but leads on margin quality..."
Be specific and data-driven."""

    collected = []
    try:
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        with client.messages.stream(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                collected.append(text)
                yield text
    except Exception as exc:
        error_msg = f"\n*Peer narrative error: {exc}*"
        yield error_msg
        return

    if use_cache and collected:
        _store_cached_response(f"peer_narrative:{cache_key}", "".join(collected))


# ---------------------------------------------------------------------------
# P10.4: Earnings Prediction & Beat Probability
# ---------------------------------------------------------------------------


def compute_earnings_beat_stats(earnings_history: list[dict]) -> dict:
    """Compute earnings beat statistics from historical EPS surprises.

    Parameters
    ----------
    earnings_history : list of dicts from api.get_earnings()
                       Each dict has: actual, estimate, period, surprise, surprisePercent

    Returns
    -------
    dict with beat_rate, avg_surprise_pct, trend, last_8_quarters
    """
    if not earnings_history:
        return {}

    valid = [
        e for e in earnings_history
        if e.get("actual") is not None and e.get("estimate") is not None
    ]
    if not valid:
        return {}

    beats = sum(1 for e in valid if (e.get("actual") or 0) > (e.get("estimate") or 0))
    beat_rate = beats / len(valid) * 100

    surprise_pcts = [e.get("surprisePercent") or 0 for e in valid]
    avg_surprise = sum(surprise_pcts) / len(surprise_pcts) if surprise_pcts else 0

    # Trend: compare last 4 vs prior 4 beat rates
    trend = "flat"
    if len(valid) >= 8:
        recent_beats = sum(1 for e in valid[:4] if (e.get("actual") or 0) > (e.get("estimate") or 0))
        prior_beats = sum(1 for e in valid[4:8] if (e.get("actual") or 0) > (e.get("estimate") or 0))
        if recent_beats > prior_beats:
            trend = "improving"
        elif recent_beats < prior_beats:
            trend = "deteriorating"

    return {
        "beat_rate": round(beat_rate, 1),
        "avg_surprise_pct": round(avg_surprise, 2),
        "beats": beats,
        "total": len(valid),
        "trend": trend,
        "history": valid[:8],
    }


def stream_earnings_prediction(
    symbol: str, beat_stats: dict, next_earnings_date: str | None = None
) -> "Generator[str, None, None]":
    """Stream Claude qualitative earnings beat probability analysis."""

    if not beat_stats:
        yield "Insufficient earnings history for prediction."
        return

    context = f"""Stock: {symbol}
Historical earnings beat rate: {beat_stats.get('beat_rate', 'N/A')}% ({beat_stats.get('beats', 0)}/{beat_stats.get('total', 0)} quarters)
Average EPS surprise: {beat_stats.get('avg_surprise_pct', 'N/A')}%
Beat trend (last 4 vs prior 4): {beat_stats.get('trend', 'N/A')}
Next earnings date: {next_earnings_date or 'Unknown'}"""

    prompt = f"""{context}

Based on this earnings history, provide:
1. A qualitative beat probability assessment (Low / Moderate / High) with rationale
2. Key factors that could drive a beat or miss
3. What to watch for in the upcoming earnings report

Keep it concise (3-4 sentences). Be calibrated — don't guarantee outcomes."""

    try:
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        with client.messages.stream(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                yield text
    except Exception as exc:
        yield f"\n*Earnings prediction error: {exc}*"


# ---------------------------------------------------------------------------
# P15.2: AI Price Target — Bull / Base / Bear
# ---------------------------------------------------------------------------

_PRICE_TARGET_TTL = 86_400  # 24 hours


def stream_price_target(
    symbol: str,
    data_prompt: str,
    stock_type: str = "growth",
) -> "Generator[str, None, None]":
    """Stream a 12-month price target with Bull, Base, and Bear scenarios.

    Parameters
    ----------
    symbol : stock ticker symbol
    data_prompt : assembled financial data context (from build_data_prompt)
    stock_type : stock classification for context (e.g. "growth", "value")

    Yields text chunks from Claude in the structured price-target format.
    The output format is::

        BULL_TARGET: $XXX.XX | Key assumption: [one sentence]
        BASE_TARGET: $XXX.XX | Key assumption: [one sentence]
        BEAR_TARGET: $XXX.XX | Key assumption: [one sentence]
        RATIONALE: [2-3 sentences explaining the range]
    """
    cache_key = _compute_context_hash(data_prompt)
    cached = _disk_cache.get(f"price_target:{cache_key}")
    if cached is not None:
        log.info("Price target cache hit for %s", symbol)
        yield cached
        return

    prompt = f"""You are an equity research analyst providing a 12-month price target for {symbol}.

Stock type: {stock_type}

{data_prompt}

Based on the data above, provide a 12-month price target with three scenarios.
You MUST output EXACTLY this format (no other text before or after):

BULL_TARGET: $XXX.XX | Key assumption: [one sentence describing the key bull case driver]
BASE_TARGET: $XXX.XX | Key assumption: [one sentence describing the base case assumption]
BEAR_TARGET: $XXX.XX | Key assumption: [one sentence describing the key downside risk]
RATIONALE: [2-3 sentences explaining the spread between scenarios and the key factors driving the range]

Use the current price and financial metrics provided. Be specific with dollar values."""

    collected: list[str] = []
    try:
        client = _get_client()
        with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                collected.append(text)
                yield text
    except Exception as exc:
        log.warning("Price target stream error for %s: %s", symbol, exc)
        yield f"\n*Price target error: {exc}*"
        return

    if collected:
        full_text = "".join(collected)
        _disk_cache.set(f"price_target:{cache_key}", full_text, ttl=_PRICE_TARGET_TTL)
        log.info("Price target cached for %s (key=%s)", symbol, cache_key[:12])


def parse_price_targets(text: str, current_price: float) -> dict:
    """Parse the structured price target text from stream_price_target.

    Parameters
    ----------
    text : the full text output from stream_price_target
    current_price : current stock price for computing upside/downside %

    Returns
    -------
    dict with keys: bull, base, bear, rationale,
    bull_upside_pct, base_upside_pct, bear_downside_pct
    """
    import re

    result: dict = {
        "bull": None,
        "base": None,
        "bear": None,
        "rationale": "",
        "bull_upside_pct": None,
        "base_upside_pct": None,
        "bear_downside_pct": None,
    }

    def _parse_price(line: str) -> float | None:
        match = re.search(r"\$([0-9,]+(?:\.[0-9]{1,2})?)", line)
        if match:
            try:
                return float(match.group(1).replace(",", ""))
            except ValueError:
                pass
        return None

    for line in text.splitlines():
        line = line.strip()
        if line.upper().startswith("BULL_TARGET:"):
            result["bull"] = _parse_price(line)
        elif line.upper().startswith("BASE_TARGET:"):
            result["base"] = _parse_price(line)
        elif line.upper().startswith("BEAR_TARGET:"):
            result["bear"] = _parse_price(line)
        elif line.upper().startswith("RATIONALE:"):
            result["rationale"] = line[len("RATIONALE:"):].strip()

    # Compute percentage changes vs. current price
    if current_price and current_price > 0:
        if result["bull"] is not None:
            result["bull_upside_pct"] = round(
                (result["bull"] - current_price) / current_price * 100, 1
            )
        if result["base"] is not None:
            result["base_upside_pct"] = round(
                (result["base"] - current_price) / current_price * 100, 1
            )
        if result["bear"] is not None:
            result["bear_downside_pct"] = round(
                (result["bear"] - current_price) / current_price * 100, 1
            )

    return result


# ---------------------------------------------------------------------------
# P15.5: Transcript Q&A
# ---------------------------------------------------------------------------

_TRANSCRIPT_QA_TTL = 21_600  # 6 hours


def stream_transcript_qa(
    question: str,
    transcript_text: str,
    symbol: str,
) -> "Generator[str, None, None]":
    """Stream a Claude answer to a question about an earnings call transcript.

    Parameters
    ----------
    question : user's natural-language question about the transcript
    transcript_text : full or partial transcript text (truncated to 8000 chars)
    symbol : stock ticker for context

    Yields text chunks from Claude.
    """
    cache_key = _compute_context_hash(f"{symbol}:{question}:{transcript_text[:500]}")
    cached = _disk_cache.get(f"transcript_qa:{cache_key}")
    if cached is not None:
        log.info("Transcript Q&A cache hit for %s", symbol)
        yield cached
        return

    truncated = transcript_text[:8000]
    system_prompt = (
        f"You are a financial analyst assistant. You have been given an earnings call "
        f"transcript for {symbol}. Answer the user's question based only on the content "
        f"of the transcript. If the transcript does not contain sufficient information to "
        f"answer the question, say so clearly. Be concise and cite specific quotes or "
        f"sections where helpful."
    )

    user_message = f"""## Earnings Call Transcript — {symbol}

{truncated}

---

**Question:** {question}"""

    collected: list[str] = []
    try:
        client = _get_client()
        with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=600,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        ) as stream:
            for text in stream.text_stream:
                collected.append(text)
                yield text
    except Exception as exc:
        log.warning("Transcript Q&A stream error for %s: %s", symbol, exc)
        yield f"\n*Transcript Q&A error: {exc}*"
        return

    if collected:
        full_text = "".join(collected)
        _disk_cache.set(f"transcript_qa:{cache_key}", full_text, ttl=_TRANSCRIPT_QA_TTL)
        log.info("Transcript Q&A cached for %s (key=%s)", symbol, cache_key[:12])


# ---------------------------------------------------------------------------
# P19.2: Supply Chain Analysis via EDGAR
# ---------------------------------------------------------------------------

_SUPPLY_CHAIN_TTL = 604_800  # 7 days


def stream_supply_chain_analysis(
    symbol: str,
    filing_text: str,
) -> "Generator[str, None, None]":
    """Stream Claude supply chain analysis extracted from a 10-K filing.

    Parameters
    ----------
    symbol : stock ticker
    filing_text : text content of the 10-K filing (business/risk sections preferred)

    Yields structured bullet-point text from Claude covering suppliers, customers,
    geographic breakdown, and concentration risks.
    """
    cache_key = _compute_context_hash(f"supply_chain:{symbol}:{filing_text[:1000]}")
    cached = _disk_cache.get(f"supply_chain:{cache_key}")
    if cached is not None:
        log.info("Supply chain cache hit for %s", symbol)
        yield cached
        return

    prompt = f"""You are a supply chain analyst reviewing the 10-K filing for {symbol}.

**Filing Text (excerpts):**
{filing_text[:8000]}

Extract and organize the following supply chain information from this filing.
Output as structured bullet points under each heading:

## Key Suppliers
- [List the top 3-5 key suppliers or supplier categories mentioned. Include any named suppliers and their significance.]

## Key Customers
- [List the top 3-5 key customers or customer categories mentioned. Include any named customers and their revenue contribution if disclosed.]

## Geographic Revenue Breakdown
- [List geographic regions and their revenue contribution percentages if disclosed.]

## Concentration Risks
- [Identify any concentration risks: single-source suppliers, customer concentration, geographic exposure, etc.]

If a category is not mentioned in the filing, note "Not disclosed in filing."
Be specific and quote actual names, percentages, or descriptions from the text where available."""

    collected: list[str] = []
    try:
        client = _get_client()
        with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                collected.append(text)
                yield text
    except Exception as exc:
        log.warning("Supply chain stream error for %s: %s", symbol, exc)
        yield f"\n*Supply chain analysis error: {exc}*"
        return

    if collected:
        full_text = "".join(collected)
        _disk_cache.set(f"supply_chain:{cache_key}", full_text, ttl=_SUPPLY_CHAIN_TTL)
        log.info("Supply chain analysis cached for %s (key=%s)", symbol, cache_key[:12])


def extract_supply_chain_structured(supply_chain_text: str) -> dict:
    """Parse Claude's supply chain output into structured lists.

    Parameters
    ----------
    supply_chain_text : the full text output from stream_supply_chain_analysis

    Returns
    -------
    dict with keys: suppliers (list[str]), customers (list[str]),
    geographic_breakdown (list[str]), concentration_risks (list[str]),
    available (bool)
    """
    result: dict = {
        "suppliers": [],
        "customers": [],
        "geographic_breakdown": [],
        "concentration_risks": [],
        "available": False,
    }

    if not supply_chain_text or not supply_chain_text.strip():
        return result

    current_section: str | None = None
    section_map = {
        "supplier": "suppliers",
        "customer": "customers",
        "geographic": "geographic_breakdown",
        "concentration": "concentration_risks",
    }

    for line in supply_chain_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        lower = stripped.lower()
        # Detect section headers
        if lower.startswith("## ") or lower.startswith("# "):
            header = lower.lstrip("#").strip()
            current_section = None
            for keyword, key in section_map.items():
                if keyword in header:
                    current_section = key
                    break
            continue

        # Collect bullet points
        if current_section and (stripped.startswith("-") or stripped.startswith("*")):
            content = stripped.lstrip("-*").strip()
            if content and "not disclosed" not in content.lower():
                result[current_section].append(content)
                result["available"] = True

    return result


# ---------------------------------------------------------------------------
# P20.2: News Impact Scoring
# ---------------------------------------------------------------------------

_NEWS_IMPACT_TTL = 86_400  # 24 hours

_NEWS_IMPACT_WEIGHTS = {
    "High": 3,
    "Medium": 2,
    "Low": 1,
    "Negligible": 0.5,
}


def score_news_impact(headlines: list[str]) -> list[dict]:
    """Score a list of news headlines by their market impact level.

    Makes a single non-streaming Claude API call with up to 10 headlines and
    parses the response into structured impact ratings.

    Parameters
    ----------
    headlines : list of headline strings (max 10 used)

    Returns
    -------
    list of dicts with keys: headline (str), level (str), weight (float)
    where level is one of High / Medium / Low / Negligible.
    """
    if not headlines:
        return []

    capped = headlines[:10]
    cache_key = _compute_context_hash("|".join(capped))
    cached = _disk_cache.get(f"news_impact:{cache_key}")
    if cached is not None:
        log.info("News impact cache hit (key=%s)", cache_key[:12])
        return cached  # type: ignore[return-value]

    numbered = "\n".join(f"{i}: {h}" for i, h in enumerate(capped))
    prompt = f"""Rate the market impact of each headline below.
For each headline, output EXACTLY one line in this format:
{{index}}: {{level}}
where level is one of: High, Medium, Low, Negligible

Headlines:
{numbered}

Output only the rated lines, nothing else."""

    def _default_result() -> list[dict]:
        return [
            {
                "headline": h,
                "level": "Medium",
                "weight": _NEWS_IMPACT_WEIGHTS["Medium"],
            }
            for h in capped
        ]

    try:
        client = _get_client()
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
    except Exception as exc:
        log.warning("News impact scoring error: %s", exc)
        return _default_result()

    # Parse "index: level" lines
    import re as _re

    ratings: dict[int, str] = {}
    for line in raw.splitlines():
        line = line.strip()
        match = _re.match(r"^(\d+)\s*:\s*(High|Medium|Low|Negligible)", line, _re.IGNORECASE)
        if match:
            idx = int(match.group(1))
            level = match.group(2).capitalize()
            # Normalize "Negligible" capitalisation
            if level.lower() == "negligible":
                level = "Negligible"
            ratings[idx] = level

    results: list[dict] = []
    for i, headline in enumerate(capped):
        level = ratings.get(i, "Medium")
        if level not in _NEWS_IMPACT_WEIGHTS:
            level = "Medium"
        results.append(
            {
                "headline": headline,
                "level": level,
                "weight": _NEWS_IMPACT_WEIGHTS[level],
            }
        )

    _disk_cache.set(f"news_impact:{cache_key}", results, ttl=_NEWS_IMPACT_TTL)
    log.info("News impact scores cached for %d headlines (key=%s)", len(results), cache_key[:12])
    return results
