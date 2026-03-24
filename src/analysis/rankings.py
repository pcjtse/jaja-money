"""Cross-Sectional Daily Long/Short Ranking Engine (21.4).

Scores the entire S&P 500 (or Russell 1000) universe, ranks stocks
cross-sectionally and sector-neutrally by composite factor score, and
persists the daily snapshot to SQLite.

Usage:
    from src.analysis.rankings import run_daily_ranking, get_todays_ranking
    result = run_daily_ranking(api)
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from src.core.log_setup import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _score_universe(
    tickers: list[str],
    api,
    max_workers: int = 4,
) -> tuple[list[dict], list[str]]:
    """Score all tickers using the lightweight screener analysis.

    Returns (results, errors).  Each result dict contains at minimum:
    symbol, sector, factor_score, risk_score, market_cap_b, composite_label.
    The `adv` field (avg daily value) is derived from price * volume if
    unavailable; defaults to 0 when data is missing.
    """
    from src.trading.screener import _quick_analyze

    results: list[dict] = []
    errors: list[str] = []

    def _worker(sym: str) -> dict | None:
        return _quick_analyze(sym, api=api)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_worker, t): t for t in tickers}
        for fut in as_completed(futures):
            sym = futures[fut]
            try:
                r = fut.result()
                if r is not None:
                    results.append(r)
            except Exception as exc:
                errors.append(f"{sym}: {exc}")
                log.debug("Ranking: skipped %s — %s", sym, exc)

    log.info(
        "Ranking: scored %d/%d tickers (%d errors)",
        len(results),
        len(tickers),
        len(errors),
    )
    return results, errors


def _apply_liquidity_filter(
    results: list[dict],
    min_adv_m: float,
) -> list[dict]:
    """Remove stocks where avg daily value < min_adv_m million dollars."""
    if min_adv_m <= 0:
        return results

    min_adv = min_adv_m * 1_000_000
    passed = [r for r in results if (r.get("adv") or 0) >= min_adv]
    removed = len(results) - len(passed)
    if removed:
        log.info(
            "Liquidity filter: removed %d stocks (min_adv=%.1fM)", removed, min_adv_m
        )
    return passed


def _assign_overall_ranks(results: list[dict]) -> list[dict]:
    """Sort by factor_score descending and assign rank_overall + percentile."""
    sorted_results = sorted(
        results,
        key=lambda r: r.get("factor_score") or 0,
        reverse=True,
    )
    n = len(sorted_results)
    for i, r in enumerate(sorted_results):
        r["rank_overall"] = i + 1
        # With only one stock it is at the 100th percentile by convention
        r["percentile"] = 100.0 if n == 1 else round((n - i - 1) / (n - 1) * 100, 1)
    return sorted_results


def _assign_sector_ranks(results: list[dict]) -> list[dict]:
    """Assign rank_in_sector within each sector group (by factor_score desc)."""
    # Group by sector
    sector_map: dict[str, list[dict]] = {}
    for r in results:
        sector = r.get("sector") or "N/A"
        sector_map.setdefault(sector, []).append(r)

    for sector_results in sector_map.values():
        sector_sorted = sorted(
            sector_results,
            key=lambda r: r.get("factor_score") or 0,
            reverse=True,
        )
        for i, r in enumerate(sector_sorted):
            r["rank_in_sector"] = i + 1

    return results


def _build_response(ranked: list[dict], top_n: int = 10) -> dict:
    """Slice top/bottom N and build the sector breakdown."""
    n = len(ranked)
    longs = ranked[:top_n]
    shorts = ranked[max(0, n - top_n) :][::-1] if n > 0 else []

    # Sector breakdown: top 5 longs + top 5 shorts per sector
    sector_map: dict[str, list[dict]] = {}
    for r in ranked:
        sector = r.get("sector") or "N/A"
        sector_map.setdefault(sector, []).append(r)

    by_sector: dict[str, dict] = {}
    for sector, rows in sector_map.items():
        # Already sorted overall; sector-neutral sort uses rank_in_sector
        sector_sorted = sorted(rows, key=lambda r: r.get("rank_in_sector") or 9999)
        by_sector[sector] = {
            "longs": sector_sorted[:5],
            "shorts": sector_sorted[-5:][::-1] if len(sector_sorted) >= 5 else [],
        }

    return {
        "top_longs": longs,
        "top_shorts": shorts,
        "by_sector": by_sector,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_daily_ranking(
    api,
    universe: str = "sp500",
    min_adv_m: float = 0.0,
    max_workers: int = 4,
    force: bool = False,
) -> dict:
    """Score and rank the full universe, persist results, return summary.

    Parameters
    ----------
    api         : FinnhubAPI instance
    universe    : 'sp500' | 'russell1000'
    min_adv_m   : minimum average daily value in millions (0 = no filter)
    max_workers : thread pool size for concurrent scoring
    force       : if True, rescore even if today's ranking already exists

    Returns
    -------
    dict with keys: run_date, universe_size, scored_count, top_longs,
    top_shorts, by_sector, errors.
    """
    from src.trading.screener import load_universe
    from src.data.history import save_ranking_snapshot, get_latest_ranking

    run_date = datetime.utcnow().strftime("%Y-%m-%d")

    # Short-circuit if today's ranking already exists and force=False
    if not force:
        existing = get_latest_ranking()
        if existing and existing.get("date") == run_date:
            log.info("Ranking for %s already exists; returning cached", run_date)
            response = _build_response(existing["all_rows"])
            response.update(
                {
                    "run_date": run_date,
                    "universe_size": len(existing["all_rows"]),
                    "scored_count": len(existing["all_rows"]),
                    "errors": [],
                    "cached": True,
                }
            )
            return response

    tickers = load_universe(universe)
    log.info("Running daily ranking: universe=%s (%d tickers)", universe, len(tickers))

    raw_results, errors = _score_universe(tickers, api, max_workers=max_workers)
    filtered = _apply_liquidity_filter(raw_results, min_adv_m)
    ranked = _assign_overall_ranks(filtered)
    ranked = _assign_sector_ranks(ranked)

    # Persist to SQLite
    save_ranking_snapshot(run_date, ranked)

    response = _build_response(ranked)
    response.update(
        {
            "run_date": run_date,
            "universe_size": len(tickers),
            "scored_count": len(ranked),
            "errors": errors,
            "cached": False,
        }
    )
    log.info(
        "Daily ranking complete: %d scored, top long=%s, top short=%s",
        len(ranked),
        response["top_longs"][0]["symbol"] if response["top_longs"] else "N/A",
        response["top_shorts"][0]["symbol"] if response["top_shorts"] else "N/A",
    )
    return response


def get_todays_ranking(api) -> dict | None:
    """Return today's ranking, running it if not yet computed.

    Returns None only if scoring completely fails.
    """
    try:
        return run_daily_ranking(api, force=False)
    except Exception as exc:
        log.error("get_todays_ranking failed: %s", exc)
        return None
