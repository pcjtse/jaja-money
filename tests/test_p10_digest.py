"""Tests for P10.1: Automated Daily Watchlist Digest."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from digest import (
    _build_html,
    _generate_ticker_section,
    generate_digest,
    get_latest_digest,
    list_digests,
    read_digest_html,
    send_digest_email,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_api():
    api = MagicMock()
    api.get_quote.return_value = {"c": 150.0, "pc": 148.0, "dp": 1.35}
    api.get_news.return_value = [
        {"headline": "AAPL hits new high", "summary": "Apple stock rises."},
        {"headline": "Strong iPhone demand", "summary": "Demand remains strong."},
    ]
    return api


@pytest.fixture
def tmp_digest_dir(tmp_path, monkeypatch):
    digest_dir = tmp_path / "digests"
    digest_dir.mkdir()
    monkeypatch.setattr("digest._DIGEST_DIR", digest_dir)
    monkeypatch.setattr("digest._DATA_DIR", tmp_path)
    return digest_dir


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_build_html_contains_tickers():
    sections = ["<div>AAPL section</div>", "<div>MSFT section</div>"]
    html = _build_html("2024-01-15", sections)
    assert "2024-01-15" in html
    assert "AAPL section" in html
    assert "MSFT section" in html
    assert "<!DOCTYPE html>" in html


def test_build_html_structure():
    html = _build_html("2024-01-15", ["<div>test</div>"])
    assert "<html" in html
    assert "</html>" in html
    assert "jaja-money" in html.lower() or "Morning Watchlist" in html


def test_generate_ticker_section_success(mock_api):
    with patch("digest.anthropic") as mock_anthropic:
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Apple is up 1.35% on strong demand.")]
        mock_client.messages.create.return_value = mock_response

        section = _generate_ticker_section("AAPL", mock_api)

    assert section is not None
    assert "AAPL" in section
    assert "150.00" in section or "1.35" in section


def test_generate_ticker_section_api_failure():
    api = MagicMock()
    api.get_quote.side_effect = ValueError("No data")
    section = _generate_ticker_section("INVALID", api)
    assert section is None


def test_list_digests_empty(tmp_digest_dir):
    digests = list_digests()
    assert digests == []


def test_list_digests_with_files(tmp_digest_dir):
    # Create test digest files
    (tmp_digest_dir / "2024-01-15.html").write_text("<html>test</html>")
    (tmp_digest_dir / "2024-01-14.html").write_text("<html>old</html>")

    digests = list_digests()
    assert len(digests) == 2
    # Newest first
    assert digests[0]["date"] == "2024-01-15"
    assert digests[1]["date"] == "2024-01-14"


def test_get_latest_digest_none(tmp_digest_dir):
    assert get_latest_digest() is None


def test_get_latest_digest(tmp_digest_dir):
    (tmp_digest_dir / "2024-01-15.html").write_text("<html>latest</html>")
    path = get_latest_digest()
    assert path is not None
    assert "2024-01-15" in path


def test_read_digest_html(tmp_path):
    test_file = tmp_path / "test.html"
    test_file.write_text("<html>content</html>")
    content = read_digest_html(str(test_file))
    assert content == "<html>content</html>"


def test_read_digest_html_missing(tmp_path):
    content = read_digest_html(str(tmp_path / "nonexistent.html"))
    assert content == ""


def test_generate_digest_empty_watchlist(tmp_digest_dir):
    with patch("digest.get_watchlist", return_value=[]):
        result = generate_digest(MagicMock())
    assert result is None


def test_generate_digest_creates_file(tmp_digest_dir, mock_api):
    with patch("digest.get_watchlist", return_value=[{"symbol": "AAPL"}]):
        with patch("digest._generate_ticker_section", return_value="<div>AAPL</div>"):
            result = generate_digest(mock_api)

    assert result is not None
    assert Path(result).exists()


def test_send_email_missing_smtp():
    # Should fail gracefully (no real SMTP server)
    success = send_digest_email(
        html_path="/nonexistent/path.html",
        to_address="test@example.com",
        smtp_host="invalid.host",
        smtp_port=25,
    )
    assert success is False
