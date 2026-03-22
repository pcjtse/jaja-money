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
    "Signal Change (Factor)",
    "Signal Change (Risk Level)",
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
    alerts.append(
        {
            "id": int(time.time() * 1000),
            "symbol": symbol.upper(),
            "condition": condition,
            "threshold": threshold,
            "note": note,
            "status": "active",
            "created_at": int(time.time()),
            "triggered_at": None,
        }
    )
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
        elif (
            cond == "Factor Score Above"
            and factor_score is not None
            and factor_score > thresh
        ):
            hit = True
        elif (
            cond == "Factor Score Below"
            and factor_score is not None
            and factor_score < thresh
        ):
            hit = True
        elif (
            cond == "Risk Score Above"
            and risk_score is not None
            and risk_score > thresh
        ):
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
            from cache import CACHE_MISS

            quote = cache.get(f"quote:{sym}")
            if quote is CACHE_MISS or not quote:
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


# ---------------------------------------------------------------------------
# P12.1: Slack / Discord / Telegram Alert Webhooks
# ---------------------------------------------------------------------------

import json as _json  # noqa: E402

try:
    import urllib.request as _urllib_request  # noqa: F401

    _HAS_URLLIB = True
except ImportError:
    _HAS_URLLIB = False

_SEVERITY_COLORS = {
    "info": "#2196F3",
    "warning": "#FF9800",
    "critical": "#F44336",
}

_SEVERITY_EMOJIS = {
    "info": "ℹ️",
    "warning": "⚠️",
    "critical": "🚨",
}


def _get_severity(condition: str, threshold: float, current_value: float | None) -> str:
    """Determine alert severity based on condition."""
    if "Risk" in condition:
        return "critical" if (current_value or 0) > 75 else "warning"
    return "warning"


def send_webhook_notification(
    alert: dict,
    current_value: float | None = None,
    slack_url: str = "",
    discord_url: str = "",
    telegram_token: str = "",
    telegram_chat_id: str = "",
    app_url: str = "",
) -> dict:
    """Send alert notification to configured webhook destinations.

    Parameters
    ----------
    alert : triggered alert dict
    current_value : current metric value that triggered the alert
    slack_url : Slack incoming webhook URL
    discord_url : Discord webhook URL
    telegram_token : Telegram Bot API token
    telegram_chat_id : Telegram chat/channel ID
    app_url : deep link back to the app

    Returns dict with success/failure per destination.
    """
    symbol = alert.get("symbol", "?")
    condition = alert.get("condition", "")
    threshold = alert.get("threshold", 0)
    note = alert.get("note", "")

    severity = _get_severity(condition, threshold, current_value)
    emoji = _SEVERITY_EMOJIS.get(severity, "📊")
    color = _SEVERITY_COLORS.get(severity, "#607D8B")

    current_str = f"{current_value:.2f}" if current_value is not None else "N/A"
    title = f"{emoji} Alert Triggered: {symbol}"
    body = (
        f"**{condition}** threshold {threshold} reached\nCurrent value: {current_str}"
    )
    if note:
        body += f"\nNote: {note}"
    if app_url:
        body += f"\n[Open in jaja-money]({app_url}?ticker={symbol})"

    results = {}

    # Slack
    if slack_url:
        results["slack"] = _send_slack(slack_url, title, body, color)

    # Discord
    if discord_url:
        results["discord"] = _send_discord(discord_url, title, body, color)

    # Telegram
    if telegram_token and telegram_chat_id:
        results["telegram"] = _send_telegram(
            telegram_token, telegram_chat_id, f"{title}\n{body}"
        )

    log.info("Webhook notifications sent for %s: %s", symbol, results)
    return results


def _send_slack(webhook_url: str, title: str, body: str, color: str) -> bool:
    payload = {
        "attachments": [
            {
                "color": color,
                "title": title,
                "text": body,
                "footer": "jaja-money alerts",
            }
        ]
    }
    return _post_json(webhook_url, payload)


def _send_discord(webhook_url: str, title: str, body: str, color: str) -> bool:
    # Discord color is an integer
    color_int = int(color.lstrip("#"), 16)
    payload = {
        "embeds": [
            {
                "title": title,
                "description": body,
                "color": color_int,
                "footer": {"text": "jaja-money alerts"},
            }
        ]
    }
    return _post_json(webhook_url, payload)


def _send_telegram(token: str, chat_id: str, message: str) -> bool:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
    }
    return _post_json(url, payload)


def _post_json(url: str, payload: dict) -> bool:
    """POST JSON payload to a URL. Returns True on success."""
    if not url:
        return False
    try:
        data = _json.dumps(payload).encode("utf-8")
        req = _urllib_request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with _urllib_request.urlopen(req, timeout=10) as resp:
            return resp.status < 400
    except Exception as exc:
        log.warning("Webhook POST failed to %s: %s", url[:50], exc)
        return False


# ---------------------------------------------------------------------------
# P20.3: Signal change notifications
# ---------------------------------------------------------------------------

_RISK_LEVEL_NUMERIC = {
    "Low": 1,
    "Moderate": 2,
    "Elevated": 3,
    "High": 4,
    "Extreme": 5,
}


