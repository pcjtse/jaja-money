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

## Endpoints

### `GET /health`
Returns `{"status": "ok"}`.

### `POST /analyze`
Run a full stock analysis.

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

### `GET /screen`
Natural-language or rule-based stock screening.

```bash
curl "http://localhost:8080/screen?query=tech+stocks+with+low+risk" \
  -H "X-API-Key: your-secret-key"
```

### `GET /portfolio`
Portfolio-level risk and correlation analysis.

```bash
curl "http://localhost:8080/portfolio?symbols=AAPL,MSFT,GOOGL" \
  -H "X-API-Key: your-secret-key"
```

### `POST /chat`
Interactive Q&A about a stock.

```json
{ "symbol": "AAPL", "message": "What is the bull case?" }
```

```bash
curl -X POST http://localhost:8080/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret-key" \
  -d '{"symbol": "AAPL", "message": "What is the bull case?"}'
```

## Docker Compose

```bash
# Start with the API server profile
JAJA_API_KEY=your-secret docker compose --profile server up --build

# Start with Redis + API server
JAJA_API_KEY=your-secret docker compose --profile redis --profile server up --build
```

## Authentication

When `JAJA_API_KEY` is set, every request must include the header:

```
X-API-Key: your-secret-key
```

Requests without a valid key receive `403 Forbidden`.

## Dependencies

```bash
pip install fastapi "uvicorn[standard]"
```
