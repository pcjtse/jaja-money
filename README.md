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
flowchart LR
    %% Global Styles
    classDef start fill:#1e293b,stroke:#0f172a,color:#fff
    classDef finish fill:#059669,stroke:#065f46,color:#fff
    classDef step fill:#fff,stroke:#cbd5e1,color:#475569
    
    classDef buy fill:#dcfce7,stroke:#22c55e,color:#166534
    classDef hold fill:#f8fafc,stroke:#94a3b8,color:#475569
    classDef sell fill:#fee2e2,stroke:#ef4444,color:#991b1b

    START(["🔍 Enter Ticker"]):::start

    subgraph D [Data Collection]
        D1["Sources:
        • Quote & Price History
        • Fundamentals & Earnings
        • News & Analyst Ratings"]:::step
    end

    subgraph F [Factor Scoring]
        F1["8 Core Factors:
        Valuation, Trend, MACD,
        Momentum, Sentiment
        ---
        0 to 100 Score"]:::step
    end

    subgraph R [Risk Assessment]
        R1["Risk Metrics:
        Volatility & Drawdown
        RSI & 200-Day Trend
        ---
        13 Red-Flag Alerts"]:::step
    end

    subgraph AI [AI Analysis]
        AI1["Claude Synthesis:
        Bull/Bear Thesis
        Price Targets
        Sentiment Synthesis"]:::step
    end

    subgraph SIG [Investment Signal]
        direction TB
        S1["Strong Buy"]:::buy
        S2["Buy"]:::buy
        S3["Hold"]:::hold
        S4["Sell"]:::sell
        S5["Strong Sell"]:::sell
    end

    END(["💡 Watchlist & Backtests"]):::finish

    %% Connections
    START --> D
    D --> F
    F --> R
    F --> AI
    R --> SIG
    AI --> SIG
    SIG --> END

    %% Subgraph Styling
    style D fill:#f1f5f9,stroke:#cbd5e1,stroke-dasharray: 5 5
    style F fill:#f1f5f9,stroke:#cbd5e1,stroke-dasharray: 5 5
    style R fill:#fff1f2,stroke:#fecaca,stroke-dasharray: 5 5
    style AI fill:#f5f3ff,stroke:#ddd6fe,stroke-dasharray: 5 5
    style SIG fill:#f8fafc,stroke:#e2e8f0
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
- **OpenClaw integration** — Publish as a ClawHub skill, connect to a local or remote jaja-money server, and trigger analysis on market events (see below)

---

## OpenClaw Integration

jaja-money can be published to the [ClawHub](https://clawhub.io) skill marketplace and
wired into OpenClaw agent workflows. The skill can run **locally** (importing analysis
modules directly) or in **remote mode** — connecting to any running jaja-money server
over HTTP via `JAJA_API_URL`.

> **Note:** Real order execution has been removed. `broker.py` provides read-only Alpaca
> account/position monitoring and a **simulation-only** `execute_signal()` that returns
> what a trade *would* do without placing any real orders.

| Feature | Module / Endpoint |
|---------|-------------------|
| ClawHub skill package (local + remote) | `openclaw_skill.py` |
| Lightweight factor/risk scores | `POST /score` |
| Structured signal API | `POST /signals` |
| Active price alerts | `GET /alerts` |
| Incoming webhook receiver | `POST /openclaw/webhook` |
| Portfolio rebalancing | `POST /openclaw/rebalance` |
| Autonomous research agent | `POST /openclaw/agent` |
| Event-triggered analysis | `openclaw_events.py` |
| Skill manifest | `GET /openclaw/manifest` |
| Alpaca monitoring (read-only) | `broker.py` |

### 1. ClawHub Skill Package

`openclaw_skill.py` is a self-contained module ready for ClawHub registration.
It operates in two modes:

- **Local mode** (default) — imports analysis modules directly; use when running
  the skill in the same Python environment as jaja-money.
- **Remote mode** — set `JAJA_API_URL` to delegate all calls to a running
  jaja-money REST server (local network or remote host). No local dependencies
  required beyond `requests`.

**Local mode:**

```python
from openclaw_skill import analyze, screen, score, get_alerts, research

# Full fundamental + risk analysis
result = analyze("AAPL")
# {'symbol': 'AAPL', 'signal': 'BUY', 'confidence': 74, 'factor_score': 72, ...}

# Lightweight factor/risk score only
s = score("MSFT")
# {'symbol': 'MSFT', 'signal': 'HOLD', 'confidence': 50, ...}

# Screen a list of tickers
hits = screen(["AAPL", "MSFT", "NVDA"], min_factor_score=65, max_risk_score=50)

# Active price/signal alerts
alerts = get_alerts("AAPL")

# Autonomous multi-step research agent (returns full memo dict)
memo = research("TSLA", question="What is the bear case?")
```

**Remote mode** — point the skill at a running jaja-money server:

```bash
# All skill function calls are forwarded to the server via HTTP
export JAJA_API_URL=http://analysis-server:8080
export JAJA_API_KEY=mysecret   # optional, forwarded as X-API-Key
```

```python
from openclaw_skill import analyze, score  # works exactly the same

result = analyze("AAPL")   # calls http://analysis-server:8080/analyze
s = score("MSFT")          # calls http://analysis-server:8080/score
```

You can also use `JajaMoneyClient` directly for finer control:

```python
from openclaw_skill import JajaMoneyClient

client = JajaMoneyClient("http://analysis-server:8080", api_key="mysecret")
client.health()                         # GET /health
client.analyze("AAPL")                  # POST /analyze
client.score("MSFT")                    # POST /score
client.screen(["AAPL", "MSFT"])         # POST /screen
client.signals(["AAPL", "MSFT"])        # POST /signals
client.get_alerts("AAPL")              # GET /alerts?symbol=AAPL
client.research("TSLA", question="Bear case?")  # POST /openclaw/agent (streaming, collected)
```

Retrieve the full manifest for ClawHub registration:

```bash
curl http://localhost:8080/openclaw/manifest
```

### 2. REST API — OpenClaw Endpoints

Start the API server:

```bash
uvicorn server:app --host 0.0.0.0 --port 8080
# or: python server.py
```

**`POST /score`** — lightweight factor + risk scores for a single ticker (used by remote skill):

```bash
curl -X POST http://localhost:8080/score \
  -H "Content-Type: application/json" \
  -d '{"symbol": "AAPL"}'
```

```json
{
  "symbol": "AAPL",
  "factor_score": 72,
  "composite_label": "Buy",
  "risk_score": 38,
  "risk_level": "Low",
  "signal": "BUY",
  "confidence": 74,
  "factors": [],
  "flags": [],
  "timestamp": 1742500000
}
```

**`GET /alerts`** — list active price/signal alerts (used by remote skill):

```bash
curl "http://localhost:8080/alerts"
curl "http://localhost:8080/alerts?symbol=AAPL"
```

**`POST /signals`** — batch BUY / HOLD / SELL signals with confidence scores:

```bash
curl -X POST http://localhost:8080/signals \
  -H "Content-Type: application/json" \
  -d '{"symbols": ["AAPL", "MSFT", "NVDA"]}'
```

```json
{
  "signals": [
    {"symbol": "AAPL", "signal": "BUY", "confidence": 74, "factor_score": 72, "risk_score": 38},
    {"symbol": "MSFT", "signal": "HOLD", "confidence": 50, "factor_score": 58, "risk_score": 52}
  ],
  "count": 2
}
```

Signal logic:

| Signal | Condition |
|--------|-----------|
| **BUY** | `factor_score ≥ 65` **and** `risk_score ≤ 50` |
| **SELL** | `factor_score ≤ 35` **or** `risk_score ≥ 75` |
| **HOLD** | everything else |

**`GET /openclaw/manifest`** — returns the ClawHub skill manifest.

**`POST /openclaw/agent`** — streams the autonomous research agent:

```bash
curl -X POST http://localhost:8080/openclaw/agent \
  -H "Content-Type: application/json" \
  -d '{"symbol": "AAPL", "question": "What is the bull case?"}'
```

**`POST /openclaw/rebalance`** — portfolio drift analysis and rebalancing suggestions:

```bash
curl -X POST http://localhost:8080/openclaw/rebalance \
  -H "Content-Type: application/json" \
  -d '{
    "tickers": ["AAPL", "MSFT"],
    "target_weights": {"AAPL": 0.6, "MSFT": 0.4},
    "current_weights": {"AAPL": 0.72, "MSFT": 0.28}
  }'
```

### 3. Alpaca Account Monitoring (Read-Only)

`broker.py` provides **read-only** monitoring of an [Alpaca](https://alpaca.markets)
account. Real order placement has been removed — `execute_signal()` always returns a
simulation result and never submits orders to Alpaca.

**Setup:**

```bash
# Add to your .env file (read-only monitoring only)
ALPACA_API_KEY=your_alpaca_key
ALPACA_API_SECRET=your_alpaca_secret
ALPACA_BASE_URL=https://paper-api.alpaca.markets   # default
```

**Usage:**

```python
from broker import execute_signal, get_positions, get_account, is_configured

if is_configured():
    # Inspect account and positions (read-only Alpaca API calls)
    account = get_account()
    # {'cash': 10000.0, 'portfolio_value': 25000.0, 'buying_power': 20000.0, ...}

    positions = get_positions()
    # [{'symbol': 'AAPL', 'qty': 10.0, 'unrealized_pl': 120.0, ...}, ...]

    # Simulate a signal — no order is placed regardless of dry_run flag
    result = execute_signal("AAPL", signal="BUY", qty=5)
    # {'symbol': 'AAPL', 'signal': 'BUY', 'action': 'simulated',
    #  'simulated': True, 'order': None,
    #  'note': 'Real trading is disabled. This is a simulation only.'}
```

**Combining with `score()` for simulation:**

```python
from openclaw_skill import score
from broker import execute_signal

s = score("AAPL")
result = execute_signal(
    "AAPL",
    signal=s["signal"],
    qty=10,
    factor_score=s["factor_score"],
    risk_score=s["risk_score"],
)
# Always returns a simulation — use Forward Test for paper portfolio tracking
```

### 4. OpenClaw Incoming Webhook Receiver

**`POST /openclaw/webhook`** accepts commands from an OpenClaw agent at runtime.

Supported `event_type` values:

| `event_type` | Required `payload` fields | Action |
|---|---|---|
| `analyze_request` | `symbol` | Runs full analysis and returns signal |
| `alert_request` | `symbol`, `condition`, `threshold` | Creates a price alert |
| `screen_request` | `tickers` | Runs the screener and returns results |

```bash
# Trigger analysis from an OpenClaw agent
curl -X POST http://localhost:8080/openclaw/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "analyze_request",
    "payload": {"symbol": "NVDA"},
    "agent_id": "my-openclaw-agent"
  }'

# Create an alert
curl -X POST http://localhost:8080/openclaw/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "alert_request",
    "payload": {"symbol": "AAPL", "condition": "Price Above", "threshold": 220}
  }'
```

### 5. Event-Triggered Analysis

`openclaw_events.py` uses APScheduler to automatically fire analysis callbacks
when market events occur — no manual polling required.

**Supported events:**

| Event type | Trigger condition |
|---|---|
| `earnings_approaching` | Earnings date within 3 days |
| `new_sec_filing` | 10-K, 10-Q, or 8-K filed today |
| `price_alert_triggered` | Price / factor threshold breached |

**Setup:**

```bash
# APScheduler is already in requirements.txt
pip install APScheduler
```

**Usage:**

```python
from openclaw_events import (
    register_event_callback,
    start_event_scheduler,
    stop_event_scheduler,
)

def on_earnings(event):
    """Auto-score the stock when earnings are imminent."""
    from openclaw_skill import score
    s = score(event["symbol"])
    print(f"{event['symbol']} earnings in {event['days_away']}d — signal: {s['signal']}")

def on_price_alert(event):
    """Log a simulated trade when a price alert fires."""
    from broker import execute_signal
    result = execute_signal(event["symbol"], signal="SELL", qty=10)
    # result["action"] == "simulated" — no real order placed
    print(f"Simulated: {result}")

register_event_callback("earnings_approaching", on_earnings)
register_event_callback("price_alert_triggered", on_price_alert)

# Monitor AAPL, MSFT, NVDA every 5 minutes
start_event_scheduler(tickers=["AAPL", "MSFT", "NVDA"], interval_seconds=300)
```

Configure the scheduler in `config.yaml`:

```yaml
openclaw:
  event_scheduler_interval_seconds: 300   # poll every 5 minutes
  earnings_alert_days_ahead: 3            # fire when earnings < 3 days out
  signal_buy_factor_min: 65
  signal_buy_risk_max: 50
  signal_sell_factor_max: 35
  signal_sell_risk_min: 75
```

### Full Environment Variables

| Variable | Required | Description |
|---|---|---|
| `FINNHUB_API_KEY` | Yes | Finnhub market data |
| `ANTHROPIC_API_KEY` | Yes* | Claude AI (*or use `ai_backend: cli`) |
| `JAJA_API_KEY` | No | Protects REST API endpoints (disabled if unset) |
| `JAJA_API_URL` | OpenClaw remote | URL of jaja-money server for remote skill mode (e.g. `http://host:8080`) |
| `JAJA_API_PORT` | No | REST API server port (default: `8080`) |
| `ALPACA_API_KEY` | Monitoring only | Alpaca API key for read-only account monitoring |
| `ALPACA_API_SECRET` | Monitoring only | Alpaca API secret |
| `ALPACA_BASE_URL` | Monitoring only | Alpaca base URL (default: `https://paper-api.alpaca.markets`) |

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
