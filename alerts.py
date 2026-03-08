"""Price & signal alert system.

Alerts are stored in ~/.jaja-money/alerts.json.
Each alert has a condition type, threshold, and status (active/triggered).
Call check_alerts(quote, factor_score, risk_score) to evaluate all alerts
for a symbol and return triggered ones.

Background polling (P2.5):
  start_alert_scheduler() — launch APScheduler background job (requires APScheduler)
  stop_alert_scheduler()  — shut down the scheduler
  is_scheduler_running()  — check scheduler status
Desktop notifications use plyer (optional).
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from log_setup import get_logger

log = get_logger(__name__)

_DATA_DIR = Path.home() / ".jaja-money"
_ALERTS_FILE = _DATA_DIR / "alerts.json"

# Optional APScheduler
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    _HAS_APSCHEDULER = True
except ImportError:
    _HAS_APSCHEDULER = False

# Optional plyer desktop notifications
try:
    from plyer import notification as _plyer_notification
    _HAS_PLYER = True
except ImportError:
    _HAS_PLYER = False

_scheduler = None
_scheduler_lock = threading.Lock()

# Alert condition types
CONDITION_TYPES = [
    "Price Above",
    "Price Below",
    "Factor Score Above",
    "Factor Score Below",
    "Risk Score Above",
]


def _load() -> list[dict]:
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not _ALERTS_FILE.exists():
            return []
        with open(_ALERTS_FILE, "r") as f:
            return json.load(f) or []
    except Exception as exc:
        log.warning("Failed to load alerts: %s", exc)
        return []


def _save(alerts: list[dict]) -> None:
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(_ALERTS_FILE, "w") as f:
            json.dump(alerts, f, indent=2)
    except Exception as exc:
        log.warning("Failed to save alerts: %s", exc)


def get_alerts(symbol: str | None = None) -> list[dict]:
    """Return all alerts, optionally filtered by symbol."""
    alerts = _load()
    if symbol:
        alerts = [a for a in alerts if a["symbol"] == symbol.upper()]
    return alerts


def add_alert(
    symbol: str,
    condition: str,
    threshold: float,
    note: str = "",
) -> None:
    """Add a new alert."""
    alerts = _load()
    alerts.append({
        "id": int(time.time() * 1000),
        "symbol": symbol.upper(),
        "condition": condition,
        "threshold": threshold,
        "note": note,
        "status": "active",
        "created_at": int(time.time()),
        "triggered_at": None,
    })
    _save(alerts)
    log.info("Alert added: %s %s %.2f", symbol, condition, threshold)


def delete_alert(alert_id: int) -> None:
    alerts = [a for a in _load() if a["id"] != alert_id]
    _save(alerts)


def check_alerts(
    symbol: str,
    price: float | None,
    factor_score: int | None,
    risk_score: int | None,
) -> list[dict]:
    """Check active alerts for a symbol. Returns list of newly triggered alerts."""
    alerts = _load()
    triggered = []
    updated = False

    for alert in alerts:
        if alert["symbol"] != symbol.upper():
            continue
        if alert["status"] != "active":
            continue

        cond = alert["condition"]
        thresh = alert["threshold"]
        hit = False

        if cond == "Price Above" and price is not None and price > thresh:
            hit = True
        elif cond == "Price Below" and price is not None and price < thresh:
            hit = True
        elif cond == "Factor Score Above" and factor_score is not None and factor_score > thresh:
            hit = True
        elif cond == "Factor Score Below" and factor_score is not None and factor_score < thresh:
            hit = True
        elif cond == "Risk Score Above" and risk_score is not None and risk_score > thresh:
            hit = True

        if hit:
            alert["status"] = "triggered"
            alert["triggered_at"] = int(time.time())
            triggered.append(alert)
            updated = True

    if updated:
        _save(alerts)

    return triggered


def reset_alert(alert_id: int) -> None:
    """Re-activate a triggered alert."""
    alerts = _load()
    for a in alerts:
        if a["id"] == alert_id:
            a["status"] = "active"
            a["triggered_at"] = None
            break
    _save(alerts)


# ---------------------------------------------------------------------------
# P2.5: Background polling with APScheduler + desktop notifications
# ---------------------------------------------------------------------------

def _send_desktop_notification(title: str, message: str) -> None:
    """Send a desktop notification via plyer (if available)."""
    if _HAS_PLYER:
        try:
            _plyer_notification.notify(
                title=title,
                message=message,
                app_name="jaja-money",
                timeout=10,
            )
        except Exception as exc:
            log.warning("Desktop notification failed: %s", exc)
    else:
        log.info("Alert notification (plyer unavailable): %s — %s", title, message)


def _poll_all_alerts() -> None:
    """Background job: evaluate active alerts using cached quote data."""
    try:
        from cache import get_cache
        cache = get_cache()
    except Exception:
        return

    alerts = _load()
    active = [a for a in alerts if a["status"] == "active"]
    if not active:
        return

    symbols = {a["symbol"] for a in active}
    for sym in symbols:
        try:
            quote = cache.get(f"quote:{sym}")
            if not quote:
                continue
            price = quote.get("c")
            triggered = check_alerts(sym, price, None, None)
            for t in triggered:
                _send_desktop_notification(
                    f"jaja-money: {sym}",
                    f"{t['condition']} {t['threshold']} triggered",
                )
        except Exception as exc:
            log.warning("Alert poll error for %s: %s", sym, exc)


def start_alert_scheduler(interval_seconds: int = 300) -> bool:
    """Start the background alert polling scheduler.

    Returns True if the scheduler was started (requires APScheduler).
    """
    global _scheduler
    if not _HAS_APSCHEDULER:
        log.warning("APScheduler not installed; background alerts unavailable")
        return False

    with _scheduler_lock:
        if _scheduler is not None and _scheduler.running:
            return True
        _scheduler = BackgroundScheduler()
        _scheduler.add_job(
            _poll_all_alerts,
            "interval",
            seconds=interval_seconds,
            id="alert_poll",
            replace_existing=True,
        )
        _scheduler.start()
        log.info("Alert scheduler started (interval=%ds)", interval_seconds)
    return True


def stop_alert_scheduler() -> None:
    """Stop the background alert scheduler."""
    global _scheduler
    with _scheduler_lock:
        if _scheduler is not None and _scheduler.running:
            _scheduler.shutdown(wait=False)
            _scheduler = None
            log.info("Alert scheduler stopped")


def is_scheduler_running() -> bool:
    """Return True if the background scheduler is active."""
    return _scheduler is not None and _scheduler.running
