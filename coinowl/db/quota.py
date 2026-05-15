"""DB-backed rolling-window quota (replaces the in-memory QuotaTracker)."""

from __future__ import annotations

from coinowl.db.pool import pool

_DEFAULT_LIMIT = 10
_DEFAULT_WINDOW_HOURS = 3


async def check_and_consume(
    user_id: int,
    *,
    limit: int = _DEFAULT_LIMIT,
    window_hours: int = _DEFAULT_WINDOW_HOURS,
) -> tuple[bool, int]:
    """Roll the window, count, and consume one slot if under the limit.

    Returns (allowed, remaining_after_this_call).
    Counter survives restarts because the window is computed against `ts`
    rather than process uptime.
    """
    async with pool().acquire() as conn:
        async with conn.transaction():
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
            if used >= limit:
                return False, 0
            await conn.execute(
                "INSERT INTO quota_log (user_id) VALUES ($1)",
                user_id,
            )
            return True, limit - used - 1
