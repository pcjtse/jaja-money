# Service Quality Assessment: jaja-money

**Date:** 2026-03-24
**Scope:** Full codebase review (~22,000 lines of Python across 45+ source files)
**Objective:** Determine whether this service performs real, meaningful work or is superficial slop.

---

## Overall Rating: 6.5 / 10

---

## Executive Summary

jaja-money is a Streamlit-based stock analysis dashboard that combines technical indicators, fundamental data, sentiment analysis (via FinBERT), and Claude AI commentary into a unified research tool. The codebase contains **real algorithmic substance** in its core analysis engine and is not outright slop. However, the service is best described as a **well-assembled glue layer** — it stitches together third-party APIs and standard textbook indicators rather than implementing novel analysis. The code is competent but the value proposition is thin: most of what it computes is available in any free stock screener.

---

## Module-by-Module Findings

### Core Infrastructure (`src/core/`) — Legitimate

| File | Verdict | Notes |
|------|---------|-------|
| `config.py` | Real work | YAML config loading with recursive deep-merge. Functional singleton pattern. |
| `cache.py` | Real work | Disk + Redis backends with TTL, pickle serialization, sentinel pattern for cached `None`. Production-grade. |
| `rate_limiter.py` | Real work | Token bucket algorithm with thread-safe locking. Correct refill math. |
| `log_setup.py` | Real work | Rotating file handler, hierarchical loggers. Standard but necessary. |

**Assessment:** The infrastructure layer is solid and shows engineering discipline. No complaints here.

### Data Layer (`src/data/`) — Functional but Heavily Guarded

| File | Verdict | Notes |
|------|---------|-------|
| `api.py` | Real work | Finnhub wrapper with exponential backoff, cache integration, rate limiting. The `get_earnings_calendar()` function does real implied-move math from ATM straddle pricing. |
| `providers.py` | Real work | Finnhub → yfinance → Alpha Vantage fallback chain with source normalization. Handles cross-library schema differences. |
| `mock_data.py` | Test fixture | Seeded random data generators for all endpoints. Properly gated behind `MOCK_DATA=1`. |
| `sentiment.py` | Mixed | Loads ProsusAI/finbert (real transformer model) for sentiment scoring with impact-weighted aggregation. Falls back to keyword matching in mock mode. The real path does genuine NLP work. |
| `ownership.py` | Real work | Institutional concentration analysis, insider transaction classification, short-selling composite score combining three bearish signals. |
| `social.py` | Real work | Social sentiment aggregation. |
| `edgar.py` | Real work | SEC EDGAR filing fetcher. |
| `history.py` | Real work | Historical data management. |

**Assessment:** The data layer is the strongest part of the codebase. API integration is done correctly with retries, caching, and fallbacks. The mock data system is well-structured and clearly separated from production paths. The heavy `try/except → return empty dict` pattern in optional data fetchers (ownership, social) is defensible since this data is supplementary, but it does mean failures are silently swallowed.

### Analysis Engine (`src/analysis/`) — Real Math, Textbook Implementation

| File | Verdict | Notes |
|------|---------|-------|
| `factors.py` | Real work | 8-factor composite scoring: P/E valuation, SMA trend, RSI momentum, MACD, sentiment, earnings quality, analyst consensus, 52-week strength. Also implements Bollinger Bands, OBV, Fibonacci retracements, VWAP. |
| `guardrails.py` | Real work | 4-dimension risk scoring (volatility, drawdown, signal, regime) with 13 structured alert types. Correct log-return volatility annualization. |
| `backtest.py` | Real work | Walk-forward backtesting with slippage, commission modeling, and no look-ahead bias. Computes Sharpe, CAGR, max drawdown, win rate. |
| `analyzer.py` | Real work | Claude AI integration with stock-type classification (Growth/Value/Dividend/Cyclical/Defensive) that adapts system prompts. Response caching with TTL. |
| `forward_test.py` | Real work | SQLite-backed paper trading with position management and equity curve snapshots. |
| `portfolio_analysis.py` | Real work | Portfolio-level analytics. |
| `comparison.py` | Real work | Multi-stock comparison logic. |
| `pairs.py` | Real work | Pairs trading analysis. |
| `pead.py` | Real work | Post-earnings announcement drift analysis. |
| `options_analysis.py` | Real work | Options analytics. |
| `document_analysis.py` | Real work | Document/transcript analysis via Claude. |

