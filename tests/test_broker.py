"""Tests for broker.py — Alpaca broker integration (simulation / read-only mode)."""

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
# TRADING_DISABLED constant
# ---------------------------------------------------------------------------


def test_trading_disabled_constant():
    from broker import TRADING_DISABLED

    assert TRADING_DISABLED is True


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
# execute_signal — always simulated, no real orders
# ---------------------------------------------------------------------------


def test_execute_signal_hold_no_order():
    from broker import execute_signal

    result = execute_signal("AAPL", "HOLD", qty=1)
    assert result["signal"] == "HOLD"
    assert result["action"] == "none"
    assert result["simulated"] is True


def test_execute_signal_buy_is_simulation():
    from broker import execute_signal

    result = execute_signal("AAPL", "BUY", qty=5)
    assert result["action"] == "simulated"
    assert result["simulated"] is True
    assert result["order"] is None
    assert result["dry_run"] is True
    assert result["signal"] == "BUY"
    assert result["side"] == "buy"


def test_execute_signal_sell_is_simulation():
    from broker import execute_signal

    result = execute_signal("TSLA", "SELL", qty=2)
    assert result["action"] == "simulated"
    assert result["simulated"] is True
    assert result["order"] is None
    assert result["signal"] == "SELL"
    assert result["side"] == "sell"


def test_execute_signal_dry_run_flag_is_simulation():
    """dry_run flag has no effect — execution is always simulated."""
    from broker import execute_signal

    result = execute_signal("AAPL", "BUY", qty=5, dry_run=True)
    assert result["action"] == "simulated"
    assert result["simulated"] is True


def test_execute_signal_with_scores():
    from broker import execute_signal

    result = execute_signal("AAPL", "BUY", qty=3, factor_score=72, risk_score=35)
    assert result["factor_score"] == 72
    assert result["risk_score"] == 35
    assert result["simulated"] is True


def test_execute_signal_invalid_raises():
    from broker import execute_signal

    with pytest.raises(ValueError, match="Unknown signal"):
        execute_signal("AAPL", "STRONG_BUY", qty=1)


def test_execute_signal_note_field():
    from broker import execute_signal

    result = execute_signal("AAPL", "BUY", qty=1)
    assert "note" in result
    assert (
        "simulation" in result["note"].lower() or "disabled" in result["note"].lower()
    )


# ---------------------------------------------------------------------------
# Ensure place_order and cancel_order no longer exist
# ---------------------------------------------------------------------------


def test_place_order_not_exported():
    import broker

    assert not hasattr(broker, "place_order"), (
        "place_order should have been removed; real trading is disabled"
    )


def test_cancel_order_not_exported():
    import broker

    assert not hasattr(broker, "cancel_order"), (
        "cancel_order should have been removed; real trading is disabled"
    )
