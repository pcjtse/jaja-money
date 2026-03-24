"""Historical factor score tracking using SQLite.

Stores analysis snapshots (factor score, risk score, price, flags) keyed
by (symbol, date) in ~/.jaja-money/history.db.

Usage:
    from src.data.history import save_analysis, get_history, get_score_trend
"""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from src.core.log_setup import get_logger

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


# ---------------------------------------------------------------------------
# P22.1: Paper portfolio tables
# ---------------------------------------------------------------------------


def _ensure_paper_tables() -> None:
    """Create paper portfolio tables if they don't exist."""
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS paper_portfolio (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                name         TEXT NOT NULL,
                created_date TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS paper_trades (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                portfolio_id       INTEGER NOT NULL,
                symbol             TEXT NOT NULL,
                entry_price        REAL NOT NULL,
                entry_date         TEXT NOT NULL,
                exit_price         REAL,
                exit_date          TEXT,
                factor_score_entry INTEGER,
                risk_score_entry   INTEGER,
                shares             REAL NOT NULL DEFAULT 1.0,
                FOREIGN KEY (portfolio_id) REFERENCES paper_portfolio(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS paper_portfolio_history (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                portfolio_id INTEGER NOT NULL,
                date         TEXT NOT NULL,
                total_value  REAL NOT NULL,
                UNIQUE(portfolio_id, date),
                FOREIGN KEY (portfolio_id) REFERENCES paper_portfolio(id)
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_paper_trades_portfolio "
            "ON paper_trades (portfolio_id)"
        )


_ensure_paper_tables()


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
        "composite_score": risk.get("composite_score")
        or sum(v for v in factor_scores.values() if isinstance(v, (int, float)))
        / max(len(factor_scores), 1),
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
            snapshots.append(
                {
                    "filename": path.name,
                    "path": str(path),
                    "symbol": data.get("symbol", ""),
                    "name": data.get("name", ""),
                    "date": data.get("date", ""),
                    "timestamp": data.get("timestamp", 0),
                    "composite_score": data.get("composite_score", 0),
                    "risk_level": data.get("risk", {}).get("risk_level", ""),
                }
            )
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


# ---------------------------------------------------------------------------
# P20.3: Signal change support
# ---------------------------------------------------------------------------


def get_last_n_snapshots(symbol: str, n: int = 2) -> list[dict]:
    """Return the last n analysis snapshots for a symbol, newest first.

    Parameters
    ----------
    symbol : stock ticker symbol
    n : number of snapshots to retrieve (default 2)

    Returns
    -------
    list of dicts with keys: date, price, factor_score, risk_score,
    risk_level, composite_label — ordered newest first (index 0 is most recent).
    Returns an empty list on error or if no records exist.
    """
    symbol = symbol.upper()
    try:
        with _connect() as conn:
            rows = conn.execute(
                """SELECT date, price, factor_score, risk_score, risk_level,
                          composite_label
                   FROM analysis_history
                   WHERE symbol=?
                   ORDER BY date DESC
                   LIMIT ?""",
                (symbol, n),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as exc:
        log.warning("Failed to fetch last %d snapshots for %s: %s", n, symbol, exc)
        return []


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
                changes["changed_factors"].append(
                    {
                        "factor": factor,
                        "before": a_val,
                        "after": b_val,
                        "change": round(diff, 1),
                        "direction": "up" if diff > 0 else "down",
                    }
                )

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
                    changes["changed_metrics"].append(
                        {
                            "metric": key,
                            "before": a_val,
                            "after": b_val,
                            "pct_change": round(pct_change, 1),
                        }
                    )
            except (TypeError, ZeroDivisionError):
                pass

    return changes


# ---------------------------------------------------------------------------
# 21.1: ML-trained adaptive factor weights table
# ---------------------------------------------------------------------------


def _ensure_ml_weights_table() -> None:
    """Create ml_weights table if it doesn't exist."""
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ml_weights (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                trained_date         TEXT NOT NULL,
                weights_json         TEXT NOT NULL,
                auc                  REAL,
                precision_top_decile REAL,
                n_samples            INTEGER
            )
        """)


_ensure_ml_weights_table()


def save_ml_weights(
    weights: dict,
    trained_date: str,
    auc: float | None = None,
    precision_top_decile: float | None = None,
    n_samples: int = 0,
) -> None:
    """Persist a trained ML weights snapshot."""
    try:
        with _connect() as conn:
            conn.execute(
                """INSERT INTO ml_weights
                   (trained_date, weights_json, auc, precision_top_decile, n_samples)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    trained_date,
                    json.dumps(weights),
                    auc,
                    precision_top_decile,
                    n_samples,
                ),
            )
        log.info("Saved ML weights trained on %s (n=%d)", trained_date, n_samples)
    except Exception as exc:
        log.warning("Failed to save ML weights: %s", exc)


def get_latest_ml_weights() -> dict | None:
    """Return the most recent ML weights row, or None if table is empty."""
    try:
        with _connect() as conn:
            row = conn.execute(
                "SELECT * FROM ml_weights ORDER BY id DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        return dict(row)
    except Exception as exc:
        log.warning("Failed to load ML weights: %s", exc)
        return None


def get_all_factor_snapshots() -> list[dict]:
    """Return all analysis_history rows that contain factor score data.

    Each row includes: symbol, date, price, factors_json.
    Used by ml_weights.py to build a training dataset.
    """
    try:
        with _connect() as conn:
            rows = conn.execute(
                """SELECT symbol, date, price, factors_json
                   FROM analysis_history
                   WHERE factors_json IS NOT NULL AND factors_json != '[]'
                   ORDER BY date ASC"""
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as exc:
        log.warning("Failed to load factor snapshots: %s", exc)
        return []


# ---------------------------------------------------------------------------
# 21.4: Cross-Sectional Daily Rankings
# ---------------------------------------------------------------------------


def _ensure_ranking_tables() -> None:
    """Create cross-sectional ranking tables if they don't exist."""
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cross_sectional_rankings (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                run_date        TEXT NOT NULL,
                symbol          TEXT NOT NULL,
                sector          TEXT,
                rank_overall    INTEGER,
                rank_in_sector  INTEGER,
                percentile      REAL,
                factor_score    INTEGER,
                risk_score      INTEGER,
                market_cap_b    REAL,
                adv             REAL,
                composite_label TEXT,
                UNIQUE(run_date, symbol)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ranking_theses (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                run_date     TEXT NOT NULL UNIQUE,
                long_symbol  TEXT,
                long_thesis  TEXT,
                short_symbol TEXT,
                short_thesis TEXT,
                generated_at INTEGER
            )
        """)


_ensure_ranking_tables()


def save_ranking_snapshot(run_date: str, results: list[dict]) -> None:
    """Bulk upsert a cross-sectional ranking snapshot for a given date.

    Each dict in results should contain: symbol, sector, rank_overall,
    rank_in_sector, percentile, factor_score, risk_score, market_cap_b,
    adv, composite_label.
    """
    try:
        with _connect() as conn:
            conn.execute(
                "DELETE FROM cross_sectional_rankings WHERE run_date=?",
                (run_date,),
            )
            conn.executemany(
                """INSERT INTO cross_sectional_rankings
                   (run_date, symbol, sector, rank_overall, rank_in_sector,
                    percentile, factor_score, risk_score, market_cap_b, adv,
                    composite_label)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                [
                    (
                        run_date,
                        r.get("symbol", ""),
                        r.get("sector"),
                        r.get("rank_overall"),
                        r.get("rank_in_sector"),
                        r.get("percentile"),
                        r.get("factor_score"),
                        r.get("risk_score"),
                        r.get("market_cap_b"),
                        r.get("adv"),
                        r.get("composite_label"),
                    )
                    for r in results
                ],
            )
        log.info("Saved %d ranking rows for %s", len(results), run_date)
    except Exception as exc:
        log.warning("Failed to save ranking snapshot for %s: %s", run_date, exc)


def get_latest_ranking(top_n: int = 10, bottom_n: int = 10) -> dict | None:
    """Return the most recent ranking snapshot.

    Returns a dict with keys: date, longs (top_n by factor_score),
    shorts (bottom_n by factor_score), all_rows.  Returns None if no
    ranking exists.
    """
    try:
        with _connect() as conn:
            date_row = conn.execute(
                "SELECT run_date FROM cross_sectional_rankings "
                "ORDER BY run_date DESC LIMIT 1"
            ).fetchone()
            if date_row is None:
                return None
            run_date = date_row["run_date"]
            rows = conn.execute(
                """SELECT * FROM cross_sectional_rankings
                   WHERE run_date=?
                   ORDER BY rank_overall ASC""",
                (run_date,),
            ).fetchall()
        all_rows = [dict(r) for r in rows]
        return {
            "date": run_date,
            "longs": all_rows[:top_n],
            "shorts": all_rows[-bottom_n:] if len(all_rows) >= bottom_n else all_rows,
            "all_rows": all_rows,
        }
    except Exception as exc:
        log.warning("Failed to load latest ranking: %s", exc)
        return None


def get_ranking_for_date(date: str) -> list[dict]:
    """Return the full ranking snapshot for a specific date."""
    try:
        with _connect() as conn:
            rows = conn.execute(
                """SELECT * FROM cross_sectional_rankings
                   WHERE run_date=?
                   ORDER BY rank_overall ASC""",
                (date,),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as exc:
        log.warning("Failed to load ranking for %s: %s", date, exc)
        return []


def save_ranking_thesis(
    run_date: str,
    long_symbol: str,
    long_thesis: str,
    short_symbol: str,
    short_thesis: str,
) -> None:
    """Persist the Claude-generated long/short thesis for a ranking date."""
    try:
        with _connect() as conn:
            conn.execute(
                """INSERT INTO ranking_theses
                   (run_date, long_symbol, long_thesis, short_symbol, short_thesis,
                    generated_at)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT(run_date) DO UPDATE SET
                     long_symbol=excluded.long_symbol,
                     long_thesis=excluded.long_thesis,
                     short_symbol=excluded.short_symbol,
                     short_thesis=excluded.short_thesis,
                     generated_at=excluded.generated_at""",
                (
                    run_date,
                    long_symbol,
                    long_thesis,
                    short_symbol,
                    short_thesis,
                    int(time.time()),
                ),
            )
        log.info(
            "Saved ranking thesis for %s (%s long, %s short)",
            run_date,
            long_symbol,
            short_symbol,
        )
    except Exception as exc:
        log.warning("Failed to save ranking thesis for %s: %s", run_date, exc)


def get_latest_thesis() -> dict | None:
    """Return the most recent ranking thesis, or None if none exists."""
    try:
        with _connect() as conn:
            row = conn.execute(
                "SELECT * FROM ranking_theses ORDER BY run_date DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None
    except Exception as exc:
        log.warning("Failed to load latest thesis: %s", exc)
        return None


# ---------------------------------------------------------------------------
# 21.3: Signal Validity — forward return caching
# ---------------------------------------------------------------------------


def _ensure_signal_returns_table() -> None:
    """Create signal_returns table if it doesn't exist."""
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS signal_returns (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol          TEXT NOT NULL,
                signal_date     TEXT NOT NULL,
                signal_score    INTEGER,
                price_at_signal REAL,
                return_21d      REAL,
                return_63d      REAL,
                return_126d     REAL,
                fetched_at      INTEGER,
                UNIQUE(symbol, signal_date)
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_signal_returns_symbol "
            "ON signal_returns (symbol, signal_date)"
        )


_ensure_signal_returns_table()


def upsert_signal_return(
    symbol: str,
    signal_date: str,
    signal_score: int | None,
    price_at_signal: float | None,
    return_21d: float | None = None,
    return_63d: float | None = None,
    return_126d: float | None = None,
) -> None:
    """Insert or update a forward-return record for a signal."""
    try:
        with _connect() as conn:
            conn.execute(
                """INSERT INTO signal_returns
                   (symbol, signal_date, signal_score, price_at_signal,
                    return_21d, return_63d, return_126d, fetched_at)
                   VALUES (?,?,?,?,?,?,?,?)
                   ON CONFLICT(symbol, signal_date) DO UPDATE SET
                     signal_score=excluded.signal_score,
                     price_at_signal=excluded.price_at_signal,
                     return_21d=excluded.return_21d,
                     return_63d=excluded.return_63d,
                     return_126d=excluded.return_126d,
                     fetched_at=excluded.fetched_at""",
                (
                    symbol.upper(),
                    signal_date,
                    signal_score,
                    price_at_signal,
                    return_21d,
                    return_63d,
                    return_126d,
                    int(time.time()),
                ),
            )
    except Exception as exc:
        log.warning("Failed to upsert signal return for %s %s: %s", symbol, signal_date, exc)


def get_signal_returns(symbol: str | None = None) -> list[dict]:
    """Return all cached signal return rows, optionally filtered by symbol."""
    try:
        with _connect() as conn:
            if symbol:
                rows = conn.execute(
                    """SELECT * FROM signal_returns
                       WHERE symbol=?
                       ORDER BY signal_date ASC""",
                    (symbol.upper(),),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM signal_returns ORDER BY signal_date ASC"
                ).fetchall()
        return [dict(r) for r in rows]
    except Exception as exc:
        log.warning("Failed to fetch signal returns: %s", exc)
        return []


def get_all_analysis_signals() -> list[dict]:
    """Return all rows from analysis_history with symbol, date, price, factor_score."""
    try:
        with _connect() as conn:
            rows = conn.execute(
                """SELECT symbol, date, price, factor_score
                   FROM analysis_history
                   WHERE factor_score IS NOT NULL
                   ORDER BY date ASC"""
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as exc:
        log.warning("Failed to load analysis signals: %s", exc)
        return []
