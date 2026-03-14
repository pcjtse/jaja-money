"""SEC EDGAR Filing Analysis (P10.2).

Fetches 10-K / 10-Q / 8-K filings from SEC EDGAR and streams Claude analysis
covering key risks, revenue drivers, guidance language, and red flags.

Usage:
    from edgar import get_recent_filings, fetch_filing_text, stream_filing_analysis
"""
from __future__ import annotations

import os
import re
from typing import Generator

import anthropic
import requests

from log_setup import get_logger

log = get_logger(__name__)

_EDGAR_BASE = "https://data.sec.gov"
_EDGAR_SEARCH = "https://efts.sec.gov/LATEST/search-index"
_HEADERS = {"User-Agent": "jaja-money/1.0 (research tool; contact@example.com)"}
_CHUNK_SIZE = 8_000  # characters per chunk sent to Claude
_MAX_CHUNKS = 6  # limit chunks to control token costs


# ---------------------------------------------------------------------------
# EDGAR API helpers
# ---------------------------------------------------------------------------


def get_cik(ticker: str) -> str | None:
    """Look up the CIK (Central Index Key) for a ticker symbol."""
    try:
        # Use EDGAR company tickers JSON
        resp = requests.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers=_HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        ticker_upper = ticker.upper()
        for entry in data.values():
            if entry.get("ticker", "").upper() == ticker_upper:
                cik = str(entry["cik_str"]).zfill(10)
                log.debug("CIK for %s: %s", ticker, cik)
                return cik
    except Exception as exc:
        log.warning("Failed to look up CIK for %s: %s", ticker, exc)
    return None


def get_recent_filings(ticker: str, form_types: list[str] | None = None) -> list[dict]:
    """Return recent filings for a ticker from SEC EDGAR.

    Parameters
    ----------
    ticker : stock ticker symbol
    form_types : list of form types to filter, e.g. ["10-K", "10-Q", "8-K"]
                 Defaults to ["10-K", "10-Q"].

    Returns list of dicts with: form, filingDate, accessionNumber, primaryDocument.
    """
    if form_types is None:
        form_types = ["10-K", "10-Q"]

    cik = get_cik(ticker)
    if not cik:
        return []

    try:
        url = f"{_EDGAR_BASE}/submissions/CIK{cik}.json"
        resp = requests.get(url, headers=_HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        filings = data.get("filings", {}).get("recent", {})
        forms = filings.get("form", [])
        dates = filings.get("filingDate", [])
        accessions = filings.get("accessionNumber", [])
        primary_docs = filings.get("primaryDocument", [])

        results = []
        for form, date, acc, doc in zip(forms, dates, accessions, primary_docs):
            if form in form_types:
                results.append(
                    {
                        "form": form,
                        "filingDate": date,
                        "accessionNumber": acc,
                        "primaryDocument": doc,
                        "cik": cik,
                        "url": _filing_url(cik, acc, doc),
                    }
                )
        # Return most recent first
        results.sort(key=lambda x: x["filingDate"], reverse=True)
        log.info("Found %d %s filings for %s", len(results), form_types, ticker)
        return results[:10]
    except Exception as exc:
        log.warning("Failed to fetch filings for %s: %s", ticker, exc)
        return []


def _filing_url(cik: str, accession: str, document: str) -> str:
    acc_clean = accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_clean}/{document}"


def fetch_filing_text(filing: dict, max_chars: int = 50_000) -> str:
    """Download and extract plain text from an EDGAR filing document.

    Parameters
    ----------
    filing : filing dict from get_recent_filings
    max_chars : maximum characters to return

    Returns cleaned plain text content.
    """
    url = filing.get("url", "")
    if not url:
        return ""

    try:
        resp = requests.get(url, headers=_HEADERS, timeout=30)
        resp.raise_for_status()
        raw = resp.text

        # Strip HTML tags if present
        if "<html" in raw.lower() or "<body" in raw.lower():
            raw = _strip_html(raw)

        # Clean up excessive whitespace
        text = re.sub(r"\n{3,}", "\n\n", raw)
        text = re.sub(r"[ \t]{2,}", " ", text)
        text = text.strip()

        log.info(
            "Fetched filing text: %d chars (truncated to %d)", len(text), max_chars
        )
        return text[:max_chars]
    except Exception as exc:
        log.warning("Failed to fetch filing text from %s: %s", url, exc)
        return ""


