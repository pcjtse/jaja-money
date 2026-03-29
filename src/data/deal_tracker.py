"""Special Situations Deal Tracker.

Fetches M&A, tender offer, spin-off, and restructuring filings from
SEC EDGAR to identify event-driven investment opportunities.
"""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path

from src.core.log_setup import get_logger

log = get_logger(__name__)

_DATA_DIR = Path.home() / ".jaja-money"
_DB_FILE = _DATA_DIR / "history.db"

_EDGAR_SEARCH = "https://efts.sec.gov/LATEST/search-index"
_EDGAR_API = "https://data.sec.gov/submissions"

_SITUATION_FORMS = {
    "merger": ["8-K", "SC TO-T", "SC TO-I", "SC 13E-3", "DEFM14A", "PREM14A"],
    "spinoff": ["10-12B", "10-12G", "FORM 10"],
    "tender": ["SC TO-T", "SC TO-I", "SC TO-C"],
    "going_private": ["SC 13E-3"],
}

_MERGER_KEYWORDS = [
    "merger agreement", "acquisition agreement", "definitive agreement",
    "transaction agreement", "business combination", "merger consideration",
]

_SPINOFF_KEYWORDS = [
    "spin-off", "spinoff", "separation", "distribution of shares",
    "new independent company",
]


def _connect() -> sqlite3.Connection:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_FILE))
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_situations_table() -> None:
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS special_situations (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol         TEXT NOT NULL,
                situation_type TEXT NOT NULL,
                deal_date      TEXT,
                description    TEXT,
                form_type      TEXT,
                accession      TEXT,
                fetched_at     INTEGER,
                UNIQUE(symbol, situation_type, deal_date)
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_situations_symbol "
            "ON special_situations (symbol)"
        )


_ensure_situations_table()


def _search_edgar_full_text(symbol: str, keywords: list[str], forms: list[str]) -> list[dict]:
    """Search EDGAR full-text for keywords in specific form types."""
    results = []
    try:
        import requests

        query = " OR ".join(f'"{kw}"' for kw in keywords[:3])
        resp = requests.get(
            "https://efts.sec.gov/LATEST/search-index",
            params={
                "q": query,
                "entity": symbol,
                "forms": ",".join(forms),
                "dateRange": "custom",
                "startdt": (datetime.utcnow() - timedelta(days=365)).strftime("%Y-%m-%d"),
                "enddt": datetime.utcnow().strftime("%Y-%m-%d"),
            },
            timeout=10,
            headers={"User-Agent": "jaja-money/1.0 research@example.com"},
        )
        if resp.status_code != 200:
            return results

        data = resp.json()
        hits = data.get("hits", {}).get("hits", [])
        for hit in hits[:5]:
            src = hit.get("_source", {})
            results.append({
                "form_type": src.get("form_type", ""),
                "filed_at": src.get("file_date", ""),
                "accession": src.get("accession_no", ""),
                "description": src.get("period_of_report", ""),
                "entity_name": src.get("entity_name", ""),
            })
    except Exception as exc:
        log.debug("EDGAR full-text search failed for %s: %s", symbol, exc)
    return results


def get_special_situation_filings(symbol: str) -> dict:
    """Search for special situation SEC filings for a symbol.

    Returns
    -------
    dict with keys:
        available (bool)
        situation_type (str): "merger" | "spinoff" | "tender" | "restructuring" | "none"
        filings (list of dict)
        deal_date (str | None)
        description (str)
    """
    symbol = symbol.upper()

    # Check cache
    try:
        cutoff = int(time.time()) - 3600 * 24  # 24h cache
        with _connect() as conn:
            rows = conn.execute(
                "SELECT * FROM special_situations WHERE symbol=? AND fetched_at>? ORDER BY deal_date DESC",
                (symbol, cutoff),
            ).fetchall()
        if rows:
            row = dict(rows[0])
            return {
                "available": True,
                "situation_type": row["situation_type"],
                "filings": [dict(r) for r in rows],
                "deal_date": row.get("deal_date"),
                "description": row.get("description", ""),
            }
    except Exception:
        pass

    merger_filings = _search_edgar_full_text(symbol, _MERGER_KEYWORDS, _SITUATION_FORMS["merger"])
    spinoff_filings = _search_edgar_full_text(symbol, _SPINOFF_KEYWORDS, _SITUATION_FORMS["spinoff"])

    situation_type = "none"
    filings = []
    deal_date = None
    description = ""

    if merger_filings:
        situation_type = "merger"
        filings = merger_filings
        deal_date = merger_filings[0].get("filed_at", "")
        description = f"M&A filing detected: {merger_filings[0].get('form_type', '')}"
    elif spinoff_filings:
        situation_type = "spinoff"
        filings = spinoff_filings
        deal_date = spinoff_filings[0].get("filed_at", "")
        description = f"Spin-off filing detected: {spinoff_filings[0].get('form_type', '')}"

    if situation_type != "none":
        try:
            now = int(time.time())
            with _connect() as conn:
                conn.execute(
                    """INSERT OR REPLACE INTO special_situations
                       (symbol, situation_type, deal_date, description, form_type, accession, fetched_at)
                       VALUES (?,?,?,?,?,?,?)""",
                    (
                        symbol,
                        situation_type,
                        deal_date,
                        description,
                        filings[0].get("form_type", "") if filings else "",
                        filings[0].get("accession", "") if filings else "",
                        now,
                    ),
                )
        except Exception as exc:
            log.debug("Failed to cache special situation for %s: %s", symbol, exc)

    return {
        "available": situation_type != "none",
        "situation_type": situation_type,
        "filings": filings,
        "deal_date": deal_date,
        "description": description,
    }
