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
    gemini_model: str                    # default: gemini-2.5-flash
    openai_api_key: str | None           # primary LLM for non-chart queries; unset = Gemini-only
    openai_model: list[str]              # ordered preference list, e.g. ['gpt-5.4', 'gpt-5.4-mini']
    openai_model_caps: dict[str, int]    # per-model daily token cap (UTC midnight reset). Defaults below.
    anthropic_api_key: str | None        # last-resort fallback LLM
    coingecko_api_key: str | None        # demo plan key, optional
    database_url: str                    # Supabase Postgres (session pooler, port 5432)
    admin_user_id: int | None            # Telegram user_id allowed to use /admin commands


# Conservative caps just below OpenAI's traffic-share free-tier limits. Keeps
# the bot from spilling onto paid credits when the free bucket is exhausted —
# on accounts WITH paid balance, OpenAI silently bills past the free limit
# rather than returning RateLimitError, so we MUST cap client-side.
_DEFAULT_OPENAI_MODEL_CAPS: dict[str, int] = {
    "gpt-5.4": 220_000,        # 88% of 250K/day free
    "gpt-5.4-mini": 2_200_000, # 88% of 2.5M/day free
}


def _parse_openai_model_caps(raw: str | None) -> dict[str, int]:
    """Parse OPENAI_MODEL_CAPS=key=val,key=val into a dict, merged onto defaults.

    Examples:
      'gpt-5.4=180000'                       → override gpt-5.4 only
      'gpt-5.4=180000,gpt-5.4-mini=1800000'  → override both
      None or ''                             → defaults
    Bad entries (no '=', non-int value) are skipped with no error so a typo
    can't take down startup.
    """
    caps = dict(_DEFAULT_OPENAI_MODEL_CAPS)
    if not raw:
        return caps
    for pair in raw.split(","):
        pair = pair.strip()
        if "=" not in pair:
            continue
        key, _, val = pair.partition("=")
        key = key.strip()
        try:
            caps[key] = int(val.strip())
        except ValueError:
            continue
    return caps


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

    # OPENAI_MODEL: comma-separated, ordered preference. Single value (no comma)
    # behaves exactly as before. Default keeps gpt-5.4-mini as the safe option.
    openai_model_raw = os.environ.get("OPENAI_MODEL", "").strip()
    if openai_model_raw:
        openai_model_list = [m.strip() for m in openai_model_raw.split(",") if m.strip()]
    else:
        openai_model_list = ["gpt-5.4-mini"]

    openai_model_caps = _parse_openai_model_caps(_optional("OPENAI_MODEL_CAPS"))

    return Settings(
        telegram_api_id=api_id,
        telegram_api_hash=_require("TELEGRAM_API_HASH"),
        telegram_bot_token=_require("TELEGRAM_BOT_TOKEN"),
        telegram_session_string=_optional("TELEGRAM_SESSION_STRING"),
        gemini_api_key=_require("GEMINI_API_KEY"),
        gemini_model=os.environ.get("GEMINI_MODEL", "").strip() or "gemini-2.5-flash",
        openai_api_key=_optional("OPENAI_API_KEY"),
        openai_model=openai_model_list,
        openai_model_caps=openai_model_caps,
        anthropic_api_key=_optional("ANTHROPIC_API_KEY"),
        coingecko_api_key=_optional("COINGECKO_API_KEY"),
        database_url=_require("DATABASE_URL"),
        admin_user_id=admin_user_id,
    )
