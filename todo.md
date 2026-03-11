# jaja-money — Enhancement Backlog

> **App:** Multi-factor stock analysis dashboard (Streamlit + Claude + Finnhub + FinBERT)
> **Status tracking:** [ ] pending · [x] done · [~] in progress

---

## Priority 1 — High Impact, Low Effort

### 1.1 Multi-Stock Comparison View
Allow users to enter 2–5 ticker symbols and display side-by-side factor scores, risk scores, and key metrics in a comparison table.

- [x] Add multi-ticker input widget in sidebar
- [x] Run `compute_factors` and `compute_risk` for each ticker in parallel
- [x] Render comparison table (tickers as columns, metrics as rows)
- [x] Highlight best/worst value per row with conditional coloring
- [x] Add a radar chart overlay showing all tickers' 8-factor profiles

**Files:** `comparison.py`, `pages/2_Compare.py`

---

### 1.2 Watchlist (Save & Load Tickers)
Let users maintain a persistent watchlist so they can quickly revisit previously analyzed stocks.

- [x] Store watchlist in a local JSON file (`~/.jaja-money/watchlist.json`)
- [x] Add "Add to Watchlist" / "Remove" buttons after analysis
- [x] Show watchlist in sidebar with one-click load
- [x] Display a mini snapshot (price, factor score, risk level) for each watchlist item

**Files:** `watchlist.py`, `app.py`

---

### 1.3 Export Report to PDF / CSV
Allow users to download the full analysis as a formatted report or raw CSV data.

- [x] Add "Export CSV" button that downloads the raw metric DataFrame
- [x] Add "Export HTML" button generating a printable styled report
- [x] Add "Export PDF" button using `reportlab` or `weasyprint` to render the analysis sections
- [x] Include charts as embedded images in PDF (Plotly `write_image`)
- [x] Add `reportlab` / `weasyprint` and `kaleido` to `requirements.txt`

**Files:** `export.py`, `app.py`

---

### 1.4 Additional Technical Indicators
Expand the technical analysis section with widely-used indicators.

- [x] **Bollinger Bands** (20-day SMA ± 2σ) — added to candlestick chart and factor logic
- [x] **Volume bars** — volume subplot under candlestick chart
- [x] **VWAP** (20-day Volume-Weighted Average Price) — overlaid on candlestick
- [x] **OBV** (On-Balance Volume) — momentum confirmation indicator
- [x] Bollinger Band %B incorporated into the factor engine as a volatility-adjusted momentum signal
- [x] **Fibonacci retracement levels** — overlay key retracement lines on price chart

**Files:** `factors.py`, `app.py`

---

### 1.5 Persistent Disk Cache
Replace the in-memory 5-minute Streamlit cache with a disk-based cache to survive page refreshes and reduce API calls.

- [x] Custom disk cache backend with TTL (`~/.jaja-money/cache/`)
- [x] Cache API responses with configurable TTL
- [x] Add a "Clear Cache" button in the sidebar

**Files:** `cache.py`, `api.py`, `app.py`

---

## Priority 2 — Medium Impact, Moderate Effort

### 2.1 Stock Screener
Let users define filter criteria (e.g., factor score > 70, risk < 40) and scan a list of tickers to find candidates that match.

- [x] Add a "Screener" page in the sidebar
- [x] Accept a list of tickers (manual input or pre-loaded S&P 500 sample)
- [x] Run factor + risk computation for each ticker
- [x] Display ranked results table with sorting and filtering controls
- [x] Add Claude-powered "Why does this stock rank high?" quick summary per row

**Files:** `screener.py`, `pages/3_Screener.py`

---

### 2.2 Historical Factor Score Tracking
Record factor scores and risk scores over time to show how a stock's profile evolves.

- [x] Store each analysis result with a timestamp in a local SQLite database (`~/.jaja-money/history.db`)
- [x] Add a "History" panel showing a line chart of composite factor score over time
- [x] Show risk score trend alongside factor score
- [x] Add a "Compare to previous analysis" diff view highlighting changed red flags

**Files:** `history.py`, `app.py`

---

### 2.3 Earnings Call Transcript Analysis
Fetch and analyze earnings call transcripts with Claude for sentiment, guidance quality, and management tone.

- [x] Integrate Finnhub transcripts API (`get_transcripts_list`, `get_transcript`)
- [x] Add "Analyze Earnings Call" section in the app
- [x] Stream Claude analysis covering: management tone, guidance confidence, risk language, Q&A sentiment
- [x] Extract forward-looking statements and flag cautionary language

**Files:** `analyzer.py` (`stream_transcript_analysis`), `api.py`, `app.py`

---

### 2.4 Portfolio-Level Risk & Correlation Analysis
Allow users to input a multi-stock portfolio and analyze aggregate risk, diversification, and correlation.

- [x] Add a "Portfolio" page in the UI
- [x] Accept a list of tickers with optional weights
- [x] Compute a correlation matrix (Pearson) from daily returns
- [x] Render correlation heatmap (Plotly)
- [x] Compute portfolio-level beta, volatility, and weighted factor score
- [x] Generate Claude portfolio diversification memo

**Files:** `portfolio_analysis.py`, `portfolio.py`, `pages/4_Portfolio.py`

---

### 2.5 Price Alert System
Let users set threshold alerts for price, factor score, or risk level and receive notifications.

- [x] Add alert configuration panel (price above/below, factor score change, risk level change)
- [x] Store alerts in local JSON (`~/.jaja-money/alerts.json`)
- [x] Evaluate alerts on demand via `check_alerts(quote, factor_score, risk_score)`
- [x] Add a background polling loop or scheduled check (APScheduler)
- [x] Notify via desktop notification or email (SMTP or `plyer`)
- [x] Add `APScheduler` and `plyer` to `requirements.txt`

**Files:** `alerts.py`, `app.py`

---

### 2.6 Options Market Data
Integrate basic options data to surface implied volatility and market sentiment signals.

- [x] Fetch options chain data via Finnhub options endpoint
- [x] Display put/call ratio and implied volatility overview
- [x] Add IV rank / IV percentile metric
- [x] Incorporate put/call ratio into the risk guardrails as a market-sentiment signal
- [x] Add IV-based expected move visualization on the price chart

**Files:** `api.py`, `guardrails.py`, `app.py`

---

## Priority 3 — High Complexity, High Value

### 3.1 AI Stock Screener with Natural Language Queries
Let users describe what they are looking for in plain English and have Claude translate that into filter criteria.

- [x] Add a natural language query input: e.g., "find undervalued tech stocks with low risk"
- [x] Claude parses query → structured filter criteria (factor dimensions, thresholds)
- [x] Run screener against a ticker universe
- [x] Claude narrates why the top results match the query
- [x] Add conversation-style follow-up refinement

