# REST API Endpoints

The jaja-money server exposes these endpoints for remote skill mode.
Start the server with:

```bash
uvicorn server:app --host 0.0.0.0 --port 8080
```

## Core Endpoints

### POST /analyze
Full stock analysis with factors, risk, and financials.

```bash
curl -X POST http://localhost:8080/analyze \
  -H "Content-Type: application/json" \
  -d '{"symbol": "AAPL"}'
```

### POST /score
Lightweight factor + risk scores with BUY/HOLD/SELL signal.

```bash
curl -X POST http://localhost:8080/score \
  -H "Content-Type: application/json" \
  -d '{"symbol": "AAPL"}'
```

### POST /screen
Screen tickers against factor and risk thresholds.

```bash
curl -X POST http://localhost:8080/screen \
  -H "Content-Type: application/json" \
  -d '{"tickers": ["AAPL", "MSFT", "NVDA"], "min_factor_score": 65}'
```

### GET /alerts
List active price/signal alerts.

```bash
curl "http://localhost:8080/alerts?symbol=AAPL"
```

### POST /signals
Batch BUY/HOLD/SELL signals with confidence scores.

```bash
curl -X POST http://localhost:8080/signals \
  -H "Content-Type: application/json" \
  -d '{"symbols": ["AAPL", "MSFT"]}'
```

### POST /openclaw/agent
Stream autonomous research agent output.

```bash
curl -X POST http://localhost:8080/openclaw/agent \
  -H "Content-Type: application/json" \
  -d '{"symbol": "AAPL", "question": "What is the bull case?"}'
```

### POST /openclaw/webhook
Incoming webhook receiver for AI agent commands.

Supported `event_type` values:
- `analyze_request` — trigger analysis (requires `payload.symbol`)
- `alert_request` — create price alert (requires `payload.symbol`, `payload.condition`, `payload.threshold`)
- `screen_request` — run screener (requires `payload.tickers`)

### POST /openclaw/rebalance
Portfolio drift analysis and rebalancing suggestions.

```bash
curl -X POST http://localhost:8080/openclaw/rebalance \
  -H "Content-Type: application/json" \
  -d '{"tickers": ["AAPL", "MSFT"], "target_weights": {"AAPL": 0.6, "MSFT": 0.4}}'
```

### GET /openclaw/manifest
Returns the skill manifest for registry/discovery.

### GET /health
Server health check.

## Authentication

Set `JAJA_API_KEY` environment variable on the server to enable API key auth.
Pass the key via `X-API-Key` header or `?api_key=` query parameter.
If `JAJA_API_KEY` is not set, authentication is disabled.
