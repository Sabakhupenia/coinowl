"""Environment-backed settings.

Loaded once at startup. Failing fast with a clear message beats discovering a
missing secret deep inside an async Telethon stack trace.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


class MissingEnvVarError(RuntimeError):
    """Raised when a required environment variable is unset or empty."""


@dataclass(frozen=True)
class Settings:
    telegram_api_id: int
    telegram_api_hash: str
    telegram_bot_token: str
    gemini_api_key: str
    anthropic_api_key: str
    coingecko_api_key: str | None  # demo plan key, optional


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise MissingEnvVarError(
            f"Required environment variable {name!r} is not set. "
            f"Copy .env.example to .env and fill it in."
        )
    return value


def _optional(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or None


def load_settings() -> Settings:
    api_id_raw = _require("TELEGRAM_API_ID")
    try:
        api_id = int(api_id_raw)
    except ValueError as exc:
        raise MissingEnvVarError(
            f"TELEGRAM_API_ID must be an integer, got {api_id_raw!r}."
        ) from exc

    return Settings(
        telegram_api_id=api_id,
        telegram_api_hash=_require("TELEGRAM_API_HASH"),
        telegram_bot_token=_require("TELEGRAM_BOT_TOKEN"),
        gemini_api_key=_require("GEMINI_API_KEY"),
        anthropic_api_key=_require("ANTHROPIC_API_KEY"),
        coingecko_api_key=_optional("COINGECKO_API_KEY"),
    )