**Files:** `screener.py` (integrated with 2.1), `pages/3_Screener.py`

---

### 3.2 Backtesting Engine
Validate the factor model's predictive power by testing historical signals against forward returns.

- [x] Add a "Backtest" page
- [x] Accept a ticker, lookback period, and entry/exit signal thresholds
- [x] Fetch sufficient historical price data (1–5 years of daily candles)
- [x] Simulate trades and compute: total return, Sharpe ratio, max drawdown, win rate
- [x] Plot equity curve vs. buy-and-hold benchmark
- [x] Claude summary of backtest results and strategy robustness

**Files:** `backtest.py`, `pages/6_Backtest.py`

---

### 3.3 Sector & Industry Rotation Tracker
Show relative strength across sectors to identify rotation trends for top-down analysis.

- [x] Track 11 sector ETFs (XLK, XLF, XLE, XLV, etc.) as proxies
- [x] Compute factor scores for each sector ETF
- [x] Render sector rotation heatmap (color by momentum)
- [x] Classify each sector into a rotation phase (accumulation / leading / distribution / lagging)
- [x] Claude sector rotation narrative and implication for individual stock analysis

**Files:** `sectors.py`, `pages/5_Sectors.py`

---

### 3.4 Interactive AI Chat for Stock Q&A
Replace one-shot Claude analysis buttons with a persistent chat interface for follow-up questions.

- [x] Add a "Chat with Claude" panel at the bottom of the analysis page
- [x] Pass full stock context (metrics, scores, flags, news) as system prompt
- [x] Maintain conversation history within Streamlit session state
- [x] Support multi-turn Q&A (e.g., "Why is the RSI overbought?", "What is the bear case?")
- [x] Add "Clear Chat" button

**Files:** `analyzer.py` (`stream_chat_response`, `build_chat_system_prompt`), `app.py`

---

### 3.5 Multi-Data-Source Support & Fallback
Reduce single-source dependency on Finnhub by adding fallback data providers.

- [x] Integrate Yahoo Finance (`yfinance`) as a fallback data source
- [x] Abstract data fetching behind a provider interface with automatic failover
- [x] Add data source indicator in the UI (shows which source was used)
- [x] Integrate Alpha Vantage for fundamentals (P/E, EPS, cash flow)
- [x] Add `alpha-vantage` to `requirements.txt`

**Files:** `providers.py`, `api.py`

---

## Priority 4 — Infrastructure & Developer Experience

### 4.1 Docker Containerization
Package the app for consistent one-command deployment.

- [x] Write `Dockerfile` (Python 3.11-slim base, install deps, expose port 8501)
- [x] Write `docker-compose.yml`
- [x] Add `.dockerignore`
- [x] Update README with Docker setup instructions

**Files:** `Dockerfile`, `docker-compose.yml`, `.dockerignore`

---

### 4.2 CI/CD Pipeline (GitHub Actions)
Automate testing and linting on every push.

- [x] Add `.github/workflows/ci.yml`
- [x] Steps: checkout → install deps → run `pytest` with coverage → lint with `ruff`
- [x] Add badge to README

**Files:** `.github/workflows/ci.yml`

---

### 4.3 Structured Logging & Error Reporting
Replace bare `print` / `st.error` calls with structured logging for easier debugging.

- [x] Integrate Python `logging` module with rotating file handler (`~/.jaja-money/jaja.log`)
- [x] Log all API calls with latency metrics
- [x] Log Claude token usage per request
- [x] Add a developer debug panel (hidden behind env flag) showing recent log entries

**Files:** `log_setup.py`, all modules

---

### 4.4 Test Coverage Expansion
Extend the test suite to cover all major modules.

- [x] `tests/test_alerts.py` — alert CRUD and evaluation
- [x] `tests/test_backtest.py` — backtesting engine
- [x] `tests/test_cache.py` — disk cache TTL behaviour
- [x] `tests/test_config.py` — config loading and defaults
- [x] `tests/test_export.py` — CSV and HTML export
- [x] `tests/test_factors.py` / `test_factors_extended.py` — all 8 factors + composite
- [x] `tests/test_guardrails.py` — risk dimensions and flag conditions
- [x] `tests/test_history.py` — SQLite history persistence
- [x] `tests/test_portfolio.py` / `test_portfolio_analysis.py` — portfolio sizing and analysis
- [x] `tests/test_sectors.py` — sector rotation logic
- [x] `tests/test_sentiment.py` — FinBERT scoring
- [x] `tests/test_watchlist.py` — watchlist CRUD operations
- [x] 87%+ line coverage achieved (target was 50%)
- [x] Add `tests/test_api.py` — mock Finnhub SDK calls and test all API wrappers
- [x] Add `tests/test_analyzer.py` — mock Anthropic SDK and test prompt builders

**Files:** `tests/` directory

---

### 4.5 Configuration File Support
Allow power users to customize factor weights, risk thresholds, and display preferences without editing source code.

- [x] Add `config.yaml` with all tunable parameters (factor weights, risk bands, cache TTL, etc.)
- [x] Load config at startup with `PyYAML`
- [x] Validate config schema on startup
- [x] Add a "Settings" panel in the sidebar for runtime overrides

**Files:** `config.py`, `config.yaml`

---

---

## Priority 5 — Analytical Depth (New)

### 5.1 Relative / Sector-Adjusted Valuation
Replace absolute P/E thresholds with sector-median comparisons so valuation scores are apples-to-apples across industries.

- [x] Fetch sector-median P/E from a reference table or computed from sector ETF constituents
- [x] Score valuation factor as `stock P/E vs. sector median` percentile rather than fixed thresholds
- [x] Apply same relative approach to Price/Book and EV/EBITDA if available
- [x] Update factor engine tests to cover sector-relative logic

**Files:** `factors.py`, `api.py`

---

### 5.2 Analyst Estimate Revision Momentum
Track the direction of consensus EPS estimate changes over the last 30/60/90 days — a well-documented alpha factor.

- [x] Fetch historical estimate snapshots from Finnhub or yfinance
- [x] Compute 30d, 60d, 90d revision direction (positive / flat / negative)
- [x] Add as a 9th factor (weight ~10%, reduce other weights proportionally)
- [x] Display estimate revision trend chart in the Fundamental Analysis section

**Files:** `factors.py`, `api.py`, `app.py`

---

### 5.3 Earnings Calendar Integration
Surface upcoming earnings dates and flag the associated event risk prominently.

- [x] Fetch next earnings date from Finnhub earnings calendar endpoint
- [x] Display days-to-earnings badge in the quote header
- [x] Add an "earnings within 14 days" red flag in the risk guardrails
- [x] Show historical earnings reaction (day-after price change) for last 4 quarters

