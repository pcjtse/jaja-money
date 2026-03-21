"""Tests for broker.py — Alpaca broker integration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_response(json_data, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status.return_value = None
    return resp


# ---------------------------------------------------------------------------
# is_configured
# ---------------------------------------------------------------------------


def test_is_configured_false_when_no_env(monkeypatch):
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_API_SECRET", raising=False)

    from broker import is_configured

    assert is_configured() is False


def test_is_configured_true_when_env_set(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "test-key")
    monkeypatch.setenv("ALPACA_API_SECRET", "test-secret")

    from broker import is_configured

    assert is_configured() is True


# ---------------------------------------------------------------------------
# get_account
# ---------------------------------------------------------------------------


def test_get_account_returns_normalized_fields(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "k")
    monkeypatch.setenv("ALPACA_API_SECRET", "s")

    raw = {
        "cash": "10000.50",
        "portfolio_value": "25000.00",
        "buying_power": "20000.00",
        "equity": "25000.00",
        "status": "ACTIVE",
        "currency": "USD",
    }
    with patch("broker._requests") as mock_req:
        mock_req.get.return_value = _make_response(raw)
        from broker import get_account

        result = get_account()

    assert result["cash"] == pytest.approx(10000.50)
    assert result["portfolio_value"] == pytest.approx(25000.00)
    assert result["status"] == "ACTIVE"
    assert result["currency"] == "USD"


# ---------------------------------------------------------------------------
# get_positions
# ---------------------------------------------------------------------------


def test_get_positions_returns_list(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "k")
    monkeypatch.setenv("ALPACA_API_SECRET", "s")

    raw = [
        {
            "symbol": "AAPL",
            "qty": "10",
            "avg_entry_price": "145.00",
            "current_price": "155.00",
            "market_value": "1550.00",
            "unrealized_pl": "100.00",
            "unrealized_plpc": "0.069",
            "side": "long",
        }
    ]
    with patch("broker._requests") as mock_req:
        mock_req.get.return_value = _make_response(raw)
        from broker import get_positions

        positions = get_positions()

    assert len(positions) == 1
    assert positions[0]["symbol"] == "AAPL"
    assert positions[0]["qty"] == pytest.approx(10.0)
    assert positions[0]["side"] == "long"


def test_get_positions_empty(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "k")
    monkeypatch.setenv("ALPACA_API_SECRET", "s")

    with patch("broker._requests") as mock_req:
        mock_req.get.return_value = _make_response([])
        from broker import get_positions

        positions = get_positions()

    assert positions == []


# ---------------------------------------------------------------------------
# place_order
# ---------------------------------------------------------------------------


def test_place_order_buy(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "k")
    monkeypatch.setenv("ALPACA_API_SECRET", "s")

    raw = {
        "id": "order-123",
        "symbol": "AAPL",
        "side": "buy",
        "qty": "5",
        "status": "accepted",
        "type": "market",
        "submitted_at": "2026-03-21T10:00:00Z",
    }
    with patch("broker._requests") as mock_req:
        mock_req.post.return_value = _make_response(raw)
        from broker import place_order

        result = place_order("AAPL", side="buy", qty=5)

    assert result["order_id"] == "order-123"
    assert result["symbol"] == "AAPL"
    assert result["side"] == "buy"


def test_place_order_invalid_side():
    from broker import place_order

    with pytest.raises(ValueError, match="Invalid order side"):
        place_order("AAPL", side="hold", qty=1)


def test_place_order_limit_requires_price():
    from broker import place_order

    with pytest.raises(ValueError, match="limit_price required"):
        place_order("AAPL", side="buy", qty=1, order_type="limit")


def test_place_order_limit_with_price(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "k")
    monkeypatch.setenv("ALPACA_API_SECRET", "s")

    raw = {
        "id": "order-456",
        "symbol": "AAPL",
        "side": "buy",
        "qty": "1",
        "status": "new",
        "type": "limit",
        "submitted_at": "2026-03-21T10:00:00Z",
    }
    with patch("broker._requests") as mock_req:
        mock_req.post.return_value = _make_response(raw)
        from broker import place_order

        result = place_order(
            "AAPL", side="buy", qty=1, order_type="limit", limit_price=145.0
        )

    assert result["type"] == "limit"
    # Verify limit_price was included in the POST payload
    call_args = mock_req.post.call_args
    payload = call_args.kwargs.get("json") or call_args[1].get("json", {})
    assert "limit_price" in payload


# ---------------------------------------------------------------------------
# cancel_order
# ---------------------------------------------------------------------------


def test_cancel_order_success(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "k")
    monkeypatch.setenv("ALPACA_API_SECRET", "s")

    with patch("broker._requests") as mock_req:
        mock_req.delete.return_value = _make_response({}, status_code=204)
        from broker import cancel_order

        result = cancel_order("order-123")

    assert result is True


def test_cancel_order_failure(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "k")
    monkeypatch.setenv("ALPACA_API_SECRET", "s")

    with patch("broker._requests") as mock_req:
        mock_req.delete.side_effect = Exception("Connection refused")
        from broker import cancel_order

        result = cancel_order("order-999")

    assert result is False


# ---------------------------------------------------------------------------
# execute_signal
# ---------------------------------------------------------------------------


def test_execute_signal_hold_no_order():
    from broker import execute_signal

    result = execute_signal("AAPL", "HOLD", qty=1)
    assert result["signal"] == "HOLD"
    assert result["action"] == "none"


def test_execute_signal_dry_run_no_order():
    from broker import execute_signal

    result = execute_signal("AAPL", "BUY", qty=5, dry_run=True)
    assert result["action"] == "dry_run"
    assert result["order"] is None
    assert result["dry_run"] is True


def test_execute_signal_buy(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "k")
    monkeypatch.setenv("ALPACA_API_SECRET", "s")

    raw = {
        "id": "order-buy-1",
        "symbol": "AAPL",
        "side": "buy",
        "qty": "3",
        "status": "accepted",
        "type": "market",
        "submitted_at": "2026-03-21T10:00:00Z",
    }
    with patch("broker._requests") as mock_req:
        mock_req.post.return_value = _make_response(raw)
        from broker import execute_signal

        result = execute_signal("AAPL", "BUY", qty=3, factor_score=72, risk_score=35)

    assert result["action"] == "order_placed"
    assert result["signal"] == "BUY"
    assert result["side"] == "buy"
    assert result["order"]["order_id"] == "order-buy-1"


def test_execute_signal_sell(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "k")
    monkeypatch.setenv("ALPACA_API_SECRET", "s")

    raw = {
        "id": "order-sell-1",
        "symbol": "TSLA",
        "side": "sell",
        "qty": "2",
        "status": "accepted",
        "type": "market",
        "submitted_at": "2026-03-21T10:00:00Z",
    }
    with patch("broker._requests") as mock_req:
        mock_req.post.return_value = _make_response(raw)
        from broker import execute_signal

        result = execute_signal("TSLA", "SELL", qty=2)

    assert result["action"] == "order_placed"
    assert result["side"] == "sell"


def test_execute_signal_invalid_raises():
    from broker import execute_signal

    with pytest.raises(ValueError, match="Unknown signal"):
        execute_signal("AAPL", "STRONG_BUY", qty=1)
