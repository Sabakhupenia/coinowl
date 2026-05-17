"""Price-alert DAO.

Each alert is a threshold + direction the watcher polls against current prices.
Non-recurring alerts auto-disable on first fire so the user isn't pinged
repeatedly for the same cross.
"""

from __future__ import annotations

from typing import Any

from coinowl.db.pool import pool


async def create_alert(
    *,
    user_id: int,
    symbol: str,
    coin_id: str,
    threshold: float,
    direction: str,
    recurring: bool,
    original_phrasing: str,
) -> dict[str, Any]:
    row = await pool().fetchrow(
        """
        INSERT INTO alerts
            (user_id, symbol, coin_id, threshold, direction, recurring, original_phrasing)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING *
        """,
        user_id,
        symbol.upper(),
        coin_id,
        threshold,
        direction,
        recurring,
        original_phrasing,
    )
    return dict(row)


async def list_alerts(user_id: int, *, only_enabled: bool = True) -> list[dict[str, Any]]:
    if only_enabled:
        rows = await pool().fetch(
            "SELECT * FROM alerts WHERE user_id = $1 AND enabled = TRUE "
            "ORDER BY created_at DESC",
            user_id,
        )
    else:
        rows = await pool().fetch(
            "SELECT * FROM alerts WHERE user_id = $1 ORDER BY created_at DESC",
            user_id,
        )
    return [dict(r) for r in rows]


async def cancel_alert(*, user_id: int, alert_id: int) -> bool:
    row = await pool().fetchrow(
        """
        UPDATE alerts SET enabled = FALSE
         WHERE id = $1 AND user_id = $2 AND enabled = TRUE
        RETURNING id
        """,
        alert_id,
        user_id,
    )
    return row is not None


async def all_active_alerts() -> list[dict[str, Any]]:
    """Watcher reads every active alert each tick. Volume stays small in
    practice (cap is implicit in user count × alerts-per-user)."""
    rows = await pool().fetch("SELECT * FROM alerts WHERE enabled = TRUE")
    return [dict(r) for r in rows]


async def mark_alert_fired(alert_id: int) -> None:
    """Update last_fired_at and auto-disable if not recurring.

    `enabled = (recurring AND enabled)` keeps recurring alerts armed and
    flips one-shot alerts off in a single statement.
    """
    await pool().execute(
        """
        UPDATE alerts
           SET last_fired_at = NOW(),
               enabled       = (recurring AND enabled)
         WHERE id = $1
        """,
        alert_id,
    )
