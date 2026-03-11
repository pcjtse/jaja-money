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
    raise ImportError(
        "FastAPI not installed. Run: pip install fastapi uvicorn"
    )

from log_setup import get_logger  # noqa: E402

log = get_logger(__name__)

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
    weights: list[float] | None = Field(None, description="Portfolio weights (sum to 1)")


# ---------------------------------------------------------------------------
# Lazy API/analyzer initialization
# ---------------------------------------------------------------------------

_api_instance = None
_api_error = None


def _get_api():
    global _api_instance, _api_error
    if _api_error:
        raise HTTPException(status_code=503, detail=f"API initialization failed: {_api_error}")
    if _api_instance is None:
        try:
            from api import FinnhubAPI
            _api_instance = FinnhubAPI()
        except Exception as exc:
            _api_error = str(exc)
            raise HTTPException(status_code=503, detail=f"API initialization failed: {exc}")
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
                raise HTTPException(status_code=400, detail="weights length must match tickers")
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
            "correlation": corr.to_dict() if corr is not None and not corr.empty else {},
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
    api = _get_api()
    symbol = req.symbol.upper()

    try:
        from factors import compute_factors
        from guardrails import compute_risk
        from analyzer import stream_chat_response, build_chat_system_prompt

        quote = api.get_quote(symbol)
        financials = api.get_financials(symbol)
        daily = api.get_daily(symbol)
        news = api.get_news(symbol)

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
# Run as script
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("JAJA_API_PORT", "8080"))
    log.info("Starting jaja-money API server on port %d", port)
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)
