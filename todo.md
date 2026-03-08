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

- [ ] Fetch sector-median P/E from a reference table or computed from sector ETF constituents
- [ ] Score valuation factor as `stock P/E vs. sector median` percentile rather than fixed thresholds
- [ ] Apply same relative approach to Price/Book and EV/EBITDA if available
- [ ] Update factor engine tests to cover sector-relative logic

**Files:** `factors.py`, `api.py`

---

### 5.2 Analyst Estimate Revision Momentum
Track the direction of consensus EPS estimate changes over the last 30/60/90 days — a well-documented alpha factor.

- [ ] Fetch historical estimate snapshots from Finnhub or yfinance
- [ ] Compute 30d, 60d, 90d revision direction (positive / flat / negative)
- [ ] Add as a 9th factor (weight ~10%, reduce other weights proportionally)
- [ ] Display estimate revision trend chart in the Fundamental Analysis section

**Files:** `factors.py`, `api.py`, `app.py`

---

### 5.3 Earnings Calendar Integration
Surface upcoming earnings dates and flag the associated event risk prominently.

- [ ] Fetch next earnings date from Finnhub earnings calendar endpoint
- [ ] Display days-to-earnings badge in the quote header
- [ ] Add an "earnings within 14 days" red flag in the risk guardrails
- [ ] Show historical earnings reaction (day-after price change) for last 4 quarters

**Files:** `api.py`, `guardrails.py`, `app.py`

---

### 5.4 Insider Trading Signal
Cluster insider buy transactions are a strong contrarian signal, especially after a drawdown.

- [ ] Fetch insider transactions from Finnhub (`stock_insider_transactions`)
- [ ] Detect net buy/sell clusters in the past 90 days
- [ ] Add insider signal as a red flag (heavy insider selling) or positive note (cluster buys)
- [ ] Show insider activity timeline in the app

**Files:** `api.py`, `factors.py`, `guardrails.py`, `app.py`

---

### 5.5 Short Interest Tracking
Elevated short interest combined with improving fundamentals sets up a potential squeeze.

- [ ] Fetch short interest data (Finnhub `stock_short_interest` or alternative)
- [ ] Compute short interest as % of float and days-to-cover
- [ ] Flag extreme short interest (> 20% of float) in the risk panel
- [ ] Use short interest as a contrarian factor sub-signal in the analyst consensus dimension

**Files:** `api.py`, `guardrails.py`, `app.py`

---

### 5.6 Macroeconomic Context Overlay
Incorporate market-wide risk context so individual stock scores reflect the broader environment.

- [ ] Fetch VIX (CBOE Volatility Index) as market fear proxy
- [ ] Fetch 2y/10y Treasury yield spread as recession/cycle indicator
- [ ] Display a macro risk banner when VIX > 30 or curve is inverted
- [ ] Apply a configurable macro risk multiplier to all individual stock risk scores when macro is elevated

**Files:** `api.py` (new macro endpoints), `guardrails.py`, `app.py`

---

### 5.7 Dividend Yield Factor
Add dividend yield as a 9th factor dimension (or sub-factor of valuation) for income-oriented screening.

- [ ] Extract dividend yield from existing `get_financials()` response
- [ ] Score: yield > 3% = strong positive, > 1.5% = mild positive, 0% = neutral
- [ ] Apply negative adjustment for payout ratio > 100% (unsustainable dividend)
- [ ] Add dividend yield filter to screener

**Files:** `factors.py`, `screener.py`

---

## Priority 6 — Backtest Integrity (New)

### 6.1 Fix Look-Ahead Bias in Backtest
The current backtest computes signals using the full price history visible at each step — this inflates backtest performance unrealistically.

- [ ] Refactor signal computation to use a rolling/expanding window: at time `t`, only data `[0..t]` is used
- [ ] Add configurable transaction costs (slippage + commission, default 0.1% per trade)
- [ ] Add walk-forward validation: split history into in-sample (70%) and out-of-sample (30%) periods
- [ ] Report in-sample vs. out-of-sample metrics side by side

