# REST API Server

The optional FastAPI server (`server.py`) exposes the jaja-money analysis engine as a
standalone REST API — useful for programmatic access, CI pipelines, or integrating with
other tools.

## Starting the server

```bash
uvicorn server:app --host 0.0.0.0 --port 8080
# or simply:
python server.py
```

Interactive OpenAPI docs are available at `http://localhost:8080/docs` once the server is running.

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `JAJA_API_KEY` | _(empty — auth disabled)_ | Set to a secret string to require `X-API-Key` header on every request |
| `JAJA_API_PORT` | `8080` | Listening port |
| `FINNHUB_API_KEY` | _(required)_ | Finnhub API key |
| `ANTHROPIC_API_KEY` | _(required for sdk backend)_ | Anthropic API key |
| `CACHE_BACKEND` | `disk` | `disk` or `redis` |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis URL (when `CACHE_BACKEND=redis`) |

## Authentication

When `JAJA_API_KEY` is set, every request must include the header:

```
X-API-Key: your-secret-key
```

Requests without a valid key receive `403 Forbidden`.
Authentication is disabled when `JAJA_API_KEY` is not set.

---

## Endpoints

### `GET /health`

Server health check. Returns status, version, and configuration flags.

```bash
curl http://localhost:8080/health
```

```json
{
  "status": "ok",
  "timestamp": 1742500000,
  "version": "1.0.0",
  "finnhub_configured": true,
  "anthropic_configured": true
}
```

---

### `POST /analyze`

Full stock analysis — factor scores, risk metrics, financials, and company profile.
Does **not** include AI narrative; use `/analyze/stream` for Claude output.

**Request body:**
```json
{ "symbol": "AAPL" }
```

**Example:**
```bash
curl -X POST http://localhost:8080/analyze \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret-key" \
  -d '{"symbol": "AAPL"}'
```

---

### `POST /analyze/stream`

Stream a Claude AI fundamental analysis report for a stock symbol as plain text.
The response is a `text/plain` streaming body (Server-Sent Events compatible).

```bash
curl -X POST http://localhost:8080/analyze/stream \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret-key" \
  -d '{"symbol": "AAPL"}'
```

---

### `POST /score`

Lightweight factor + risk scores with BUY/HOLD/SELL signal. Faster than `/analyze` —
no AI narrative, scores only.

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

---

### `POST /screen`

Screen a list of tickers against factor and risk thresholds.

```bash
curl -X POST http://localhost:8080/screen \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret-key" \
  -d '{"tickers": ["AAPL", "MSFT", "NVDA"], "min_factor_score": 65, "max_risk_score": 50}'
```

**Request fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `tickers` | list[str] | required | Tickers to screen |
| `min_factor_score` | int | 0 | Minimum composite factor score |
| `max_risk_score` | int | 100 | Maximum risk score |
| `limit` | int | 50 | Maximum results to return |

---

### `POST /portfolio`

Compute portfolio-level risk and correlation metrics.

```bash
curl -X POST http://localhost:8080/portfolio \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret-key" \
  -d '{"tickers": ["AAPL", "MSFT", "GOOGL"], "weights": [0.5, 0.3, 0.2]}'
```

**Request fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `tickers` | list[str] | required | Portfolio tickers |
| `weights` | list[float] | equal-weight | Position weights (must sum to 1) |

---

### `POST /chat`

Stream a Claude conversational response about a stock with full market context.
Supports multi-turn history.

```bash
curl -X POST http://localhost:8080/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret-key" \
  -d '{"symbol": "AAPL", "message": "What is the bull case?", "history": []}'
```

---

### `GET /alerts`

List active and triggered price/signal alerts. Optionally filter by ticker.

```bash
curl "http://localhost:8080/alerts" \
  -H "X-API-Key: your-secret-key"

curl "http://localhost:8080/alerts?symbol=AAPL" \
  -H "X-API-Key: your-secret-key"
```

---

### `POST /signals`

Batch BUY/HOLD/SELL signals with confidence scores for a list of symbols.

```bash
curl -X POST http://localhost:8080/signals \
  -H "Content-Type: application/json" \
  -d '{"symbols": ["AAPL", "MSFT", "NVDA"]}'
```

**Signal logic:**

| Signal | Condition |
|--------|-----------|
| **BUY** | `factor_score >= 65` **and** `risk_score <= 50` |
| **SELL** | `factor_score <= 35` **or** `risk_score >= 75` |
| **HOLD** | everything else |

---

## Forward Test Endpoints

### `POST /forward-test/portfolio`

Create a new named paper portfolio for forward testing.

```bash
curl -X POST http://localhost:8080/forward-test/portfolio \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret-key" \
  -d '{"name": "My Test Portfolio"}'
```

Returns `{"portfolio_id": 1, "name": "My Test Portfolio"}`.

---

### `GET /forward-test/portfolios`

List all existing paper portfolios.

```bash
curl "http://localhost:8080/forward-test/portfolios" \
  -H "X-API-Key: your-secret-key"
```

---

### `POST /forward-test/trade`

Add a position (simulated trade) to a paper portfolio.

```bash
curl -X POST http://localhost:8080/forward-test/trade \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret-key" \
  -d '{
    "portfolio_id": 1,
    "symbol": "AAPL",
    "entry_price": 185.00,
    "shares": 10,
    "factor_score": 72,
    "risk_score": 38
  }'
```

---

### `GET /forward-test/portfolio/{portfolio_id}`

Return full summary for a paper portfolio including positions, trades, and performance stats.

```bash
curl "http://localhost:8080/forward-test/portfolio/1" \
  -H "X-API-Key: your-secret-key"
```

---

## OpenClaw / Agent Skill Endpoints

### `POST /openclaw/agent`

Stream output from the autonomous multi-step research agent (up to 10 turns).

```bash
curl -X POST http://localhost:8080/openclaw/agent \
  -H "Content-Type: application/json" \
  -d '{"symbol": "AAPL", "question": "What is the bull case?"}'
```

---

### `POST /openclaw/webhook`

Incoming webhook receiver for AI agent commands at runtime.

| `event_type` | Required `payload` fields | Action |
|---|---|---|
| `analyze_request` | `symbol` | Runs full analysis and returns signal |
| `alert_request` | `symbol`, `condition`, `threshold` | Creates a price alert |
| `screen_request` | `tickers` | Runs the screener and returns results |

```bash
curl -X POST http://localhost:8080/openclaw/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "analyze_request",
    "payload": {"symbol": "NVDA"},
    "agent_id": "my-agent"
  }'
```

---

### `POST /openclaw/rebalance`

Portfolio drift analysis and rebalancing suggestions.

```bash
curl -X POST http://localhost:8080/openclaw/rebalance \
  -H "Content-Type: application/json" \
  -d '{
    "tickers": ["AAPL", "MSFT"],
    "target_weights": {"AAPL": 0.6, "MSFT": 0.4},
    "current_weights": {"AAPL": 0.72, "MSFT": 0.28}
  }'
```

---

### `GET /openclaw/manifest`

Returns the skill manifest for registry and auto-discovery.

```bash
curl http://localhost:8080/openclaw/manifest
```

---

## Docker Compose

```bash
# Start with the API server profile
JAJA_API_KEY=your-secret docker compose --profile server up --build

# Start with Redis + API server
JAJA_API_KEY=your-secret docker compose --profile redis --profile server up --build
```

## Dependencies

```bash
pip install fastapi "uvicorn[standard]"
```
