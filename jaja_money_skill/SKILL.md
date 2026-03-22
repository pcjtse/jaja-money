---
name: jaja-money
description: >
  Multi-factor stock analysis skill powered by Finnhub and Claude AI.
  Provides factor scoring (0-100), risk assessment, BUY/HOLD/SELL signals,
  stock screening, alert management, and autonomous investment research.
  Use this skill when a user asks about stock analysis, investment signals,
  portfolio screening, or market research for specific tickers.
compatibility: >
  Requires Python 3.10+. Network access needed for Finnhub API and
  optional jaja-money REST server. Works with OpenClaw, Claude Code,
  and any agent supporting the Agent Skills standard.
metadata:
  version: "1.0.0"
  author: jaja-money
  category: finance
  license: MIT
---

# jaja-money — Multi-Factor Stock Analysis

Analyze any stock ticker using an 8-factor quantitative scoring engine,
risk guardrail assessment, and Claude AI synthesis. Returns structured
JSON with actionable BUY/HOLD/SELL signals.

## Capabilities

- **analyze** — Full fundamental + risk analysis for a ticker
- **score** — Lightweight factor/risk scores with signal
- **screen** — Filter a list of tickers by factor and risk thresholds
- **get_alerts** — List active price and signal alerts
- **research** — Autonomous multi-step investment research agent

## Operating Modes

### Local Mode (default)

Import the skill functions directly. Requires the jaja-money codebase
and a `FINNHUB_API_KEY` environment variable.

```python
from jaja_money_skill.scripts.jaja_skill import analyze, score, screen

result = analyze("AAPL")
# {'symbol': 'AAPL', 'signal': 'BUY', 'confidence': 74, 'factor_score': 72, ...}
```

### Remote Mode

Set `JAJA_API_URL` to delegate all calls to a running jaja-money REST server.
No local analysis dependencies required — only `requests`.

```bash
export JAJA_API_URL=http://localhost:8080
export JAJA_API_KEY=mysecret   # optional
```

```python
from jaja_money_skill.scripts.jaja_skill import analyze, score
result = analyze("AAPL")   # calls http://localhost:8080/analyze
```

## Signal Logic

| Signal | Condition |
|--------|-----------|
| **BUY** | `factor_score >= 65` AND `risk_score <= 50` |
| **SELL** | `factor_score <= 35` OR `risk_score >= 75` |
| **HOLD** | everything else |

Confidence is calculated as a weighted blend of factor and risk scores,
capped at 100.

## Factor Scoring

Eight factors are scored 0–100 and weighted into a composite signal:

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

## Risk Assessment

Four risk dimensions produce an overall Risk Score (Low → Extreme) with
13 red-flag alerts for volatility, drawdown, overbought/oversold RSI,
downtrend conditions, high P/E, earnings miss rate, and negative analyst
sentiment.

## Event Scheduler

Monitor tickers for market events using the event scheduler:

```python
from jaja_money_skill.scripts.jaja_events import (
    register_event_callback,
    start_event_scheduler,
)

def on_earnings(event):
    print(f"Earnings soon for {event['symbol']}")

register_event_callback("earnings_approaching", on_earnings)
start_event_scheduler(tickers=["AAPL", "MSFT"], interval_seconds=300)
```

Supported events: `earnings_approaching`, `new_sec_filing`, `price_alert_triggered`.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `FINNHUB_API_KEY` | Yes (local mode) | Finnhub market data API key |
| `ANTHROPIC_API_KEY` | For research | Claude AI for analysis narratives |
| `JAJA_API_URL` | Remote mode | URL of jaja-money server |
| `JAJA_API_KEY` | No | API key for server authentication |

## Output Format

All functions return structured JSON dicts. See `references/api_schema.md`
for full response schemas.

## Scripts

- `scripts/jaja_skill.py` — Core skill functions (analyze, score, screen, get_alerts, research)
- `scripts/jaja_events.py` — Event-triggered analysis scheduler
- `scripts/jaja_client.py` — HTTP client for remote mode

## References

- `references/api_schema.md` — Full API response schemas
- `references/endpoints.md` — REST API endpoint documentation
