# jaja-money — Stock Analysis Dashboard

[![CI](https://github.com/pcjtse/jaja-money/actions/workflows/ci.yml/badge.svg)](https://github.com/pcjtse/jaja-money/actions/workflows/ci.yml)

> ⚠️ **Investment Disclaimer** — jaja-money is a research and educational tool only.
> **Nothing in this application constitutes financial, investment, or trading advice.**
> Always consult a qualified financial advisor before making any investment decisions.
> Past performance shown in backtests does not guarantee future results.

A Streamlit-based stock analysis dashboard powered by the **Finnhub API** and **Claude AI**.
Enter any ticker to get real-time quotes, interactive charts, technical indicators,
AI-driven fundamental analysis, FinBERT news sentiment, an 8-factor quantitative score,
and a comprehensive risk guardrail engine — all in a clean dark-theme UI.

---

## Screenshots

| Homepage | Stock Analysis |
|----------|----------------|
| ![Homepage](screenshots/01_homepage.png) | ![Analysis](screenshots/02_aapl_analysis.png) |

| Compare Stocks | Stock Screener |
|----------------|----------------|
| ![Compare](screenshots/03_compare.png) | ![Screener](screenshots/04_screener.png) |

| Portfolio Analysis | Sector Rotation |
|--------------------|-----------------|
| ![Portfolio](screenshots/05_portfolio.png) | ![Sectors](screenshots/06_sectors.png) |

| Strategy Backtesting | |
|----------------------|-|
| ![Backtest](screenshots/07_backtest.png) | |

---

## Analysis Workflow

```mermaid
flowchart TD
    A([🔍 Enter Ticker Symbol]) --> B

    subgraph FETCH ["📡 Data Collection"]
        B[Real-time Quote\nprice · change · volume]
        C[Company Fundamentals\nP/E · EPS · margins · growth]
        D[Price History\n2 years of daily OHLCV]
        E[Recent News\nlast 7 days of headlines]
        F[Earnings History\n4 quarters of EPS vs estimates]
        G[Analyst Recommendations\nbuy / hold / sell counts]
        H[Insider Activity\nrecent buy / sell transactions]
    end

    B --> I
    C --> I
    D --> I
    E --> I
    F --> I
    G --> I
    H --> I

    subgraph SCORE ["⚙️ Quantitative Scoring"]
        I{8-Factor\nEngine}
        I --> J1[Valuation\nP/E vs peers · 15%]
        I --> J2[Trend\nSMA-50 / SMA-200 · 20%]
        I --> J3[Momentum\nRSI-14 · 10%]
        I --> J4[MACD Signal\ndirection change · 10%]
        I --> J5[News Sentiment\nFinBERT score · 15%]
        I --> J6[Earnings Quality\nbeat consistency · 15%]
        I --> J7[Analyst Consensus\nrecommendation mix · 10%]
        I --> J8[52-Week Strength\nprice vs range · 5%]
        J1 & J2 & J3 & J4 & J5 & J6 & J7 & J8 --> K[Weighted\nComposite Score\n0 – 100]
    end

    subgraph RISK ["🛡️ Risk Assessment"]
        K --> L{4-Dimension\nRisk Engine}
        L --> M1[Volatility Risk\nhistorical vol · regime]
        L --> M2[Drawdown Risk\npeak-to-trough pullback]
        L --> M3[Overbought / Oversold\nRSI extremes]
        L --> M4[Trend Risk\nprice vs 200-day SMA]
        M1 & M2 & M3 & M4 --> N[Overall Risk Score\nLow → Extreme]
        N --> O{13 Red-Flag\nAlerts}
    end

    subgraph AI ["🤖 AI Narrative  ·  Claude"]
        K --> P[Investment Thesis\nbull case · growth · moat]
        K --> Q[Risk Analysis\nbear case · headwinds]
        K --> R[Valuation & Price Target\n12-month bull / base / bear]
        K --> S[Financial Health\nbalance sheet · cash flow]
        P & Q & R & S --> T[News Sentiment\nSynthesis]
    end

    subgraph VERDICT ["📊 Signal & Verdict"]
        K --> U{Score\nBand}
        U -->|80–100| V1[🟢 Strong Buy]
        U -->|60–80| V2[🟩 Buy]
        U -->|40–60| V3[⬜ Hold]
        U -->|20–40| V4[🟧 Sell]
        U -->|0–20| V5[🔴 Strong Sell]
    end

    N --> V1
    N --> V2
    N --> V3
    N --> V4
    N --> V5
    T --> W

    subgraph ACTIONS ["💡 Next Steps"]
        W[Interactive\nAI Chat]
        X[Save to\nWatchlist]
        Y[Set Price\nAlert]
        Z[Export\nReport]
        AA[Backtest\nStrategy]
    end

    V1 & V2 & V3 & V4 & V5 --> W
    V1 & V2 & V3 & V4 & V5 --> X
    V1 & V2 & V3 & V4 & V5 --> Y
    V1 & V2 & V3 & V4 & V5 --> Z
    V1 & V2 & V3 & V4 & V5 --> AA

    style FETCH fill:#1a2332,stroke:#2d4a6e,color:#a8c4e0
    style SCORE fill:#1a2a1a,stroke:#2d5a2d,color:#a8d4a8
    style RISK  fill:#2a1a1a,stroke:#5a2d2d,color:#d4a8a8
    style AI    fill:#1a1a2a,stroke:#2d2d5a,color:#a8a8d4
    style VERDICT fill:#1a2020,stroke:#2d5050,color:#a8d4d4
    style ACTIONS fill:#2a2a1a,stroke:#5a5a2d,color:#d4d4a8

    style A fill:#0066cc,stroke:#0044aa,color:#fff
```

---

## Key Features

### Market Data & Technicals
- **Real-time quotes** — price, change, day high/low, previous close
- **Company overview** — sector, market cap, P/E, EPS, dividend yield, 52-week range
- **Interactive price chart** — candlestick with SMA(50/200), Bollinger Bands, volume, OBV, VWAP
- **Technical indicators** — RSI(14), MACD, Fibonacci levels (computed locally)
- **Earnings history** — EPS vs estimate vs surprise for last 4 quarters
- **Analyst recommendations** — consensus bar chart and estimate revision momentum
- **Insider trading** — recent insider buy/sell activity
- **Options market data** — IV surface and hedge suggestions
- **Export** — CSV, HTML report, or PDF download

### Factor Score Engine
Eight factors scored 0–100 and weighted into a single composite signal (Strong Sell → Strong Buy),
displayed as a gauge, radar chart, and progress-bar breakdown:

| Factor | Weight |
|--------|--------|
| Valuation (P/E) | 15% |
| Trend (SMA-50/200) | 20% |
| Momentum (RSI-14) | 10% |
| MACD Signal | 10% |
| News Sentiment | 15% |
| Earnings Quality | 15% |
| Analyst Consensus | 10% |
| 52-Week Strength | 5% |

### Risk Guardrails
Four risk dimensions weighted into an overall **Risk Score** (Low → Extreme),
with 13 colour-coded red-flag alerts covering volatility, drawdown, overbought/oversold
RSI, downtrend conditions, high P/E, earnings miss rate, and negative analyst sentiment.

### AI Analysis (Claude Opus 4.6)
- **Fundamental analysis** — 8-section investment research report streamed live
- **News sentiment themes** — Claude synthesises bullish/bearish narratives from headlines
- **Price target** — AI-generated 12-month price target with bull/bear scenarios
- **Interactive chat** — Ask any question about the stock; Claude answers with full context
- **SEC EDGAR** — Fetch and analyse 10-K, 10-Q, and 8-K filings directly from EDGAR
- **Autonomous agent** — Multi-step research workflow with tool-call authority (up to 10 turns)

### Multi-Page App
| Page | Description |
|------|-------------|
| **Compare** | Side-by-side factor scores, risk, P/E, RSI for up to 5 stocks with correlation heatmap |
| **Screener** | Filter S&P 500 or custom universe by factor/risk/P/E/RSI; supports Claude natural-language queries |
| **Portfolio** | Correlation matrix, beta, Monte Carlo simulation, Kelly sizing, factor attribution |
| **Sectors** | Relative strength across 11 S&P 500 sector ETFs with rotation phase classification |
| **Backtest** | Historical signal simulation with equity curve, Sharpe ratio, max drawdown, and DRIP support |
| **Forward Test** | Paper portfolio tracker to validate AI signals without real capital |

### Additional Capabilities
- **Watchlist** — Save tickers with factor scores; persisted across sessions
- **Price & signal alerts** — Threshold alerts with Slack / Discord / Telegram webhook delivery
- **Daily digest** — Claude-written morning briefing for your entire watchlist (HTML + optional email)
- **Named snapshots** — Save and diff analysis states over time
- **Google Sheets export** — Write results to a Google Sheet via service account
- **Brokerage CSV import** — Auto-detect Schwab, Fidelity, and IBKR position exports
- **REST API** — FastAPI server for programmatic access (see [REST_API.md](REST_API.md))

---

## Prerequisites

- **Python 3.10+**
- A free [Finnhub](https://finnhub.io) API key
- An [Anthropic](https://console.anthropic.com) API key **or** the [Claude Code CLI](https://claude.ai/code)

> **Tip:** If you have Claude Code CLI installed (`claude` on your PATH), you can set
> `ai_backend: "cli"` in `config.yaml` and skip the `ANTHROPIC_API_KEY` entirely.

---

## Setup

1. **Clone and enter the repo:**
   ```bash
   cd jaja-money
   ```

2. **Create a virtual environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate        # macOS / Linux
   # venv\Scripts\activate          # Windows
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
   > The FinBERT model (~500 MB) downloads automatically on first run and is cached locally.

4. **Configure API keys:**
   ```bash
   cp .env.example .env
   ```
   Edit `.env`:
   ```
   FINNHUB_API_KEY=your_finnhub_key_here
   ANTHROPIC_API_KEY=your_anthropic_key_here
   ```

---

## Usage

```bash
streamlit run app.py
```

Open `http://localhost:8501`, enter a ticker (e.g. `AAPL`) in the sidebar, and click **Analyze**.
Use the sidebar navigation to switch between pages.

### Docker

```bash
# Quick start
cp .env.example .env   # add your keys
docker compose up --build

# With Redis cache
docker compose --profile redis up --build
```

Persistent data (history, watchlist, alerts, cache) is stored inside the container at
`~/.jaja-money/`. Mount a volume to keep it across restarts:
```bash
docker run -p 8501:8501 --env-file .env \
  -v "$HOME/.jaja-money:/root/.jaja-money" jaja-money
```

---

## ⚠️ API Usage Limits

**Set spending and rate limits before running bulk operations.**
The Screener and Sector pages can make hundreds of API calls in a single session.

### Anthropic (Claude) — Spend Limits

1. Go to [console.anthropic.com](https://console.anthropic.com) → **Settings → Billing**
2. Set a **monthly spend limit** (e.g. $10–20 for light use, $50+ for heavy screener workflows)
3. Optionally set a notification threshold to get an email before you reach your cap

Every "Analyze with Claude" call streams ~1 000–3 000 tokens. Claude responses are
disk-cached for 30 minutes, so re-running the same analysis is free — but new symbols always
hit the API.

### Finnhub — Rate Limits

The free plan allows **60 requests per minute**.
Approximate call counts per operation:

| Operation | API calls |
|-----------|-----------|
| Single stock analysis | ~12 |
| Compare (5 stocks) | ~25 |
| Sector Rotation (11 ETFs) | ~55 |
| Screener — S&P 500 (100 tickers) | ~400–500 |
| Screener — Russell 1000 (500 tickers) | ~2 000–2 500 |

Monitor usage at [finnhub.io/dashboard](https://finnhub.io/dashboard).
For the Screener, prefer the **Default** or **S&P 500** universe to stay within free-tier limits.
If you see `429 Too Many Requests`, wait 60 seconds before retrying.

---

## Webhook Notifications

Configure Slack, Discord, or Telegram alerts in `config.yaml`:

```yaml
webhooks:
  slack_url: "https://hooks.slack.com/services/..."
  discord_url: "https://discord.com/api/webhooks/..."
  telegram_token: "123456:ABC-..."
  telegram_chat_id: "-100123456789"
```

---

*For REST API documentation, see [REST_API.md](REST_API.md).*
