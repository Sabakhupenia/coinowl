"""Users DAO — identity, watchlist, onboarding profile.

`onboarded` is a computed state: true only when display_name AND ≥1 language
AND ≥1 watched coin are all present. Each write that touches one of those
fields recomputes the flag inline.
"""

from __future__ import annotations

from typing import Any

from coinowl.db.pool import pool

WATCHLIST_MAX = 10


class WatchlistTooLarge(ValueError):
    """Raised when an update would exceed WATCHLIST_MAX."""


async def get_or_create_user(
    user_id: int,
    telegram_username: str | None = None,
) -> dict[str, Any]:
    """Upsert and return the user row as a dict."""
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
    coins: list[str],
    timezone: str | None = None,
) -> None:
    """Save full onboarding profile (name + languages + watchlist) atomically.

    Recomputes `onboarded` from the new values. If timezone is None, the
    existing DB value is kept (default 'Asia/Tbilisi' for new rows).
    """
    if timezone is None:
        await pool().execute(
            """
            UPDATE users
               SET display_name        = $2::text,
                   preferred_languages = $3::text[],
                   watched_coins       = $4::text[],
                   onboarded           = (
                     $2::text IS NOT NULL
                     AND COALESCE(array_length($3::text[], 1), 0) >= 1
                     AND COALESCE(array_length($4::text[], 1), 0) >= 1
                   )
             WHERE user_id = $1
            """,
            user_id,
            display_name,
            preferred_languages,
            coins,
        )
    else:
        await pool().execute(
            """
            UPDATE users
               SET display_name        = $2::text,
                   preferred_languages = $3::text[],
                   watched_coins       = $4::text[],
                   timezone            = $5::text,
                   onboarded           = (
                     $2::text IS NOT NULL
                     AND COALESCE(array_length($3::text[], 1), 0) >= 1
                     AND COALESCE(array_length($4::text[], 1), 0) >= 1
                   )
             WHERE user_id = $1
            """,
            user_id,
            display_name,
            preferred_languages,
            coins,
            timezone,
        )


async def set_timezone(user_id: int, timezone: str) -> None:
    """Update only the timezone field."""
    await pool().execute(
        "UPDATE users SET timezone = $2::text WHERE user_id = $1",
        user_id,
        timezone,
    )


async def get_watchlist(user_id: int) -> list[str]:
    row = await pool().fetchrow(
        "SELECT watched_coins FROM users WHERE user_id = $1",
        user_id,
    )
    if row is None:
        return []
    return list(row["watched_coins"] or [])


async def update_watchlist(
    user_id: int,
    *,
    symbols: list[str],
    mode: str,
) -> list[str]:
    """Mutate the watchlist (replace / add / remove).

    Returns the resulting watchlist (uppercased, deduped).
    Raises WatchlistTooLarge if the result would exceed WATCHLIST_MAX.
    """
    new_syms = [s.strip().upper() for s in symbols if s and s.strip()]
    current = await get_watchlist(user_id)

    if mode == "replace":
        result = list(dict.fromkeys(new_syms))
    elif mode == "add":
        result = list(dict.fromkeys(current + new_syms))
    elif mode == "remove":
        drop = set(new_syms)
        result = [c for c in current if c not in drop]
    else:
        raise ValueError(f"Unknown mode: {mode!r}")

    if len(result) > WATCHLIST_MAX:
        raise WatchlistTooLarge(
            f"Watchlist would have {len(result)} coins (cap is {WATCHLIST_MAX})"
        )

    await pool().execute(
        """
        UPDATE users
           SET watched_coins = $2::text[],
               onboarded     = (
                 display_name IS NOT NULL
                 AND COALESCE(array_length(preferred_languages, 1), 0) >= 1
                 AND COALESCE(array_length($2::text[], 1), 0) >= 1
               )
         WHERE user_id = $1
        """,
        user_id,
        result,
    )
    return result
