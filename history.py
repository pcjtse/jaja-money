"""Historical factor score tracking using SQLite.

Stores analysis snapshots (factor score, risk score, price, flags) keyed
by (symbol, date) in ~/.jaja-money/history.db.

Usage:
    from history import save_analysis, get_history, get_score_trend
"""
from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from log_setup import get_logger

log = get_logger(__name__)

_DATA_DIR = Path.home() / ".jaja-money"
_DB_FILE = _DATA_DIR / "history.db"


def _connect() -> sqlite3.Connection:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_FILE))
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_table() -> None:
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS analysis_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol      TEXT NOT NULL,
                date        TEXT NOT NULL,
                timestamp   INTEGER NOT NULL,
                price       REAL,
                factor_score INTEGER,
                risk_score   INTEGER,
                composite_label TEXT,
                risk_level   TEXT,
                factors_json TEXT,
                flags_json   TEXT
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_symbol_date "
            "ON analysis_history (symbol, date)"
        )


_ensure_table()


def save_analysis(
    symbol: str,
    price: float | None,
    factor_score: int,
    risk_score: int,
    composite_label: str = "",
    risk_level: str = "",
    factors: list | None = None,
    flags: list | None = None,
) -> None:
    """Upsert today's analysis snapshot for a symbol."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    symbol = symbol.upper()
    try:
        with _connect() as conn:
            # Remove existing entry for today
            conn.execute(
                "DELETE FROM analysis_history WHERE symbol=? AND date=?",
                (symbol, today),
            )
            conn.execute(
                """INSERT INTO analysis_history
                   (symbol, date, timestamp, price, factor_score, risk_score,
                    composite_label, risk_level, factors_json, flags_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    symbol,
                    today,
                    int(time.time()),
                    price,
                    factor_score,
                    risk_score,
                    composite_label,
                    risk_level,
                    json.dumps(factors or []),
                    json.dumps(flags or []),
                ),
            )
        log.info("Saved analysis snapshot for %s on %s", symbol, today)
    except Exception as exc:
        log.warning("Failed to save analysis history for %s: %s", symbol, exc)


def get_history(symbol: str, limit: int = 90) -> list[dict]:
    """Return chronological analysis history for a symbol (up to `limit` days)."""
    symbol = symbol.upper()
    try:
        with _connect() as conn:
            rows = conn.execute(
                """SELECT * FROM analysis_history
                   WHERE symbol=?
                   ORDER BY date ASC
                   LIMIT ?""",
                (symbol, limit),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as exc:
        log.warning("Failed to fetch history for %s: %s", symbol, exc)
        return []


def get_score_trend(symbol: str, limit: int = 30) -> dict:
    """Return date/factor_score/risk_score arrays for charting."""
    rows = get_history(symbol, limit=limit)
    return {
        "dates": [r["date"] for r in rows],
        "factor_scores": [r["factor_score"] for r in rows],
        "risk_scores": [r["risk_score"] for r in rows],
        "prices": [r["price"] for r in rows],
    }


def get_latest_two_snapshots(symbol: str) -> list[dict]:
    """Return the two most recent distinct-date analysis snapshots for a symbol.

    Returns a list of 0–2 dicts, sorted oldest-first, so index 0 is the
    previous snapshot and index 1 is the most recent one.
    """
    symbol = symbol.upper()
    try:
        with _connect() as conn:
            rows = conn.execute(
                """SELECT * FROM analysis_history
                   WHERE symbol=?
                   ORDER BY date DESC
                   LIMIT 2""",
                (symbol,),
            ).fetchall()
        result = [dict(r) for r in rows]
        result.reverse()
        return result
    except Exception as exc:
        log.warning("Failed to fetch latest snapshots for %s: %s", symbol, exc)
        return []


def get_tracked_symbols() -> list[str]:
    """Return all symbols that have at least one history entry."""
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT symbol FROM analysis_history ORDER BY symbol"
            ).fetchall()
        return [r["symbol"] for r in rows]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# P13.3: Named Analysis Snapshots
# ---------------------------------------------------------------------------

_SNAPSHOTS_DIR = _DATA_DIR / "snapshots"