**Files:** `api.py`, `guardrails.py`, `app.py`

---

### 5.4 Insider Trading Signal
Cluster insider buy transactions are a strong contrarian signal, especially after a drawdown.

- [x] Fetch insider transactions from Finnhub (`stock_insider_transactions`)
- [x] Detect net buy/sell clusters in the past 90 days
- [x] Add insider signal as a red flag (heavy insider selling) or positive note (cluster buys)
- [x] Show insider activity timeline in the app

**Files:** `api.py`, `factors.py`, `guardrails.py`, `app.py`

---

### 5.5 Short Interest Tracking
Elevated short interest combined with improving fundamentals sets up a potential squeeze.

- [x] Fetch short interest data (Finnhub `stock_short_interest` or alternative)
- [x] Compute short interest as % of float and days-to-cover
- [x] Flag extreme short interest (> 20% of float) in the risk panel
- [x] Use short interest as a contrarian factor sub-signal in the analyst consensus dimension

**Files:** `api.py`, `guardrails.py`, `app.py`

---

### 5.6 Macroeconomic Context Overlay
Incorporate market-wide risk context so individual stock scores reflect the broader environment.

- [x] Fetch VIX (CBOE Volatility Index) as market fear proxy
- [x] Fetch 2y/10y Treasury yield spread as recession/cycle indicator
- [x] Display a macro risk banner when VIX > 30 or curve is inverted
- [x] Apply a configurable macro risk multiplier to all individual stock risk scores when macro is elevated

**Files:** `api.py` (new macro endpoints), `guardrails.py`, `app.py`

---

### 5.7 Dividend Yield Factor
Add dividend yield as a 9th factor dimension (or sub-factor of valuation) for income-oriented screening.

- [x] Extract dividend yield from existing `get_financials()` response
- [x] Score: yield > 3% = strong positive, > 1.5% = mild positive, 0% = neutral
- [x] Apply negative adjustment for payout ratio > 100% (unsustainable dividend)
- [x] Add dividend yield filter to screener

**Files:** `factors.py`, `screener.py`

---

## Priority 6 — Backtest Integrity (New)

### 6.1 Fix Look-Ahead Bias in Backtest
The current backtest computes signals using the full price history visible at each step — this inflates backtest performance unrealistically.

- [x] Refactor signal computation to use a rolling/expanding window: at time `t`, only data `[0..t]` is used
- [x] Add configurable transaction costs (slippage + commission, default 0.1% per trade)
- [x] Add walk-forward validation: split history into in-sample (70%) and out-of-sample (30%) periods
- [x] Report in-sample vs. out-of-sample metrics side by side

**Files:** `backtest.py`, `pages/6_Backtest.py`

---

### 6.2 Parameter Sensitivity Sweep
Allow users to see how sensitive backtest results are to the choice of entry/exit thresholds.

- [x] Add a parameter sweep mode: test all combinations of entry ∈ [55, 60, 65, 70] × exit ∈ [30, 35, 40, 45]
- [x] Render a heatmap of Sharpe ratio / total return across the parameter grid
- [x] Highlight the optimal and most robust parameter set
- [x] Warn when the optimal parameters are at the boundary (overfitting signal)

**Files:** `backtest.py`, `pages/6_Backtest.py`

---

### 6.3 Transaction Cost & Dividend Reinvestment
Make backtest returns realistic.

- [x] Add configurable commission per trade (flat fee or % of trade value)
- [x] Add configurable slippage model (fixed bps or volatility-proportional)
- [x] Fetch historical dividend data and reinvest in the equity curve
- [x] Show gross return vs. net-of-costs return comparison

**Files:** `backtest.py`

---

## Priority 7 — Screener Improvements (New)

### 7.1 Larger Screener Universe
The default 10-ticker universe is too small for meaningful screening.

- [x] Bundle a CSV of S&P 500 tickers (scraped from Wikipedia or static file in repo)
- [x] Bundle a CSV of Russell 1000 tickers as an extended universe option
- [x] Add universe selector in Screener UI: Custom / S&P 500 / Russell 1000
- [x] Add sector filter to pre-filter universe before running screen

**Files:** `screener.py`, `pages/3_Screener.py`, new `data/sp500.csv`, `data/russell1000.csv`

---

### 7.2 OR-Logic Filter Support
Currently all screener filters are combined with AND. Express compound criteria like "high growth OR deep value".

- [x] Extend filter schema to support filter groups with AND/OR connectors
- [x] Update `apply_filters()` to evaluate grouped logic
- [x] Update NL screener parser prompt to emit grouped filter JSON
- [x] Add filter group UI in the Screener page

**Files:** `screener.py`, `analyzer.py`

---

### 7.3 Screener Sentiment Warning & Export
Two quick wins for the screener.

- [x] Show a warning banner when `_quick_analyze()` skips FinBERT — explain that factor scores may be lower than in full analysis
- [x] Add "Export Results to CSV" button reusing existing `export.py`
- [x] Add "Save Screen Template" / "Load Screen Template" to persist filter configurations

**Files:** `screener.py`, `pages/3_Screener.py`, `export.py`

---

## Priority 8 — Risk Model Enhancements (New)

### 8.1 Liquidity Risk Flag
Flag positions where the stock's average daily volume is too thin relative to the intended position size.

- [x] Compute 20-day average daily volume (ADV) from price data
- [x] Add portfolio context input: account size and max position % to the risk panel
- [x] Flag when intended position size > 10% of ADV (liquidity risk)
- [x] Show ADV and "days to exit" estimate in the risk breakdown

**Files:** `guardrails.py`, `app.py`

---

### 8.2 Volatility Regime Detection
Distinguish transient volatility spikes (e.g., earnings) from structural trend reversals.

- [x] Compute 5-day realized vol vs. 30-day realized vol
- [x] If 5d vol > 2× 30d vol: flag as "volatility spike — may be transient"
- [x] If both 5d and 30d vol elevated: flag as "sustained elevated volatility"
- [x] Adjust overall risk score upward more aggressively for sustained vs. transient volatility

**Files:** `guardrails.py`

---

### 8.3 Live Risk-Free Rate
Replace the hardcoded 5% risk-free rate with a fetched 3-month T-bill rate.

- [x] Fetch 3-month T-bill rate from FRED API (free, no key required for some endpoints) or Finnhub
- [x] Cache with 24-hour TTL
- [x] Use live rate in Sharpe ratio calculations across `backtest.py`, `portfolio_analysis.py`
- [x] Display current rate used in the UI

