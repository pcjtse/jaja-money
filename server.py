"""FastAPI REST API Server (P14.3).

Exposes the jaja-money analysis engine as a REST API for integration
with other tools and services.

Endpoints:
  POST /analyze        — Full stock analysis
  GET  /screen         — Stock screener
  GET  /portfolio      — Portfolio analysis
  POST /chat           — Chat with Claude about a stock
  GET  /health         — Health check
  GET  /docs           — OpenAPI documentation (auto-generated)

Auth: API key via X-API-Key header or ?api_key= query parameter.

Usage:
    uvicorn server:app --host 0.0.0.0 --port 8080
    or:
    python server.py
"""

from __future__ import annotations

import os
import time

from dotenv import load_dotenv

load_dotenv()

try:
    from fastapi import FastAPI, HTTPException, Depends, Security
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.security.api_key import APIKeyHeader, APIKeyQuery
    from fastapi.responses import StreamingResponse
    from pydantic import BaseModel, Field

    _HAS_FASTAPI = True
except ImportError:
    _HAS_FASTAPI = False
    raise ImportError("FastAPI not installed. Run: pip install fastapi uvicorn")

from log_setup import get_logger  # noqa: E402
from rate_limiter import TokenBucketRateLimiter  # noqa: E402

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Per-endpoint server-side rate limiting
# ---------------------------------------------------------------------------

_server_limiter = TokenBucketRateLimiter(
    max_tokens=30, refill_period=60.0, name="server"
)
_heavy_limiter = TokenBucketRateLimiter(
    max_tokens=5, refill_period=60.0, name="server_heavy"
)


def _check_rate_limit(limiter: TokenBucketRateLimiter) -> None:
    """Acquire a token or raise 429."""
    if not limiter.try_acquire():
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Please try again shortly.",
        )


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="jaja-money API",
    description="Multi-factor stock analysis engine powered by Claude AI and Finnhub",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

_CORS_ORIGINS = os.getenv(
    "JAJA_CORS_ORIGINS", "http://localhost:8501,http://localhost:3000"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# API Key authentication
# ---------------------------------------------------------------------------

_API_KEY = os.getenv("JAJA_API_KEY", "")
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_api_key_query = APIKeyQuery(name="api_key", auto_error=False)


async def _get_api_key(
    header_key: str | None = Security(_api_key_header),
    query_key: str | None = Security(_api_key_query),
) -> str:
    """Validate API key. If JAJA_API_KEY is not set, auth is disabled."""
    if not _API_KEY:
        return "no_auth"
    key = header_key or query_key
    if key != _API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return key


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class AnalyzeRequest(BaseModel):
    symbol: str = Field(..., description="Stock ticker symbol (e.g., AAPL)")
    use_cache: bool = Field(True, description="Use cached data if available")


class ChatRequest(BaseModel):
    symbol: str = Field(..., description="Stock ticker symbol")
    message: str = Field(..., description="User message / question")
    history: list[dict] = Field(default=[], description="Previous conversation turns")


class ScreenRequest(BaseModel):
    tickers: list[str] = Field(..., description="List of tickers to screen")
    min_factor_score: int = Field(0, ge=0, le=100)
    max_risk_score: int = Field(100, ge=0, le=100)
    limit: int = Field(20, ge=1, le=100)


class PortfolioRequest(BaseModel):
    tickers: list[str] = Field(..., description="Portfolio tickers")
    weights: list[float] | None = Field(
        None, description="Portfolio weights (sum to 1)"
    )


class ForwardPortfolioRequest(BaseModel):
    name: str = Field(..., description="Portfolio name")


class ForwardTradeRequest(BaseModel):
    portfolio_id: int = Field(..., description="Target portfolio ID")
    symbol: str = Field(..., description="Stock ticker symbol")
    entry_price: float = Field(..., gt=0, description="Entry price per share")
    factor_score: int | None = Field(None, ge=0, le=100)
    risk_score: int | None = Field(None, ge=0, le=100)
    shares: float = Field(1.0, gt=0, description="Number of shares")


class SignalsRequest(BaseModel):
    symbols: list[str] = Field(..., description="Stock ticker symbols", max_length=20)


class OpenClawWebhookRequest(BaseModel):
    event_type: str = Field(..., description="OpenClaw event type")
    payload: dict = Field(default={}, description="Event payload")
    agent_id: str | None = Field(None, description="Originating OpenClaw agent ID")


class RebalanceRequest(BaseModel):
    tickers: list[str] = Field(..., description="Portfolio tickers", max_length=30)
    target_weights: dict[str, float] = Field(
        ..., description="Target weights per ticker (sum to 1)"
    )
    current_weights: dict[str, float] | None = Field(
        None, description="Current weights per ticker (computed if omitted)"
    )


class AgentRequest(BaseModel):
    symbol: str = Field(..., description="Stock ticker to research")
    question: str = Field(
        default=(
            "Produce a comprehensive investment memo with bear, base, and bull case."
        ),
        description="Research question or objective",
    )


class ScoreRequest(BaseModel):
    symbol: str = Field(..., description="Stock ticker symbol (e.g., AAPL)")


# ---------------------------------------------------------------------------
# Lazy API/analyzer initialization
# ---------------------------------------------------------------------------

_api_instance = None
_api_error = None


def _get_api():
    global _api_instance, _api_error
    if _api_error:
        raise HTTPException(
            status_code=503, detail=f"API initialization failed: {_api_error}"
        )
    if _api_instance is None:
        try:
            from api import get_api

            _api_instance = get_api()
        except Exception as exc:
            _api_error = str(exc)
            raise HTTPException(
                status_code=503, detail=f"API initialization failed: {exc}"
            )
    return _api_instance


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "timestamp": int(time.time()),
        "version": "1.0.0",
        "finnhub_configured": bool(os.getenv("FINNHUB_API_KEY")),
        "anthropic_configured": bool(os.getenv("ANTHROPIC_API_KEY")),
    }


