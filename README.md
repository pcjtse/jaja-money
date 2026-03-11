# Stock Analysis Dashboard

[![CI](https://github.com/pcjtse/jaja-money/actions/workflows/ci.yml/badge.svg)](https://github.com/pcjtse/jaja-money/actions/workflows/ci.yml)

A Streamlit-based stock analysis app powered by the Finnhub API and Claude AI.
Enter a stock symbol to get real-time quotes, technicals, AI-driven fundamental
analysis, FinBERT news sentiment, an 8-factor quantitative score, a risk
guardrail engine with actionable alerts, multi-stock comparison, a stock
screener, portfolio analysis, sector rotation tracking, strategy backtesting,
SEC EDGAR filing analysis, autonomous research agent mode, webhook notifications,
a REST API server, and more.

![Screenshot](screenshot.png)

## Features

### Market Data
- **Stock Quote** — Current price, change, day high/low, previous close
- **Company Overview** — Name, sector, market cap, P/E, EPS, dividend yield, 52-week range
- **Technical Indicators** — SMA(50), SMA(200), RSI(14), MACD with signal and histogram (computed locally from price data)
- **Price Chart** — Interactive candlestick chart of the last 100 trading days (Plotly)
- **Market Research** — Analyst recommendations (bar chart), earnings history (EPS vs estimate vs surprise), peer companies
- **Export** — Download results as CSV, printable HTML report, or PDF
- **Concurrent Data Fetching** — All API calls for a symbol are parallelised with `ThreadPoolExecutor`; a per-source latency breakdown is returned alongside results

### News Sentiment Scan _(FinBERT)_
- Scores up to 10 recent headlines with **ProsusAI/finbert** (runs locally, cached across reruns)
- Per-article colour-coded badge — 🟢 Positive · 🔴 Negative · ⚪ Neutral — with confidence %
- Aggregate donut chart and net sentiment score (Bullish / Bearish / Mixed)
- **"Analyze Sentiment Themes with Claude"** button — on-demand streaming synthesis of key bullish/bearish narratives and investor takeaways via Claude Opus 4.6

### Factor Score Engine _(quantitative)_
Eight factors scored 0-100, weighted into a single composite signal:

| Factor | Weight | Data source |
|--------|--------|-------------|
| Valuation (P/E) | 15% | 7-band P/E scale |
| Trend (SMA) | 20% | Price vs SMA-50 / SMA-200 regime |
| Momentum (RSI-14) | 10% | 8-zone piecewise RSI |
| MACD Signal | 10% | Histogram direction (accelerating / decelerating) |
| News Sentiment | 15% | FinBERT net score mapped to 0-100 |
| Earnings Quality | 15% | Average EPS surprise % over last 4 quarters |
| Analyst Consensus | 10% | Strong-buy + buy / total analyst ratio |
| 52-Wk Strength | 5% | Price percentile within 52-week range |

Composite maps to: **Strong Sell · Sell · Neutral · Buy · Strong Buy**

Displayed as a Plotly gauge + radar/spider chart + progress-bar breakdown table.

### Risk Guardrails
Four risk dimensions (each 0-100) weighted into an overall **Risk Score**:

| Dimension | Weight |
|-----------|--------|
| Volatility (20-day annualised HV) | 25% |
| Drawdown from 52-week high | 25% |
| Signal risk (inverted factor score) | 25% |
| Red-flag count (×20 pts each, capped) | 25% |

Risk levels: **Low · Moderate · Elevated · High · Extreme**

Thirteen red-flag conditions produce colour-coded alerts (🔴 danger · 🟡 warning · 🔵 info):
- Volatility > 40% / > 60%
- Drawdown > 25% / > 40%
- RSI overbought (>74 / >80) or oversold (<28 / <20)
- Strong downtrend (price < SMA-50 < SMA-200)
- Negative P&L, P/E > 50 / > 80
- Earnings miss rate ≥ 2/4 or 3/4 quarters
- Analyst bullish ratio < 20% / < 35%
- News sentiment net score < −0.3 / < −0.6
- Composite factor score < 25 (multi-factor sell) or > 85 (euphoria risk)

### Fundamental Analyzer _(Claude AI)_
On-demand analysis powered by **Claude Opus 4.6 with adaptive thinking**.
Synthesises all fetched data into a structured 8-section investment research report:
Company Snapshot · Valuation · Financial Health · Technical Posture ·
Analyst Sentiment · Peer Context · Key Risks & Catalysts · Investment Thesis.

### Price & Signal Alerts
- Set price threshold, factor-score, or risk-score alerts per ticker
- Alerts persisted locally in `~/.jaja-money/alerts.json`
- Evaluated on demand via `check_alerts(quote, factor_score, risk_score)`
- **Webhook notifications** — fire alerts to Slack, Discord, or Telegram (see [Webhook Setup](#webhook-notifications-p121))

### Watchlist
- Save any analysed ticker to `~/.jaja-money/watchlist.json`
- Stores ticker, name, last price, factor score, and timestamp
- Accessible across sessions without re-fetching

### Historical Tracking & Named Snapshots
- Every analysis snapshot (factor score, risk score, price, flags) stored in `~/.jaja-money/history.db` (SQLite)
- Keyed by `(symbol, date)` for trend-over-time queries
- **Named snapshots** — save any analysis state with a custom name; list, load, diff, and delete snapshots via `history.save_named_snapshot / diff_snapshots`

---

## Multi-Page App

The app ships five additional Streamlit pages:

### Compare Stocks (`pages/2_Compare.py`)
Enter 2–5 tickers to compare side-by-side across factor scores, risk scores,
P/E, RSI, and key metrics. Correlation heatmap included. Peer percentile ranks
are computed for each ticker via the Finnhub peers API.

### Stock Screener (`pages/3_Screener.py`)
Filter the S&P 500 sample (or a custom universe) by factor score, risk score,
P/E, RSI, and more. Also supports **natural-language queries parsed by Claude**
(e.g. "tech stocks with low risk and strong momentum").

### Portfolio Analysis (`pages/4_Portfolio.py`)
Enter a multi-stock portfolio with optional weights to compute:
- Correlation matrix from daily returns
- Portfolio-level beta, volatility, and weighted factor score
- Diversification score and concentration warnings
- **Monte Carlo simulation** — bootstrapped 1-year forward return distribution with 5th/50th/95th percentile paths and VaR/CVaR (P11.1)
- **Kelly Criterion position sizing** — optimal fraction per position using factor scores as edge proxy (P11.2)
- **Factor attribution** — contribution and concentration of each of the 8 factors across the portfolio (P11.3)
- AI-generated portfolio commentary via Claude
- **Import from brokerage CSV** — auto-detect Schwab, Fidelity, or IBKR export formats (P12.3)

### Sector Rotation (`pages/5_Sectors.py`)
Tracks relative strength across **11 S&P 500 sector ETFs** to identify
rotation trends, leading sectors, and lagging sectors. Each sector is
classified into a rotation phase (accumulation / leading / distribution / lagging).

### Strategy Backtesting (`pages/6_Backtest.py`)
Simulates historical trades on a price-derived composite signal (SMA trend,
RSI, MACD). Configurable entry/exit thresholds and lookback period (1–5 years).
Returns trade log, equity curve, Sharpe ratio, max drawdown, and win rate.
Supports **dividend reinvestment** (DRIP) in return calculations.

---

## New Capabilities (P10–P14)

### Automated Daily Digest (`digest.py`) — P10.1
Claude writes a morning briefing for every ticker on your watchlist.
- Output: `~/.jaja-money/digests/YYYY-MM-DD.html`
- Optional scheduled delivery via **APScheduler** (configurable hour/minute in `config.yaml`)
- Optional email delivery via SMTP (see [Digest Email Setup](#digest-email-setup-p101))

### SEC EDGAR Filing Analysis (`edgar.py`) — P10.2
Fetches and streams Claude analysis of 10-K, 10-Q, and 8-K filings directly from SEC EDGAR.
- Looks up CIK numbers automatically from the ticker
- Chunks large filings and streams analysis covering risks, revenue drivers, guidance language, and red flags
- No additional API key required (SEC EDGAR is public)

### Autonomous Research Agent (`agent.py`) — P10.3
Gives Claude tool-call authority over the app's data fetchers to autonomously
execute a multi-step research workflow and produce a structured investment memo.
- Capped at 10 agentic turns to control costs
- Tools available: quote, fundamentals, news, technicals, screener, peers, earnings

### PDF / Document Analysis (`document_analysis.py`) — P10.5
Upload any financial PDF (10-K, earnings slides, research reports) and stream Claude analysis.
- Extracts text via **pdfplumber** (primary) or **PyMuPDF/fitz** (fallback)
- Chunks up to 20 MB documents; configurable chunk size and max chunks
- Optional `market_data` dict injected into the prompt for cross-referencing

### Advanced Portfolio Analytics (`portfolio_analysis.py`) — P11.1–P11.4
| Function | Description |
|----------|-------------|
| `monte_carlo_simulation` | 1 000-path bootstrapped simulation; VaR, CVaR, percentile fan |
| `kelly_sizing` | Full/half-Kelly position sizes using factor score as edge |
| `factor_attribution` | Per-factor contribution scores and concentration Herfindahl index |
| `fetch_peer_metrics` | Peer group percentile ranks across key metrics |

### Webhook Notifications (`alerts.py`) — P12.1
Push alert payloads to **Slack**, **Discord**, or **Telegram** when thresholds are breached.
See [Webhook Setup](#webhook-notifications-p121) for configuration.

### Google Sheets Export (`export.py`) — P12.2
`export_to_google_sheets(data, spreadsheet_id)` writes analysis results to a Google Sheet
via a service-account credential. See [Google Sheets Setup](#google-sheets-export-p122).

### Brokerage CSV Import (`export.py`) — P12.3
`parse_brokerage_csv(csv_bytes)` auto-detects and parses position exports from:
- **Charles Schwab** — positions export CSV
- **Fidelity** — portfolio CSV
- **Interactive Brokers (IBKR)** — activity statement CSV
- **Generic** — any CSV with symbol/quantity/cost-basis columns

### Dashboard Preferences & Onboarding Tour (`ui_prefs.py`) — P13.1/P13.2
- Per-section visibility toggles stored in `~/.jaja-money/ui_prefs.json`
- First-run onboarding tour with step-by-step guidance (auto-shown once, manually re-triggerable)

### Named Portfolio Snapshots (`history.py`) — P13.3
Save, compare, and diff named analysis snapshots:
```python
from history import save_named_snapshot, diff_snapshots, list_snapshots, load_snapshot
save_named_snapshot("AAPL", analysis_data, name="pre-earnings")
diff_snapshots(snap_a, snap_b)   # returns delta dict
```

### Redis Cache Backend (`cache.py`) — P14.2
Drop-in replacement for the default disk cache. Activate via environment variable:
```bash
CACHE_BACKEND=redis REDIS_URL=redis://localhost:6379/0 streamlit run app.py
```
See [Redis Cache Setup](#redis-cache-backend-p142).

### FastAPI REST Server (`server.py`) — P14.3
Run the analysis engine as a standalone REST API:
```bash
uvicorn server:app --host 0.0.0.0 --port 8080
# or
python server.py
```
Endpoints: `POST /analyze`, `GET /screen`, `GET /portfolio`, `POST /chat`, `GET /health`.
OpenAPI docs available at `/docs`. See [API Server Setup](#rest-api-server-p143).

---

## Prerequisites

- Python 3.10+
- A free [Finnhub](https://finnhub.io) API key
- An [Anthropic](https://console.anthropic.com) API key (for Claude analysis and sentiment themes)

## Setup

1. Clone the repository and navigate to the project directory:

   ```bash
   cd jaja-money
   ```

2. Create and activate a virtual environment:

   ```bash
   python3 -m venv venv
   source venv/bin/activate        # macOS / Linux
   # venv\Scripts\activate          # Windows
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

   > **Note:** `transformers` and `torch` are included for FinBERT sentiment scoring.
   > The model (~500 MB) is downloaded automatically on first run and cached locally.

4. Get API keys:
   - Finnhub: [https://finnhub.io](https://finnhub.io) (free tier)
   - Anthropic: [https://console.anthropic.com](https://console.anthropic.com)

5. Create a `.env` file from the example and add your keys:

   ```bash
   cp .env.example .env
   ```

   Edit `.env`:
   ```
   FINNHUB_API_KEY=your_finnhub_key_here
   ANTHROPIC_API_KEY=your_anthropic_key_here
   ```

## Usage

```bash
streamlit run app.py
```

Open the URL shown in the terminal (typically `http://localhost:8501`).
Enter a stock symbol (e.g. `AAPL`) in the sidebar and click **Analyze**.
Use the sidebar navigation to switch between the main dashboard and the
additional pages (Compare, Screener, Portfolio, Sectors, Backtest).

---

## Additional Setup Instructions

### Webhook Notifications (P12.1)

Configure webhook URLs in `config.yaml` (or the equivalent `.env` / Streamlit secrets):

```yaml
# config.yaml
webhooks:
  slack_url: "https://hooks.slack.com/services/..."   # Slack Incoming Webhook URL
  discord_url: "https://discord.com/api/webhooks/..."  # Discord Webhook URL
  telegram_token: "123456:ABC-..."                     # Telegram Bot token
  telegram_chat_id: "-100123456789"                    # Telegram chat/channel ID
  app_url: "http://localhost:8501"                     # Optional deep-link base URL
```

- **Slack**: Create an Incoming Webhook at [api.slack.com/apps](https://api.slack.com/apps).
- **Discord**: In your server → channel settings → Integrations → Webhooks → New Webhook.
- **Telegram**: Create a bot via [@BotFather](https://t.me/botfather), then add it to your
  channel and retrieve the `chat_id` via `https://api.telegram.org/bot<TOKEN>/getUpdates`.

Test your webhooks:
```python
from alerts import send_test_webhook
send_test_webhook("slack", "https://hooks.slack.com/services/...")
send_test_webhook("discord", "https://discord.com/api/webhooks/...")
send_test_webhook("telegram", "BOT_TOKEN", chat_id="CHAT_ID")
```

---

### Digest Email Setup (P10.1)

The daily digest can be emailed via any SMTP server. Pass credentials to `send_digest_email`:

```python
from digest import generate_digest, send_digest_email
path = generate_digest(api)
send_digest_email(
    path,
    to_address="you@example.com",
    smtp_host="smtp.gmail.com",
    smtp_port=587,
    smtp_user="you@gmail.com",
    smtp_password="your-app-password",   # Gmail: use an App Password
)
```

Schedule it to run automatically at a configured UTC time (default 08:00):

```yaml
# config.yaml
digest:
  schedule_hour: 8    # UTC hour
  schedule_minute: 0
  email: "you@example.com"
```

**Gmail users**: enable 2-Step Verification and generate an [App Password](https://myaccount.google.com/apppasswords) — do not use your regular Gmail password.

Requires `APScheduler`:
```bash
pip install APScheduler
```

---

### Google Sheets Export (P12.2)

1. Create a [Google Cloud service account](https://console.cloud.google.com/iam-admin/serviceaccounts)
   and download the JSON key file.
2. Enable the **Google Sheets API** and **Google Drive API** for your project.
3. Share your target spreadsheet with the service account email (Editor role).
4. Configure in `config.yaml`:

   ```yaml
   google_sheets:
     spreadsheet_id: "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms"
     sheet_name: "jaja-money"
     credentials_path: "/path/to/service-account.json"
     append_log: true   # append rows instead of overwriting
   ```

5. Use from code:

   ```python
   from export import export_to_google_sheets
   export_to_google_sheets(analysis_data, spreadsheet_id="...")
   ```

Requires:
```bash
pip install gspread google-auth
```

---

### Redis Cache Backend (P14.2)

Replace the default disk cache with Redis for multi-instance or container deployments.

**Local Redis:**
```bash
# Start Redis (or use Docker)
redis-server
# or
docker run -d -p 6379:6379 redis:7-alpine

# Run the app with Redis cache
CACHE_BACKEND=redis REDIS_URL=redis://localhost:6379/0 streamlit run app.py
```

**Docker Compose (includes Redis profile):**
```bash
docker compose --profile redis up --build
```

**Environment variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `CACHE_BACKEND` | `disk` | `disk` or `redis` |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |

Requires:
```bash
pip install redis
```

---

### REST API Server (P14.3)

Run `server.py` as a standalone FastAPI service alongside or instead of the Streamlit app.

**Start the server:**
```bash
uvicorn server:app --host 0.0.0.0 --port 8080
# or simply:
python server.py
```

**Environment variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `JAJA_API_KEY` | _(empty — auth disabled)_ | Set to a secret string to require `X-API-Key` header |
| `JAJA_API_PORT` | `8080` | Listening port |
| `FINNHUB_API_KEY` | _(required)_ | Finnhub API key |
| `ANTHROPIC_API_KEY` | _(required)_ | Anthropic API key |
| `CACHE_BACKEND` | `disk` | `disk` or `redis` |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis URL (when `CACHE_BACKEND=redis`) |

**Example requests:**
```bash
# Health check
curl http://localhost:8080/health

# Full stock analysis
curl -X POST http://localhost:8080/analyze \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret-key" \
  -d '{"symbol": "AAPL"}'

# Natural-language screener
curl "http://localhost:8080/screen?query=tech+stocks+with+low+risk" \
  -H "X-API-Key: your-secret-key"

# Chat about a stock
curl -X POST http://localhost:8080/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret-key" \
  -d '{"symbol": "AAPL", "message": "What is the bull case?"}'
```

Interactive OpenAPI docs: `http://localhost:8080/docs`

**Docker Compose (API server profile):**
```bash
JAJA_API_KEY=your-secret docker compose --profile server up --build
```

Requires:
```bash
pip install fastapi "uvicorn[standard]"
```

---

### PDF Document Analysis (P10.5)

Install at least one PDF extraction library:

```bash
pip install pdfplumber          # recommended
# or
pip install pymupdf             # alternative (fitz)
```

Both are optional — the feature is gracefully skipped if neither is installed.

---

### SEC EDGAR Filing Analysis (P10.2)

No additional API key or package is required. The EDGAR API is public.
The SEC requires a descriptive `User-Agent` header; the app sends
`jaja-money/1.0 (research tool; contact@example.com)` by default.
If you encounter 403 errors, update the `_HEADERS` constant in `edgar.py`
with your own contact email.

---

## Project Structure

```
jaja-money/
├── app.py                  # Streamlit UI — layout, caching, all section rendering
├── api.py                  # Finnhub API wrapper + concurrent fetch_all()
├── analyzer.py             # Claude Opus 4.6 — fundamental analysis + streaming
├── agent.py                # Autonomous research agent with tool-call loop (P10.3)
├── digest.py               # Automated daily watchlist digest + email delivery (P10.1)
├── edgar.py                # SEC EDGAR filing fetcher + Claude streaming analysis (P10.2)
├── document_analysis.py    # PDF upload & Claude document analysis (P10.5)
├── sentiment.py            # FinBERT sentiment scoring (score_articles, aggregate_sentiment)
├── factors.py              # Factor score engine — 8 factors + composite + label/colour helpers
├── guardrails.py           # Risk guardrail engine — 4 dimensions, 13 flag conditions
├── alerts.py               # Price/signal alerts + Slack/Discord/Telegram webhooks (P12.1)
├── watchlist.py            # Watchlist persistence (stored in ~/.jaja-money/watchlist.json)
├── history.py              # Historical tracking (SQLite) + named snapshots (P13.3)
├── export.py               # CSV, HTML, PDF export + Google Sheets (P12.2) + brokerage CSV import (P12.3)
├── backtest.py             # Backtesting engine — signal simulation, equity curve, metrics, DRIP
├── comparison.py           # Multi-stock comparison + peer percentile ranks (P11.4)
├── screener.py             # Stock screener — rule-based + Claude NL query support
├── sectors.py              # Sector & industry rotation tracker (11 ETFs)
├── portfolio.py            # Portfolio suggestion engine — sizing, stops, targets
├── portfolio_analysis.py   # Portfolio risk, correlation, Monte Carlo, Kelly, factor attribution (P11.1–P11.3)
├── ui_prefs.py             # Dashboard layout preferences + onboarding tour (P13.1/P13.2)
├── server.py               # FastAPI REST API server (P14.3)
├── providers.py            # Multi-source data provider (Finnhub primary, yfinance fallback)
├── cache.py                # Persistent cache — disk (default) or Redis backend (P14.2)
├── config.py               # Centralised config (config.yaml + built-in defaults)
├── log_setup.py            # Structured logging (console + rotating file)
├── pages/
│   ├── 2_Compare.py        # Multi-stock comparison page
│   ├── 3_Screener.py       # Stock screener page
│   ├── 4_Portfolio.py      # Portfolio analysis page
│   └── 5_Sectors.py        # Sector rotation page
│   └── 6_Backtest.py       # Strategy backtesting page
├── config.yaml             # Runtime configuration
└── requirements.txt
```

---

## Docker Setup

### Quick start with Docker Compose

```bash
# 1. Copy .env.example and add your API keys
cp .env.example .env
# Edit .env:
#   FINNHUB_API_KEY=your_finnhub_key_here
#   ANTHROPIC_API_KEY=your_anthropic_key_here

# 2. Build and start (Streamlit only)
docker compose up --build

# 3. With Redis cache backend
docker compose --profile redis up --build

# 4. With REST API server
JAJA_API_KEY=your-secret docker compose --profile server up --build

# 5. All services
JAJA_API_KEY=your-secret docker compose --profile redis --profile server up --build
```

Open `http://localhost:8501` (Streamlit) or `http://localhost:8080` (API server).

### Build manually

```bash
docker build -t jaja-money .
docker run -p 8501:8501 --env-file .env jaja-money
```

### Notes
- The container exposes port **8501** (Streamlit default) and optionally **8080** (API server).
- Persistent data (`history.db`, `watchlist.json`, `alerts.json`, cache, digests, snapshots) lives
  inside the container at `~/.jaja-money/`. Mount a volume to persist across
  container restarts:
  ```bash
  docker run -p 8501:8501 --env-file .env \
    -v "$HOME/.jaja-money:/root/.jaja-money" jaja-money
  ```
- The FinBERT model (~500 MB) is downloaded on first run. Pre-download it into
  the image by uncommenting the relevant line in the `Dockerfile`.

---

## ⚠️ Set API Usage Limits Before Running

**Configure hard spending and rate limits on both APIs before running bulk
operations.** The Screener and Sector pages can make hundreds of API calls and
trigger significant Claude token usage in a single session.

### Anthropic (Claude) — Spend Limits

1. Go to [console.anthropic.com](https://console.anthropic.com) → **Settings → Billing**.
2. Set a **monthly spend limit** appropriate for your usage (e.g. $10–20 for
   light use, $50+ for heavy screener/backtest workflows).
3. Optionally set a lower **monthly notification threshold** to receive an email
   before you approach your cap.

**Why this matters:**
- Every "Analyze with Claude" call streams a full investment research report
  (~1 000–3 000 tokens output with Claude Opus 4.6).
- The Screener's "Explain top results with Claude" + the Sector and Backtest
  commentary buttons each trigger separate API calls.
- The autonomous research agent (P10.3) can make up to 10 agentic turns per run.
- Claude responses are disk-cached for 30 minutes (keyed by content hash), so
  re-running the same analysis is free — but new symbols or changed data always
  hit the API.

### Finnhub — Rate Limits & Monitoring

The free Finnhub plan allows **60 requests per minute**. Each full analysis
uses approximately 8–12 API calls (quote, profile, financials, daily candles,
recommendations, earnings, peers, news, earnings calendar, insider transactions).
Technical indicators and all factor/risk computations run locally from the
fetched price data — no extra API calls. Results are cached for 5 minutes
(disk cache with TTL), so repeated lookups within that window cost 0 additional
calls.

**Bulk-operation call counts (approx.):**

| Page | Calls per run |
|------|--------------|
| Main analysis (single stock) | ~12 |
| Compare (5 stocks) | ~25 |
| Sector Rotation (11 ETFs) | ~55 |
| Screener — S&P 500 default (100 tickers) | ~400–500 |
| Screener — Russell 1000 (500 tickers) | ~2 000–2 500 |

**Recommendations:**
- Monitor your Finnhub usage at [finnhub.io/dashboard](https://finnhub.io/dashboard).
- For the Screener, prefer the **Default (config sample)** or **S&P 500** universe
  rather than Russell 1000 to stay within free-tier limits.
- If you see `429 Too Many Requests` errors, wait 60 seconds before retrying;
  the built-in 0.3 s delay between screener requests helps but cannot fully
  prevent rate limiting on large universes.
- Consider upgrading to a paid Finnhub plan if you plan to run the Screener
  or Sector Rotation repeatedly throughout the day.