**Files:** `api.py`, `backtest.py`, `portfolio_analysis.py`

---

## Priority 9 — AI & Claude Integration (New)

### 9.1 Cache Claude Responses
Identical symbol + identical data fingerprint should not trigger a duplicate Claude API call.

- [x] Compute a hash of the input context (metrics, prices, news) passed to Claude
- [x] Cache Claude text responses in the disk cache with a 30-minute TTL
- [x] Add a "Refresh Analysis" button to bypass cache and force a new Claude call
- [x] Log cache hits/misses for token cost visibility

**Files:** `analyzer.py`, `cache.py`

---

### 9.2 Adaptive System Prompts
Growth stocks, dividend payers, and cyclicals need different analytical lenses.

- [x] Classify stock type at runtime: Growth / Value / Dividend / Cyclical / Defensive based on sector, P/E, and dividend yield
- [x] Select the appropriate system prompt template per stock type
- [x] Expose stock type classification in the UI header
- [x] Allow user to override the detected stock type

**Files:** `analyzer.py`, `app.py`

---

### 9.3 Claude Backtest Narrative
Stream a Claude commentary on backtest results after the simulation completes (currently in todo as pending).

- [x] Pass backtest metrics (total return, Sharpe, max drawdown, win rate, trade log) to Claude
- [x] Prompt: analyze regime performance, identify periods of outperformance/underperformance, comment on robustness
- [x] Stream narrative below the equity curve chart

**Files:** `analyzer.py`, `backtest.py`, `pages/6_Backtest.py`

---

### 9.4 Claude Sector Rotation Narrative
Stream a Claude commentary on sector rotation analysis (currently in todo as pending).

- [x] Pass sector scores, phases, and momentum rankings to Claude
- [x] Prompt: identify rotation thesis, leading sectors' implications for individual stocks, macro interpretation
- [x] Stream narrative below the sector heatmap

**Files:** `analyzer.py`, `sectors.py`, `pages/5_Sectors.py`

---

### 9.5 Chat History Trim
Prevent long chat sessions from silently hitting the context window limit.

- [x] Track approximate token count of chat history (count words × 1.3 as proxy)
- [x] When history exceeds 80% of context budget, drop oldest turns (keep system prompt + last N exchanges)
- [x] Show a "Chat history trimmed to fit context" notice when truncation occurs

**Files:** `analyzer.py`, `app.py`

---

---

## Priority 10 — Advanced AI & Agentic Features

### 10.1 Automated Daily Watchlist Digest
Generate and deliver a Claude-written morning briefing for all tickers on the watchlist.

- [x] Schedule a daily digest job (APScheduler or cron) that runs pre-market
- [x] For each watchlist ticker: fetch overnight news, after-hours price moves, and flag changes
- [x] Claude writes a concise narrative for each ticker — "what changed since yesterday"
- [x] Deliver digest via email (SMTP) or save to `~/.jaja-money/digests/YYYY-MM-DD.html`
- [x] Add "View Digest" panel in the sidebar showing the latest report

**Files:** `digest.py`, `alerts.py`, `analyzer.py`

---

### 10.2 SEC EDGAR Filing Analysis
Fetch and analyze 10-K / 10-Q / 8-K filings directly so users don't have to read them manually.

- [x] Query SEC EDGAR full-text search API for the most recent filings for a given ticker
- [x] Download and chunk the filing text (risk factors, MD&A, financial statements)
- [x] Stream Claude analysis: key risks, revenue drivers, guidance language, red flags
- [x] Compare current filing language to prior quarter (diffing key sections)
- [x] Add "Analyze Latest Filing" button in the Fundamental Analysis section

**Files:** `edgar.py`, `analyzer.py`, `app.py`

---

### 10.3 Autonomous Research Agent Mode
Let Claude autonomously plan and execute a multi-step research workflow for a stock.

- [x] Add an "Agent Mode" toggle that gives Claude tool-call authority over the app's data fetchers
- [x] Claude decides which data to pull (news, earnings, insider trades, options, peers) based on the question
- [x] Claude synthesizes findings into a structured investment memo (bear / base / bull case)
- [x] Show a step-by-step reasoning trace in an expandable panel ("Here's what I looked at…")
- [x] Cap agent turns at 10 to avoid runaway API costs; show token count

**Files:** `agent.py`, `analyzer.py`, `app.py`

---

### 10.4 Earnings Prediction & Surprise Tracker
Build a model that estimates the probability of an earnings beat using historical patterns.

- [x] Fetch last 8 quarters of EPS actuals vs. estimates for any ticker
- [x] Compute beat rate, average surprise %, and trend direction
- [x] Claude interprets the pattern and assigns a qualitative beat probability
- [x] Surface "beat probability" badge next to the earnings calendar widget
- [x] Track predicted vs. actual outcomes in history.db for model calibration

**Files:** `factors.py`, `api.py`, `history.py`, `app.py`

---

### 10.5 Multi-Modal: Upload & Analyze Financial PDFs
Allow users to upload 10-K / earnings slides / research reports for Claude to analyze.

- [x] Add a file uploader widget (PDF, max 20 MB) in a new "Document Analysis" tab
- [x] Extract text from PDF using `pdfplumber` or `PyMuPDF`
- [x] Chunk document and pass to Claude with a financial analysis prompt
- [x] Claude surfaces key numbers, risks, guidance, and red flags in structured output
- [x] Cross-reference extracted data with live market data for context

**Files:** `document_analysis.py`, `analyzer.py`, `app.py`

---

## Priority 11 — Portfolio Intelligence

### 11.1 Monte Carlo Portfolio Simulation
Simulate thousands of future portfolio outcomes to give users a probabilistic return distribution.

- [x] Run N=10,000 simulations using bootstrapped daily returns from historical price data
- [x] Plot the distribution of 1-year outcomes: median, 10th percentile, 90th percentile
- [x] Compute Probability of achieving target return and Probability of ruin (drawdown > X%)
- [x] Claude interprets the simulation and gives plain-English odds

**Files:** `portfolio_analysis.py`, `pages/4_Portfolio.py`

---

### 11.2 Kelly Criterion & Optimal Position Sizing
Recommend scientifically-grounded position sizes based on edge and variance.

- [x] Compute full-Kelly and fractional-Kelly (25%, 50%) position sizes using factor score as proxy for edge
- [x] Show position size recommendation as % of portfolio and dollar amount (requires account size input)
- [x] Warn when Kelly fraction exceeds max-position-% config setting
- [x] Add side-by-side comparison: Kelly sizing vs. equal-weight vs. user's current allocation

**Files:** `portfolio_analysis.py`, `app.py`

---

### 11.3 Factor Attribution Analysis
Decompose the portfolio's returns into contributions from each of the 8 factor dimensions.

