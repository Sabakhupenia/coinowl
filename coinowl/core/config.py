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
    telegram_session_string: str | None  # if set, used instead of .session file (for Railway / stateless deploys)
    gemini_api_key: str
    gemini_model: str              # default: gemini-2.5-flash
    openai_api_key: str | None     # primary LLM for non-chart queries; unset = Gemini-only
    openai_model: str              # default: gpt-5.4-mini
    anthropic_api_key: str | None  # last-resort fallback LLM
    coingecko_api_key: str | None  # demo plan key, optional
    database_url: str              # Supabase Postgres (session pooler, port 5432)
    admin_user_id: int | None      # Telegram user_id allowed to use /admin commands


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

    admin_raw = _optional("ADMIN_TELEGRAM_USER_ID")
    admin_user_id: int | None
    if admin_raw is None:
        admin_user_id = None
    else:
        try:
            admin_user_id = int(admin_raw)
        except ValueError as exc:
            raise MissingEnvVarError(
                f"ADMIN_TELEGRAM_USER_ID must be an integer if set, got {admin_raw!r}."
            ) from exc

    return Settings(
        telegram_api_id=api_id,
        telegram_api_hash=_require("TELEGRAM_API_HASH"),
        telegram_bot_token=_require("TELEGRAM_BOT_TOKEN"),
        telegram_session_string=_optional("TELEGRAM_SESSION_STRING"),
        gemini_api_key=_require("GEMINI_API_KEY"),
        gemini_model=os.environ.get("GEMINI_MODEL", "").strip() or "gemini-2.5-flash",
        openai_api_key=_optional("OPENAI_API_KEY"),
        openai_model=os.environ.get("OPENAI_MODEL", "").strip() or "gpt-5.4-mini",
        anthropic_api_key=_optional("ANTHROPIC_API_KEY"),
        coingecko_api_key=_optional("COINGECKO_API_KEY"),
        database_url=_require("DATABASE_URL"),
        admin_user_id=admin_user_id,
    )