@app.post("/analyze")
async def analyze(
    req: AnalyzeRequest,
    _key: str = Depends(_get_api_key),
):
    """Full stock analysis: factors, risk, financials, profile.

    Returns a JSON object with all computed metrics.
    Does not include AI narrative (use /analyze/stream for streaming).
    """
    _check_rate_limit(_server_limiter)
    api = _get_api()
    symbol = req.symbol.upper()

    try:
        from factors import compute_factors
        from guardrails import compute_risk

        # Use parallel fetch if available
        data = api.fetch_all_parallel(symbol)
        if isinstance(data.get("quote"), Exception):
            raise HTTPException(status_code=404, detail=f"No data found for {symbol}")

        quote = data["quote"]
        profile = data.get("profile") or {}
        financials = data.get("financials") or {}
        daily = data.get("daily") or {}
        news = data.get("news") or []

        factors_result = compute_factors(symbol, quote, financials, daily, news)
        risk_result = compute_risk(symbol, quote, financials, daily, news)

        return {
            "symbol": symbol,
            "name": profile.get("name", ""),
            "sector": profile.get("finnhubIndustry", ""),
            "price": quote.get("c"),
            "change_pct": quote.get("dp"),
            "factor_score": factors_result.get("composite_score"),
            "composite_label": factors_result.get("composite_label"),
            "risk_score": risk_result.get("risk_score"),
            "risk_level": risk_result.get("risk_level"),
            "factors": factors_result.get("factors", []),
            "flags": risk_result.get("flags", []),
            "latency": data.get("latency_breakdown", {}),
        }
    except HTTPException:
        raise
    except Exception as exc:
        log.error("Analyze failed for %s: %s", symbol, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/analyze/stream")
async def analyze_stream(
    req: AnalyzeRequest,
    _key: str = Depends(_get_api_key),
):
    """Stream Claude AI analysis for a stock symbol."""
    _check_rate_limit(_server_limiter)
    api = _get_api()
    symbol = req.symbol.upper()

    try:
        from factors import compute_factors
        from guardrails import compute_risk
        from analyzer import stream_fundamental_analysis, classify_stock_type

        data = api.fetch_all_parallel(symbol)
        quote = data.get("quote") or {}
        financials = data.get("financials") or {}
        daily = data.get("daily") or {}
        news = data.get("news") or []
        profile = data.get("profile") or {}

        factors_result = compute_factors(symbol, quote, financials, daily, news)
        risk_result = compute_risk(symbol, quote, financials, daily, news)

        stock_type = classify_stock_type(
            sector=profile.get("finnhubIndustry"),
            pe_ratio=financials.get("peBasicExclExtraTTM"),
            div_yield=financials.get("dividendYieldIndicatedAnnual"),
        )

        def _generate():
            for chunk in stream_fundamental_analysis(
                symbol=symbol,
                quote=quote,
                financials=financials,
                factors=factors_result,
                risk=risk_result,
                news=news,
                stock_type=stock_type,
            ):
                yield chunk

        return StreamingResponse(_generate(), media_type="text/plain")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/screen")
async def screen(
    req: ScreenRequest,
    _key: str = Depends(_get_api_key),
):
    """Screen a list of tickers against factor and risk thresholds."""
    _check_rate_limit(_heavy_limiter)
    api = _get_api()

    try:
        from screener import run_screener

        results = run_screener(
            tickers=req.tickers,
            api=api,
            min_factor_score=req.min_factor_score,
            max_risk_score=req.max_risk_score,
        )
        return {"results": results[: req.limit], "total": len(results)}
    except Exception as exc:
        log.error("Screener failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/portfolio")
async def portfolio(
    req: PortfolioRequest,
    _key: str = Depends(_get_api_key),
):
    """Compute portfolio-level risk and correlation metrics."""
    api = _get_api()

    try:
        from portfolio_analysis import analyze_portfolio

        tickers = [t.upper() for t in req.tickers]
        n = len(tickers)

        if req.weights:
            weights = req.weights
            if len(weights) != n:
                raise HTTPException(
                    status_code=400, detail="weights length must match tickers"
                )
        else:
            weights = [1 / n] * n

        result = analyze_portfolio(tickers, weights, api)

        # Serialize DataFrames
        corr = result.get("correlation")
        return {
            "tickers": result["tickers"],
            "weights": result["weights"],
            "stats": result["stats"],
            "portfolio_beta": result["portfolio_beta"],
            "correlation": corr.to_dict()
            if corr is not None and not corr.empty
            else {},
        }
    except HTTPException:
        raise
    except Exception as exc:
        log.error("Portfolio failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/chat")
async def chat(
    req: ChatRequest,
    _key: str = Depends(_get_api_key),
):
    """Stream a Claude chat response about a stock."""
    _check_rate_limit(_server_limiter)
    api = _get_api()
    symbol = req.symbol.upper()

    try:
        from factors import compute_factors
        from guardrails import compute_risk
        from analyzer import stream_chat_response, build_chat_system_prompt

        data = api.fetch_all_parallel(symbol)
        quote = data.get("quote") or {}
        financials = data.get("financials") or {}
        daily = data.get("daily") or {}
        news = data.get("news") or []

        factors_result = compute_factors(symbol, quote, financials, daily, news)
        risk_result = compute_risk(symbol, quote, financials, daily, news)

        system_prompt = build_chat_system_prompt(
            symbol=symbol,
            quote=quote,
            financials=financials,
            factors=factors_result,
            risk=risk_result,
            news=news,
        )

        def _generate():
            for chunk in stream_chat_response(
                message=req.message,
                conversation_history=req.history,
                system_prompt=system_prompt,
            ):
                yield chunk

        return StreamingResponse(_generate(), media_type="text/plain")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# P22.1: Forward Test endpoints
# ---------------------------------------------------------------------------


@app.post("/forward-test/portfolio")
async def forward_test_portfolio(
    req: ForwardPortfolioRequest,
    _key: str = Depends(_get_api_key),
):
    """Create a new paper portfolio for forward testing.

    Returns the new portfolio's id and name.
    """
    try:
        from forward_test import create_portfolio

        portfolio_id = create_portfolio(req.name)
        return {"portfolio_id": portfolio_id, "name": req.name}
    except Exception as exc:
        log.error("Failed to create forward-test portfolio: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/forward-test/portfolios")
async def forward_test_list_portfolios(
    _key: str = Depends(_get_api_key),
):
    """List all paper portfolios."""
    try:
        from forward_test import list_portfolios

        return {"portfolios": list_portfolios()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/forward-test/trade")
async def forward_test_trade(
    req: ForwardTradeRequest,
    _key: str = Depends(_get_api_key),
):
    """Add a new position to a paper portfolio.

    Returns the trade id and a snapshot of the current portfolio value.
    """
    try:
        from forward_test import add_position, snapshot_portfolio

        trade_id = add_position(
            portfolio_id=req.portfolio_id,
            symbol=req.symbol,
            entry_price=req.entry_price,
            factor_score=req.factor_score,
            risk_score=req.risk_score,
            shares=req.shares,
        )
        snapshot_portfolio(req.portfolio_id, {req.symbol.upper(): req.entry_price})
        return {
            "trade_id": trade_id,
            "portfolio_id": req.portfolio_id,
            "symbol": req.symbol.upper(),
            "entry_price": req.entry_price,
            "shares": req.shares,
        }
    except Exception as exc:
        log.error("Failed to add forward-test trade: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/forward-test/portfolio/{portfolio_id}")
async def forward_test_summary(
    portfolio_id: int,
    _key: str = Depends(_get_api_key),
):
    """Return full summary for a paper portfolio including positions, trades, and stats."""
    try:
        from forward_test import get_portfolio_summary

        summary = get_portfolio_summary(portfolio_id)
        return summary
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# /score endpoint — lightweight factor + risk scores for OpenClaw skill
# ---------------------------------------------------------------------------


@app.post("/score", tags=["openclaw"])
async def score_endpoint(
    req: ScoreRequest,
    _key: str = Depends(_get_api_key),
):
    """Return lightweight factor and risk scores for a ticker.

    Faster than /analyze — returns scores and signal only, no AI narrative.
    Used by the OpenClaw skill's score() function in remote mode.
    """
    _check_rate_limit(_server_limiter)
    api = _get_api()
    symbol = req.symbol.upper()

    try:
        from factors import compute_factors
        from guardrails import compute_risk
        from jaja_money_skill.scripts.jaja_skill import derive_signal

        data = api.fetch_all_parallel(symbol)
        quote = data.get("quote") or {}
        financials = data.get("financials") or {}
        daily = data.get("daily") or {}
        news = data.get("news") or []

        factors_result = compute_factors(symbol, quote, financials, daily, news)
        risk_result = compute_risk(symbol, quote, financials, daily, news)

        factor_score = int(factors_result.get("composite_score", 50))
        risk_score = int(risk_result.get("risk_score", 50))
        sig = derive_signal(factor_score, risk_score)

        return {
            "symbol": symbol,
            "factor_score": factor_score,
            "composite_label": factors_result.get("composite_label"),
            "risk_score": risk_score,
            "risk_level": risk_result.get("risk_level"),
            "signal": sig["signal"],
            "confidence": sig["confidence"],
            "factors": factors_result.get("factors", []),
            "flags": risk_result.get("flags", []),
            "timestamp": int(time.time()),
        }
    except HTTPException:
        raise
    except Exception as exc:
        log.error("Score failed for %s: %s", symbol, exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# /alerts endpoint — list active price/signal alerts for OpenClaw skill
# ---------------------------------------------------------------------------


@app.get("/alerts", tags=["openclaw"])
async def alerts_endpoint(
    symbol: str | None = None,
    _key: str = Depends(_get_api_key),
):
    """Return active and triggered price/signal alerts.

    Optionally filter by ticker symbol via the ?symbol= query parameter.
    Used by the OpenClaw skill's get_alerts() function in remote mode.
    """
    try:
        from alerts import get_alerts as _get_alerts

        all_alerts = _get_alerts(symbol)
        active = [a for a in all_alerts if a.get("status") == "active"]
        triggered = [a for a in all_alerts if a.get("status") == "triggered"]
        return {
            "symbol": symbol,
            "active_count": len(active),
            "triggered_count": len(triggered),
            "active": active,
            "triggered": triggered,
            "timestamp": int(time.time()),
        }
    except Exception as exc:
        log.error("Alerts failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# OpenClaw: /signals endpoint
# ---------------------------------------------------------------------------


@app.post(
    "/signals",
    summary="OpenClaw — Structured BUY/HOLD/SELL signals",
    tags=["openclaw"],
)
async def signals(
    req: SignalsRequest,
    _key: str = Depends(_get_api_key),
):
    """Return structured BUY/HOLD/SELL signals with confidence scores.

    Derives signals from factor + risk scores using:
        BUY  — factor_score >= 65 and risk_score <= 50
        SELL — factor_score <= 35 or risk_score >= 75
        HOLD — all other combinations
    """
    _check_rate_limit(_heavy_limiter)
    api = _get_api()

    from factors import compute_factors
    from guardrails import compute_risk
    from jaja_money_skill.scripts.jaja_skill import derive_signal

    results = []
    for ticker in req.symbols:
        symbol = ticker.upper()
        try:
            data = api.fetch_all_parallel(symbol)
            quote = data.get("quote") or {}
            financials = data.get("financials") or {}
            daily = data.get("daily") or {}
            news = data.get("news") or []

            factors_result = compute_factors(symbol, quote, financials, daily, news)
            risk_result = compute_risk(symbol, quote, financials, daily, news)

            factor_score = int(factors_result.get("composite_score", 50))
            risk_score = int(risk_result.get("risk_score", 50))
            sig = derive_signal(factor_score, risk_score)

            results.append(
                {
                    "symbol": symbol,
                    "price": quote.get("c"),
                    "factor_score": factor_score,
                    "risk_score": risk_score,
                    "signal": sig["signal"],
                    "confidence": sig["confidence"],
                    "risk_level": risk_result.get("risk_level"),
                }
            )
        except Exception as exc:
            log.warning("signals: error for %s: %s", symbol, exc)
            results.append({"symbol": symbol, "error": str(exc)})

    return {"signals": results, "count": len(results)}


# ---------------------------------------------------------------------------
# OpenClaw: incoming webhook receiver
# ---------------------------------------------------------------------------


@app.post(
    "/openclaw/webhook",
    summary="OpenClaw — Incoming event webhook",
    tags=["openclaw"],
)
async def openclaw_webhook(
    req: OpenClawWebhookRequest,
    _key: str = Depends(_get_api_key),
):
    """Receive incoming events from an OpenClaw agent.

    Supported event types:
        analyze_request  — trigger analysis for a ticker in payload["symbol"]
        alert_request    — create a price alert from payload fields
        screen_request   — run the screener with payload["tickers"]
    """
    import time as _time

    event_type = req.event_type
    payload = req.payload
    log.info("OpenClaw webhook received: event=%s agent=%s", event_type, req.agent_id)

    if event_type == "analyze_request":
        symbol = payload.get("symbol", "").upper()
        if not symbol:
            from fastapi import HTTPException as _HTTPException

            raise _HTTPException(
                status_code=400, detail="payload.symbol required for analyze_request"
            )
        api = _get_api()
        from factors import compute_factors
        from guardrails import compute_risk
        from jaja_money_skill.scripts.jaja_skill import derive_signal

        data = api.fetch_all_parallel(symbol)
        quote = data.get("quote") or {}
        financials = data.get("financials") or {}
        daily = data.get("daily") or {}
        news = data.get("news") or []

        factors_result = compute_factors(symbol, quote, financials, daily, news)
        risk_result = compute_risk(symbol, quote, financials, daily, news)
        factor_score = int(factors_result.get("composite_score", 50))
        risk_score = int(risk_result.get("risk_score", 50))
        sig = derive_signal(factor_score, risk_score)

        return {
            "event_type": event_type,
            "symbol": symbol,
            "factor_score": factor_score,
            "risk_score": risk_score,
            "signal": sig["signal"],
            "confidence": sig["confidence"],
            "processed_at": int(_time.time()),
        }

    if event_type == "alert_request":
        from alerts import add_alert

        symbol = payload.get("symbol", "").upper()
        condition = payload.get("condition", "Price Above")
        threshold = float(payload.get("threshold", 0))
        note = payload.get("note", "via OpenClaw")
        if not symbol:
            from fastapi import HTTPException as _HTTPException

            raise _HTTPException(
                status_code=400, detail="payload.symbol required for alert_request"
            )
        add_alert(symbol, condition, threshold, note)
        return {
            "event_type": event_type,
            "status": "alert_created",
            "symbol": symbol,
            "condition": condition,
            "threshold": threshold,
            "processed_at": int(_time.time()),
        }

    if event_type == "screen_request":
        tickers = payload.get("tickers", [])
        min_factor = int(payload.get("min_factor_score", 0))
        max_risk = int(payload.get("max_risk_score", 100))
        api = _get_api()
        from screener import run_screener

        results = run_screener(
            tickers=tickers,
            api=api,
            min_factor_score=min_factor,
            max_risk_score=max_risk,
        )
        return {
            "event_type": event_type,
            "results": results,
            "total": len(results),
            "processed_at": int(_time.time()),
        }

    return {
        "event_type": event_type,
        "status": "received",
        "note": f"Unhandled event type: {event_type!r}",
        "processed_at": int(_time.time()),
    }


# ---------------------------------------------------------------------------
# OpenClaw: portfolio rebalancing
# ---------------------------------------------------------------------------


@app.post(
    "/openclaw/rebalance",
    summary="OpenClaw — Portfolio rebalancing suggestions",
    tags=["openclaw"],
)
async def openclaw_rebalance(
    req: RebalanceRequest,
    _key: str = Depends(_get_api_key),
):
    """Return rebalancing trade suggestions based on target vs current weights.

    For each ticker, computes the drift between current and target weight
    and returns suggested BUY/SELL/HOLD actions with share-count estimates.
    """
    _check_rate_limit(_heavy_limiter)
    api = _get_api()

    from factors import compute_factors
    from guardrails import compute_risk
    from jaja_money_skill.scripts.jaja_skill import derive_signal

    tickers = [t.upper() for t in req.tickers]
    n = len(tickers)
    if n == 0:
        from fastapi import HTTPException as _HTTPException

        raise _HTTPException(status_code=400, detail="tickers list must not be empty")

    # Validate target weights
    total_weight = sum(req.target_weights.values())
    if not (0.99 <= total_weight <= 1.01):
        from fastapi import HTTPException as _HTTPException

        raise _HTTPException(
            status_code=400,
            detail=f"target_weights must sum to 1.0 (got {total_weight:.3f})",
        )

    suggestions = []
    for symbol in tickers:
        try:
            data = api.fetch_all_parallel(symbol)
            quote = data.get("quote") or {}
            financials = data.get("financials") or {}
            daily = data.get("daily") or {}
            news = data.get("news") or []

            factors_result = compute_factors(symbol, quote, financials, daily, news)
            risk_result = compute_risk(symbol, quote, financials, daily, news)
            factor_score = int(factors_result.get("composite_score", 50))
            risk_score = int(risk_result.get("risk_score", 50))
            sig = derive_signal(factor_score, risk_score)

            target_w = req.target_weights.get(symbol, 1 / n)
            current_w = (
                req.current_weights.get(symbol, 1 / n) if req.current_weights else 1 / n
            )
            drift = current_w - target_w

            # Rebalancing action
            if abs(drift) < 0.01:
                action = "HOLD"
            elif drift > 0:
                action = "SELL"
            else:
                action = "BUY"

            suggestions.append(
                {
                    "symbol": symbol,
                    "target_weight": target_w,
                    "current_weight": current_w,
                    "drift": round(drift, 4),
                    "rebalance_action": action,
                    "factor_signal": sig["signal"],
                    "factor_score": factor_score,
                    "risk_score": risk_score,
                    "price": quote.get("c"),
                }
            )
        except Exception as exc:
            log.warning("rebalance: error for %s: %s", symbol, exc)
            suggestions.append({"symbol": symbol, "error": str(exc)})

    return {
        "suggestions": suggestions,
        "tickers": tickers,
        "total_drift": round(sum(abs(s.get("drift", 0)) for s in suggestions), 4),
    }


# ---------------------------------------------------------------------------
# OpenClaw: autonomous research agent endpoint
# ---------------------------------------------------------------------------


@app.post(
    "/openclaw/agent",
    summary="OpenClaw — Stream autonomous research agent",
    tags=["openclaw"],
)
async def openclaw_agent(
    req: AgentRequest,
    _key: str = Depends(_get_api_key),
):
    """Stream an autonomous multi-step research agent for a stock symbol.

    The agent uses Claude tool-calling to gather data (quote, financials,
    news, earnings, insider transactions, options) then synthesises an
    investment memo covering bear / base / bull cases.
    """
    _check_rate_limit(_heavy_limiter)
    api = _get_api()
    symbol = req.symbol.upper()

    from agent import run_research_agent

    def _generate():
        for chunk in run_research_agent(symbol, api, question=req.question):
            yield chunk

    return StreamingResponse(_generate(), media_type="text/plain")


# ---------------------------------------------------------------------------
# OpenClaw: skill manifest endpoint
# ---------------------------------------------------------------------------


@app.get(
    "/openclaw/manifest",
    summary="OpenClaw — Skill manifest for ClawHub registration",
    tags=["openclaw"],
)
async def openclaw_manifest():
    """Return the ClawHub skill manifest describing jaja-money's capabilities."""
    from jaja_money_skill.scripts.jaja_skill import get_skill_manifest

    return get_skill_manifest()


# ---------------------------------------------------------------------------
# Run as script
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("JAJA_API_PORT", "8080"))
    log.info("Starting jaja-money API server on port %d", port)
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)