- [x] For each portfolio position: multiply factor weight × factor score × position weight
- [x] Aggregate factor contributions across all positions
- [x] Render a stacked bar chart showing which factors are driving the portfolio's composite score
- [x] Highlight factor concentration risk (e.g., portfolio is 70% momentum-driven)

**Files:** `portfolio_analysis.py`, `pages/4_Portfolio.py`

---

### 11.4 Peer Group Automatic Comparison
Automatically fetch sector peers and benchmark a stock's metrics against them.

- [x] Use Finnhub `company_peers` endpoint to get peer tickers
- [x] Fetch key metrics (P/E, ROE, revenue growth, margin) for all peers
- [x] Display percentile rank vs. peers for each metric in a table
- [x] Claude summarizes: "AAPL trades at a premium to peers on valuation but leads on margin quality"

**Files:** `comparison.py`, `api.py`, `analyzer.py`, `app.py`

---

## Priority 12 — Notifications & Integrations

### 12.1 Slack / Discord / Telegram Alert Webhooks
Send price and risk alerts to team messaging platforms instead of (or in addition to) email.

- [x] Add webhook URL config for Slack, Discord, and Telegram Bot API in config.yaml
- [x] Format alert messages with stock emoji, color-coded severity, and deep link back to the app
- [x] Test webhook on config save ("Send test message" button)
- [x] Support multiple destinations per alert (e.g., email + Slack)

**Files:** `alerts.py`, `config.py`, `config.yaml`

---

### 12.2 Google Sheets Export & Sync
Let users push analysis results to a Google Sheet for further manipulation or sharing.

- [x] Integrate Google Sheets API via `gspread` + service account credentials
- [x] Add "Export to Google Sheets" button on the main dashboard, comparison, and screener pages
- [x] Write factor scores, risk metrics, and key financials to a structured sheet
- [x] Optional: append rows on each analysis so the sheet becomes a running log

**Files:** `export.py`, `app.py`

---

### 12.3 Brokerage Portfolio Import
Allow users to import their actual holdings from a brokerage account instead of typing tickers manually.

- [x] Support CSV import in the standard brokerage export format (Schwab, Fidelity, IBKR)
- [x] Parse symbol, quantity, and cost basis from uploaded CSV
- [x] Pre-populate the Portfolio page with imported positions and calculated weights
- [x] Show unrealized P&L alongside factor scores for each position

**Files:** `portfolio_analysis.py`, `pages/4_Portfolio.py`

---

## Priority 13 — UX & Personalization

### 13.1 Customizable Dashboard Layout
Let power users rearrange or hide sections of the main analysis page.

- [x] Store section visibility preferences in `~/.jaja-money/ui_prefs.json`
- [x] Add a "Customize Layout" sidebar panel with toggles per section (Technical, Fundamental, Risk, Chat, etc.)
- [x] Remember expanded/collapsed state for each accordion section across sessions
- [x] Add a "Reset to Default" button

**Files:** `app.py`, `config.py`

---

### 13.2 Onboarding Tour & Help System
Reduce friction for new users with an interactive walkthrough.

- [x] Add a first-run detection flag in `~/.jaja-money/prefs.json`
- [x] Implement a step-by-step tour using `streamlit-tour` or custom tooltip overlays
- [x] Add a persistent "?" help icon next to each major section with a popover explanation
- [x] Include an example analysis (pre-loaded AAPL data) for users who haven't set up API keys yet

**Files:** `app.py`

---

### 13.3 Named Analysis Snapshots
Allow users to save and name a complete analysis state so they can revisit it later.

- [x] Add a "Save Snapshot" button that serializes all current metrics, scores, charts, and Claude output to JSON
- [x] Store snapshots in `~/.jaja-money/snapshots/` with user-provided name and timestamp
- [x] Add a "Load Snapshot" browser panel — list snapshots with ticker, date, and composite score
- [x] Enable snapshot diffing: compare two saved snapshots for the same ticker side by side

**Files:** `history.py`, `app.py`

---

## Priority 14 — Performance & Scale

### 14.1 Async / Concurrent API Fetching
Replace sequential API calls in the analysis pipeline with concurrent fetching to cut latency.

- [x] Refactor `api.py` data-gathering functions to use `asyncio` + `httpx` (or `concurrent.futures`)
- [x] Fetch quote, profile, financials, candles, news, and insider data in parallel
- [x] Add a latency breakdown debug panel showing time spent per data source
- [x] Measure and document end-to-end analysis latency improvement

**Files:** `api.py`, `app.py`

---

### 14.2 Redis Cache Backend Option
Support Redis as an optional high-performance, shared cache for multi-user or team deployments.

- [x] Abstract cache backend behind a `CacheBackend` interface (disk vs. Redis)
- [x] Implement `RedisCacheBackend` using `redis-py`
- [x] Add `CACHE_BACKEND=redis` env variable and `REDIS_URL` config option
- [x] Update `docker-compose.yml` to optionally include a Redis service

**Files:** `cache.py`, `docker-compose.yml`, `config.yaml`

---

### 14.3 API Server Mode (FastAPI)
Expose the analysis engine as a REST API so the platform can be integrated into other tools.

- [x] Create a `server.py` FastAPI app wrapping the core analysis functions
- [x] Endpoints: `POST /analyze`, `GET /screen`, `GET /portfolio`, `POST /chat`
- [x] Add API key authentication middleware
- [x] Generate OpenAPI docs automatically (`/docs`)
- [x] Update `docker-compose.yml` to offer a `server` profile alongside the Streamlit UI

**Files:** `server.py`, `docker-compose.yml`

---

## Summary

