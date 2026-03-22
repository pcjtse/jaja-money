"""Alpaca Broker Integration — Read-Only / Simulation Mode.

Real order execution has been removed. This module provides:
  - Account and position monitoring (read-only Alpaca API calls)
  - execute_signal() always runs in simulation mode; no real orders are placed

Environment variables:
    ALPACA_API_KEY     — Alpaca API key
    ALPACA_API_SECRET  — Alpaca API secret
    ALPACA_BASE_URL    — Base URL (default: https://paper-api.alpaca.markets)

Usage:
    from src.trading.broker import execute_signal, get_positions, get_account
    result = execute_signal("AAPL", "BUY", qty=1)  # simulation only
"""

from __future__ import annotations

import os
from typing import Any

from src.core.log_setup import get_logger

log = get_logger(__name__)

# Real order placement is permanently disabled in this module.
TRADING_DISABLED = True

_PAPER_URL = "https://paper-api.alpaca.markets"

try:
    import requests as _requests

    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False


# ---------------------------------------------------------------------------
# Credential helpers
# ---------------------------------------------------------------------------


def _get_credentials() -> tuple[str, str, str]:
    """Return (api_key, api_secret, base_url) from environment."""
    key = os.getenv("ALPACA_API_KEY", "")
    secret = os.getenv("ALPACA_API_SECRET", "")
    base_url = os.getenv("ALPACA_BASE_URL", _PAPER_URL).rstrip("/")
    return key, secret, base_url


def _alpaca_headers() -> dict[str, str]:
    key, secret, _ = _get_credentials()
    return {
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# Low-level HTTP helper (read-only)
# ---------------------------------------------------------------------------


def _alpaca_get(path: str) -> Any:
    """Make an authenticated GET request to the Alpaca API."""
    if not _HAS_REQUESTS:
        raise ImportError("requests library not installed")
    _, _, base_url = _get_credentials()
    url = f"{base_url}{path}"
    response = _requests.get(url, headers=_alpaca_headers(), timeout=10)
    response.raise_for_status()
    return response.json()


# ---------------------------------------------------------------------------
# Public account/position functions (read-only)
# ---------------------------------------------------------------------------


def get_account() -> dict[str, Any]:
    """Fetch Alpaca account details (cash, portfolio value, buying power)."""
    try:
        data = _alpaca_get("/v2/account")
        return {
            "cash": float(data.get("cash", 0)),
            "portfolio_value": float(data.get("portfolio_value", 0)),
            "buying_power": float(data.get("buying_power", 0)),
            "equity": float(data.get("equity", 0)),
            "status": data.get("status"),
            "currency": data.get("currency", "USD"),
        }
    except Exception as exc:
        log.error("Failed to fetch Alpaca account: %s", exc)
        raise


def get_positions() -> list[dict[str, Any]]:
    """Return all open positions from Alpaca."""
    try:
        positions = _alpaca_get("/v2/positions")
        return [
            {
                "symbol": p.get("symbol"),
                "qty": float(p.get("qty", 0)),
                "avg_entry_price": float(p.get("avg_entry_price", 0)),
                "current_price": float(p.get("current_price", 0)),
                "market_value": float(p.get("market_value", 0)),
                "unrealized_pl": float(p.get("unrealized_pl", 0)),
                "unrealized_plpc": float(p.get("unrealized_plpc", 0)),
                "side": p.get("side"),
            }
            for p in positions
        ]
    except Exception as exc:
        log.error("Failed to fetch Alpaca positions: %s", exc)
        raise


# ---------------------------------------------------------------------------
# Signal simulation (no real orders placed)
# ---------------------------------------------------------------------------


def execute_signal(
    symbol: str,
    signal: str,
    qty: float = 1.0,
    factor_score: int | None = None,
    risk_score: int | None = None,
    dry_run: bool = False,  # retained for API compatibility; always simulated
) -> dict[str, Any]:
    """Simulate execution of a trade signal — no real orders are placed.

    Real order placement has been removed from this module. This function
    always returns a simulation result regardless of the dry_run flag.

    Parameters
    ----------
    symbol       : stock ticker
    signal       : "BUY", "SELL", or "HOLD"
    qty          : number of shares (informational only)
    factor_score : optional factor score from jaja-money (0-100)
    risk_score   : optional risk score from jaja-money (0-100)
    dry_run      : ignored — execution is always simulated
    """
    signal = signal.upper()
    if signal == "HOLD":
        log.info("execute_signal: HOLD for %s — no action", symbol)
        return {
            "symbol": symbol,
            "signal": "HOLD",
            "action": "none",
            "simulated": True,
        }

    if signal not in ("BUY", "SELL"):
        raise ValueError(f"Unknown signal: {signal!r}. Expected BUY, SELL, or HOLD.")

    side = "buy" if signal == "BUY" else "sell"
    result: dict[str, Any] = {
        "symbol": symbol,
        "signal": signal,
        "side": side,
        "qty": qty,
        "factor_score": factor_score,
        "risk_score": risk_score,
        "dry_run": True,
        "simulated": True,
        "action": "simulated",
        "order": None,
        "note": "Real trading is disabled. This is a simulation only.",
    }
    log.info("SIMULATION execute_signal: %s %s qty=%s", signal, symbol, qty)
    return result


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def is_configured() -> bool:
    """Return True if Alpaca credentials are present in the environment."""
    key, secret, _ = _get_credentials()
    return bool(key and secret)
