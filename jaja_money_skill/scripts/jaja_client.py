"""HTTP client for interacting with a remote jaja-money server.

Use this when you want the skill to delegate all analysis calls to a
running jaja-money REST API instead of importing the analysis modules
directly.

Usage:
    from jaja_money_skill.scripts.jaja_client import JajaMoneyClient

    client = JajaMoneyClient("http://localhost:8080", api_key="secret")
    result = client.analyze("AAPL")
"""

from __future__ import annotations

import time
from typing import Any


class JajaMoneyClient:
    """HTTP client for a remote (or local) jaja-money server.

    Parameters
    ----------
    base_url : Base URL of the jaja-money server, e.g. "http://localhost:8080"
    api_key  : Optional API key sent as the X-API-Key header.
    timeout  : Per-request timeout in seconds (default 30).
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
