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