**Files:** `backtest.py`, `pages/6_Backtest.py`

---

### 6.2 Parameter Sensitivity Sweep
Allow users to see how sensitive backtest results are to the choice of entry/exit thresholds.

- [ ] Add a parameter sweep mode: test all combinations of entry ∈ [55, 60, 65, 70] × exit ∈ [30, 35, 40, 45]
- [ ] Render a heatmap of Sharpe ratio / total return across the parameter grid
- [ ] Highlight the optimal and most robust parameter set
- [ ] Warn when the optimal parameters are at the boundary (overfitting signal)

**Files:** `backtest.py`, `pages/6_Backtest.py`

---

### 6.3 Transaction Cost & Dividend Reinvestment
Make backtest returns realistic.

- [ ] Add configurable commission per trade (flat fee or % of trade value)
- [ ] Add configurable slippage model (fixed bps or volatility-proportional)
- [ ] Fetch historical dividend data and reinvest in the equity curve
- [ ] Show gross return vs. net-of-costs return comparison

**Files:** `backtest.py`

---

## Priority 7 — Screener Improvements (New)

### 7.1 Larger Screener Universe
The default 10-ticker universe is too small for meaningful screening.

- [ ] Bundle a CSV of S&P 500 tickers (scraped from Wikipedia or static file in repo)
- [ ] Bundle a CSV of Russell 1000 tickers as an extended universe option
- [ ] Add universe selector in Screener UI: Custom / S&P 500 / Russell 1000
- [ ] Add sector filter to pre-filter universe before running screen

**Files:** `screener.py`, `pages/3_Screener.py`, new `data/sp500.csv`, `data/russell1000.csv`

---

### 7.2 OR-Logic Filter Support
Currently all screener filters are combined with AND. Express compound criteria like "high growth OR deep value".

- [ ] Extend filter schema to support filter groups with AND/OR connectors
- [ ] Update `apply_filters()` to evaluate grouped logic
- [ ] Update NL screener parser prompt to emit grouped filter JSON
- [ ] Add filter group UI in the Screener page

**Files:** `screener.py`, `analyzer.py`

---

### 7.3 Screener Sentiment Warning & Export
Two quick wins for the screener.

- [ ] Show a warning banner when `_quick_analyze()` skips FinBERT — explain that factor scores may be lower than in full analysis
- [ ] Add "Export Results to CSV" button reusing existing `export.py`
- [ ] Add "Save Screen Template" / "Load Screen Template" to persist filter configurations

**Files:** `screener.py`, `pages/3_Screener.py`, `export.py`

---

## Priority 8 — Risk Model Enhancements (New)

### 8.1 Liquidity Risk Flag
Flag positions where the stock's average daily volume is too thin relative to the intended position size.

- [ ] Compute 20-day average daily volume (ADV) from price data
- [ ] Add portfolio context input: account size and max position % to the risk panel
- [ ] Flag when intended position size > 10% of ADV (liquidity risk)
- [ ] Show ADV and "days to exit" estimate in the risk breakdown

**Files:** `guardrails.py`, `app.py`

---

### 8.2 Volatility Regime Detection
Distinguish transient volatility spikes (e.g., earnings) from structural trend reversals.

- [ ] Compute 5-day realized vol vs. 30-day realized vol
- [ ] If 5d vol > 2× 30d vol: flag as "volatility spike — may be transient"
- [ ] If both 5d and 30d vol elevated: flag as "sustained elevated volatility"
- [ ] Adjust overall risk score upward more aggressively for sustained vs. transient volatility

**Files:** `guardrails.py`

---

### 8.3 Live Risk-Free Rate
Replace the hardcoded 5% risk-free rate with a fetched 3-month T-bill rate.

- [ ] Fetch 3-month T-bill rate from FRED API (free, no key required for some endpoints) or Finnhub
- [ ] Cache with 24-hour TTL
- [ ] Use live rate in Sharpe ratio calculations across `backtest.py`, `portfolio_analysis.py`
- [ ] Display current rate used in the UI