def save_named_snapshot(
    symbol: str,
    name: str,
    metrics: dict,
    factor_scores: dict,
    risk: dict,
    claude_output: str = "",
    factors_list: list | None = None,
) -> str:
    """Save a named analysis snapshot to disk.

    Parameters
    ----------
    symbol : stock ticker
    name : user-provided snapshot name
    metrics : dict of financial/price metrics
    factor_scores : dict of individual factor scores
    risk : risk analysis result dict
    claude_output : Claude AI analysis text
    factors_list : list of factor dicts (name, score, label, etc.)

    Returns
    -------
    snapshot filename (without path)
    """
    _SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    ts = int(time.time())
    safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in name)[:50]
    filename = f"{symbol}_{ts}_{safe_name}.json"
    path = _SNAPSHOTS_DIR / filename

    snapshot = {
        "symbol": symbol.upper(),
        "name": name,
        "timestamp": ts,
        "date": datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M"),
        "metrics": metrics,
        "factor_scores": factor_scores,
        "risk": risk,
        "claude_output": claude_output,
        "factors_list": factors_list or [],
        "composite_score": risk.get("composite_score") or sum(
            v for v in factor_scores.values() if isinstance(v, (int, float))
        ) / max(len(factor_scores), 1),
    }

    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, indent=2, default=str)
        log.info("Snapshot saved: %s", path)
        return filename
    except OSError as exc:
        log.error("Failed to save snapshot %s: %s", filename, exc)
        return ""


def list_snapshots(symbol: str | None = None) -> list[dict]:
    """Return list of saved snapshots, newest first.

    Parameters
    ----------
    symbol : optional filter by ticker symbol
    """
    _SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(_SNAPSHOTS_DIR.glob("*.json"), reverse=True)
    snapshots = []

    for path in files:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if symbol and data.get("symbol", "").upper() != symbol.upper():
                continue
            snapshots.append({
                "filename": path.name,
                "path": str(path),
                "symbol": data.get("symbol", ""),
                "name": data.get("name", ""),
                "date": data.get("date", ""),
                "timestamp": data.get("timestamp", 0),
                "composite_score": data.get("composite_score", 0),
                "risk_level": data.get("risk", {}).get("risk_level", ""),
            })
        except Exception as exc:
            log.debug("Could not read snapshot %s: %s", path.name, exc)

    return snapshots


def load_snapshot(filename: str) -> dict | None:
    """Load a snapshot by filename.

    Returns the full snapshot dict, or None if not found.
    """
    path = _SNAPSHOTS_DIR / filename
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        log.warning("Failed to load snapshot %s: %s", filename, exc)
        return None


def delete_snapshot(filename: str) -> bool:
    """Delete a snapshot file. Returns True on success."""
    path = _SNAPSHOTS_DIR / filename
    try:
        path.unlink(missing_ok=True)
        log.info("Deleted snapshot: %s", filename)
        return True
    except OSError as exc:
        log.warning("Failed to delete snapshot %s: %s", filename, exc)
        return False


def diff_snapshots(snap_a: dict, snap_b: dict) -> dict:
    """Compare two snapshots and return a diff summary.

    Parameters
    ----------
    snap_a : older snapshot dict
    snap_b : newer snapshot dict

    Returns
    -------
    dict with changed_factors, changed_metrics, risk_change, summary
    """
    changes = {
        "symbol": snap_b.get("symbol", ""),
        "name_a": snap_a.get("name", ""),
        "name_b": snap_b.get("name", ""),
        "date_a": snap_a.get("date", ""),
        "date_b": snap_b.get("date", ""),
        "changed_factors": [],
        "changed_metrics": [],
        "risk_change": None,
        "score_change": None,
    }

    # Factor score changes
    scores_a = snap_a.get("factor_scores", {})
    scores_b = snap_b.get("factor_scores", {})
    for factor in set(list(scores_a.keys()) + list(scores_b.keys())):
        a_val = scores_a.get(factor)
        b_val = scores_b.get(factor)
        if a_val is not None and b_val is not None:
            diff = b_val - a_val
            if abs(diff) >= 5:
                changes["changed_factors"].append({
                    "factor": factor,
                    "before": a_val,
                    "after": b_val,
                    "change": round(diff, 1),
                    "direction": "up" if diff > 0 else "down",
                })

    # Composite score change
    score_a = snap_a.get("composite_score", 0)
    score_b = snap_b.get("composite_score", 0)
    if score_a and score_b:
        changes["score_change"] = round(score_b - score_a, 1)

    # Risk change
    risk_a = snap_a.get("risk", {}).get("risk_level", "")
    risk_b = snap_b.get("risk", {}).get("risk_level", "")
    if risk_a != risk_b:
        changes["risk_change"] = {"before": risk_a, "after": risk_b}

    # Metric changes
    metrics_a = snap_a.get("metrics", {})
    metrics_b = snap_b.get("metrics", {})
    key_metrics = ["price", "pe", "eps", "revenue_growth", "gross_margin"]
    for key in key_metrics:
        a_val = metrics_a.get(key)
        b_val = metrics_b.get(key)
        if a_val is not None and b_val is not None:
            try:
                pct_change = (float(b_val) - float(a_val)) / abs(float(a_val)) * 100
                if abs(pct_change) >= 5:
                    changes["changed_metrics"].append({
                        "metric": key,
                        "before": a_val,
                        "after": b_val,
                        "pct_change": round(pct_change, 1),
                    })
            except (TypeError, ZeroDivisionError):
                pass

    return changes
