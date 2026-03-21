"""Alpaca Broker Integration for OpenClaw trade execution.

Connects jaja-money's factor/risk signals to Alpaca's trading API,
enabling automated order placement based on analysis results.

Environment variables:
    ALPACA_API_KEY     — Alpaca API key (paper or live)
    ALPACA_API_SECRET  — Alpaca API secret
    ALPACA_BASE_URL    — Base URL (default: https://paper-api.alpaca.markets)

Usage:
    from broker import execute_signal, get_positions, get_account
    result = execute_signal("AAPL", "BUY", qty=1, dry_run=True)
"""

from __future__ import annotations

import os
from typing import Any

from log_setup import get_logger

log = get_logger(__name__)

_PAPER_URL = "https://paper-api.alpaca.markets"
_LIVE_URL = "https://api.alpaca.markets"

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
# Low-level HTTP helpers
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


def _alpaca_post(path: str, payload: dict) -> dict:
    """Make an authenticated POST request to the Alpaca API."""
    if not _HAS_REQUESTS:
        raise ImportError("requests library not installed")
    _, _, base_url = _get_credentials()
    url = f"{base_url}{path}"
    response = _requests.post(url, headers=_alpaca_headers(), json=payload, timeout=10)
    response.raise_for_status()
    return response.json()


def _alpaca_delete(path: str) -> bool:
    """Make an authenticated DELETE request to the Alpaca API."""
    if not _HAS_REQUESTS:
        raise ImportError("requests library not installed")
    _, _, base_url = _get_credentials()
    url = f"{base_url}{path}"
    response = _requests.delete(url, headers=_alpaca_headers(), timeout=10)
    return response.status_code < 400


# ---------------------------------------------------------------------------
# Public account/position functions
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
# Order management
# ---------------------------------------------------------------------------


def place_order(
    symbol: str,
    side: str,
    qty: float,
    order_type: str = "market",
    time_in_force: str = "day",
    limit_price: float | None = None,
) -> dict[str, Any]:
    """Place an order on Alpaca.

    Parameters
    ----------
    symbol        : stock ticker (e.g., "AAPL")
    side          : "buy" or "sell"
    qty           : number of shares
    order_type    : "market" or "limit"
    time_in_force : "day", "gtc", "ioc", or "fok"
    limit_price   : required if order_type == "limit"
    """
    side = side.lower()
    if side not in ("buy", "sell"):
        raise ValueError(f"Invalid order side: {side!r}. Must be 'buy' or 'sell'")
    if order_type == "limit" and limit_price is None:
        raise ValueError("limit_price required for limit orders")

    payload: dict[str, Any] = {
        "symbol": symbol.upper(),
        "qty": str(qty),
        "side": side,
        "type": order_type,
        "time_in_force": time_in_force,
    }
    if limit_price is not None:
        payload["limit_price"] = str(limit_price)

    try:
        result = _alpaca_post("/v2/orders", payload)
        log.info("Order placed: %s %s %s qty=%s", side, symbol, order_type, qty)
        return {
            "order_id": result.get("id"),
            "symbol": result.get("symbol"),
            "side": result.get("side"),
            "qty": result.get("qty"),
            "status": result.get("status"),
            "type": result.get("type"),
            "submitted_at": result.get("submitted_at"),
        }
    except Exception as exc:
        log.error("Order placement failed for %s: %s", symbol, exc)
        raise


def cancel_order(order_id: str) -> bool:
    """Cancel an open order by ID. Returns True on success."""
    try:
        result = _alpaca_delete(f"/v2/orders/{order_id}")
        log.info("Order %s cancelled: %s", order_id, result)
        return result
    except Exception as exc:
        log.error("Failed to cancel order %s: %s", order_id, exc)
        return False


# ---------------------------------------------------------------------------
# High-level signal execution
# ---------------------------------------------------------------------------


def execute_signal(
    symbol: str,
    signal: str,
    qty: float = 1.0,
    factor_score: int | None = None,
    risk_score: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Execute a trade signal from jaja-money's factor engine.

    Translates a BUY/SELL/HOLD signal into an Alpaca market order.

    Parameters
    ----------
    symbol       : stock ticker
    signal       : "BUY", "SELL", or "HOLD"
    qty          : number of shares to trade
    factor_score : optional factor score from jaja-money (0-100)
    risk_score   : optional risk score from jaja-money (0-100)
    dry_run      : if True, log the intended action but don't place the order
    """
    signal = signal.upper()
    if signal == "HOLD":
        log.info("execute_signal: HOLD for %s — no action taken", symbol)
        return {
            "symbol": symbol,
            "signal": "HOLD",
            "action": "none",
            "dry_run": dry_run,
        }

    if signal not in ("BUY", "SELL"):
        raise ValueError(f"Unknown signal: {signal!r}. Expected BUY, SELL, or HOLD.")

    side = "buy" if signal == "BUY" else "sell"
    action_summary: dict[str, Any] = {
        "symbol": symbol,
        "signal": signal,
        "side": side,
        "qty": qty,
        "factor_score": factor_score,
        "risk_score": risk_score,
        "dry_run": dry_run,
    }

    if dry_run:
        log.info("DRY RUN execute_signal: %s", action_summary)
        return {**action_summary, "action": "dry_run", "order": None}

    order = place_order(symbol, side=side, qty=qty)
    return {**action_summary, "action": "order_placed", "order": order}


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def is_configured() -> bool:
    """Return True if Alpaca credentials are present in the environment."""
    key, secret, _ = _get_credentials()
    return bool(key and secret)
