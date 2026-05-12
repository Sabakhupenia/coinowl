"""Logging via loguru.

All timestamps are rendered in Asia/Tbilisi time (UTC+4) — including the
internal `record["time"]` value, so file and console sinks stay in sync.

`get_logger(name)` returns a logger bound with a `component` field for
backward compatibility with the stdlib-style call sites that already exist
in the codebase. Call `configure_logging()` once at startup (from main.py)
before any logger is used.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from loguru import logger

_TBILISI_TZ = ZoneInfo("Asia/Tbilisi")  # UTC+4, no DST
_LOG_DIR = Path("logs")
_LOG_FILE = _LOG_DIR / "coinowl.log"

_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> "
    "<level>{level: <8}</level> "
    "<cyan>{extra[component]}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> "
    "- <level>{message}</level>"
)
_FILE_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} "
    "{level: <8} "
    "{extra[component]}:{function}:{line} "
    "- {message}"
)

_configured = False


def _shift_to_tbilisi(record: dict[str, Any]) -> None:
    """Loguru patcher: rewrite `record["time"]` into the Tbilisi timezone.

    Loguru's `time` field is a timezone-aware `datetime`; reassigning it to a
    different tz changes both the displayed time and the comparison value.
    """
    t = record["time"]
    if isinstance(t, datetime):
        record["time"] = t.astimezone(_TBILISI_TZ)


def configure_logging() -> None:
    """Idempotent — call once at startup."""
    global _configured
    if _configured:
        return

    logger.remove()  # drop the default stderr handler
    logger.configure(patcher=_shift_to_tbilisi, extra={"component": "coinowl"})

    logger.add(
        sys.stderr,
        format=_FORMAT,
        level="INFO",
        colorize=True,
        backtrace=False,
        diagnose=False,
    )

    _LOG_DIR.mkdir(exist_ok=True)
    logger.add(
        _LOG_FILE,
        format=_FILE_FORMAT,
        level="DEBUG",
        rotation="10 MB",
        retention="7 days",
        encoding="utf-8",
        backtrace=False,
        diagnose=False,
    )

    _configured = True


def get_logger(name: str) -> "logger.__class__":  # type: ignore[name-defined]
    """Backward-compat shim: returns a logger bound with `component=<name>`.

    Existing call sites use `log = get_logger(__name__); log.info(...)`. With
    loguru bound, those keep working — log messages just gain the component
    field in the format template.
    """
    if not _configured:
        configure_logging()
    return logger.bind(component=name)