| Priority | Feature | Status |
|----------|---------|--------|
| 1 | Multi-Stock Comparison View | ✅ Done |
| 1 | Watchlist (Save & Load) | ✅ Done |
| 1 | Export Report to CSV/HTML/PDF | ✅ Done |
| 1 | Additional Technical Indicators | ✅ Done |
| 1 | Persistent Disk Cache | ✅ Done |
| 2 | Stock Screener | ✅ Done |
| 2 | Historical Factor Score Tracking | ✅ Done (diff view added) |
| 2 | Earnings Call Transcript Analysis | ✅ Done (forward-looking extraction added) |
| 2 | Portfolio-Level Risk & Correlation | ✅ Done |
| 2 | Price Alert System | ✅ Done |
| 2 | Options Market Data | ✅ Done |
| 3 | AI Natural Language Screener | ✅ Done (follow-up refinement added) |
| 3 | Backtesting Engine | ✅ Done |
| 3 | Sector & Industry Rotation Tracker | ✅ Done |
| 3 | Interactive AI Chat (Q&A) | ✅ Done |
| 3 | Multi-Data-Source Support | ✅ Done |
| 4 | Docker Containerization | ✅ Done |
| 4 | CI/CD Pipeline | ✅ Done |
| 4 | Structured Logging | ✅ Done |
| 4 | Test Coverage Expansion | ✅ Done |
| 4 | Configuration File Support | ✅ Done |
| 4 | Test Coverage Expansion | ✅ Done (api/analyzer tests pending) |
| 4 | Configuration File Support | ✅ Done (settings UI pending) |
| 5 | Relative / Sector-Adjusted Valuation | ✅ Done |
| 5 | Analyst Estimate Revision Momentum | ✅ Done |
| 5 | Earnings Calendar Integration | ✅ Done |
| 5 | Insider Trading Signal | ✅ Done |
| 5 | Short Interest Tracking | ✅ Done |
| 5 | Macroeconomic Context Overlay | ✅ Done |
| 5 | Dividend Yield Factor | ✅ Done |
| 6 | Fix Look-Ahead Bias in Backtest | ✅ Done |
| 6 | Parameter Sensitivity Sweep | ✅ Done |
| 6 | Transaction Cost & Dividend Reinvestment | ✅ Done |
| 7 | Larger Screener Universe | ✅ Done |
| 7 | OR-Logic Filter Support | ✅ Done |
| 7 | Screener Sentiment Warning & Export | ✅ Done |
| 8 | Liquidity Risk Flag | ✅ Done |
| 8 | Volatility Regime Detection | ✅ Done |
| 8 | Live Risk-Free Rate | ✅ Done |
| 9 | Cache Claude Responses | ✅ Done |
| 9 | Adaptive System Prompts | ✅ Done |
| 9 | Claude Backtest Narrative | ✅ Done |
| 9 | Claude Sector Rotation Narrative | ✅ Done |
| 9 | Chat History Trim | ✅ Done |
| 10 | Automated Daily Watchlist Digest | ✅ Done |
| 10 | SEC EDGAR Filing Analysis | ✅ Done |
| 10 | Autonomous Research Agent Mode | ✅ Done |
| 10 | Earnings Prediction & Surprise Tracker | ✅ Done |
| 10 | Multi-Modal: Upload & Analyze Financial PDFs | ✅ Done |
| 11 | Monte Carlo Portfolio Simulation | ✅ Done |
| 11 | Kelly Criterion & Optimal Position Sizing | ✅ Done |
| 11 | Factor Attribution Analysis | ✅ Done |
| 11 | Peer Group Automatic Comparison | ✅ Done |
| 12 | Slack / Discord / Telegram Alert Webhooks | ✅ Done |
| 12 | Google Sheets Export & Sync | ✅ Done |
| 12 | Brokerage Portfolio Import | ✅ Done |
| 13 | Customizable Dashboard Layout | ✅ Done |
| 13 | Onboarding Tour & Help System | ✅ Done |
| 13 | Named Analysis Snapshots | ✅ Done |
| 14 | Async / Concurrent API Fetching | ✅ Done |
| 14 | Redis Cache Backend Option | ✅ Done |
| 14 | API Server Mode (FastAPI) | ✅ Done |
| 15 | Options Chain Analysis & IV Surface | [ ] Pending |
| 15 | AI-Generated Price Target (Bull/Base/Bear) | [ ] Pending |
| 15 | Multi-Timeframe Factor Scoring | [ ] Pending |
| 15 | Custom Factor Weights via UI | [ ] Pending |
| 15 | Earnings Call Q&A (Transcript Chat) | [ ] Pending |
| 16 | Reddit/StockTwits Social Sentiment | [ ] Pending |
| 16 | Institutional 13F Ownership Tracker | [ ] Pending |
| 16 | Unusual Options Flow Detection | [ ] Pending |
| 16 | Short Squeeze Screener | [ ] Pending |
| 16 | Earnings Calendar with Predicted Move | [ ] Pending |
| 17 | Risk-Parity Portfolio Builder | [ ] Pending |
| 17 | Historical Crash Stress Testing | [ ] Pending |
| 17 | Tax-Loss Harvesting Suggestions | [ ] Pending |
| 17 | Options Hedging Suggestions (Puts/Collars) | [ ] Pending |
| 17 | Portfolio Drift Rebalancing Alerts | [ ] Pending |
| 18 | Dark Mode Toggle | [ ] Pending |
| 18 | Batch Overnight Analysis | [ ] Pending |
| 18 | Shareable Analysis Links | [ ] Pending |
| 18 | Keyboard Shortcuts | [ ] Pending |
| 19 | Analyst Price Target Distribution | [ ] Pending |
| 19 | Supply Chain Risk Analysis via EDGAR | [ ] Pending |
| 19 | ESG Scoring & Screening | [ ] Pending |
| 19 | Earnings Surprise 8-Quarter History Chart | [ ] Pending |
| 20 | Market Regime Detection (Bull/Bear/Sideways) | [ ] Pending |
| 20 | News Impact Scoring (Claude per-article) | [ ] Pending |
| 20 | Signal Change Notifications | [ ] Pending |
| 20 | Weekly Portfolio Performance Email Report | [ ] Pending |

---

## Priority 15 — Advanced AI Analysis

### 15.1 Options Chain Analysis & IV Surface
Display the full options chain alongside an implied volatility surface and key options-derived signals.

- [ ] Fetch options chain data from Finnhub (calls + puts for nearest 3 expiries)
- [ ] Compute put/call ratio, max pain price, and open-interest distribution
- [ ] Render an IV surface (strike × expiry heatmap) using Plotly
- [ ] Flag unusual options activity (volume > 3× open interest)
- [ ] Add `options_analysis.py` and surface it in a new "Options" tab in `app.py`

**Files:** `options_analysis.py`, `app.py`

---

### 15.2 AI-Generated Price Target (Bull / Base / Bear)
Have Claude produce a structured 12-month price target with three scenarios.

- [ ] Add a dedicated Claude prompt that requests a numeric price target for each scenario
- [ ] Parse the structured JSON output (target price, key assumptions, catalysts, risks)
- [ ] Display a fan-chart (Plotly) showing the three scenarios against current price
- [ ] Cache the result for 24 hours alongside the fundamental analysis cache

**Files:** `analyzer.py`, `app.py`

---

### 15.3 Multi-Timeframe Factor Scoring
Run the 8-factor model on weekly and monthly candles in addition to daily, so users can see trend confirmation across timeframes.

