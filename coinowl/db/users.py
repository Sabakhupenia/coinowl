"""Users DAO — identity, watchlist, onboarding profile."""

from __future__ import annotations

from typing import Any

from coinowl.db.pool import pool


async def get_or_create_user(
    user_id: int,
    telegram_username: str | None = None,
) -> dict[str, Any]:
    """Upsert and return the user row as a dict.

    `last_seen_at` is refreshed on every call; `telegram_username` is updated
    only when a non-null value is supplied (so callers who don't know it can
    pass None without overwriting an existing value).
    """
    row = await pool().fetchrow(
        """
        INSERT INTO users (user_id, telegram_username)
        VALUES ($1, $2)
        ON CONFLICT (user_id) DO UPDATE
          SET last_seen_at      = NOW(),
              telegram_username = COALESCE(EXCLUDED.telegram_username, users.telegram_username)
        RETURNING *
        """,
        user_id,
        telegram_username,
    )
    return dict(row)


async def set_profile(
    user_id: int,
    *,
    display_name: str,
    preferred_languages: list[str],
) -> None:
    """Save onboarding profile and flip the `onboarded` flag."""
    await pool().execute(
        """
        UPDATE users
           SET display_name        = $2,
               preferred_languages = $3,
               onboarded           = TRUE
         WHERE user_id = $1
        """,
        user_id,
        display_name,
        preferred_languages,
    )
