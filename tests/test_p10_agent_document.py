"""Tests for P10.3: Agent Mode and P10.5: Document Analysis."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agent import _execute_tool, run_research_agent
from document_analysis import (
    _chunk_text,
    extract_pdf_text,
    stream_document_analysis,
)


# ---------------------------------------------------------------------------
# P10.3: Agent Mode tests
# ---------------------------------------------------------------------------


class TestAgentMode:
    def test_execute_tool_get_quote(self):
        mock_api = MagicMock()
        mock_api.get_quote.return_value = {"c": 150.0, "dp": 1.5}

        result = _execute_tool("get_quote", {"symbol": "AAPL"}, mock_api)
        assert "150.0" in result
        mock_api.get_quote.assert_called_once_with("AAPL")

    def test_execute_tool_get_financials(self):
        mock_api = MagicMock()
        mock_api.get_financials.return_value = {"peBasicExclExtraTTM": 25.0}

        result = _execute_tool("get_financials", {"symbol": "AAPL"}, mock_api)
        assert "25.0" in result

    def test_execute_tool_get_news(self):
        mock_api = MagicMock()
        mock_api.get_news.return_value = [
            {"headline": "AAPL hits all-time high", "summary": "Strong demand."}
        ]
        result = _execute_tool("get_news", {"symbol": "AAPL", "days": 7}, mock_api)
        assert "AAPL hits all-time high" in result

    def test_execute_tool_get_earnings(self):
        mock_api = MagicMock()
        mock_api.get_earnings.return_value = [
            {"actual": 1.5, "estimate": 1.4, "period": "2024Q1"}
        ]
        result = _execute_tool("get_earnings", {"symbol": "AAPL", "limit": 4}, mock_api)
        assert "1.5" in result

    def test_execute_tool_get_peers(self):
        mock_api = MagicMock()
        mock_api.get_peers.return_value = ["MSFT", "GOOGL", "META"]
        result = _execute_tool("get_peers", {"symbol": "AAPL"}, mock_api)
        assert "MSFT" in result

    def test_execute_tool_unknown(self):
        mock_api = MagicMock()
        result = _execute_tool("unknown_tool", {"symbol": "AAPL"}, mock_api)
        assert "Unknown tool" in result

    def test_execute_tool_api_failure(self):
        mock_api = MagicMock()
        mock_api.get_quote.side_effect = Exception("API error")
        result = _execute_tool("get_quote", {"symbol": "AAPL"}, mock_api)
        assert "error" in result.lower() or "API error" in result

    def test_run_research_agent_yields_text(self):
        mock_api = MagicMock()

        # Mock Claude client with tool use then end turn
        mock_client = MagicMock()

        # First response: text only (end_turn)
        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 200

        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Investment memo for AAPL: Strong fundamentals."

        mock_response.content = [text_block]
        mock_client.messages.create.return_value = mock_response

        with patch("agent.anthropic") as mock_anthropic_module:
            mock_anthropic_module.Anthropic.return_value = mock_client

            chunks = list(
                run_research_agent("AAPL", mock_api, "What is the bull case?")
            )

        output = "".join(chunks)
        assert "AAPL" in output or "Strong fundamentals" in output

    def test_run_research_agent_cap_on_turns(self):
        mock_api = MagicMock()
        mock_api.get_quote.return_value = {"c": 150.0}

        mock_client = MagicMock()

        # Always return tool calls (to test turn cap)
        turn_count = [0]

        def make_response():
            turn_count[0] += 1
            mock_response = MagicMock()
            mock_response.stop_reason = "tool_use"
            mock_response.usage.input_tokens = 50
            mock_response.usage.output_tokens = 50

            tool_block = MagicMock()
            tool_block.type = "tool_use"
            tool_block.name = "get_quote"
            tool_block.id = f"tool_{turn_count[0]}"
            tool_block.input = {"symbol": "AAPL"}

            mock_response.content = [tool_block]
            return mock_response

        mock_client.messages.create.side_effect = lambda **kwargs: make_response()

        with patch("agent.anthropic") as mock_anthropic_module:
            mock_anthropic_module.Anthropic.return_value = mock_client

            list(run_research_agent("AAPL", mock_api))

        # Should cap at _MAX_TURNS (10)
        assert turn_count[0] <= 10


# ---------------------------------------------------------------------------
# P10.5: Document Analysis tests
# ---------------------------------------------------------------------------


class TestDocumentAnalysis:
    def test_chunk_text_empty(self):
        assert _chunk_text("") == []

    def test_chunk_text_short(self):
        text = "Short document text"
        chunks = _chunk_text(text, size=100)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_chunk_text_long(self):
        text = "X" * 20_000
        chunks = _chunk_text(text, size=6_000)
        assert len(chunks) >= 3

    def test_extract_pdf_too_large(self):
        large_data = b"x" * (21 * 1024 * 1024)
        with pytest.raises(ValueError, match="too large"):
            extract_pdf_text(large_data)

    def test_extract_pdf_no_library(self):
        """Should raise RuntimeError when neither pdfplumber nor PyMuPDF is installed."""
        pdf_data = b"%PDF-1.4 fake pdf content"
        with patch("document_analysis._try_pdfplumber", return_value=""):
            with patch("document_analysis._try_pymupdf", return_value=""):
                with pytest.raises(RuntimeError, match="Could not extract text"):
                    extract_pdf_text(pdf_data)

    def test_extract_pdf_with_pdfplumber(self):
        """Test extraction using pdfplumber mock."""
        pdf_data = b"%PDF-1.4 content"
        with patch(
            "document_analysis._try_pdfplumber", return_value="Extracted text from PDF"
        ):
            result = extract_pdf_text(pdf_data)
        assert result == "Extracted text from PDF"

    def test_extract_pdf_fallback_to_pymupdf(self):
        """Should fall back to PyMuPDF when pdfplumber fails."""
        pdf_data = b"%PDF-1.4 content"
        with patch("document_analysis._try_pdfplumber", return_value=""):
            with patch("document_analysis._try_pymupdf", return_value="PyMuPDF text"):
                result = extract_pdf_text(pdf_data)
        assert result == "PyMuPDF text"

    def test_stream_document_analysis_empty_text(self):
        chunks = list(stream_document_analysis(""))
        assert len(chunks) == 1
        assert "No text" in chunks[0]

    def test_stream_document_analysis_with_text(self):
        text = "Revenue grew 15%. Key risks: competition and macro headwinds."

        with patch("document_analysis.anthropic") as mock_anthropic_module:
            mock_client = MagicMock()
            mock_anthropic_module.Anthropic.return_value = mock_client

            mock_stream = MagicMock()
            mock_stream.__enter__ = MagicMock(return_value=mock_stream)
            mock_stream.__exit__ = MagicMock(return_value=False)
            mock_stream.text_stream = iter(["Analysis: ", "Revenue grew."])
            mock_client.messages.stream.return_value = mock_stream

            chunks = list(
                stream_document_analysis(
                    text,
                    document_name="Test Report",
                    symbol="AAPL",
                )
            )

        assert "".join(chunks) == "Analysis: Revenue grew."

    def test_stream_document_analysis_with_market_data(self):
        text = "Strong quarterly results."
        market_data = {"price": 150.0, "pe": 25.0, "eps": 6.0}

        with patch("document_analysis.anthropic") as mock_anthropic_module:
            mock_client = MagicMock()
            mock_anthropic_module.Anthropic.return_value = mock_client

            mock_stream = MagicMock()
            mock_stream.__enter__ = MagicMock(return_value=mock_stream)
            mock_stream.__exit__ = MagicMock(return_value=False)
            mock_stream.text_stream = iter(["Complete analysis."])
            mock_client.messages.stream.return_value = mock_stream

            list(
                stream_document_analysis(
                    text,
                    symbol="AAPL",
                    market_data=market_data,
                )
            )

        # Verify market data was included in prompt (check call args)
        call_args = mock_client.messages.stream.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages", [])
        prompt = messages[0]["content"] if messages else ""
        assert "150.0" in prompt or "25.0" in prompt

    def test_stream_document_analysis_error_handling(self):
        text = "Some document text."

        with patch("document_analysis.anthropic") as mock_anthropic_module:
            mock_client = MagicMock()
            mock_anthropic_module.Anthropic.return_value = mock_client
            mock_client.messages.stream.side_effect = Exception("API error")

            chunks = list(stream_document_analysis(text))

        output = "".join(chunks)
        assert "error" in output.lower() or "Error" in output