**Files:** `api.py`, `backtest.py`, `portfolio_analysis.py`

---

## Priority 9 — AI & Claude Integration (New)

### 9.1 Cache Claude Responses
Identical symbol + identical data fingerprint should not trigger a duplicate Claude API call.

- [ ] Compute a hash of the input context (metrics, prices, news) passed to Claude
- [ ] Cache Claude text responses in the disk cache with a 30-minute TTL
- [ ] Add a "Refresh Analysis" button to bypass cache and force a new Claude call
- [ ] Log cache hits/misses for token cost visibility

**Files:** `analyzer.py`, `cache.py`

---

### 9.2 Adaptive System Prompts
Growth stocks, dividend payers, and cyclicals need different analytical lenses.

- [ ] Classify stock type at runtime: Growth / Value / Dividend / Cyclical / Defensive based on sector, P/E, and dividend yield
- [ ] Select the appropriate system prompt template per stock type
- [ ] Expose stock type classification in the UI header
- [ ] Allow user to override the detected stock type

**Files:** `analyzer.py`, `app.py`

---

### 9.3 Claude Backtest Narrative
Stream a Claude commentary on backtest results after the simulation completes (currently in todo as pending).

- [ ] Pass backtest metrics (total return, Sharpe, max drawdown, win rate, trade log) to Claude
- [ ] Prompt: analyze regime performance, identify periods of outperformance/underperformance, comment on robustness
- [ ] Stream narrative below the equity curve chart

**Files:** `analyzer.py`, `backtest.py`, `pages/6_Backtest.py`

---

### 9.4 Claude Sector Rotation Narrative
Stream a Claude commentary on sector rotation analysis (currently in todo as pending).

- [ ] Pass sector scores, phases, and momentum rankings to Claude
- [ ] Prompt: identify rotation thesis, leading sectors' implications for individual stocks, macro interpretation
- [ ] Stream narrative below the sector heatmap

**Files:** `analyzer.py`, `sectors.py`, `pages/5_Sectors.py`

---

### 9.5 Chat History Trim
Prevent long chat sessions from silently hitting the context window limit.

- [ ] Track approximate token count of chat history (count words × 1.3 as proxy)
- [ ] When history exceeds 80% of context budget, drop oldest turns (keep system prompt + last N exchanges)
- [ ] Show a "Chat history trimmed to fit context" notice when truncation occurs

**Files:** `analyzer.py`, `app.py`

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
| 5 | Relative / Sector-Adjusted Valuation | [ ] Pending |
| 5 | Analyst Estimate Revision Momentum | [ ] Pending |
| 5 | Earnings Calendar Integration | [ ] Pending |
| 5 | Insider Trading Signal | [ ] Pending |
| 5 | Short Interest Tracking | [ ] Pending |
| 5 | Macroeconomic Context Overlay | [ ] Pending |
| 5 | Dividend Yield Factor | [ ] Pending |
| 6 | Fix Look-Ahead Bias in Backtest | [ ] Pending |
| 6 | Parameter Sensitivity Sweep | [ ] Pending |
| 6 | Transaction Cost & Dividend Reinvestment | [ ] Pending |
| 7 | Larger Screener Universe | [ ] Pending |
| 7 | OR-Logic Filter Support | [ ] Pending |
| 7 | Screener Sentiment Warning & Export | [ ] Pending |
| 8 | Liquidity Risk Flag | [ ] Pending |
| 8 | Volatility Regime Detection | [ ] Pending |
| 8 | Live Risk-Free Rate | [ ] Pending |
| 9 | Cache Claude Responses | [ ] Pending |
| 9 | Adaptive System Prompts | [ ] Pending |
| 9 | Claude Backtest Narrative | [ ] Pending |
| 9 | Claude Sector Rotation Narrative | [ ] Pending |
| 9 | Chat History Trim | [ ] Pending |
