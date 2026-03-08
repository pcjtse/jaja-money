# jaja-money — Enhancement Backlog

> **App:** Multi-factor stock analysis dashboard (Streamlit + Claude + Finnhub + FinBERT)
> **Status tracking:** [ ] pending · [x] done · [~] in progress

---

## Priority 1 — High Impact, Low Effort

### 1.1 Multi-Stock Comparison View
Allow users to enter 2–5 ticker symbols and display side-by-side factor scores, risk scores, and key metrics in a comparison table.

- [ ] Add multi-ticker input widget in sidebar
- [ ] Run `compute_factors` and `compute_risk` for each ticker in parallel
- [ ] Render comparison table (tickers as columns, metrics as rows)
- [ ] Highlight best/worst value per row with conditional coloring
- [ ] Add a radar chart overlay showing all tickers' 8-factor profiles

**Files:** `app.py`, `factors.py`, `guardrails.py`

---

### 1.2 Watchlist (Save & Load Tickers)
Let users maintain a persistent watchlist so they can quickly revisit previously analyzed stocks.

- [ ] Store watchlist in a local JSON file (`watchlist.json`)
- [ ] Add "Add to Watchlist" / "Remove" buttons after analysis
- [ ] Show watchlist in sidebar with one-click load
- [ ] Display a mini snapshot (price, factor score, risk level) for each watchlist item

**Files:** `app.py` (new `watchlist.py` helper)

---

### 1.3 Export Report to PDF / CSV
Allow users to download the full analysis as a formatted PDF report or raw CSV data.

- [ ] Add "Export CSV" button that downloads the raw metric DataFrame
- [ ] Add "Export PDF" button using `reportlab` or `weasyprint` to render the analysis sections
- [ ] Include charts as embedded images in PDF (Plotly `write_image`)
- [ ] Add `reportlab` / `weasyprint` and `kaleido` to `requirements.txt`

**Files:** `app.py` (new `export.py` module)

---

### 1.4 Additional Technical Indicators
Expand the technical analysis section with widely-used indicators.

- [ ] **Bollinger Bands** (20-day SMA ± 2σ) — add to candlestick chart and factor logic
- [ ] **Volume bars** — add volume subplot under candlestick chart
- [ ] **VWAP** (Volume-Weighted Average Price) — overlay on candlestick
- [ ] **OBV** (On-Balance Volume) — momentum confirmation indicator
- [ ] **Fibonacci retracement levels** — overlay key retracement lines on price chart
- [ ] Incorporate Bollinger Band width / %B into the factor engine as a volatility-adjusted momentum signal

**Files:** `factors.py`, `app.py`

---

### 1.5 Persistent Disk Cache
Replace the in-memory 5-minute Streamlit cache with a disk-based cache to survive page refreshes and reduce API calls.

- [ ] Add `diskcache` or `joblib.Memory` as a caching backend
- [ ] Cache API responses to `~/.jaja-money/cache/` with TTL
- [ ] Add a "Clear Cache" button in the sidebar
- [ ] Add `diskcache` to `requirements.txt`

**Files:** `api.py`, `app.py`

---

## Priority 2 — Medium Impact, Moderate Effort

### 2.1 Stock Screener
Let users define filter criteria (e.g., factor score > 70, risk < 40) and scan a list of tickers to find candidates that match.

- [ ] Add a "Screener" tab or page in the sidebar
- [ ] Accept a list of tickers (manual input or pre-loaded S&P 500 / NASDAQ 100 list)
- [ ] Run factor + risk computation for each ticker
- [ ] Display ranked results table with sorting and filtering controls
- [ ] Add Claude-powered "Why does this stock rank high?" quick summary per row

**Files:** `app.py` (new `screener.py` module)

---

### 2.2 Historical Factor Score Tracking
Record factor scores and risk scores over time to show how a stock's profile evolves.

- [ ] Store each analysis result with a timestamp in a local SQLite database
- [ ] Add a "History" panel showing a line chart of composite factor score over time
- [ ] Show risk score trend alongside factor score
- [ ] Add a "Compare to previous analysis" diff view highlighting changed red flags
- [ ] Add `sqlite3` (stdlib) or `SQLAlchemy` for persistence

**Files:** `app.py` (new `history.py` module)

---

### 2.3 Earnings Call Transcript Analysis
Fetch and analyze earnings call transcripts with Claude for sentiment, guidance quality, and management tone.