- [ ] Extend `api.py` to fetch weekly and monthly OHLCV candles from Finnhub
- [ ] Add a `timeframe` parameter to `compute_factors()` in `factors.py`
- [ ] Display a 3-row table (Daily / Weekly / Monthly) in the factor section of `app.py`
- [ ] Highlight agreement (all three align) vs divergence (mixed signals) with color coding

**Files:** `factors.py`, `api.py`, `app.py`

---

### 15.4 Custom Factor Weights via UI
Let users override the 8-factor weights directly in the dashboard without editing `config.yaml`.

- [ ] Add an expandable "Factor Weights" panel in the sidebar with 8 sliders (0–2×)
- [ ] Normalise weights so they sum to 1.0 and recompute the composite score live
- [ ] Save per-user weight presets (e.g. "Value", "Momentum", "Quality") to local JSON
- [ ] Add a "Reset to defaults" button that loads values from `config.yaml`

**Files:** `factors.py`, `ui_prefs.py`, `app.py`

---

### 15.5 Earnings Call Q&A (Transcript Chat)
Fetch the most recent earnings call transcript and let users ask natural-language questions against it.

- [ ] Integrate a transcript data source (e.g. The Motley Fool transcript scraper or Finnhub transcripts endpoint)
- [ ] Chunk and store transcript text; prepend relevant chunks to each user query
- [ ] Add a "Transcript Q&A" tab with a dedicated chat widget
- [ ] Show management tone metrics (positive/negative/cautious word counts) via FinBERT

**Files:** `analyzer.py`, `app.py`

---

## Priority 16 — Social & Alternative Data

### 16.1 Reddit / StockTwits Social Sentiment
Aggregate social media chatter into a quantifiable signal alongside FinBERT news sentiment.

- [ ] Call Reddit's JSON API (`/r/wallstreetbets/search.json`) for ticker mentions (no API key needed)
- [ ] Call StockTwits `/api/2/streams/symbol/{ticker}.json` for recent messages
- [ ] Run FinBERT over post titles/bodies; aggregate to a social-sentiment score
- [ ] Add a "Social Buzz" gauge to the sentiment section; include mention count trend

**Files:** `sentiment.py`, `app.py`

---

### 16.2 Institutional 13F Ownership Tracker
Show which major institutions hold the stock and how their positions changed last quarter.

- [ ] Fetch 13F data from SEC EDGAR XBRL API or a free data provider
- [ ] Display top-10 institutional holders sorted by position size
- [ ] Compute QoQ change (added / reduced / new / exited) with directional arrows
- [ ] Flag concentrated ownership (top 5 holders > 50%) as a liquidity risk signal

**Files:** `edgar.py` (extend) or new `ownership.py`, `app.py`

---

### 16.3 Unusual Options Flow Detection
Surface large, potentially informed options trades as a supplementary signal.

- [ ] Reuse options chain data from 15.1; compute volume-to-OI ratio per contract
- [ ] Flag contracts where volume > 5× average daily volume or single-trade sweeps detected
- [ ] Assign a directional bias (bullish call sweep / bearish put sweep)
- [ ] Add a collapsible "Options Flow" panel in the risk section

**Files:** `options_analysis.py`, `guardrails.py`, `app.py`

---

### 16.4 Short Squeeze Screener
Identify stocks with the conditions for a potential short squeeze.

- [ ] Add squeeze score to `screener.py`: short float % > 15%, days-to-cover > 5, upward price momentum
- [ ] Add "Short Squeeze" as a preset filter in the Screener page
- [ ] Rank results by squeeze probability score; show key metrics table
- [ ] Include a brief Claude narrative explaining the squeeze setup for top candidates

**Files:** `screener.py`, `pages/3_Screener.py`

---

### 16.5 Earnings Calendar with Predicted Move
Show upcoming earnings dates alongside the options-implied expected move.

- [ ] Fetch upcoming earnings dates from Finnhub `/calendar/earnings`
- [ ] Compute the at-the-money straddle cost as the implied move percentage
- [ ] Display a timeline chart of watchlist stocks' upcoming earnings
- [ ] Show historical actual moves vs implied moves for the last 4 quarters

**Files:** `api.py`, `app.py` (new "Earnings Calendar" section)

---

## Priority 17 — Portfolio & Risk Management

### 17.1 Risk-Parity Portfolio Builder
Automatically size positions so each contributes equal risk to the overall portfolio.

- [ ] Add a "Risk-Parity" toggle in `pages/4_Portfolio.py`
- [ ] Compute inverse-volatility weights from 60-day rolling realised vol
- [ ] Visualise the risk contribution breakdown (pie chart) vs equal-weight
- [ ] Export the suggested weights as a downloadable CSV

**Files:** `portfolio_analysis.py`, `pages/4_Portfolio.py`

---

### 17.2 Historical Crash Stress Testing
Run the current portfolio through major historical drawdown periods and show projected loss.

- [ ] Define 5 stress scenarios: 2000 dot-com, 2008 financial crisis, 2020 COVID crash, 2022 rate shock, 2024 AI correction
- [ ] Apply the average sector/factor loss for each period to portfolio holdings
- [ ] Display a waterfall chart showing contribution by position to each scenario loss
- [ ] Have Claude generate a one-paragraph narrative for the worst scenario

**Files:** `portfolio_analysis.py`, `pages/4_Portfolio.py`

---

### 17.3 Tax-Loss Harvesting Suggestions
Identify losing positions and suggest substantially-similar replacements to harvest losses without disrupting exposure.

- [ ] Flag positions with an unrealised loss > 5% from purchase price (user-input cost basis)
- [ ] Map each holding to a peer/ETF with high correlation (> 0.85) as a wash-sale-safe swap
- [ ] Display a side-by-side table of original vs replacement with tracking-error estimate
- [ ] Include a disclaimer that this is not tax advice

**Files:** `portfolio_analysis.py`, `pages/4_Portfolio.py`

---

### 17.4 Options Hedging Suggestions (Puts / Collars)
Let Claude recommend simple protective options strategies for existing positions.

- [ ] Pull at-the-money IV and nearest put prices from options chain (15.1)
- [ ] Compute breakeven, max loss, and cost as % of position for a 30-day protective put
- [ ] Also price a zero-cost collar (sell call to fund put)
- [ ] Display in a summary card; have Claude explain the trade-off in plain language

**Files:** `options_analysis.py`, `analyzer.py`, `pages/4_Portfolio.py`

---

### 17.5 Portfolio Drift Rebalancing Alerts
Notify users when any position's actual allocation drifts beyond a configurable threshold from its target.

- [ ] Let users set target weights alongside current positions in Portfolio page
- [ ] Poll (via APScheduler) and compute current vs target weight using latest prices
- [ ] Trigger alert (webhook + in-app badge) when drift exceeds threshold (default 5%)
- [ ] Show a rebalancing trade list (buy/sell X shares) to restore target weights