def check_signal_changes(
    symbol: str,
    new_factor_score: int,
    new_risk_level: str,
    history_fn=None,
) -> list[dict]:
    """Detect significant signal changes by comparing to recent history.

    Compares the provided new values against the most recent stored snapshot
    for the symbol. A factor score change of more than 10 points, or a risk
    level shift of 1 or more tiers, generates a change event.

    Parameters
    ----------
    symbol : stock ticker symbol
    new_factor_score : newly computed composite factor score (0-100)
    new_risk_level : newly computed risk level string (Low/Moderate/Elevated/High/Extreme)
    history_fn : optional callable that accepts symbol and returns list of
                 snapshot dicts sorted newest-first. Defaults to importing
                 get_last_n_snapshots from history module.

    Returns
    -------
    list of dicts with keys:
        symbol, change_type ("factor_score" | "risk_level"),
        old_value, new_value, delta, message
    """
    if history_fn is None:
        try:
            from history import get_last_n_snapshots as history_fn  # type: ignore[assignment]
        except ImportError:
            log.warning("check_signal_changes: could not import history module")
            return []

    try:
        snapshots = history_fn(symbol)
    except Exception as exc:
        log.warning("check_signal_changes: history_fn error for %s: %s", symbol, exc)
        return []

    if not snapshots or len(snapshots) < 2:
        log.debug(
            "check_signal_changes: fewer than 2 snapshots for %s; skipping", symbol
        )
        return []

    # snapshots returned newest-first; previous snapshot is index 1
    previous = snapshots[1]
    changes: list[dict] = []

    # --- Factor score change ---
    prev_factor = previous.get("factor_score")
    if prev_factor is not None:
        delta = new_factor_score - int(prev_factor)
        if abs(delta) > 10:
            direction = "increased" if delta > 0 else "decreased"
            changes.append(
                {
                    "symbol": symbol,
                    "change_type": "factor_score",
                    "old_value": int(prev_factor),
                    "new_value": new_factor_score,
                    "delta": delta,
                    "message": (
                        f"{symbol} factor score {direction} by {abs(delta)} points "
                        f"({int(prev_factor)} → {new_factor_score})"
                    ),
                }
            )

    # --- Risk level change ---
    prev_risk_level = previous.get("risk_level", "")
    prev_risk_num = _RISK_LEVEL_NUMERIC.get(prev_risk_level)
    new_risk_num = _RISK_LEVEL_NUMERIC.get(new_risk_level)
    if prev_risk_num is not None and new_risk_num is not None:
        level_delta = new_risk_num - prev_risk_num
        if abs(level_delta) >= 1:
            direction = "upgraded to lower risk" if level_delta < 0 else "elevated"
            changes.append(
                {
                    "symbol": symbol,
                    "change_type": "risk_level",
                    "old_value": prev_risk_level,
                    "new_value": new_risk_level,
                    "delta": level_delta,
                    "message": (
                        f"{symbol} risk level changed from {prev_risk_level} "
                        f"to {new_risk_level} ({direction})"
                    ),
                }
            )

    if changes:
        log.info("Signal changes detected for %s: %d event(s)", symbol, len(changes))
    return changes


# ---------------------------------------------------------------------------
# P17.5: Portfolio drift alert checking
# ---------------------------------------------------------------------------


def check_drift_alerts(
    symbol: str,
    current_weight: float,
    target_weight: float,
    threshold: float = 0.05,
) -> dict | None:
    """Check whether a position has drifted beyond an acceptable threshold.

    Parameters
    ----------
    symbol : stock ticker symbol
    current_weight : current portfolio weight as a decimal (e.g. 0.12 = 12%)
    target_weight : target portfolio weight as a decimal
    threshold : maximum allowed drift before an alert is raised (default 0.05 = 5pp)

    Returns
    -------
    dict with keys symbol, current_weight, target_weight, drift, message
    if the drift exceeds the threshold; otherwise None.
    """
    drift = current_weight - target_weight
    if abs(drift) > threshold:
        direction = "overweight" if drift > 0 else "underweight"
        message = (
            f"{symbol} is {direction} by {abs(drift) * 100:.1f}pp "
            f"(current: {current_weight * 100:.1f}%, "
            f"target: {target_weight * 100:.1f}%)"
        )
        log.info("Drift alert: %s", message)
        return {
            "symbol": symbol,
            "current_weight": current_weight,
            "target_weight": target_weight,
            "drift": drift,
            "message": message,
        }
    return None


def send_test_webhook(
    webhook_type: str,
    url_or_config: str,
    chat_id: str = "",
) -> bool:
    """Send a test message to verify webhook configuration.

    Parameters
    ----------
    webhook_type : "slack", "discord", or "telegram"
    url_or_config : webhook URL (slack/discord) or bot token (telegram)
    chat_id : required for telegram
    """
    test_msg = "✅ jaja-money webhook test — your alerts are configured correctly!"

    if webhook_type == "slack":
        return _send_slack(url_or_config, "Webhook Test", test_msg, "#2196F3")
    elif webhook_type == "discord":
        return _send_discord(url_or_config, "Webhook Test", test_msg, "#2196F3")
    elif webhook_type == "telegram":
        return _send_telegram(url_or_config, chat_id, test_msg)

    log.warning("Unknown webhook type: %s", webhook_type)
    return False
