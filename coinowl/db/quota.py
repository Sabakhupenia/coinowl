"""DB-backed rolling-window quota (replaces the in-memory QuotaTracker)."""

from __future__ import annotations

from coinowl.db.pool import pool

DEFAULT_LIMIT = 10
DEFAULT_WINDOW_HOURS = 3


async def _effective_limit(conn, user_id: int, default: int) -> int:
    """Look up users.quota_override; fall back to default."""
    row = await conn.fetchrow(
        "SELECT quota_override FROM users WHERE user_id = $1", user_id
    )
    if row is None or row["quota_override"] is None:
        return default
    return int(row["quota_override"])


async def check_and_consume(
    user_id: int,
    *,
    limit: int = DEFAULT_LIMIT,
    window_hours: int = DEFAULT_WINDOW_HOURS,
) -> tuple[bool, int]:
    """Roll the window, count, and consume one slot if under the limit.

    Returns (allowed, remaining_after_this_call).
    Counter survives restarts because the window is computed against `ts`
    rather than process uptime. Uses users.quota_override when set, otherwise
    the `limit` argument.
    """
    async with pool().acquire() as conn:
        async with conn.transaction():
            effective = await _effective_limit(conn, user_id, limit)
            await conn.execute(
                "DELETE FROM quota_log "
                "WHERE user_id = $1 AND ts < NOW() - ($2 || ' hours')::INTERVAL",
                user_id,
                str(window_hours),
            )
            used = await conn.fetchval(
                "SELECT COUNT(*) FROM quota_log WHERE user_id = $1",
                user_id,
            )
            used = int(used or 0)
            if used >= effective:
                return False, 0
            await conn.execute(
                "INSERT INTO quota_log (user_id) VALUES ($1)",
                user_id,
            )
            return True, effective - used - 1


async def usage_in_window(
    user_id: int, *, window_hours: int = DEFAULT_WINDOW_HOURS
) -> int:
    """Count messages this user sent within the rolling window. Read-only."""
    row = await pool().fetchrow(
        "SELECT COUNT(*) AS n FROM quota_log "
        "WHERE user_id = $1 AND ts > NOW() - ($2 || ' hours')::INTERVAL",
        user_id,
        str(window_hours),
    )
    return int(row["n"] if row else 0)


async def clear_quota(user_id: int) -> int:
    """Delete this user's quota_log rows. Returns rows removed."""
    result = await pool().execute(
        "DELETE FROM quota_log WHERE user_id = $1", user_id
    )
    # asyncpg returns "DELETE <n>" — parse trailing int
    try:
        return int(result.rsplit(" ", 1)[1])
    except (ValueError, IndexError):
        return 0


async def set_quota_override(user_id: int, override: int | None) -> bool:
    """Set or clear users.quota_override. Returns True if a row was updated."""
    result = await pool().execute(
        "UPDATE users SET quota_override = $2 WHERE user_id = $1",
        user_id,
        override,
    )
    try:
        return int(result.rsplit(" ", 1)[1]) > 0
    except (ValueError, IndexError):
        return False