- [ ] Integrate a transcript data source (e.g., Finnhub transcripts API or Alpha Vantage)
- [ ] Add "Analyze Earnings Call" button in the Fundamental Analysis section
- [ ] Stream Claude analysis covering: management tone, guidance confidence, risk language, Q&A sentiment
- [ ] Extract forward-looking statements and flag cautionary language

**Files:** `analyzer.py`, `api.py`, `app.py`

---

### 2.4 Portfolio-Level Risk & Correlation Analysis
Allow users to input a multi-stock portfolio and analyze aggregate risk, diversification, and correlation.

- [ ] Add a "Portfolio" tab in the UI
- [ ] Accept a list of tickers with weights
- [ ] Compute a correlation matrix (Pearson) from daily returns
- [ ] Render correlation heatmap (Plotly)
- [ ] Compute portfolio-level beta, volatility, and weighted factor score
- [ ] Generate Claude portfolio diversification memo

**Files:** `app.py`, `portfolio.py` (new `portfolio_analysis.py`)

---

### 2.5 Price Alert System
Let users set threshold alerts for price, factor score, or risk level and receive notifications.

- [ ] Add alert configuration panel (price above/below, factor score change, risk level change)
- [ ] Store alerts in local JSON/SQLite
- [ ] Add a background polling loop or scheduled check (APScheduler)
- [ ] Notify via desktop notification or email (SMTP or `plyer`)
- [ ] Add `APScheduler` and `plyer` to `requirements.txt`

**Files:** new `alerts.py` module, `app.py`

---

### 2.6 Options Market Data
Integrate basic options data to surface implied volatility and market sentiment signals.

- [ ] Fetch options chain data (Finnhub options endpoint or alternative)
- [ ] Display put/call ratio, implied volatility surface overview
- [ ] Add IV rank / IV percentile metric
- [ ] Incorporate put/call ratio into the risk guardrails as a market-sentiment signal
- [ ] Add IV-based expected move visualization on the price chart

**Files:** `api.py`, `guardrails.py`, `app.py`

---

## Priority 3 — High Complexity, High Value

### 3.1 AI Stock Screener with Natural Language Queries
Let users describe what they are looking for in plain English and have Claude translate that into filter criteria and return matching stocks.

- [ ] Add a natural language query input: e.g., "find undervalued tech stocks with low risk"
- [ ] Claude parses query → structured filter criteria (factor dimensions, thresholds)
- [ ] Run screener against a ticker universe
- [ ] Claude narrates why the top results match the query
- [ ] Add conversation-style follow-up refinement

**Files:** `analyzer.py`, new `screener.py`, `app.py`

---

### 3.2 Backtesting Engine
Validate the factor model's predictive power by testing historical signals against forward returns.

- [ ] Add a "Backtest" tab
- [ ] Accept a ticker, date range, and entry/exit rules (e.g., enter when factor score > 70, exit when < 45)
- [ ] Fetch sufficient historical price data (12–24 months of daily candles)
- [ ] Simulate trades and compute: total return, Sharpe ratio, max drawdown, win rate
- [ ] Plot equity curve vs. buy-and-hold benchmark
- [ ] Claude summary of backtest results and strategy robustness

**Files:** new `backtest.py` module, `app.py`

---

### 3.3 Sector & Industry Rotation Tracker
Show relative strength across sectors to identify rotation trends for top-down analysis.

- [ ] Track sector ETFs (XLK, XLF, XLE, XLV, etc.) as proxies
- [ ] Compute factor scores for each sector ETF
- [ ] Render sector rotation heatmap (color by momentum)
- [ ] Show which sectors are leading / lagging on a 4-quadrant momentum chart
- [ ] Claude sector rotation narrative and implication for individual stock analysis

**Files:** `app.py`, new `sectors.py` module

---

### 3.4 Interactive AI Chat for Stock Q&A
Replace one-shot Claude analysis buttons with a persistent chat interface for follow-up questions.

- [ ] Add a "Chat with Claude" panel at the bottom of the analysis page
- [ ] Pass full stock context (metrics, scores, flags, news) as system prompt
- [ ] Maintain conversation history within Streamlit session state
- [ ] Support multi-turn Q&A (e.g., "Why is the RSI overbought?", "What is the bear case?")
- [ ] Add "Clear Chat" button

**Files:** `analyzer.py`, `app.py`

---