**Assessment:** The analysis engine does real quantitative work. The factor scoring system uses genuine financial logic — P/E ranges map to sensible scores, SMA crossover detection is correct, RSI computation follows the standard Wilder smoothing approach, MACD histogram analysis considers both direction and acceleration. The backtester properly models transaction costs and avoids look-ahead bias.

**However:** Every single indicator here is textbook. There is zero alpha in this analysis. The P/E scoring uses hardcoded bracket thresholds (P/E < 15 = 88 points, etc.) that are simplistic. The factor weights are configurable but ship with naive defaults. The composite score is a weighted average — there is no machine learning, no adaptive weighting, no regime-conditional logic. Any quant would recognize this as a teaching exercise, not a production trading system.

### Trading Layer (`src/trading/`) — Intentionally Neutered

| File | Verdict | Notes |
|------|---------|-------|
| `broker.py` | Deliberately limited | Alpaca integration is **read-only by design**. `TRADING_DISABLED = True` is hardcoded. `execute_signal()` always returns a simulation dict regardless of `dry_run` flag. Account and position reads are real. |
| `portfolio.py` | Real work | Position sizing with risk-tolerance scaling, volatility-normalized stop-losses, factor-score-based allocation multipliers. |
| `screener.py` | Real work | Rule-based stock screening with AND/OR filter logic, S&P 500 / Russell 1000 universe support, saved templates. |
| `sectors.py` | Real work | Sector rotation analysis. |
| `watchlist.py` | Real work | Watchlist management. |

**Assessment:** The trading layer is honest about what it is — a simulation/research tool. The broker module explicitly documents that live trading is disabled. Position sizing math is sound (volatility-normalized stops using `daily_vol * sqrt(14) * z_mult` is a legitimate Kelly-adjacent approach). The screener does real work but is nothing you can't get from Finviz for free.

### Services Layer (`src/services/`) — The AI Integration

| File | Verdict | Notes |
|------|---------|-------|
| `agent.py` | Real work | Multi-turn agentic loop where Claude calls 8 tools (get_quote, get_financials, get_news, etc.) autonomously. Capped at 8 turns / 30 API calls for cost control. |
| `server.py` | Real work | FastAPI REST API with 10+ endpoints, per-endpoint rate limiting, optional API key auth, CORS config, streaming responses. |
| `digest.py` | Real work | Digest/summary generation. |

**Assessment:** The agent mode is genuinely interesting — it gives Claude tool-calling authority to research a stock autonomously, which is a meaningful feature beyond simple prompt engineering. The REST server is production-shaped with proper rate limiting and auth. This is the most differentiated part of the codebase.

### UI Layer (`src/ui/`, `pages/`, `app.py`) — Functional Dashboard

| File | Verdict | Notes |
|------|---------|-------|
| `app.py` | Real work | Main Streamlit app (~3000 lines). Proper caching, interactive Plotly charts, multi-page navigation. |
| `pages/*.py` | Real work | Compare, Screener, Portfolio, Sectors, Backtest, ForwardTest pages. |
| `theme.py` | Polish | Dark mode toggle. |
| `export.py` | Real work | CSV/HTML/PDF export functionality. |
| `alerts.py` | Real work | APScheduler-based alert system with webhook delivery (Slack/Discord/Telegram). |
| `ui_prefs.py` | Polish | UI preference management. |

**Assessment:** The UI is a competent Streamlit application. Nothing extraordinary, but it ties all the analysis modules together into a usable interface.

---

## Slop Indicators Checked

