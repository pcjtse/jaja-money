"""Centralized configuration management.

Loads config.yaml from the project root, resolves ~ paths, and exposes
a singleton Config object. Falls back to built-in defaults if the YAML
file is missing or malformed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_CONFIG_FILE = _PROJECT_ROOT / "config.yaml"

# ---------------------------------------------------------------------------
# Defaults (used when YAML is absent or a key is missing)
# ---------------------------------------------------------------------------

_DEFAULTS: dict[str, Any] = {
    "cache": {
        "ttl_seconds": 300,
        "disk_cache_dir": str(Path.home() / ".jaja-money" / "cache"),
        "use_disk_cache": True,
    },
    "factor_weights": {
        "valuation": 0.15,
        "trend": 0.20,
        "rsi": 0.10,
        "macd": 0.10,
        "sentiment": 0.15,
        "earnings": 0.15,
        "analyst": 0.10,
        "range": 0.05,
    },
    "risk": {
        "bands": {
            "extreme": 80,
            "high": 65,
            "elevated": 45,
            "moderate": 25,
        }
    },
    "portfolio": {
        "max_positions": {
            "conservative": 5.0,
            "moderate": 10.0,
            "aggressive": 20.0,
        }
    },
    "screener": {
        "default_universe": [
            "AAPL",
            "MSFT",
            "GOOGL",
            "AMZN",
            "NVDA",
            "META",
            "TSLA",
            "JPM",
            "JNJ",
            "V",
        ]
    },
    "sectors": {
        "etfs": [
            {"ticker": "XLK", "name": "Technology"},
            {"ticker": "XLF", "name": "Financials"},
            {"ticker": "XLE", "name": "Energy"},
            {"ticker": "XLV", "name": "Health Care"},
            {"ticker": "XLI", "name": "Industrials"},
            {"ticker": "XLY", "name": "Consumer Disc."},
            {"ticker": "XLP", "name": "Consumer Staples"},
            {"ticker": "XLRE", "name": "Real Estate"},
            {"ticker": "XLB", "name": "Materials"},
            {"ticker": "XLU", "name": "Utilities"},
            {"ticker": "XLC", "name": "Communication"},
        ]
    },
    "display": {
        "chart_height": 500,
        "max_news_articles": 10,
    },
    "logging": {
        "level": "INFO",
        "max_bytes": 10_485_760,
        "backup_count": 3,
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base, returning a new dict."""
    result = base.copy()
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def _load_yaml() -> dict:
    try:
        import yaml  # optional dep

        with open(_CONFIG_FILE, "r") as f:
            data = yaml.safe_load(f) or {}
        return data
    except FileNotFoundError:
        return {}
    except Exception:
        return {}


def _resolve_paths(data: dict) -> dict:
    """Expand ~ in path-like string values."""
    if "cache" in data and "disk_cache_dir" in data["cache"]:
        data["cache"]["disk_cache_dir"] = str(
            Path(data["cache"]["disk_cache_dir"]).expanduser()
        )
    return data


class _Config:
    """Thin wrapper around a merged config dict."""

    def __init__(self, data: dict) -> None:
        self._data = data

    def get(self, *keys: str, default: Any = None) -> Any:
        """Traverse nested keys, e.g. cfg.get('cache', 'ttl_seconds')."""
        node = self._data
        for k in keys:
            if not isinstance(node, dict) or k not in node:
                return default
            node = node[k]
        return node

    # Convenience properties
    @property
    def cache_ttl(self) -> int:
        return int(self.get("cache", "ttl_seconds", default=300))

    @property
    def cache_dir(self) -> Path:
        return Path(
            self.get(
                "cache",
                "disk_cache_dir",
                default=str(Path.home() / ".jaja-money" / "cache"),
            )
        )

    @property
    def use_disk_cache(self) -> bool:
        return bool(self.get("cache", "use_disk_cache", default=True))

    @property
    def factor_weights(self) -> dict[str, float]:
        return self.get("factor_weights", default=_DEFAULTS["factor_weights"])

    @factor_weights.setter
    def factor_weights(self, value: dict[str, float]) -> None:
        self._data["factor_weights"] = value

    @property
    def screener_universe(self) -> list[str]:
        return self.get(
            "screener",
            "default_universe",
            default=_DEFAULTS["screener"]["default_universe"],
        )

    @property
    def sector_etfs(self) -> list[dict]:
        return self.get("sectors", "etfs", default=_DEFAULTS["sectors"]["etfs"])

    @property
    def chart_height(self) -> int:
        return int(self.get("display", "chart_height", default=500))

    @property
    def max_news_articles(self) -> int:
        return int(self.get("display", "max_news_articles", default=10))

    @property
    def log_level(self) -> str:
        return str(self.get("logging", "level", default="INFO"))

    @property
    def log_max_bytes(self) -> int:
        return int(self.get("logging", "max_bytes", default=10_485_760))

    @property
    def log_backup_count(self) -> int:
        return int(self.get("logging", "backup_count", default=3))

    @property
    def ai_backend(self) -> str:
        """AI backend to use: 'sdk' (default) or 'cli'."""
        return str(self.get("ai_backend", default="sdk"))


def _build_config() -> _Config:
    yaml_data = _load_yaml()
    merged = _deep_merge(_DEFAULTS, yaml_data)
    merged = _resolve_paths(merged)
    return _Config(merged)


# Singleton
cfg: _Config = _build_config()
