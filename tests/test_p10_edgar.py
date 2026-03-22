"""Tests for P10.2: SEC EDGAR Filing Analysis."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import src.data.edgar as edgar_mod
from src.data.edgar import (
    _strip_html,
    chunk_text,
)


def test_strip_html_basic():
    html = "<html><body><p>Hello World</p></body></html>"
    text = _strip_html(html)
    assert "Hello World" in text
    assert "<" not in text


def test_strip_html_entities():
    html = "Revenue &amp; Profit &lt;growth&gt;"
    text = _strip_html(html)
    assert "&" in text
    assert "<growth>" in text


def test_chunk_text_empty():
    assert chunk_text("") == []


def test_chunk_text_short():
    text = "Short text"
    chunks = chunk_text(text, chunk_size=100)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_chunk_text_long():
    text = "A" * 20_000
    chunks = chunk_text(text, chunk_size=8_000)
    assert len(chunks) >= 2
    # All chunks should have content
    for chunk in chunks:
        assert len(chunk) > 0


def test_get_cik_not_found():
    with patch.object(edgar_mod, "requests") as mock_requests:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "0": {"cik_str": 1, "ticker": "AAPL", "title": "Apple Inc."}
        }
        mock_response.raise_for_status = MagicMock()
        mock_requests.get.return_value = mock_response

        cik = edgar_mod.get_cik("AAPL")
        assert cik == "0000000001"


def test_get_cik_request_failure():
    with patch.object(edgar_mod, "requests") as mock_requests:
        mock_requests.get.side_effect = Exception("Network error")
        cik = edgar_mod.get_cik("AAPL")
        assert cik is None


def test_get_recent_filings_no_cik():
    with patch.object(edgar_mod, "get_cik", return_value=None):
        filings = edgar_mod.get_recent_filings("INVALID")
    assert filings == []


def test_get_recent_filings_success():
    mock_submissions = {
        "filings": {
            "recent": {
                "form": ["10-K", "10-Q", "8-K"],
                "filingDate": ["2024-02-01", "2023-11-01", "2023-10-01"],
                "accessionNumber": [
                    "0001234-24-001",
                    "0001234-23-002",
                    "0001234-23-003",
                ],
                "primaryDocument": ["doc1.htm", "doc2.htm", "doc3.htm"],
            }
        }
    }

    with patch.object(edgar_mod, "get_cik", return_value="0000320193"):
        with patch.object(edgar_mod, "requests") as mock_requests:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_submissions
            mock_response.raise_for_status = MagicMock()
            mock_requests.get.return_value = mock_response

            filings = edgar_mod.get_recent_filings("AAPL", form_types=["10-K", "10-Q"])

    assert len(filings) == 2
    assert filings[0]["form"] == "10-K"


def test_fetch_filing_text_failure():
    filing = {"url": "https://invalid.sec.gov/test.htm"}
    with patch.object(edgar_mod, "requests") as mock_requests:
        mock_requests.get.side_effect = Exception("Connection failed")
        text = edgar_mod.fetch_filing_text(filing)
    assert text == ""


def test_fetch_filing_text_html():
    html_content = "<html><body><p>Annual report text here</p></body></html>"
    filing = {"url": "https://sec.gov/test.htm"}

    with patch.object(edgar_mod, "requests") as mock_requests:
        mock_response = MagicMock()
        mock_response.text = html_content
        mock_response.raise_for_status = MagicMock()
        mock_requests.get.return_value = mock_response

        text = edgar_mod.fetch_filing_text(filing, max_chars=1000)

    assert "Annual report text here" in text
    assert "<html>" not in text


def test_stream_filing_analysis_no_text():
    filing = {"form": "10-K", "filingDate": "2024-01-01"}
    chunks = list(edgar_mod.stream_filing_analysis("AAPL", filing, ""))
    assert len(chunks) == 1
    assert "No filing text" in chunks[0]


def test_stream_filing_analysis_with_text():
    filing = {"form": "10-K", "filingDate": "2024-02-01"}
    text = "Revenue grew 12% year over year. Key risks include market competition."

    mock_client = MagicMock()
    mock_stream = MagicMock()
    mock_stream.__enter__ = MagicMock(return_value=mock_stream)
    mock_stream.__exit__ = MagicMock(return_value=False)
    mock_stream.text_stream = iter(["Analysis ", "complete."])
    mock_client.messages.stream.return_value = mock_stream

    with patch.object(edgar_mod, "anthropic") as mock_anthropic_mod:
        mock_anthropic_mod.Anthropic.return_value = mock_client
        chunks = list(edgar_mod.stream_filing_analysis("AAPL", filing, text))

    assert len(chunks) > 0
    assert "".join(chunks) == "Analysis complete."
