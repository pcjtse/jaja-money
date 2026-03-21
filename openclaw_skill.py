"""OpenClaw Skill Package for jaja-money.

Packages jaja-money's analysis engine as a publishable OpenClaw skill
compatible with the ClawHub marketplace. Exposes structured JSON outputs
for all core analysis capabilities.

Skill functions:
    analyze(ticker)              — Full fundamental + risk analysis
    screen(tickers, ...)         — Factor/risk-based stock screener
    score(ticker)                — Structured factor/risk scores
    get_alerts(symbol)           — Active price/signal alerts
    research(ticker, question)   — Autonomous multi-step research

Remote mode:
    Set JAJA_API_URL to the URL of a running jaja-money server to run the
    skill against a remote (or local) instance instead of importing the
    analysis modules directly.  Optional JAJA_API_KEY is forwarded as the
    X-API-Key header.

    export JAJA_API_URL=http://localhost:8080
    export JAJA_API_KEY=mysecret   # optional

ClawHub metadata:
    SKILL_MANIFEST — dict describing name, version, capabilities, schema

Usage (OpenClaw agent):
    from openclaw_skill import analyze, screen, score, get_alerts, research
    result = analyze("AAPL")
"""

from __future__ import annotations

import os
import time
from typing import Any

from log_setup import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Skill manifest — describes this skill to the OpenClaw / ClawHub registry
# ---------------------------------------------------------------------------

SKILL_MANIFEST: dict[str, Any] = {
    "name": "jaja-money",
    "version": "1.0.0",
    "description": (
        "Multi-factor stock analysis powered by Claude AI and Finnhub. "
        "Provides factor scoring, risk assessment, stock screening, "
        "and autonomous research."
    ),
    "author": "jaja-money",
    "category": "finance",
    "capabilities": [
        "stock_analysis",
        "risk_assessment",
        "stock_screening",
        "portfolio_research",
        "alert_management",
    ],
    "functions": {
        "analyze": {
            "description": "Full fundamental + risk analysis for a stock ticker.",
            "parameters": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol (e.g., AAPL)",
                },
                "use_cache": {
                    "type": "boolean",
                    "description": "Use cached data if available",
                    "default": True,
                },
            },
            "required": ["ticker"],
        },
        "screen": {
            "description": ("Screen stocks using factor/risk thresholds."),
            "parameters": {
                "tickers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tickers to screen",
                },
                "min_factor_score": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 100,
                    "default": 0,
                },
                "max_risk_score": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 100,
                    "default": 100,
                },
            },
            "required": ["tickers"],
        },
        "score": {
            "description": "Returns structured factor and risk scores for a ticker.",
            "parameters": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol",
                },
            },
            "required": ["ticker"],
        },
        "get_alerts": {
            "description": (
                "Returns all active price and signal alerts, "
                "optionally filtered by symbol."
            ),
            "parameters": {
                "symbol": {
                    "type": "string",
                    "description": "Filter by ticker symbol (optional)",
                },
            },
        },
        "research": {
            "description": (
                "Runs an autonomous multi-step research agent to "
                "answer investment questions."
            ),
            "parameters": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker to research",
                },
                "question": {
                    "type": "string",
                    "description": "Research question or objective",
                },
            },
            "required": ["ticker"],
        },
    },
    "auth": {
        "type": "api_key",
        "header": "X-API-Key",
        "description": ("Optional: set JAJA_API_KEY env var to enable authentication"),
    },
    "endpoints": {
        "base_url": "http://localhost:8080",
        "health": "/health",
        "analyze": "/analyze",
        "score": "/score",
        "screen": "/screen",
        "signals": "/signals",
        "alerts": "/alerts",
        "research_agent": "/openclaw/agent",
        "webhook": "/openclaw/webhook",
        "rebalance": "/openclaw/rebalance",
    },
}


# ---------------------------------------------------------------------------
# Remote HTTP client
# ---------------------------------------------------------------------------


