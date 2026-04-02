"""Retroactive ledger seeding — populate ledger from analysis_history.

Seeds data/ledger.json with past signals from analysis_history rows where
factor_score >= buy_threshold. Each seeded entry has source="retroactive"
added as a field so it's distinguishable from live signals.

T+5/T+10/T+30 prices are fetched from Finnhub at seed time using get_price_on_date().

Usage:
    python -m src.analysis.retroactive
"""

from __future__ import annotations

from datetime import date, timedelta

from src.core.config import cfg
from src.core.log_setup import get_logger

log = get_logger(__name__)


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
        _load,
        _save,
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

        # Duplicate guard: check if ticker already has any entry for this date
        existing = get_all_signals()
        already_exists = any(
            s["ticker"] == symbol and s["fired_at"][:10] == signal_date
            for s in existing
        )
        if already_exists:
            skipped += 1
            log.debug("Skipping %s %s — already in ledger", symbol, signal_date)
            continue

        if dry_run:
            seeded += 1
            continue

        # Fetch SPY price on that date
        spy_price = get_price_on_date("SPY", signal_date) or 0.0

        try:
            signal_id = add_signal(
                ticker=symbol,
                composite_score=factor_score,
                factor_scores={},
                price=float(price),
                spy_price=float(spy_price),
            )
        except ValueError as exc:
            log.info("Skipping %s %s: %s", symbol, signal_date, exc)
            skipped += 1
            continue

        # Tag the entry as retroactive
        signals = _load()
        for entry in signals:
            if entry["signal_id"] == signal_id:
                entry["source"] = "retroactive"
                break
        _save(signals)

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
            spy_t30 = get_price_on_date("SPY", cutoff.isoformat()) or float(spy_price)
            exit_price = price_t30 or float(price)
            try:
                close_position(
                    signal_id=signal_id,
                    exit_price=exit_price,
                    spy_exit_price=spy_t30,
                    price_t5=price_t5,
                    price_t10=price_t10,
                    price_t30=price_t30,
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
