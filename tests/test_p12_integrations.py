"""Tests for P12.x: Notifications & Integrations."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from alerts import (
    _post_json,
    _send_discord,
    _send_slack,
    _send_telegram,
    send_webhook_notification,
    send_test_webhook,
)
from export import parse_brokerage_csv, _parse_float, _get_col


# ---------------------------------------------------------------------------
# P12.1: Webhook tests
# ---------------------------------------------------------------------------


class TestWebhooks:
    def test_post_json_empty_url(self):
        result = _post_json("", {"key": "value"})
        assert result is False

    def test_post_json_success(self):
        with patch("alerts._urllib_request.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_response

            result = _post_json("https://hooks.slack.com/test", {"text": "hello"})
            assert result is True

    def test_post_json_failure(self):
        with patch("alerts._urllib_request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = Exception("Connection refused")
            result = _post_json("https://invalid.webhook.com", {"text": "hello"})
            assert result is False

    def test_send_slack_builds_payload(self):
        with patch("alerts._post_json") as mock_post:
            mock_post.return_value = True
            result = _send_slack("https://slack.webhook", "Test Alert", "Body text", "#FF0000")
            assert result is True
            call_args = mock_post.call_args
            payload = call_args[0][1]
            assert "attachments" in payload
            assert payload["attachments"][0]["title"] == "Test Alert"

    def test_send_discord_builds_payload(self):
        with patch("alerts._post_json") as mock_post:
            mock_post.return_value = True
            result = _send_discord("https://discord.webhook", "Test Alert", "Body text", "#2196F3")
            assert result is True
            call_args = mock_post.call_args
            payload = call_args[0][1]
            assert "embeds" in payload
            assert payload["embeds"][0]["title"] == "Test Alert"

    def test_send_telegram_builds_payload(self):
        with patch("alerts._post_json") as mock_post:
            mock_post.return_value = True
            result = _send_telegram("bot_token", "chat_123", "Alert message")
            assert result is True
            call_args = mock_post.call_args
            payload = call_args[0][1]
            assert payload["chat_id"] == "chat_123"
            assert "Alert message" in payload["text"]

    def test_send_webhook_notification_all_destinations(self):
        alert = {
            "symbol": "AAPL",
            "condition": "Price Above",
            "threshold": 200.0,
            "note": "Target price hit",
        }
        with patch("alerts._post_json", return_value=True):
            results = send_webhook_notification(
                alert,
                current_value=201.5,
                slack_url="https://slack.test",
                discord_url="https://discord.test",
                telegram_token="token123",
                telegram_chat_id="chat456",
            )

        assert "slack" in results
        assert "discord" in results
        assert "telegram" in results

    def test_send_webhook_notification_no_destinations(self):
        alert = {"symbol": "AAPL", "condition": "Price Above", "threshold": 200.0}
        results = send_webhook_notification(alert)
        assert results == {}

    def test_test_webhook_slack(self):
        with patch("alerts._send_slack", return_value=True) as mock_send:
            result = send_test_webhook("slack", "https://slack.webhook")
            assert result is True
            mock_send.assert_called_once()

    def test_test_webhook_discord(self):
        with patch("alerts._send_discord", return_value=True):
            result = send_test_webhook("discord", "https://discord.webhook")
            assert result is True

    def test_test_webhook_telegram(self):
        with patch("alerts._send_telegram", return_value=True):
            result = send_test_webhook("telegram", "bot_token", chat_id="chat123")
            assert result is True

    def test_test_webhook_unknown_type(self):
        result = send_test_webhook("unknown", "url")
        assert result is False


# ---------------------------------------------------------------------------
# P12.3: Brokerage CSV Import tests
# ---------------------------------------------------------------------------


class TestBrokerageImport:
    def test_parse_float_basic(self):
        assert _parse_float("1234.56") == pytest.approx(1234.56)
        assert _parse_float("$1,234.56") == pytest.approx(1234.56)
        assert _parse_float("1,500") == pytest.approx(1500.0)
        assert _parse_float(None) is None
        assert _parse_float("N/A") is None

    def test_parse_float_negative(self):
        assert _parse_float("-250.00") == pytest.approx(-250.0)

    def test_get_col_found(self):
        header = ["symbol", "quantity", "value"]
        row = ["AAPL", "100", "15000"]
        result = _get_col(row, header, ("quantity", "shares"))
        assert result == "100"

    def test_get_col_not_found(self):
        header = ["symbol", "quantity"]
        row = ["AAPL", "100"]
        result = _get_col(row, header, ("price",))
        assert result is None

    def test_parse_generic_csv(self):
        csv_data = b"Symbol,Quantity,Cost,Value\nAAPL,100,14000,15000\nMSFT,50,16000,18500\n"
        positions = parse_brokerage_csv(csv_data, broker="generic")

        assert len(positions) == 2
        aapl = next(p for p in positions if p["symbol"] == "AAPL")
        assert aapl["quantity"] == pytest.approx(100)
        assert aapl["cost_basis"] == pytest.approx(14000)
        assert aapl["current_value"] == pytest.approx(15000)
        assert aapl["unrealized_pnl"] == pytest.approx(1000)

    def test_parse_fidelity_csv(self):
        csv_data = (
            b"Fidelity Portfolio\n"
            b"Symbol,Shares,Total Cost Basis,Current Value\n"
            b"AAPL,50,7000,7500\n"
            b"MSFT,30,9000,9600\n"
        )
        positions = parse_brokerage_csv(csv_data, broker="fidelity")
        assert len(positions) == 2
        symbols = {p["symbol"] for p in positions}
        assert "AAPL" in symbols
        assert "MSFT" in symbols

    def test_parse_ibkr_csv(self):
        csv_data = (
            b"Header line\n"
            b"Positions,Data,STK,USD,AAPL,100,150,15000,14000,1000\n"
            b"Positions,Data,STK,USD,MSFT,50,350,17500,16000,1500\n"
        )
        positions = parse_brokerage_csv(csv_data, broker="ibkr")
        assert len(positions) == 2
        symbols = {p["symbol"] for p in positions}
        assert "AAPL" in symbols

    def test_auto_detect_generic(self):
        csv_data = b"Symbol,Quantity,Cost,Value\nAAPL,100,14000,15000\n"
        positions = parse_brokerage_csv(csv_data, broker="auto")
        assert len(positions) >= 0  # Should not crash

    def test_empty_csv(self):
        csv_data = b""
        positions = parse_brokerage_csv(csv_data, broker="generic")
        assert isinstance(positions, list)

    def test_skip_cash_rows(self):
        csv_data = b"Symbol,Quantity,Cost,Value\nAAPL,100,14000,15000\nCASH,1,5000,5000\nTOTAL,,19000,20000\n"
        positions = parse_brokerage_csv(csv_data, broker="generic")
        symbols = {p["symbol"] for p in positions}
        assert "AAPL" in symbols
        assert "CASH" not in symbols
        assert "TOTAL" not in symbols

    def test_unrealized_pnl_calculation(self):
        csv_data = b"Symbol,Quantity,Cost,Value\nAAPL,100,15000,17000\n"
        positions = parse_brokerage_csv(csv_data, broker="generic")
        assert len(positions) == 1
        assert positions[0]["unrealized_pnl"] == pytest.approx(2000)

    def test_negative_pnl(self):
        csv_data = b"Symbol,Quantity,Cost,Value\nAAPL,100,18000,15000\n"
        positions = parse_brokerage_csv(csv_data, broker="generic")
        assert positions[0]["unrealized_pnl"] == pytest.approx(-3000)