def _strip_html(html: str) -> str:
    """Remove HTML tags and decode basic entities."""
    # Remove script/style blocks
    html = re.sub(r"<(script|style)[^>]*>.*?</(script|style)>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    # Remove all tags
    text = re.sub(r"<[^>]+>", " ", html)
    # Decode entities
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return text


def chunk_text(text: str, chunk_size: int = _CHUNK_SIZE) -> list[str]:
    """Split text into overlapping chunks suitable for Claude analysis."""
    if not text:
        return []
    # Ensure overlap is at most 10% of chunk_size to prevent infinite loops
    overlap = min(500, chunk_size // 10)
    step = max(1, chunk_size - overlap)
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        start += step
    return chunks


# ---------------------------------------------------------------------------
# Claude integration
# ---------------------------------------------------------------------------


def stream_filing_analysis(
    symbol: str,
    filing: dict,
    filing_text: str,
    prior_text: str = "",
) -> Generator[str, None, None]:
    """Stream Claude analysis of an SEC filing.

    Parameters
    ----------
    symbol : stock ticker
    filing : filing metadata dict
    filing_text : extracted text of current filing
    prior_text : extracted text of prior period filing (optional, for diff)

    Yields text chunks from Claude.
    """
    chunks = chunk_text(filing_text)[:_MAX_CHUNKS]
    if not chunks:
        yield "No filing text available to analyze."
        return

    combined_text = "\n\n---\n\n".join(chunks)
    form_type = filing.get("form", "Filing")
    filing_date = filing.get("filingDate", "")

    diff_section = ""
    if prior_text:
        prior_chunks = chunk_text(prior_text)[:2]
        prior_combined = "\n\n".join(prior_chunks)
        diff_section = f"""

**PRIOR PERIOD FILING (for comparison):**
{prior_combined[:4000]}

Please compare language changes between the current and prior filing in Risk Factors and MD&A sections."""

    prompt = f"""You are an expert securities analyst reviewing an SEC {form_type} filing for {symbol} (filed {filing_date}).

**FILING TEXT (excerpts):**
{combined_text}
{diff_section}

Provide a structured analysis covering:

## 1. Key Business Risks
Identify the top 3-5 material risks disclosed. Note any new or escalating risks.

## 2. Revenue Drivers & Business Momentum
Summarize the main revenue drivers, segment performance, and guidance language.

## 3. Management Tone & Language
Assess the tone of MD&A — is management confident or hedging? Any cautionary language?

## 4. Red Flags
List any concerning disclosures: litigation, regulatory issues, going-concern language, unusual accounting changes.

## 5. Forward-Looking Statements
Extract key guidance and forward-looking statements with the implied outlook.

Be specific, cite section names when possible, and flag anything a fundamental investor should scrutinize."""

    try:
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                yield text
    except Exception as exc:
        yield f"\n\n*Error during filing analysis: {exc}*"


# ---------------------------------------------------------------------------
# P19.2: Supply chain extraction — business section parser
# ---------------------------------------------------------------------------


def extract_business_sections(filing_text: str) -> dict:
    """Extract the BUSINESS and RISK FACTORS sections from a 10-K filing.

    Looks for section headers matching ``ITEM 1.`` (business) and
    ``ITEM 1A.`` (risk factors), case-insensitively. The search is tolerant
    of varied whitespace and punctuation between "ITEM" and the number.

    Parameters
    ----------
    filing_text : plain text content of a 10-K filing as returned by
                  fetch_filing_text

    Returns
    -------
    dict with keys:
        business_section : str  — first 4 000 chars of the Business section
        risk_factors     : str  — first 3 000 chars of the Risk Factors section
        available        : bool — True if at least one section was found
    """
    import re as _re

    result = {
        "business_section": "",
        "risk_factors": "",
        "available": False,
    }

    if not filing_text:
        return result

    # Patterns for common 10-K section headers (case-insensitive)
    # Matches "ITEM 1." / "ITEM 1 ." / "Item 1:" etc.
    _ITEM1_RE = _re.compile(
        r"(?:^|\n)\s*ITEM\s+1\.?\s*[:\-]?\s*BUSINESS\b",
        _re.IGNORECASE,
    )
    _ITEM1A_RE = _re.compile(
        r"(?:^|\n)\s*ITEM\s+1A\.?\s*[:\-]?\s*RISK\s+FACTORS?\b",
        _re.IGNORECASE,
    )
    # Generic next-item boundary: Item 2 onwards (or Item 1A when we are in Item 1)
    _ITEM2_RE = _re.compile(
        r"(?:^|\n)\s*ITEM\s+[2-9]",
        _re.IGNORECASE,
    )
    _ITEM1A_BOUNDARY_RE = _re.compile(
        r"(?:^|\n)\s*ITEM\s+1A\b",
        _re.IGNORECASE,
    )

    # --- Extract BUSINESS section (Item 1) ---
    m1 = _ITEM1_RE.search(filing_text)
    if m1:
        start = m1.end()
        # End at Item 1A or Item 2+
        end_match = _ITEM1A_BOUNDARY_RE.search(filing_text, start)
        if not end_match:
            end_match = _ITEM2_RE.search(filing_text, start)
        end = end_match.start() if end_match else start + 6000
        section_text = filing_text[start:end].strip()
        result["business_section"] = section_text[:4000]
        result["available"] = True
        log.debug("Extracted BUSINESS section: %d chars", len(result["business_section"]))

    # --- Extract RISK FACTORS section (Item 1A) ---
    m1a = _ITEM1A_RE.search(filing_text)
    if m1a:
        start = m1a.end()
        # End at Item 2+
        end_match = _ITEM2_RE.search(filing_text, start)
        end = end_match.start() if end_match else start + 5000
        section_text = filing_text[start:end].strip()
        result["risk_factors"] = section_text[:3000]
        result["available"] = True
        log.debug("Extracted RISK FACTORS section: %d chars", len(result["risk_factors"]))

    return result
