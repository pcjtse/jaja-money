"""Scheduled Overnight Batch Analysis (P23.1).

Scores every watchlist ticker once per trading day, populates
``analysis_history`` and seeds ``signal_returns`` so that Signal Quality,
Factor Attribution, and ML weight retraining have data to work with.

Pipeline (runs each scheduled tick):
1. For each watchlist ticker: fetch market data → compute factors → save to
   analysis_history → upsert into signal_returns with current price.
2. Call ``backfill_all_forward_returns()`` to fill T+21/T+63/T+126 returns
   for signals that are old enough.
3. Trigger ML weight retrain if new quarter's worth of data has accumulated.

Usage::

    # Start background scheduler (call once at app boot when enabled)
    from src.services.scheduler import start_batch_scheduler, is_scheduler_running
    start_batch_scheduler()

    # Run immediately for testing or manual trigger
    from src.services.scheduler import run_batch_analysis
    result = run_batch_analysis()

Configuration (config.yaml)::

    batch_analysis:
      enabled: false        # default off — set true to enable nightly scoring
      schedule_hour: 7      # UTC hour (7 = 3am ET, pre-market)
      schedule_minute: 0
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from src.core.config import cfg
from src.core.log_setup import get_logger

if TYPE_CHECKING:
    pass

log = get_logger(__name__)

# APScheduler is an optional dependency (same pattern as digest.py)
try:
    from apscheduler.schedulers.background import BackgroundScheduler

    _HAS_APSCHEDULER = True
except ImportError:
    _HAS_APSCHEDULER = False

_batch_scheduler = None


# ---------------------------------------------------------------------------
# Single-ticker scoring
# ---------------------------------------------------------------------------


def _analyze_ticker(api, symbol: str) -> dict | None:
    """Fetch market data, compute factors, save to history.

    Returns a dict with ``factor_score``, ``risk_score``, ``price`` on success,
    or None on failure.  All exceptions are swallowed so one bad ticker never
    aborts the whole batch run.
    """
    import pandas as pd

    from src.analysis.factors import composite_label_color, composite_score, compute_factors
    from src.analysis.guardrails import compute_risk
    from src.data.history import save_analysis, upsert_signal_return
    from src.data.sentiment import aggregate_sentiment, score_articles

    try:
        quote = api.get_quote(symbol)
        price: float | None = quote.get("c") or quote.get("current_price")
        if not price or price <= 0:
            log.debug("Batch: skipping %s — no valid price", symbol)
            return None
    except Exception as exc:
        log.warning("Batch: get_quote failed for %s: %s", symbol, exc)
        return None

    # Fetch supporting data — silently degrade if any call fails
    try:
        financials = api.get_financials(symbol)
    except Exception:
        financials = {}

    close: pd.Series | None = None
    try:
        daily = api.get_daily(symbol)
        if daily and daily.get("c"):
            close = pd.Series(daily["c"])
    except Exception:
        pass

    try:
        earnings = api.get_earnings(symbol, limit=4)
    except Exception:
        earnings = []

    try:
        recs = api.get_recommendations(symbol)
    except Exception:
        recs = []

    sentiment_agg: dict | None = None
    try:
        news = api.get_news(symbol, days=7)
        if news:
            scored = score_articles(news)
            sentiment_agg = aggregate_sentiment(scored)
    except Exception:
        pass

    # Alt data (optional)
    alt_data = None
    try:
        if cfg.alt_data_enabled:
            alt_data = api.get_alt_data_signals(symbol, symbol)
    except Exception:
        pass

    # Compute factor scores
    try:
        factors = compute_factors(
            quote=quote,
            financials=financials,
            close=close,
            earnings=earnings,
            recommendations=recs,
            sentiment_agg=sentiment_agg,
            alt_data=alt_data,
        )
        score = composite_score(factors)
        label, _ = composite_label_color(score)
    except Exception as exc:
        log.warning("Batch: factor computation failed for %s: %s", symbol, exc)
        return None

    # Compute risk score
    risk: dict = {}
    risk_level = ""
    try:
        risk = compute_risk(
            quote=quote,
            financials=financials,
            close=close,
            earnings=earnings,
            recommendations=recs,
            sentiment_agg=sentiment_agg,
            composite_factor_score=score,
        )
        risk_level = risk.get("risk_level", "")
    except Exception as exc:
        log.debug("Batch: risk computation failed for %s: %s", symbol, exc)

    risk_score = risk.get("risk_score", 50)

    # factors is already a list[dict] — pass through directly
    factors_list = [f for f in factors if isinstance(f, dict)]

    flags_list = risk.get("flags", [])

    # Persist to analysis_history
    try:
        save_analysis(
            symbol=symbol,
            price=price,
            factor_score=int(score),
            risk_score=int(risk_score),
            composite_label=label,
            risk_level=risk_level,
            factors=factors_list,
            flags=flags_list,
        )
    except Exception as exc:
        log.warning("Batch: save_analysis failed for %s: %s", symbol, exc)
        return None

    # Seed signal_returns with current price (forward returns filled later)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        upsert_signal_return(
            symbol=symbol,
            signal_date=today,
            signal_score=int(score),
            price_at_signal=price,
        )
    except Exception as exc:
        log.debug("Batch: upsert_signal_return failed for %s: %s", symbol, exc)

    return {"symbol": symbol, "factor_score": int(score), "risk_score": int(risk_score), "price": price}


# ---------------------------------------------------------------------------
# ML weight retrain hook
# ---------------------------------------------------------------------------


def _maybe_retrain_ml_weights() -> None:
    """Trigger ML weight retrain if a new quarter's worth of data has accumulated.

    A "new quarter" means: the data count has grown by at least MIN_SAMPLES
    since the last training date, OR the last training is older than
    RETRAIN_EVERY_DAYS.  We rely on ``get_adaptive_weights(force_retrain=True)``
    which already handles this check internally — so we just call it.
    """
    try:
        from src.analysis.ml_weights import MIN_SAMPLES, RETRAIN_EVERY_DAYS, _retrain_and_save
        from src.data.history import get_all_factor_snapshots, get_latest_ml_weights

        snapshots = get_all_factor_snapshots()
        if len(snapshots) < MIN_SAMPLES:
            log.info(
                "Batch: only %d snapshots — skipping ML retrain (need %d)",
                len(snapshots),
                MIN_SAMPLES,
            )
            return

        last = get_latest_ml_weights()
        if last is not None:
            trained_date = datetime.strptime(last["trained_date"], "%Y-%m-%d")
            age_days = (datetime.utcnow() - trained_date).days
            prev_n = last.get("n_samples", 0)
            new_data = len(snapshots) - prev_n
            if age_days < RETRAIN_EVERY_DAYS and new_data < MIN_SAMPLES:
                log.info(
                    "Batch: ML weights are %d days old and only %d new rows — "
                    "skipping retrain",
                    age_days,
                    new_data,
                )
                return

        log.info("Batch: triggering ML weight retrain (%d snapshots available)", len(snapshots))
        result = _retrain_and_save()
        log.info(
            "Batch: ML retrain complete — AUC=%.3f n=%d",
            result.get("auc", 0),
            result.get("n_samples", 0),
        )
    except Exception as exc:
        log.warning("Batch: ML retrain failed (non-fatal): %s", exc)


# ---------------------------------------------------------------------------
# Core batch run
# ---------------------------------------------------------------------------


def run_batch_analysis(api=None) -> dict:
    """Run a full batch analysis across all watchlist tickers.

    Parameters
    ----------
    api : FinnhubAPI | MockFinnhubAPI | None
        API client to use.  If None, ``get_api()`` is called automatically.

    Returns
    -------
    dict with keys: processed, errors, symbols_processed, duration_s
    """
    from src.data.api import get_api
    from src.data.history import save_batch_run
    from src.trading.watchlist import get_watchlist

    if api is None:
        api = get_api()

    tickers = [e["symbol"] for e in get_watchlist()]
    if not tickers:
        log.info("Batch: watchlist is empty — nothing to analyze")
        result = {"processed": 0, "errors": 0, "symbols_processed": [], "duration_s": 0.0}
        save_batch_run(status="success", **result)
        return result

    log.info("Batch: starting analysis for %d tickers: %s", len(tickers), tickers)
    t0 = time.monotonic()

    # Mark run as started
    save_batch_run(status="running", processed=0, errors=0, symbols_processed=[], duration_s=0.0)

    processed = 0
    errors = 0
    symbols_processed: list[str] = []

    for symbol in tickers:
        result = _analyze_ticker(api, symbol)
        if result is not None:
            processed += 1
            symbols_processed.append(symbol)
        else:
            errors += 1
        # Gentle rate limiting between tickers
        time.sleep(0.5)

    # Fill forward returns for signals old enough to have elapsed
    try:
        from src.analysis.signal_validity import backfill_all_forward_returns

        log.info("Batch: backfilling forward returns…")
        fwd = backfill_all_forward_returns()
        log.info(
            "Batch: forward returns — processed=%d skipped=%d errors=%d",
            fwd["processed"],
            fwd["skipped"],
            fwd["errors"],
        )
    except Exception as exc:
        log.warning("Batch: backfill_all_forward_returns failed: %s", exc)

    # Trigger ML retrain if warranted
    _maybe_retrain_ml_weights()

    duration_s = round(time.monotonic() - t0, 1)
    status = "success" if errors == 0 else "partial" if processed > 0 else "error"

    summary = {
        "processed": processed,
        "errors": errors,
        "symbols_processed": symbols_processed,
        "duration_s": duration_s,
    }
    save_batch_run(status=status, **summary)

    log.info(
        "Batch: done — processed=%d errors=%d duration=%.1fs",
        processed,
        errors,
        duration_s,
    )
    return summary


# ---------------------------------------------------------------------------
# APScheduler integration
# ---------------------------------------------------------------------------


def start_batch_scheduler(api=None) -> bool:
    """Start the APScheduler background job for nightly batch analysis.

    Returns True if the scheduler was started, False if APScheduler is not
    installed or batch_analysis.enabled is false in config.yaml.
    """
    global _batch_scheduler

    if not cfg.get("batch_analysis", "enabled", default=False):
        log.info("Batch: scheduler disabled (batch_analysis.enabled=false in config.yaml)")
        return False

    if not _HAS_APSCHEDULER:
        log.warning(
            "Batch: APScheduler not installed — cannot schedule batch analysis. "
            "Install with: pip install apscheduler"
        )
        return False

    if _batch_scheduler is not None and _batch_scheduler.running:
        log.debug("Batch: scheduler already running")
        return True

    hour = int(cfg.get("batch_analysis", "schedule_hour", default=7))
    minute = int(cfg.get("batch_analysis", "schedule_minute", default=0))

    def _job():
        try:
            run_batch_analysis(api)
        except Exception as exc:
            log.error("Batch scheduler job failed: %s", exc)

    _batch_scheduler = BackgroundScheduler(timezone="UTC")
    _batch_scheduler.add_job(
        _job,
        trigger="cron",
        hour=hour,
        minute=minute,
        id="batch_analysis",
        name="Nightly batch analysis",
        replace_existing=True,
    )
    _batch_scheduler.start()

    log.info(
        "Batch: scheduler started — runs daily at %02d:%02dZ UTC",
        hour,
        minute,
    )
    return True


def stop_batch_scheduler() -> None:
    """Stop the background scheduler if running."""
    global _batch_scheduler
    if _batch_scheduler is not None and _batch_scheduler.running:
        _batch_scheduler.shutdown(wait=False)
        log.info("Batch: scheduler stopped")
    _batch_scheduler = None


def is_scheduler_running() -> bool:
    """Return True if the batch scheduler is active."""
    return _batch_scheduler is not None and _batch_scheduler.running


def get_next_run_time() -> datetime | None:
    """Return the next scheduled run time (UTC), or None if not running."""
    if _batch_scheduler is None or not _batch_scheduler.running:
        return None
    job = _batch_scheduler.get_job("batch_analysis")
    if job is None:
        return None
    return job.next_run_time
