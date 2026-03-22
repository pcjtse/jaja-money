"""Event-Triggered Analysis for jaja-money skill.

Hooks APScheduler into jaja-money's data sources to automatically trigger
analysis callbacks when market events occur.

Events monitored:
    earnings_approaching   — earnings date within 3 days
    new_sec_filing         — 10-K / 10-Q / 8-K filed today
    price_alert_triggered  — price / factor threshold breached

Usage:
    from jaja_money_skill.scripts.jaja_events import (
        start_event_scheduler,
        stop_event_scheduler,
        register_event_callback,
    )

    def on_earnings(event):
        print(f"Earnings soon for {event['symbol']}: {event['date']}")

    register_event_callback("earnings_approaching", on_earnings)
    start_event_scheduler(tickers=["AAPL", "MSFT"], interval_seconds=300)
"""

from __future__ import annotations

import threading
import time
from typing import Callable

from src.core.log_setup import get_logger

log = get_logger(__name__)

_HAS_APSCHEDULER = False
try:
    from apscheduler.schedulers.background import BackgroundScheduler

    _HAS_APSCHEDULER = True
except ImportError:
    pass

_scheduler = None
_scheduler_lock = threading.Lock()

# Registry of user-supplied callbacks: event_type -> list[callable]
_event_callbacks: dict[str, list[Callable]] = {
    "earnings_approaching": [],
    "new_sec_filing": [],
    "price_alert_triggered": [],
}

VALID_EVENT_TYPES = tuple(_event_callbacks.keys())


# ---------------------------------------------------------------------------
# Callback registry
# ---------------------------------------------------------------------------


def register_event_callback(event_type: str, callback: Callable) -> None:
    """Register a callback for a specific event type.

    Parameters
    ----------
    event_type : one of "earnings_approaching", "new_sec_filing",
                 "price_alert_triggered"
    callback   : callable(event_dict) invoked when the event fires
    """
    if event_type not in _event_callbacks:
        raise ValueError(
            f"Unknown event type: {event_type!r}. Valid types: {list(_event_callbacks)}"
        )
    _event_callbacks[event_type].append(callback)
    log.info("Registered %s callback for event '%s'", callback.__name__, event_type)


def clear_event_callbacks(event_type: str | None = None) -> None:
    """Clear registered callbacks.

    If event_type is None, clears all callbacks for all event types.
    """
    if event_type is None:
        for key in _event_callbacks:
            _event_callbacks[key].clear()
    elif event_type in _event_callbacks:
        _event_callbacks[event_type].clear()


# ---------------------------------------------------------------------------
# Scheduler lifecycle
# ---------------------------------------------------------------------------


def start_event_scheduler(
    tickers: list[str] | None = None,
    interval_seconds: int = 300,
) -> bool:
    """Start the event-triggered analysis scheduler.

    Parameters
    ----------
    tickers          : tickers to monitor (uses config default_universe if None)
    interval_seconds : how often to poll for events (default 5 minutes)

    Returns True if the scheduler was started successfully.
    """
    global _scheduler
    if not _HAS_APSCHEDULER:
        log.warning("APScheduler not installed; event scheduler unavailable")
        return False

    with _scheduler_lock:
        if _scheduler is not None and _scheduler.running:
            log.info("Event scheduler already running")
            return True

        watch_tickers = tickers or _default_tickers()

        _scheduler = BackgroundScheduler()
        _scheduler.add_job(
            _check_all_events,
            "interval",
            seconds=interval_seconds,
            args=[watch_tickers],
            id="jaja_event_poll",
            replace_existing=True,
        )
        _scheduler.start()
        log.info(
            "Event scheduler started — monitoring %d tickers every %ds",
            len(watch_tickers),
            interval_seconds,
        )
    return True


def stop_event_scheduler() -> None:
    """Stop the event scheduler."""
    global _scheduler
    with _scheduler_lock:
        if _scheduler is not None and _scheduler.running:
            _scheduler.shutdown(wait=False)
            _scheduler = None
            log.info("Event scheduler stopped")


def is_scheduler_running() -> bool:
    """Return True if the event scheduler is running."""
    return _scheduler is not None and _scheduler.running


# ---------------------------------------------------------------------------
# Per-event-type checkers
# ---------------------------------------------------------------------------