### 3.5 Multi-Data-Source Support & Fallback
Reduce single-source dependency on Finnhub by adding fallback data providers.

- [ ] Integrate Yahoo Finance (`yfinance`) as a primary or fallback data source
- [ ] Integrate Alpha Vantage for fundamentals (P/E, EPS, cash flow)
- [ ] Abstract data fetching behind a provider interface with automatic failover
- [ ] Add data source indicator in the UI (shows which source was used)
- [ ] Add `yfinance` and `alpha-vantage` to `requirements.txt`

**Files:** `api.py` (new `providers/` package)

---

## Priority 4 — Infrastructure & Developer Experience

### 4.1 Docker Containerization
Package the app for consistent one-command deployment.

- [ ] Write `Dockerfile` (Python 3.11-slim base, install deps, expose port 8501)
- [ ] Write `docker-compose.yml` (app service + optional Redis for caching)
- [ ] Add `.dockerignore`
- [ ] Update README with Docker setup instructions

**Files:** new `Dockerfile`, `docker-compose.yml`, `.dockerignore`

---

### 4.2 CI/CD Pipeline (GitHub Actions)
Automate testing and linting on every push.

- [ ] Add `.github/workflows/ci.yml`
- [ ] Steps: checkout → install deps → run `pytest` → lint with `ruff` or `flake8`
- [ ] Add badge to README
- [ ] Add `ruff` to `requirements.txt` / `dev-requirements.txt`

**Files:** new `.github/workflows/ci.yml`

---

### 4.3 Structured Logging & Error Reporting
Replace bare `print` / `st.error` calls with structured logging for easier debugging.

- [ ] Integrate Python `logging` module with rotating file handler
- [ ] Log all API calls with latency metrics
- [ ] Log Claude token usage per request
- [ ] Add a developer debug panel (hidden behind env flag) showing recent log entries

**Files:** all modules

---

### 4.4 Test Coverage Expansion
Extend the existing 199-test suite to cover `api.py`, `analyzer.py`, and `app.py`.

- [ ] Add `tests/test_api.py` — mock Finnhub SDK calls and test all 8 API wrappers
- [ ] Add `tests/test_analyzer.py` — mock Anthropic SDK and test prompt builders
- [ ] Add `tests/test_watchlist.py` — test watchlist CRUD operations
- [ ] Add `tests/test_history.py` — test SQLite history persistence
- [ ] Target 90%+ line coverage with `pytest-cov`
- [ ] Add `pytest-cov` to `requirements.txt`

**Files:** `tests/` directory

---

### 4.5 Configuration File Support
Allow power users to customize factor weights, risk thresholds, and display preferences without editing source code.

- [ ] Add `config.yaml` with all tunable parameters (factor weights, risk bands, cache TTL, etc.)
- [ ] Load config at startup with `PyYAML`
- [ ] Add a "Settings" panel in the sidebar for runtime overrides
- [ ] Validate config schema on startup with `pydantic`
- [ ] Add `pyyaml` and `pydantic` to `requirements.txt`

**Files:** new `config.py`, `config.yaml`, all modules

---

## Summary

| Priority | Feature | Effort | Impact |
|----------|---------|--------|--------|
| 1 | Multi-Stock Comparison View | Low | High |
| 1 | Watchlist (Save & Load) | Low | High |
| 1 | Export Report to PDF/CSV | Low | Medium |
| 1 | Additional Technical Indicators | Low | Medium |
| 1 | Persistent Disk Cache | Low | Medium |
| 2 | Stock Screener | Medium | High |
| 2 | Historical Factor Score Tracking | Medium | High |
| 2 | Earnings Call Transcript Analysis | Medium | High |
| 2 | Portfolio-Level Risk & Correlation | Medium | High |
| 2 | Price Alert System | Medium | Medium |
| 2 | Options Market Data | Medium | Medium |
| 3 | AI Natural Language Screener | High | High |
| 3 | Backtesting Engine | High | High |
| 3 | Sector & Industry Rotation Tracker | High | High |
| 3 | Interactive AI Chat (Q&A) | High | High |
| 3 | Multi-Data-Source Support | High | Medium |
| 4 | Docker Containerization | Low | Medium |
| 4 | CI/CD Pipeline | Low | Medium |
| 4 | Structured Logging | Low | Low |
| 4 | Test Coverage Expansion | Medium | Medium |
| 4 | Configuration File Support | Medium | Medium |
