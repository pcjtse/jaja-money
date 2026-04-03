"""Retroactive ledger seeding — populate ledger from analysis_history.

Seeds data/ledger.json with past signals from analysis_history rows where
factor_score >= buy_threshold. Each seeded entry has source="retroactive"
added as a field so it's distinguishable from live signals.

Factor scores are parsed from the factors_json column stored in analysis_history
and passed to add_signal() so signal decay analysis can group retroactive signals
by leading factor.

Market regime is annotated using historical SPY 20-day return at the signal date
(not the current SPY return) using the same ±1% thresholds as ledger_check.py.

T+5/T+10/T+30 prices are fetched from Finnhub at seed time using get_price_on_date().

Usage:
    python -m src.analysis.retroactive
"""

from __future__ import annotations

import json as _json
from datetime import date, timedelta

from src.core.config import cfg
from src.core.log_setup import get_logger

log = get_logger(__name__)


def _parse_factors_json(factors_json_str: str | None) -> dict[str, float]:
    """Parse factors_json column into {display_name: score} dict.

    factors_json is stored as a JSON list of {"name": ..., "score": ...} objects.
    Returns {} on any parse error — never raises.
    """
    if not factors_json_str:
        return {}
    try:
        items = _json.loads(factors_json_str)
        result = {}
        for item in items:
            name = item.get("name")
            score = item.get("score")
            if name and score is not None:
                try:
                    result[name] = float(score)
                except (TypeError, ValueError):
                    log.warning("Skipping unparseable factor score: %s=%s", name, score)
        return result
    except Exception as exc:
        log.warning("Failed to parse factors_json: %s", exc)
        return {}


def _historical_regime(signal_date: str) -> str:
    """Return 'bull', 'bear', or 'flat' based on SPY 20-day return at signal_date.

    Uses get_daily("SPY") OHLCV series and finds the closes at signal_date and
    ~20 trading days prior. Thresholds: bull > +1%, bear < -1%, else flat.
    Returns 'flat' on any API failure.
    """
    try:
        from src.data.api import get_api
        import datetime as _dt

        api = get_api()
        daily = api.get_daily("SPY", years=2)
        if not daily or daily.get("s") != "ok":
            return "flat"
        timestamps = daily.get("t", [])
        closes = daily.get("c", [])
        if not timestamps or not closes:
            return "flat"

        target = _dt.date.fromisoformat(signal_date)
        twenty_days_before = target - timedelta(days=28)  # ~20 trading days

        # Build (date, close) pairs sorted ascending
        pairs = sorted(
            (
                (_dt.datetime.fromtimestamp(ts, tz=_dt.timezone.utc).date(), float(c))
                for ts, c in zip(timestamps, closes)
            ),
            key=lambda x: x[0],
        )

        # Find closes on or before target and on or before 28 calendar days prior
        price_now = next(
            (c for d, c in reversed(pairs) if d <= target), None
        )
        price_then = next(
            (c for d, c in reversed(pairs) if d <= twenty_days_before), None
        )

        if price_now is None or price_then is None or price_then <= 0:
            return "flat"
        ret = (price_now - price_then) / price_then
        if ret > 0.01:
            return "bull"
        elif ret < -0.01:
            return "bear"
        return "flat"
    except Exception as exc:
        log.warning("Regime lookup failed for %s: %s", signal_date, exc)
        return "flat"


def seed_from_history(buy_threshold: int | None = None, dry_run: bool = False) -> dict:
    """Seed the ledger from analysis_history rows that already scored >= buy_threshold.

    Parameters
    ----------
    buy_threshold : minimum composite score to seed; reads from config if None
    dry_run       : if True, compute counts without writing anything

    Returns
    -------
    dict with keys: seeded, skipped, dry_run
    """
    from src.data.history import get_all_analysis_signals
    from src.data.providers import get_price_on_date
    from src.analysis.ledger import (
        add_signal,
        close_position,
        get_all_signals,
    )

    if buy_threshold is None:
        buy_threshold = int(cfg.get("ledger", "buy_threshold", default=75))

    rows = get_all_analysis_signals()
    seeded = 0
    skipped = 0

    for row in rows:
        symbol = row["symbol"]
        signal_date = row["date"]
        price = row.get("price") or 0.0
        factor_score = row.get("factor_score") or 0

        if factor_score < buy_threshold:
            continue

        if dry_run:
            seeded += 1
            continue

        # Parse per-factor scores from factors_json for signal decay grouping
        factor_scores = _parse_factors_json(row.get("factors_json"))

        # Annotate regime using historical SPY return at signal date
        regime = _historical_regime(signal_date)

        # Fetch SPY price on that date
        spy_price = get_price_on_date("SPY", signal_date) or 0.0

        # Snapshot existing signal IDs to detect idempotency after add_signal()
        existing_ids = {s["signal_id"] for s in get_all_signals()}

        try:
            signal_id = add_signal(
                ticker=symbol,
                composite_score=factor_score,
                factor_scores=factor_scores,
                price=float(price),
                spy_price=float(spy_price),
                source="retroactive",
                regime=regime,
            )
        except ValueError as exc:
            log.info("Skipping %s %s: %s", symbol, signal_date, exc)
            skipped += 1
            continue

        if signal_id in existing_ids:
            # add_signal() idempotency guard fired — entry already existed
            skipped += 1
            log.debug("Skipping %s %s — already in ledger", symbol, signal_date)
            continue

        # Compute T+5/T+10/T+30 prices
        try:
            fired_dt = date.fromisoformat(signal_date)
        except ValueError:
            fired_dt = date.today()

        def _price_offset(n_days: int) -> float | None:
            target = (fired_dt + timedelta(days=n_days)).isoformat()
            return get_price_on_date(symbol, target)

        price_t5 = _price_offset(5)
        price_t10 = _price_offset(10)
        price_t30 = _price_offset(30)

        # Close the position if T+30 is in the past
        cutoff = date.fromisoformat(signal_date) + timedelta(days=30)
        if cutoff < date.today():
            spy_t30 = get_price_on_date("SPY", cutoff.isoformat())
            exit_price = price_t30 or float(price)
            try:
                close_position(
                    signal_id=signal_id,
                    exit_price=exit_price,
                    spy_exit_price=float(spy_t30 or spy_price),
                    price_t5=price_t5,
                    price_t10=price_t10,
                    price_t30=price_t30,
                    spy_price_t30=spy_t30,
                )
                log.debug("Retroactive close: %s %s", symbol, signal_date)
            except Exception as exc:
                log.warning("Failed to retroactively close %s: %s", symbol, exc)

        seeded += 1
        log.info(
            "Seeded retroactive signal: %s %s score=%d",
            symbol,
            signal_date,
            factor_score,
        )

    log.info(
        "Retroactive seed complete: seeded=%d skipped=%d dry_run=%s",
        seeded,
        skipped,
        dry_run,
    )
    return {"seeded": seeded, "skipped": skipped, "dry_run": dry_run}


if __name__ == "__main__":
    import sys

    dry = "--dry-run" in sys.argv
    result = seed_from_history(dry_run=dry)
    print(
        f"Retroactive seed {'(dry run) ' if result['dry_run'] else ''}complete:\n"
        f"  Seeded:  {result['seeded']}\n"
        f"  Skipped: {result['skipped']}\n"
    )