def check_earnings_events(tickers: list[str], api=None) -> list[dict]:
    """Check for tickers with earnings within the next 3 days."""
    events: list[dict] = []
    if api is None:
        try:
            from src.data.api import get_api

            api = get_api()
        except Exception as exc:
            log.warning("check_earnings_events: could not init API: %s", exc)
            return events

    from datetime import date, datetime

    for symbol in tickers:
        try:
            earnings = api.get_earnings(symbol, limit=1)
            if not earnings:
                continue
            next_earning = earnings[0]
            date_str = next_earning.get("period", "")
            if not date_str:
                continue
            try:
                earn_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                days_away = (earn_date - date.today()).days
                if 0 <= days_away <= 3:
                    events.append(
                        {
                            "event_type": "earnings_approaching",
                            "symbol": symbol,
                            "date": date_str,
                            "days_away": days_away,
                            "eps_estimate": next_earning.get("estimate"),
                            "timestamp": int(time.time()),
                        }
                    )
                    log.info("Earnings event: %s in %d day(s)", symbol, days_away)
            except ValueError:
                continue
        except Exception as exc:
            log.debug("check_earnings_events: error for %s: %s", symbol, exc)
    return events


def check_sec_filing_events(tickers: list[str]) -> list[dict]:
    """Check for new SEC filings (10-K, 10-Q, 8-K) filed today."""
    events: list[dict] = []
    try:
        from src.data.edgar import get_recent_filings
    except ImportError:
        log.debug("check_sec_filing_events: edgar module not available")
        return events

    from datetime import date

    today = date.today().isoformat()
    for symbol in tickers:
        try:
            filings = get_recent_filings(symbol, filing_types=["10-K", "10-Q", "8-K"])
            for filing in filings:
                filed_date = filing.get("filed", "")
                if filed_date.startswith(today):
                    events.append(
                        {
                            "event_type": "new_sec_filing",
                            "symbol": symbol,
                            "filing_type": filing.get("form", ""),
                            "filed": filed_date,
                            "url": filing.get("primaryDocument", ""),
                            "timestamp": int(time.time()),
                        }
                    )
                    log.info(
                        "SEC filing event: %s %s filed today",
                        symbol,
                        filing.get("form"),
                    )
        except Exception as exc:
            log.debug("check_sec_filing_events: error for %s: %s", symbol, exc)
    return events


def check_price_alert_events(tickers: list[str], api=None) -> list[dict]:
    """Evaluate price alerts for all monitored tickers."""
    events: list[dict] = []
    if api is None:
        try:
            from src.data.api import get_api

            api = get_api()
        except Exception as exc:
            log.warning("check_price_alert_events: could not init API: %s", exc)
            return events

    for symbol in tickers:
        try:
            quote = api.get_quote(symbol)
            price = quote.get("c")
            if price is None:
                continue

            from src.ui.alerts import check_alerts

            triggered = check_alerts(
                symbol, price=price, factor_score=None, risk_score=None
            )
            for alert in triggered:
                events.append(
                    {
                        "event_type": "price_alert_triggered",
                        "symbol": symbol,
                        "alert_id": alert.get("id"),
                        "condition": alert.get("condition"),
                        "threshold": alert.get("threshold"),
                        "current_price": price,
                        "timestamp": int(time.time()),
                    }
                )
                log.info(
                    "Price alert event: %s %s %.2f (price=%.2f)",
                    symbol,
                    alert.get("condition"),
                    alert.get("threshold", 0),
                    price,
                )
        except Exception as exc:
            log.debug("check_price_alert_events: error for %s: %s", symbol, exc)
    return events


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _fire_callbacks(event_type: str, events: list[dict]) -> None:
    """Invoke all registered callbacks for an event type."""
    callbacks = _event_callbacks.get(event_type, [])
    for event in events:
        for cb in callbacks:
            try:
                cb(event)
            except Exception as exc:
                log.warning("Event callback %s failed: %s", cb.__name__, exc)


def _check_all_events(tickers: list[str]) -> None:
    """Poll all event sources and fire callbacks. Called by APScheduler."""
    log.debug("Event poll: checking %d tickers", len(tickers))
    earnings_events = check_earnings_events(tickers)
    sec_events = check_sec_filing_events(tickers)
    price_events = check_price_alert_events(tickers)

    _fire_callbacks("earnings_approaching", earnings_events)
    _fire_callbacks("new_sec_filing", sec_events)
    _fire_callbacks("price_alert_triggered", price_events)


def _default_tickers() -> list[str]:
    """Return the default ticker universe from config."""
    try:
        from src.core.config import cfg

        return cfg.get("screener", {}).get("default_universe", [])
    except Exception:
        return ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]
