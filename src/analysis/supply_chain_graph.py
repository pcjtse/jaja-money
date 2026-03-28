"""Supply Chain Risk Graph.

Builds and scores a directed supply chain graph from SEC EDGAR business
section text. Measures:
  - Concentration risk (Herfindahl index on supplier count)
  - Geographic risk (suppliers in politically risky regions)
  - Single-source dependency

High concentration + single-source dependency = high risk signal.
"""

from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path

from src.core.log_setup import get_logger

log = get_logger(__name__)

_DATA_DIR = Path.home() / ".jaja-money"
_DB_FILE = _DATA_DIR / "history.db"

# Countries considered elevated geopolitical risk for supply chain
_HIGH_RISK_REGIONS = {
    "china", "russia", "iran", "north korea", "belarus",
    "myanmar", "venezuela", "cuba", "syria",
}

_SUPPLIER_KEYWORDS = [
    r"sole[-\s]source",
    r"single[-\s]source",
    r"sole supplier",
    r"depend\w+ on\w* (?:a single|one|sole)",
    r"key supplier",
    r"primary supplier",
    r"principal supplier",
    r"critical supplier",
    r"manufactured (?:by|in)",
    r"produced (?:by|in)",
    r"outsource\w*",
    r"contract manufacturer",
    r"third[-\s]party manufacturer",
]

_CUSTOMER_KEYWORDS = [
    r"single customer",
    r"one customer",
    r"concentration\w* (?:of|in) customer",
    r"significant customer",
    r"major customer",
    r"key customer",
]


def _connect() -> sqlite3.Connection:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_FILE))
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_supply_chain_tables() -> None:
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS supply_chain_nodes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol      TEXT NOT NULL,
                node_name   TEXT NOT NULL,
                node_type   TEXT NOT NULL,
                region      TEXT,
                fetched_at  INTEGER,
                UNIQUE(symbol, node_name, node_type)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS supply_chain_edges (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                from_symbol TEXT NOT NULL,
                to_node     TEXT NOT NULL,
                edge_type   TEXT NOT NULL,
                weight      REAL DEFAULT 1.0,
                fetched_at  INTEGER
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sc_nodes_symbol "
            "ON supply_chain_nodes (symbol)"
        )


_ensure_supply_chain_tables()


def parse_supply_chain_from_text(symbol: str, text: str) -> dict:
    """Extract supply chain risk indicators from SEC filing text.

    Parameters
    ----------
    symbol : stock ticker
    text   : business section text from 10-K / 10-Q

    Returns
    -------
    dict with keys:
        sole_source_risk (bool): single-source dependency detected
        supplier_count_est (int): estimated number of named suppliers
        customer_concentration (bool): customer concentration warning
        high_risk_regions (list): geopolitically risky regions mentioned
        risk_snippets (list): relevant text excerpts
        concentration_score (int): 0-100 (0=diverse, 100=very concentrated)
    """
    text_lower = text.lower()

    sole_source = _find_pattern_matches(text_lower, _SUPPLIER_KEYWORDS)
    customer_conc = _find_pattern_matches(text_lower, _CUSTOMER_KEYWORDS)

    risk_regions = [r for r in _HIGH_RISK_REGIONS if r in text_lower]

    # Extract snippets around matches (first 3)
    snippets: list[str] = []
    for kw in _SUPPLIER_KEYWORDS[:5]:
        for m in re.finditer(kw, text_lower):
            start = max(0, m.start() - 80)
            end = min(len(text_lower), m.end() + 80)
            snippets.append(text[start:end].strip())
            if len(snippets) >= 3:
                break
        if len(snippets) >= 3:
            break

    # Heuristic supplier count
    supplier_count = _estimate_supplier_count(text_lower)

    # Herfindahl-like concentration score
    if sole_source:
        concentration_score = 90
    elif supplier_count <= 2:
        concentration_score = 75
    elif supplier_count <= 5:
        concentration_score = 55
    elif supplier_count <= 10:
        concentration_score = 35
    else:
        concentration_score = 15

    if risk_regions:
        concentration_score = min(100, concentration_score + len(risk_regions) * 10)

    _persist_nodes(symbol, risk_regions, supplier_count, sole_source)

    return {
        "sole_source_risk": bool(sole_source),
        "supplier_count_est": supplier_count,
        "customer_concentration": bool(customer_conc),
        "high_risk_regions": risk_regions,
        "risk_snippets": snippets[:3],
        "concentration_score": concentration_score,
    }


def score_supply_chain_risk(supply_chain_data: dict) -> dict:
    """Convert parsed supply chain data to a factor score dict.

    Returns
    -------
    dict with score (int 0-100), label (str), detail (str)
    Score is INVERTED: high concentration_score = low factor score.
    """
    conc = supply_chain_data.get("concentration_score", 50)
    sole = supply_chain_data.get("sole_source_risk", False)
    regions = supply_chain_data.get("high_risk_regions", [])
    cust_conc = supply_chain_data.get("customer_concentration", False)

    # Factor score: low concentration = high score
    base = 100 - conc

    if sole:
        base = max(5, base - 15)
    if len(regions) >= 2:
        base = max(5, base - 15)
    elif len(regions) == 1:
        base = max(10, base - 8)
    if cust_conc:
        base = max(5, base - 10)

    score = max(0, min(100, base))

    if score >= 75:
        label = "Diversified supply chain"
    elif score >= 55:
        label = "Moderate supply chain risk"
    elif score >= 35:
        label = "Elevated concentration risk"
    else:
        label = "High supply chain concentration"

    parts = [f"Concentration score: {conc}/100"]
    if sole:
        parts.append("Single-source dependency detected")
    if regions:
        parts.append(f"High-risk regions: {', '.join(regions)}")
    if cust_conc:
        parts.append("Customer concentration risk")

    return {"score": score, "label": label, "detail": " | ".join(parts)}


def _find_pattern_matches(text: str, patterns: list[str]) -> list[str]:
    matches = []
    for pattern in patterns:
        if re.search(pattern, text):
            matches.append(pattern)
    return matches


def _estimate_supplier_count(text: str) -> int:
    """Rough estimate of named suppliers from text."""
    # Look for "supplier" mentions with ordinals or names
    supplier_refs = len(re.findall(r"\bsupplier\b", text))
    manufacturer_refs = len(re.findall(r"\bmanufacturer\b", text))
    total_refs = supplier_refs + manufacturer_refs
    if total_refs == 0:
        return 10
    if total_refs <= 2:
        return 2
    if total_refs <= 5:
        return 5
    if total_refs <= 10:
        return 8
    return 15


def _persist_nodes(
    symbol: str, regions: list[str], supplier_count: int, sole_source: bool
) -> None:
    now = int(time.time())
    try:
        with _connect() as conn:
            node_type = "sole_source" if sole_source else "multi_source"
            conn.execute(
                """INSERT OR REPLACE INTO supply_chain_nodes
                   (symbol, node_name, node_type, region, fetched_at)
                   VALUES (?,?,?,?,?)""",
                (symbol, f"{symbol}_suppliers", node_type, ",".join(regions) or "unknown", now),
            )
    except Exception as exc:
        log.debug("Supply chain node persist failed: %s", exc)
