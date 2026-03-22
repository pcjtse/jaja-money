"""Multi-Modal: Upload & Analyze Financial PDFs (P10.5).

Extracts text from uploaded PDFs (10-K, earnings slides, research reports)
and streams Claude financial analysis including key numbers, risks, and red flags.

Usage:
    from src.analysis.document_analysis import extract_pdf_text, stream_document_analysis
"""

from __future__ import annotations

import io
import os
from typing import Generator

import anthropic

from src.core.log_setup import get_logger

log = get_logger(__name__)

_CHUNK_SIZE = 6_000
_MAX_CHUNKS = 8
_MAX_PDF_BYTES = 20 * 1024 * 1024  # 20 MB


# ---------------------------------------------------------------------------
# PDF text extraction
# ---------------------------------------------------------------------------


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract plain text from a PDF byte stream.

    Tries pdfplumber first, falls back to PyMuPDF (fitz), then returns empty.
    """
    if len(pdf_bytes) > _MAX_PDF_BYTES:
        raise ValueError(
            f"PDF too large: {len(pdf_bytes) / 1024 / 1024:.1f} MB (max 20 MB)"
        )

    text = _try_pdfplumber(pdf_bytes)
    if text:
        return text

    text = _try_pymupdf(pdf_bytes)
    if text:
        return text

    raise RuntimeError(
        "Could not extract text from PDF. "
        "Install 'pdfplumber' or 'PyMuPDF' (pip install pdfplumber pymupdf)."
    )


def _try_pdfplumber(pdf_bytes: bytes) -> str:
    """Extract text using pdfplumber."""
    try:
        import pdfplumber

        pages = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    pages.append(page_text)
        text = "\n\n".join(pages)
        log.info("pdfplumber extracted %d chars from PDF", len(text))
        return text
    except ImportError:
        return ""
    except Exception as exc:
        log.warning("pdfplumber failed: %s", exc)
        return ""


def _try_pymupdf(pdf_bytes: bytes) -> str:
    """Extract text using PyMuPDF (fitz)."""
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages = []
        for page in doc:
            pages.append(page.get_text())
        text = "\n\n".join(pages)
        log.info("PyMuPDF extracted %d chars from PDF", len(text))
        return text
    except ImportError:
        return ""
    except Exception as exc:
        log.warning("PyMuPDF failed: %s", exc)
        return ""


# ---------------------------------------------------------------------------
# Claude analysis
# ---------------------------------------------------------------------------


def stream_document_analysis(
    text: str,
    document_name: str = "Financial Document",
    symbol: str | None = None,
    market_data: dict | None = None,
) -> Generator[str, None, None]:
    """Stream Claude analysis of extracted PDF text.

    Parameters
    ----------
    text : extracted document text
    document_name : filename or document title for context
    symbol : stock ticker if known (for cross-referencing live data)
    market_data : optional dict of live market metrics for cross-referencing

    Yields text chunks from Claude.
    """
    if not text.strip():
        yield "No text could be extracted from the document."
        return

    # Chunk and limit
    chunks = _chunk_text(text)[:_MAX_CHUNKS]
    combined = "\n\n---\n\n".join(chunks)

    market_context = ""
    if market_data and symbol:
        metrics = market_data
        market_context = f"""
**Live Market Data for {symbol}:**
- Current Price: ${metrics.get("price", "N/A")}
- P/E Ratio: {metrics.get("pe", "N/A")}
- EPS (TTM): {metrics.get("eps", "N/A")}
- Revenue Growth: {metrics.get("revenue_growth", "N/A")}%
- Gross Margin: {metrics.get("gross_margin", "N/A")}%

Cross-reference the document's claims against this live data where relevant."""

    ticker_context = f" for {symbol}" if symbol else ""

    prompt = f"""You are a senior financial analyst reviewing the document: **{document_name}**{ticker_context}.

**DOCUMENT CONTENT (excerpts):**
{combined}
{market_context}

Provide a structured financial analysis:

## Key Financial Metrics
Extract and highlight the most important numbers: revenue, earnings, margins, growth rates, guidance.

## Business Drivers
What are the primary drivers of revenue and profitability? Any notable segment performance?

## Risk Factors
Identify the top risks mentioned — operational, competitive, regulatory, macro.

## Red Flags
Flag any concerning language: going-concern, material weaknesses, unusual accounting, covenant breaches, executive departures.

## Guidance & Outlook
Summarize any forward-looking guidance, management expectations, or strategic initiatives.

## Key Takeaways
3-5 bullet points summarizing the most important insights from this document for an equity investor.

Be specific, cite page or section references if present in the text."""

    try:
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for chunk in stream.text_stream:
                yield chunk
    except Exception as exc:
        yield f"\n\n*Error during document analysis: {exc}*"


def _chunk_text(text: str, size: int = _CHUNK_SIZE) -> list[str]:
    """Split text into fixed-size chunks."""
    if not text:
        return []
    overlap = min(300, size // 10)
    step = max(1, size - overlap)
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        chunks.append(text[start:end])
        start += step
    return chunks
