#!/usr/bin/env python3
"""AutoResearch evaluation harness — DO NOT MODIFY.

Imports ``compute_signal`` from ``autoresearch/strategy_runner.py``,
runs a backtest on a fixed 3-year dataset (AAPL, MSFT, GOOGL), and
prints a parseable result block.

The autoresearch agent reads ``SHARPE: X.XX`` from stdout to decide
whether to keep or revert the current ``strategy_runner.py``.

Usage::

    python autoresearch/evaluate.py

Exit code 0 = success.  Non-zero = evaluation failed (treat as regression).
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Ensure project root is on path regardless of cwd
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

# ---------------------------------------------------------------------------
# Import the editable strategy — must come after sys.path adjustment
# ---------------------------------------------------------------------------
from autoresearch.strategy_runner import compute_signal  # noqa: E402
from src.analysis.backtest import run_backtest  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration (fixed — do not modify)
# ---------------------------------------------------------------------------
TICKERS = ["AAPL", "MSFT", "GOOGL"]
LOOKBACK_YEARS = 3.0
COMMISSION_PCT = 0.001   # 0.1%
SLIPPAGE_PCT = 0.0005    # 0.05% per side
ENTRY_THRESHOLD = 65
EXIT_THRESHOLD = 40
DATA_CACHE_DIR = _REPO_ROOT / "autoresearch" / "data"
DATA_CACHE_TTL_DAYS = 7


# ---------------------------------------------------------------------------
# Price data loading (cached)
# ---------------------------------------------------------------------------

def _cache_path(ticker: str) -> Path:
    return DATA_CACHE_DIR / f"{ticker}_daily.json"


def _load_cached(ticker: str) -> list[dict] | None:
    p = _cache_path(ticker)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
        cached_at = datetime.fromisoformat(data.get("cached_at", "2000-01-01"))
        if datetime.utcnow() - cached_at > timedelta(days=DATA_CACHE_TTL_DAYS):
            return None
        return data.get("rows")
    except Exception:
        return None


def _save_cached(ticker: str, rows: list[dict]) -> None:
    DATA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    p = _cache_path(ticker)
    p.write_text(json.dumps({"cached_at": datetime.utcnow().isoformat(), "rows": rows}))


def _fetch_price_data(ticker: str) -> list[dict] | None:
    """Return list of {Date, Close} dicts for *ticker*, from cache or API."""
    cached = _load_cached(ticker)
    if cached:
        return cached

    try:
        from src.data.api import get_api
        api = get_api()
        raw = api.get_daily(ticker, years=4)
        if not raw or raw.get("s") != "ok":
            return None
        timestamps = raw.get("t", [])
        closes = raw.get("c", [])
        if not timestamps or not closes:
            return None
        rows = [
            {"Date": str(datetime.utcfromtimestamp(ts).date()), "Close": float(c)}
            for ts, c in zip(timestamps, closes)
            if c and c > 0
        ]
        if rows:
            _save_cached(ticker, rows)
        return rows
    except Exception as exc:
        print(f"  WARNING: could not fetch {ticker}: {exc}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Main evaluation loop
# ---------------------------------------------------------------------------

def main() -> int:
    t_start = time.monotonic()
    sharpes: list[float] = []
    returns: list[float] = []
    drawdowns: list[float] = []
    win_rates: list[float] = []
    trade_counts: list[int] = []

    print(f"=== AUTORESEARCH EVALUATION — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} ===")
    print(f"Tickers: {', '.join(TICKERS)}  |  Lookback: {LOOKBACK_YEARS}y  |  "
          f"Commission: {COMMISSION_PCT*100:.2f}%  |  Slippage: {SLIPPAGE_PCT*100:.3f}%")

    import pandas as pd

    for ticker in TICKERS:
        rows = _fetch_price_data(ticker)
        if not rows:
            print(f"  SKIP {ticker}: no price data available")
            continue

        df = pd.DataFrame(rows)
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.sort_values("Date").reset_index(drop=True)

        if len(df) < 100:
            print(f"  SKIP {ticker}: insufficient history ({len(df)} rows)")
            continue

        try:
            result = run_backtest(
                df=df,
                symbol=ticker,
                entry_threshold=ENTRY_THRESHOLD,
                exit_threshold=EXIT_THRESHOLD,
                lookback_years=LOOKBACK_YEARS,
                commission_pct=COMMISSION_PCT,
                slippage_pct=SLIPPAGE_PCT,
                signal_fn=compute_signal,
            )
            sharpe = result.sharpe_ratio or 0.0
            sharpes.append(sharpe)
            returns.append(result.total_return_pct)
            drawdowns.append(result.max_drawdown_pct)
            win_rates.append(result.win_rate_pct)
            trade_counts.append(result.total_trades)
            print(
                f"  {ticker}: sharpe={sharpe:+.2f}  return={result.total_return_pct:+.1f}%  "
                f"dd={result.max_drawdown_pct:.1f}%  trades={result.total_trades}"
            )
        except Exception as exc:
            print(f"  ERROR {ticker}: {exc}", file=sys.stderr)

    if not sharpes:
        print("ERROR: no tickers evaluated — cannot compute metric")
        return 1

    avg_sharpe = sum(sharpes) / len(sharpes)
    avg_return = sum(returns) / len(returns)
    avg_dd = sum(drawdowns) / len(drawdowns)
    avg_wr = sum(win_rates) / len(win_rates)
    total_trades = sum(trade_counts)
    elapsed = time.monotonic() - t_start

    print("---")
    print(f"SHARPE: {avg_sharpe:.2f}")       # primary metric — agent reads this line
    print(f"RETURN: {avg_return:.1f}%")
    print(f"DRAWDOWN: {avg_dd:.1f}%")
    print(f"WIN_RATE: {avg_wr:.1f}%")
    print(f"TRADES: {total_trades}")
    print(f"ELAPSED: {elapsed:.1f}s")
    print("=== END ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
