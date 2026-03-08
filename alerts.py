"""Price & signal alert system.

Alerts are stored in ~/.jaja-money/alerts.json.
Each alert has a condition type, threshold, and status (active/triggered).
Call check_alerts(quote, factor_score, risk_score) to evaluate all alerts
for a symbol and return triggered ones.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from log_setup import get_logger

log = get_logger(__name__)

_DATA_DIR = Path.home() / ".jaja-money"
_ALERTS_FILE = _DATA_DIR / "alerts.json"

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
