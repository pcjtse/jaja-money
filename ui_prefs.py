"""Customizable Dashboard Layout & UX Preferences (P13.1 / P13.2).

Stores UI section visibility preferences and onboarding state in
~/.jaja-money/ui_prefs.json.

Usage:
    from ui_prefs import get_prefs, save_prefs, is_first_run, mark_onboarding_complete
"""
from __future__ import annotations

import json
from pathlib import Path

from log_setup import get_logger

log = get_logger(__name__)

_DATA_DIR = Path.home() / ".jaja-money"
_PREFS_FILE = _DATA_DIR / "ui_prefs.json"

# Default section visibility
_DEFAULT_SECTIONS = {
    "price_chart": True,
    "technical_indicators": True,
    "fundamental_analysis": True,
    "factor_engine": True,
    "risk_guardrails": True,
    "earnings_calendar": True,
    "options_data": True,
    "insider_activity": True,
    "news_sentiment": True,
    "ai_analysis": True,
    "chat": True,
    "history": True,
    "alerts": True,
}

_DEFAULT_PREFS = {
    "onboarding_completed": False,
    "sections": _DEFAULT_SECTIONS.copy(),
    "expanded_sections": {},
    "theme": "light",
    "default_ticker": "AAPL",
    "compact_mode": False,
}


def _load() -> dict:
    import copy
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not _PREFS_FILE.exists():
            return copy.deepcopy(_DEFAULT_PREFS)
        with open(_PREFS_FILE, "r") as f:
            prefs = json.load(f)
        # Merge with defaults to add any new keys
        merged = copy.deepcopy(_DEFAULT_PREFS)
        merged.update(prefs)
        merged["sections"] = {**_DEFAULT_SECTIONS, **prefs.get("sections", {})}
        return merged
    except Exception as exc:
        log.warning("Failed to load UI prefs: %s", exc)
        return copy.deepcopy(_DEFAULT_PREFS)


def _save(prefs: dict) -> None:
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(_PREFS_FILE, "w") as f:
            json.dump(prefs, f, indent=2)
    except Exception as exc:
        log.warning("Failed to save UI prefs: %s", exc)


def get_prefs() -> dict:
    """Return current UI preferences."""
    return _load()


def save_prefs(prefs: dict) -> None:
    """Save UI preferences."""
    _save(prefs)
    log.info("UI preferences saved")


def get_sections() -> dict[str, bool]:
    """Return section visibility dict."""
    return _load()["sections"]


def set_section_visibility(section: str, visible: bool) -> None:
    """Toggle a section's visibility."""
    prefs = _load()
    prefs["sections"][section] = visible
    _save(prefs)


def set_section_expanded(section: str, expanded: bool) -> None:
    """Remember expanded/collapsed state for a section."""
    prefs = _load()
    prefs["expanded_sections"][section] = expanded
    _save(prefs)


def get_section_expanded(section: str, default: bool = True) -> bool:
    """Return whether a section should be expanded."""
    prefs = _load()
    return prefs.get("expanded_sections", {}).get(section, default)


def is_first_run() -> bool:
    """Return True if the user has not completed onboarding."""
    return not _load().get("onboarding_completed", False)


def mark_onboarding_complete() -> None:
    """Mark onboarding as completed."""
    prefs = _load()
    prefs["onboarding_completed"] = True
    _save(prefs)
    log.info("Onboarding marked as complete")


def reset_to_defaults() -> None:
    """Reset all preferences to defaults."""
    import copy
    _save(copy.deepcopy(_DEFAULT_PREFS))
    log.info("UI preferences reset to defaults")


def update_pref(key: str, value) -> None:
    """Update a single top-level preference key."""
    prefs = _load()
    prefs[key] = value
    _save(prefs)


# Section display names for the UI
SECTION_LABELS = {
    "price_chart": "Price Chart",
    "technical_indicators": "Technical Indicators",
    "fundamental_analysis": "Fundamental Analysis",
    "factor_engine": "Factor Score Engine",
    "risk_guardrails": "Risk Guardrails",
    "earnings_calendar": "Earnings Calendar",
    "options_data": "Options Market Data",
    "insider_activity": "Insider Activity",
    "news_sentiment": "News & Sentiment",
    "ai_analysis": "AI Analysis",
    "chat": "Chat with Claude",
    "history": "Score History",
    "alerts": "Price Alerts",
}

# Onboarding tour steps
TOUR_STEPS = [
    {
        "step": 1,
        "title": "Welcome to jaja-money!",
        "description": (
            "Enter a stock ticker (e.g., AAPL) in the sidebar and click Analyze "
            "to get a complete multi-factor analysis powered by Claude AI."
        ),
        "section": None,
    },
    {
        "step": 2,
        "title": "Factor Score Engine",
        "description": (
            "The Factor Score Engine rates your stock on 8 dimensions including "
            "valuation, momentum, sentiment, and earnings quality. Higher = better."
        ),
        "section": "factor_engine",
    },
    {
        "step": 3,
        "title": "Risk Guardrails",
        "description": (
            "Risk Guardrails flag 13 types of risk: overbought conditions, "
            "high leverage, insider selling, and more. Keep an eye on red flags!"
        ),
        "section": "risk_guardrails",
    },
    {
        "step": 4,
        "title": "AI Analysis",
        "description": (
            "Click 'Generate AI Analysis' for Claude to provide institutional-quality "
            "commentary on the stock's investment case."
        ),
        "section": "ai_analysis",
    },
    {
        "step": 5,
        "title": "Explore More Features",
        "description": (
            "Use the sidebar to navigate to Compare (multi-stock), Screener, "
            "Portfolio Analysis, Sector Rotation, and Backtesting pages."
        ),
        "section": None,
    },
]
