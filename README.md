# jaja-money

[![CI](https://github.com/pcjtse/jaja-money/actions/workflows/ci.yml/badge.svg)](https://github.com/pcjtse/jaja-money/actions/workflows/ci.yml)

**The Bloomberg Terminal charges $25,000 per seat per year. It doesn't use AI. It doesn't measure whether its signals work. And it hasn't changed fundamentally in 30 years.**

jaja-money is what institutional stock research looks like when you build it from scratch in 2026 — a 24-factor quantitative scoring engine, Claude AI synthesis, a closed-loop signal validation system that measures real alpha, and an autonomous strategy optimizer that improves overnight while you sleep.

> ⚠️ **Investment Disclaimer** — jaja-money is a research and educational tool only. Nothing in this application constitutes financial, investment, or trading advice. Always consult a qualified financial advisor before making any investment decisions. Past performance shown in backtests does not guarantee future results.

---

## The Market

**100+ million** retail investors in the US alone. **$30 trillion** in assets managed by RIAs and family offices. **$6 billion** in annual Bloomberg Terminal revenue — from a product that charges $25,000 per seat for infrastructure that predates the smartphone.

The AI inflection point changes the economics of research entirely. Tasks that previously required a team of quant analysts — factor scoring, risk modeling, SEC filing analysis, signal backtesting, strategy optimization — now run in seconds. The question is no longer whether institutional-grade research can be democratized. It's who builds the platform that does it.

Incumbents can't retrofit AI onto 30-year-old architecture without rebuilding from scratch. We built from scratch.

---

## What We Built

**1. A 24-factor quantitative signal engine.** Valuation (sector-relative), price trend, momentum, news sentiment, earnings quality, analyst consensus, executive tone linguistic analysis, alternative data (Google Trends, job-posting velocity), dark pool activity, congressional STOCK Act disclosures, institutional 13F flow, options sweep, supply chain concentration, geographic revenue risk, and market regime — each scored 0–100, composited into a single Buy/Hold/Sell signal with an ML weighting layer.

**2. An AI research layer powered by Claude.** Not a chatbot on top of a data feed. An analyst that reads SEC 10-K and 10-Q filings directly from EDGAR, synthesizes earnings call transcripts, analyzes how executives actually speak — their confidence, hedging language, guidance specificity, and tone shift quarter-over-quarter — and generates live 12-month price targets with bull/bear scenarios.

**3. A signal validation loop.** Every signal is tracked against actual forward returns at T+21, T+63, and T+126 trading days. Spearman IC measures whether composite scores predict returns. Benjamini-Hochberg correction identifies which of the 24 factors contribute genuine alpha — and which are noise. Most platforms generate signals and never look back. This one closes the loop.

**4. A self-improving strategy engine.** The backtesting system is wired into an autonomous optimization loop modelled on [Andrej Karpathy's autoresearch](https://github.com/karpathy/autoresearch) framework. A Claude Code agent iterates strategy variants overnight — roughly 12 experiments per hour — keeping Sharpe improvements and reverting regressions automatically. The strategy compounds through machine experimentation, not manual quarterly tuning.

---

## Screenshots

| Main Dashboard | Stock Analysis |
|----------------|----------------|
| ![Homepage](screenshots/01_homepage.png) | ![Analysis](screenshots/02_aapl_analysis.png) |

| Compare Stocks | Stock Screener |
|----------------|----------------|
| ![Compare](screenshots/03_compare.png) | ![Screener](screenshots/04_screener.png) |

| Portfolio Analysis | Sector Rotation |
|--------------------|-----------------|
| ![Portfolio](screenshots/05_portfolio.png) | ![Sectors](screenshots/06_sectors.png) |

| Strategy Backtesting | Forward Testing |
|----------------------|-----------------|
| ![Backtest](screenshots/07_backtest.png) | ![Forward Test](screenshots/forward_test.png) |

| Daily Rankings | Signal Quality |
|----------------|----------------|
| ![Rankings](screenshots/rankings.png) | ![Signal Quality](screenshots/signal_quality.png) |

---

## Why This Wins

Bloomberg's moat is data access and switching costs — not analytical depth. Their terminals were designed before machine learning existed and patched forward. Adding AI to that architecture is like adding autonomous driving to a 1995 car. You can bolt sensors on, but the fundamental systems weren't designed for it.

We designed for AI from day one. Every layer was built to compound.

### Three Defensible Moats

**Signal validation data accumulates and becomes proprietary.** Every signal becomes a data point in the IC dataset. After a year of use, the system has a proprietary record of which signals predicted returns, in which sectors, under which regimes. No competitor can replicate this retroactively. The longer it runs, the better calibrated the weights become.

**The autoresearch loop creates a compounding strategy advantage.** 100 experiments overnight vs. a human researcher's quarterly tune. Each improvement is committed to version control. That gap compounds.

**The 24-factor signal depth took years to build.** Executive tone linguistic analysis, congressional STOCK Act parsing, dark pool FINRA ATS detection, supply chain concentration from 10-K text, SEC EDGAR diffing across quarters — each required real engineering investment. The validation dataset will prove which signals actually work, and that data belongs only to us.

### Why Now

Claude crossed the threshold where it can read an SEC 10-K, synthesize an earnings call, analyze how a CEO hedges their language versus last quarter, and produce a credible investment memo in seconds. The cost of that dropped to near zero. Neither was true 18 months ago. The window is open now.

---

## The Platform

| Module | What It Does |
|--------|--------------|
| **Main Analysis** | 24-factor score, 30+ risk alerts, live AI research report, and price target for any ticker |
| **Compare** | Side-by-side factor scores, risk, P/E, RSI for up to 5 stocks with correlation heatmap |
| **Screener** | Filter any universe with AND/OR logic and Claude natural-language queries |
| **Portfolio** | Monte Carlo simulation, Kelly criterion sizing, factor attribution |
| **Sectors** | Relative strength across all 11 S&P 500 sector ETFs with rotation phase classification |
| **Backtest** | Walk-forward simulation, Sharpe ratio, max drawdown, parameter sweep, autoresearch optimizer |
| **Forward Test** | Paper portfolio tracking live P&L and factor scores at entry |
| **Rankings** | Daily long/short leaderboard with AI thesis for top candidates |
| **Signal Quality** | Spearman IC at T+21/T+63/T+126 — empirical proof the score predicts returns |
| **Factor Attribution** | Per-factor IC with 95% CI and Benjamini-Hochberg correction |
| **Ledger** | Tamper-evident signal ledger; generates signal decay curves after 20+ closed trades |

---

## Technical Depth

### 24-Factor Signal Engine

Factors span five categories, each scored 0–100 and weighted into a composite:

- **Price & Technical** — SMA trend (50/200), RSI momentum, MACD histogram, Bollinger Band position, 52-week strength
- **Fundamental** — Sector-adjusted valuation, earnings quality, estimate revisions, analyst consensus, dividend yield, guidance quality, buyback effectiveness
- **Executive Tone** — Claude AI linguistic analysis of earnings call transcripts: confidence, hedging density, transparency, guidance specificity, and quarter-over-quarter tone shift
- **Alternative Data** — Google Trends slope, job-posting velocity, dark pool FINRA ATS volume, congressional STOCK Act disclosures, institutional 13F flow, options sweep/gamma
- **Structural & Regime** — Supply chain concentration (10-K), geographic revenue risk (SEC text), special situations, cross-asset momentum, 5-state regime classifier

Weights are configurable in `config.yaml` and can be replaced by the ML adaptive weighting module, which derives optimal weights from the accumulated IC validation dataset.

### Self-Improving Backtesting (AutoResearch)

1. Agent reads `autoresearch/program.md` (research brief) and `autoresearch/strategy_runner.py` (current strategy)
2. Proposes one targeted modification based on `autoresearch/results.tsv`
3. Runs `autoresearch/evaluate.py` (fixed harness — agent cannot modify it)
4. Sharpe improves: commits and logs. Sharpe regresses: reverts and logs.
5. Repeat — ~12 experiments per hour, 100+ overnight

### Signal Validation Architecture

```
Daily Batch (7am UTC)
  → Score every watchlist ticker (24 factors)
  → Save to signal_returns with entry price

Nightly Forward Return Fill
  → Fetch current price for signals T+21/T+63/T+126 days old
  → Compute and store actual return

Signal Quality Page
  → Spearman IC per horizon
  → Factor Attribution with Benjamini-Hochberg correction
  → Rolling IC trend (detects signal decay)
```

### API-First Architecture

```python
from jaja_money_skill.scripts.jaja_skill import analyze, screen, research

result = analyze("AAPL")
# {'symbol': 'AAPL', 'signal': 'BUY', 'factor_score': 72, 'risk_score': 28, ...}

hits = screen(["AAPL", "MSFT", "NVDA", "GOOGL"], min_factor_score=65, max_risk_score=50)

memo = research("TSLA", question="What is the bear case for the next 12 months?")
```

---

## Quick Start

**Requirements:** Python 3.10+, [Finnhub API key](https://finnhub.io) (free tier), [Anthropic API key](https://console.anthropic.com)

```bash
git clone https://github.com/pcjtse/jaja-money.git
cd jaja-money
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # add FINNHUB_API_KEY and ANTHROPIC_API_KEY
streamlit run app.py
```

Open `http://localhost:8501`, enter any ticker, click **Analyze**.

```bash
# Docker
cp .env.example .env
docker compose up --build
```

> If you have the [Claude Code CLI](https://claude.ai/code) installed, set `ai_backend: "cli"` in `config.yaml` — no `ANTHROPIC_API_KEY` needed.

### Run the AutoResearch Optimizer

```bash
python autoresearch/evaluate.py   # baseline Sharpe measurement
# Then in Claude Code: /loop
# Agent iterates strategy_runner.py overnight, logs results to autoresearch/results.tsv
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `FINNHUB_API_KEY` | Yes | Finnhub market data |
| `ANTHROPIC_API_KEY` | Yes* | Claude AI (*or use `ai_backend: cli`) |
| `JAJA_API_KEY` | No | Protects REST API endpoints |
| `JAJA_API_URL` | Remote mode | URL of jaja-money server |
| `ALPACA_API_KEY` | Monitoring | Read-only Alpaca account monitoring |
| `ALPACA_API_SECRET` | Monitoring | Alpaca API secret |

---

*For REST API documentation, see [REST_API.md](REST_API.md).*