class JajaMoneyClient:
    """HTTP client for interacting with a remote (or local) jaja-money server.

    Instantiate this when you want the OpenClaw skill to delegate all analysis
    calls to a running jaja-money REST API instead of importing the analysis
    modules directly.

    Parameters
    ----------
    base_url : Base URL of the jaja-money server, e.g. "http://localhost:8080"
    api_key  : Optional API key sent as the X-API-Key header.
    timeout  : Per-request timeout in seconds (default 30).

    Example
    -------
    client = JajaMoneyClient("http://analysis-server:8080", api_key="secret")
    result = client.analyze("AAPL")
    """

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        timeout: int = 30,
    ) -> None:
        try:
            import requests as _req

            self._requests = _req
        except ImportError as exc:
            raise ImportError(
                "requests library is required for remote mode. "
                "Install it with: pip install requests"
            ) from exc

        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            self._headers["X-API-Key"] = api_key

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(self, path: str, params: dict | None = None) -> Any:
        url = f"{self.base_url}{path}"
        resp = self._requests.get(
            url, headers=self._headers, params=params, timeout=self.timeout
        )
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, payload: dict) -> Any:
        url = f"{self.base_url}{path}"
        resp = self._requests.post(
            url, headers=self._headers, json=payload, timeout=self.timeout
        )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Public methods mirroring the skill API
    # ------------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        """Check server health."""
        return self._get("/health")

    def analyze(self, ticker: str, use_cache: bool = True) -> dict[str, Any]:
        """Full fundamental + risk analysis via the remote /analyze endpoint."""
        return self._post("/analyze", {"symbol": ticker, "use_cache": use_cache})

    def score(self, ticker: str) -> dict[str, Any]:
        """Factor and risk scores via the remote /score endpoint."""
        return self._post("/score", {"symbol": ticker})

    def screen(
        self,
        tickers: list[str],
        min_factor_score: int = 0,
        max_risk_score: int = 100,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Stock screener via the remote /screen endpoint."""
        return self._post(
            "/screen",
            {
                "tickers": tickers,
                "min_factor_score": min_factor_score,
                "max_risk_score": max_risk_score,
                "limit": limit,
            },
        )

    def signals(self, symbols: list[str]) -> dict[str, Any]:
        """BUY/HOLD/SELL signals via the remote /signals endpoint."""
        return self._post("/signals", {"symbols": symbols})

    def get_alerts(self, symbol: str | None = None) -> dict[str, Any]:
        """Active alerts via the remote /alerts endpoint."""
        params = {"symbol": symbol} if symbol else {}
        return self._get("/alerts", params=params)

    def research(
        self,
        ticker: str,
        question: str = (
            "Produce a comprehensive investment memo with bear, base, and bull case."
        ),
    ) -> dict[str, Any]:
        """Collect research agent output (non-streaming) via /openclaw/agent."""
        # The /openclaw/agent endpoint streams text; collect it here.
        url = f"{self.base_url}/openclaw/agent"
        resp = self._requests.post(
            url,
            headers=self._headers,
            json={"symbol": ticker, "question": question},
            timeout=max(self.timeout, 120),
            stream=True,
        )
        resp.raise_for_status()
        memo = "".join(
            chunk
            for chunk in resp.iter_content(chunk_size=None, decode_unicode=True)
            if chunk
        )
        return {
            "symbol": ticker.upper(),
            "question": question,
            "memo": memo,
            "timestamp": int(time.time()),
        }


# ---------------------------------------------------------------------------
# Remote client factory
# ---------------------------------------------------------------------------


def _get_remote_client() -> JajaMoneyClient | None:
    """Return a JajaMoneyClient if JAJA_API_URL is set, otherwise None.

    Environment variables:
        JAJA_API_URL — URL of the running jaja-money server
        JAJA_API_KEY — Optional API key for authentication
    """
    url = os.getenv("JAJA_API_URL", "").strip()
    if not url:
        return None
    api_key = os.getenv("JAJA_API_KEY", "") or None
    log.debug("OpenClaw remote mode: connecting to %s", url)
    return JajaMoneyClient(base_url=url, api_key=api_key)


# ---------------------------------------------------------------------------
# Lazy local API init helper
# ---------------------------------------------------------------------------


def _get_api():
    """Return a FinnhubAPI instance (local mode only)."""
    from api import FinnhubAPI

    return FinnhubAPI()


# ---------------------------------------------------------------------------
# Signal derivation helper
# ---------------------------------------------------------------------------


def derive_signal(factor_score: int, risk_score: int) -> dict[str, Any]:
    """Derive BUY/HOLD/SELL signal from factor and risk scores.

    Logic:
        BUY  — factor_score >= 65 and risk_score <= 50
        SELL — factor_score <= 35 or risk_score >= 75
        HOLD — everything else
    """
    if factor_score >= 65 and risk_score <= 50:
        signal = "BUY"
        confidence = min(100, int(factor_score * 0.6 + (100 - risk_score) * 0.4))
    elif factor_score <= 35 or risk_score >= 75:
        signal = "SELL"
        confidence = min(100, int((100 - factor_score) * 0.6 + risk_score * 0.4))
    else:
        signal = "HOLD"
        confidence = 50
    return {"signal": signal, "confidence": confidence}


# ---------------------------------------------------------------------------
# Public skill functions
# ---------------------------------------------------------------------------


def analyze(ticker: str, use_cache: bool = True) -> dict[str, Any]:
    """Full fundamental + risk analysis for a stock ticker.

    In remote mode (JAJA_API_URL set) delegates to the jaja-money REST API.
    Otherwise imports analysis modules directly from the local environment.

    Returns a structured JSON dict with factor scores, risk metrics, and
    key financial data — ready for consumption by OpenClaw agents.
    """
    client = _get_remote_client()
    if client:
        return client.analyze(ticker, use_cache=use_cache)

    api = _get_api()
    symbol = ticker.upper()

    from factors import compute_factors
    from guardrails import compute_risk

    data = api.fetch_all_parallel(symbol)
    quote = data.get("quote") or {}
    profile = data.get("profile") or {}
    financials = data.get("financials") or {}
    daily = data.get("daily") or {}
    news = data.get("news") or []

    factors_result = compute_factors(symbol, quote, financials, daily, news)
    risk_result = compute_risk(symbol, quote, financials, daily, news)

    factor_score = factors_result.get("composite_score", 50)
    risk_score = risk_result.get("risk_score", 50)
    signal_info = derive_signal(int(factor_score), int(risk_score))

    return {
        "symbol": symbol,
        "name": profile.get("name", ""),
        "sector": profile.get("finnhubIndustry", ""),
        "price": quote.get("c"),
        "change_pct": quote.get("dp"),
        "factor_score": factor_score,
        "composite_label": factors_result.get("composite_label"),
        "risk_score": risk_score,
        "risk_level": risk_result.get("risk_level"),
        "signal": signal_info["signal"],
        "confidence": signal_info["confidence"],
        "factors": factors_result.get("factors", []),
        "flags": risk_result.get("flags", []),
        "timestamp": int(time.time()),
    }


def screen(
    tickers: list[str],
    min_factor_score: int = 0,
    max_risk_score: int = 100,
    limit: int = 20,
) -> dict[str, Any]:
    """Screen a list of tickers against factor and risk thresholds.

    In remote mode delegates to the jaja-money REST API /screen endpoint.
    Returns a ranked list of tickers that pass the filters.
    """
    client = _get_remote_client()
    if client:
        return client.screen(
            tickers,
            min_factor_score=min_factor_score,
            max_risk_score=max_risk_score,
            limit=limit,
        )

    api = _get_api()

    from screener import run_screener

    results = run_screener(
        tickers=tickers,
        api=api,
        min_factor_score=min_factor_score,
        max_risk_score=max_risk_score,
    )
    return {
        "results": results[:limit],
        "total": len(results),
        "filters": {
            "min_factor_score": min_factor_score,
            "max_risk_score": max_risk_score,
        },
        "timestamp": int(time.time()),
    }


def score(ticker: str) -> dict[str, Any]:
    """Return structured factor and risk scores for a ticker.

    In remote mode delegates to the jaja-money REST API /score endpoint.
    Lightweight alternative to analyze() — returns scores only,
    not the full company profile.
    """
    client = _get_remote_client()
    if client:
        return client.score(ticker)

    api = _get_api()
    symbol = ticker.upper()

    from factors import compute_factors
    from guardrails import compute_risk

    quote = api.get_quote(symbol)
    financials = api.get_financials(symbol)
    daily = api.get_daily(symbol)
    news = api.get_news(symbol)

    factors_result = compute_factors(symbol, quote, financials, daily, news)
    risk_result = compute_risk(symbol, quote, financials, daily, news)

    factor_score = int(factors_result.get("composite_score", 50))
    risk_score = int(risk_result.get("risk_score", 50))
    signal_info = derive_signal(factor_score, risk_score)

    return {
        "symbol": symbol,
        "factor_score": factor_score,
        "composite_label": factors_result.get("composite_label"),
        "risk_score": risk_score,
        "risk_level": risk_result.get("risk_level"),
        "signal": signal_info["signal"],
        "confidence": signal_info["confidence"],
        "factors": factors_result.get("factors", []),
        "flags": risk_result.get("flags", []),
        "timestamp": int(time.time()),
    }


def get_alerts(symbol: str | None = None) -> dict[str, Any]:
    """Return all active price/signal alerts, optionally filtered by symbol.

    In remote mode delegates to the jaja-money REST API /alerts endpoint.
    """
    client = _get_remote_client()
    if client:
        return client.get_alerts(symbol)

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


def research(
    ticker: str,
    question: str = (
        "Produce a comprehensive investment memo with bear, base, and bull case."
    ),
) -> dict[str, Any]:
    """Run the autonomous research agent and collect output.

    In remote mode delegates to the jaja-money REST API /openclaw/agent
    endpoint (streaming output is collected into a single response dict).
    For streaming output in remote mode, call /openclaw/agent directly.
    """
    client = _get_remote_client()
    if client:
        return client.research(ticker, question=question)

    api = _get_api()
    symbol = ticker.upper()

    from agent import run_research_agent

    chunks: list[str] = []
    for chunk in run_research_agent(symbol, api, question=question):
        chunks.append(chunk)

    return {
        "symbol": symbol,
        "question": question,
        "memo": "".join(chunks),
        "timestamp": int(time.time()),
    }


def get_skill_manifest() -> dict[str, Any]:
    """Return the full skill manifest for ClawHub registration."""
    return SKILL_MANIFEST