**Files:** `alerts.py`, `portfolio_analysis.py`, `pages/4_Portfolio.py`

---

## Priority 18 — UX & Productivity

### 18.1 Dark Mode Toggle
Add a light/dark theme switch that persists across sessions.

- [ ] Inject a custom Streamlit theme via `st.markdown` CSS when dark mode is active
- [ ] Toggle stored in `ui_prefs.py`; default follows OS preference via `prefers-color-scheme`
- [ ] Update all Plotly chart templates to use `plotly_dark` when dark mode is on
- [ ] Ensure all custom HTML report exports also support dark mode styles

**Files:** `ui_prefs.py`, `app.py`, `export.py`

---

### 18.2 Batch Overnight Analysis
Queue a list of tickers to be fully analyzed overnight and present results as a morning briefing.

- [ ] Add a "Batch Queue" panel where users add up to 50 tickers
- [ ] Schedule the run via APScheduler at a user-configured time (default 06:00 local)
- [ ] Store per-ticker factor score, risk level, and Claude summary in the history DB
- [ ] Display results as a sortable dashboard table; email the digest (reuse `digest.py`)

**Files:** `digest.py`, `history.py`, `app.py`

---

### 18.3 Shareable Analysis Links
Generate a short URL or encoded link that restores a specific analysis state.

- [ ] Serialize the current ticker + key display settings to a base64-encoded URL parameter
- [ ] Add a "Share" button that copies the link to clipboard
- [ ] On page load, detect the `?share=` parameter and auto-populate the analysis
- [ ] Optionally generate a static HTML snapshot (reuse `export.py`) as a permalink

**Files:** `app.py`, `export.py`

---

### 18.4 Keyboard Shortcuts
Improve power-user productivity with hotkeys for common actions.

- [ ] Inject JavaScript via `st.components.v1.html` to capture key presses
- [ ] `A` — analyze current ticker, `W` — add/remove watchlist, `E` — export PDF
- [ ] `1`–`6` — jump to page (Dashboard, Compare, Screener, Portfolio, Sectors, Backtest)
- [ ] Show a keyboard shortcut cheatsheet overlay triggered by `?`

**Files:** `app.py`, new `shortcuts.js` embedded component

---

## Priority 19 — Data Depth & Intelligence

### 19.1 Analyst Price Target Distribution
Visualise the full range of analyst price targets rather than a single consensus number.

- [ ] Fetch analyst target data from Finnhub `/stock/price-target`
- [ ] Display a histogram of individual analyst targets with min/mean/median/max annotations
- [ ] Overlay current price as a vertical line; show upside/downside to each quartile
- [ ] Flag when the spread (max − min) / mean > 30% as high analyst disagreement

**Files:** `api.py`, `app.py`

---

### 19.2 Supply Chain Risk Analysis via EDGAR
Use Claude to identify key suppliers, customers, and geographic dependencies from 10-K filings.

- [ ] Extract the "Risk Factors" and "Business" sections of the 10-K via `edgar.py`
- [ ] Prompt Claude to list top 5 suppliers, top 5 customers, and geographic revenue breakdown
- [ ] Flag single-customer concentration risk (> 10% revenue from one customer)
- [ ] Display as a supply chain card; cache results for 30 days

**Files:** `edgar.py`, `analyzer.py`, `app.py`

---

### 19.3 ESG Scoring & Screening
Surface Environmental, Social, and Governance scores and allow ESG-based filtering in the Screener.

- [ ] Integrate a free ESG data source (e.g. Yahoo Finance via yfinance `sustainability` or Open ESG)
- [ ] Display E/S/G sub-scores with industry percentile ranks
- [ ] Add ESG min-score filter to `screener.py`
- [ ] Flag ESG controversy events (lawsuits, fines) from news sentiment scan

**Files:** `screener.py`, `api.py`, `app.py`, `pages/3_Screener.py`

---

### 19.4 Earnings Surprise 8-Quarter History Chart
Show a rolling 8-quarter view of EPS estimates vs actuals to surface consistent beat/miss patterns.

- [ ] Fetch up to 8 quarters of earnings from Finnhub `/stock/earnings`
- [ ] Render a bar chart: estimate (grey) vs actual (green/red), annotated with surprise %
- [ ] Compute a "Beat Consistency Score" (streak of beats / 8 quarters)
- [ ] Incorporate into the factor score as a tie-breaker for the Earnings Quality factor

**Files:** `api.py`, `factors.py`, `app.py`

---

## Priority 20 — Automation & Intelligence

### 20.1 Market Regime Detection (Bull / Bear / Sideways)
Classify the current macro market regime and adjust individual stock signals accordingly.

- [ ] Use SPY 200-day SMA position, VIX level, and yield-curve slope as regime inputs
- [ ] Output one of: Strong Bull, Bull, Neutral, Bear, Strong Bear
- [ ] Apply a regime multiplier to the composite factor score (e.g. −10 pts in Strong Bear)
- [ ] Display regime badge prominently in the dashboard header

**Files:** `guardrails.py`, `factors.py`, `app.py`

---

### 20.2 News Impact Scoring (Claude per-article)
Rate each recent news headline by its potential price impact before running full sentiment.

- [ ] For each of the 10 fetched headlines, ask Claude to rate impact: High / Medium / Low / Negligible
- [ ] Weight FinBERT sentiment scores by Claude's impact rating when computing aggregate sentiment
- [ ] Highlight "High Impact" articles in the news list with a badge
- [ ] Cache per-headline impact scores keyed by article URL for 24 hours

**Files:** `sentiment.py`, `analyzer.py`, `app.py`

---

### 20.3 Signal Change Notifications
Alert users when a stock's composite factor score or risk level changes materially since last analysis.

- [ ] Compare new factor score and risk level against the most recent history DB snapshot
- [ ] Trigger an alert when score changes by > 10 pts or risk level changes by ≥ 1 tier
- [ ] Display a "Signal Changed" banner in-app and fire existing webhook dispatch
- [ ] Summarise what drove the change (which sub-factors moved most)

**Files:** `alerts.py`, `history.py`, `analyzer.py`, `app.py`

---

### 20.4 Weekly Portfolio Performance Email Report
Automatically email a formatted performance summary every Monday morning.

- [ ] Compute week-over-week return for each watchlist ticker from history DB snapshots
- [ ] Rank best/worst performers; include factor score and risk level changes
- [ ] Generate an HTML email using existing digest infrastructure in `digest.py`
- [ ] Schedule via APScheduler (Monday 07:00 local); reuse SMTP config from `config.yaml`

**Files:** `digest.py`, `history.py`, `config.yaml`
