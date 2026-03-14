"""Structured logging setup for jaja-money.

Call get_logger(__name__) in each module.  Logs go to:
  - Console (INFO and above)
  - Rotating file at ~/.jaja-money/jaja.log (configurable level)

Usage:
    from log_setup import get_logger
    log = get_logger(__name__)
    log.info("Fetching quote", extra={"symbol": "AAPL"})
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config import cfg

_LOG_DIR = Path.home() / ".jaja-money"
_LOG_FILE = _LOG_DIR / "jaja.log"

_initialized = False


def _init_root_logger() -> None:
    global _initialized
    if _initialized:
        return
    _initialized = True

    # Ensure log directory exists
    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger("jaja")
    root.setLevel(getattr(logging, cfg.log_level, logging.INFO))

    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.WARNING)  # only warnings+ to stdout
    console.setFormatter(fmt)
    root.addHandler(console)

    # Rotating file handler
    try:
        fh = RotatingFileHandler(
            _LOG_FILE,
            maxBytes=cfg.log_max_bytes,
            backupCount=cfg.log_backup_count,
            encoding="utf-8",
        )
        fh.setLevel(getattr(logging, cfg.log_level, logging.INFO))
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except OSError:
        pass  # If log file can't be created, continue without file logging


def get_logger(name: str) -> logging.Logger:
    """Return a named child logger under the 'jaja' root."""
    _init_root_logger()
    # Prefix with 'jaja.' so all app loggers are under one root
    child_name = f"jaja.{name}" if not name.startswith("jaja") else name
    return logging.getLogger(child_name)