| Red Flag | Present? | Evidence |
|----------|----------|----------|
| Functions that always return the same value regardless of input | No | Factor scores vary with actual price/financial data |
| Hardcoded mock data used in production | No | Mock data is gated behind `MOCK_DATA=1` env var |
| Try/except swallowing all errors silently | Partially | Optional data fetchers (ownership, social) catch broadly and return empty dicts, but errors are logged |
| Functions that don't do what they claim | No | Implementations match docstrings |
| Excessive boilerplate wrapping trivial operations | No | Code is reasonably proportional to complexity |
| Dead code / unused functions | No | All modules appear to be wired into the app |
| AI-generated filler comments | No | Comments are sparse and relevant |
| Circular or nonsensical logic | No | Control flow is straightforward |

---

## What Lowers the Score

1. **No novel analysis.** Every technical indicator (RSI, MACD, SMA, Bollinger Bands, OBV, VWAP, Fibonacci) is a textbook implementation. The factor scoring uses hardcoded P/E brackets. There is no proprietary edge, no machine learning, no adaptive models. This is a dashboard, not an alpha generator.

2. **The composite score is naive.** A weighted average of 8 factors with static weights is the simplest possible aggregation method. There is no cross-factor interaction modeling, no non-linear combination, no regime-conditional weighting. The score is essentially a human-readable summary of standard indicators, not a predictive signal.

3. **Trading is completely disabled.** The broker integration is read-only by design. `execute_signal()` is a no-op that returns a simulation dict. This means the entire "trading" layer is aspirational — the service analyzes but cannot act. Whether this is a flaw or a feature depends on your perspective, but it does mean the service is purely informational.

4. **Heavy reliance on third-party APIs.** The service is fundamentally a presentation layer over Finnhub, yfinance, and Claude. Without API keys, it falls back to mock data. The actual "work" is done by external services; jaja-money's contribution is aggregation and display.

5. **RSI/SMA/MACD are reimplemented in multiple files.** `factors.py` and `guardrails.py` both contain their own `_rsi()` and `_sma()` functions. This duplication suggests the codebase grew organically without refactoring.

6. **The AI analysis is a black box.** The Claude integration sends a prompt with financial data and gets back prose. The quality of the analysis depends entirely on Claude, not on jaja-money's code. The stock-type classification that adapts prompts is a nice touch, but the actual analytical heavy lifting is outsourced.

## What Raises the Score

1. **The analysis engine does real math.** Factor scoring, risk assessment, backtesting, volatility regime detection — these are genuine computations that produce different outputs for different inputs. This is not a static template.

2. **Infrastructure is production-grade.** Disk/Redis caching, token bucket rate limiting, exponential backoff retries, structured logging, API key auth — the operational foundation is solid.

3. **The agent mode is genuinely useful.** Giving Claude autonomous research authority with real data tools is a meaningful feature that goes beyond what most stock dashboards offer.

4. **Data fallback chain is well-engineered.** Finnhub → yfinance → Alpha Vantage with schema normalization shows real thought about reliability.

5. **The backtester avoids common pitfalls.** No look-ahead bias, proper transaction cost modeling, walk-forward validation — this is correctly implemented even if the signals it tests are basic.

6. **Honest about its limitations.** The broker module explicitly states trading is disabled. The mock data module is clearly labeled. There's no pretense of being more than it is.

---

## Conclusion

jaja-money is a **legitimate but unremarkable** stock analysis dashboard. It does real work — computing technical indicators, scoring stocks on multiple factors, assessing risk, running backtests, and integrating AI commentary. The code is competent, the architecture is reasonable, and the infrastructure is production-grade.

But it is not novel. Every indicator is textbook. The composite scoring is a simple weighted average. Trading is disabled. The most interesting feature — the autonomous Claude research agent — outsources the actual analytical thinking to a third-party LLM. The service is essentially a well-built **aggregation and presentation layer** over Finnhub + yfinance + Claude, not an independent analytical engine.

It works. It's not slop. But it's also not doing anything you couldn't replicate with a Jupyter notebook and the same API keys in an afternoon.

**Rating: 6.5 / 10**
