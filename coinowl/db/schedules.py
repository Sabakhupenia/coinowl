"""Scheduled-push DAO.

A scheduled push is a (cron_expr, tool_name, tool_args) tuple per user. The
watcher walks active schedules each tick, asks croniter whether the next
fire-time is in the past, and if so enqueues the result into
`pending_notifications` (handled by `coinowl.db.notifications`).
"""

from __future__ import annotations

import json
from typing import Any

from coinowl.db.pool import pool


async def create_schedule(
    *,
    user_id: int,
    cron_expr: str,
    tool_name: str,
    tool_args: dict[str, Any],
    original_phrasing: str,
) -> dict[str, Any]:
    row = await pool().fetchrow(
        """
        INSERT INTO scheduled_pushes
            (user_id, cron_expr, tool_name, tool_args_json, original_phrasing)
        VALUES ($1, $2, $3, $4::jsonb, $5)
        RETURNING *
        """,
        user_id,
        cron_expr,
        tool_name,
        json.dumps(tool_args or {}),
        original_phrasing,
    )
    return _row_to_dict(row)


async def list_schedules(user_id: int, *, only_enabled: bool = True) -> list[dict[str, Any]]:
    if only_enabled:
        rows = await pool().fetch(
            "SELECT * FROM scheduled_pushes WHERE user_id = $1 AND enabled = TRUE "
            "ORDER BY created_at DESC",
            user_id,
        )
    else:
        rows = await pool().fetch(
            "SELECT * FROM scheduled_pushes WHERE user_id = $1 ORDER BY created_at DESC",
            user_id,
        )
    return [_row_to_dict(r) for r in rows]


async def cancel_schedule(*, user_id: int, schedule_id: int) -> bool:
    row = await pool().fetchrow(
        """
        UPDATE scheduled_pushes SET enabled = FALSE
         WHERE id = $1 AND user_id = $2 AND enabled = TRUE
        RETURNING id
        """,
        schedule_id,
        user_id,
    )
    return row is not None


async def all_active_schedules() -> list[dict[str, Any]]:
    rows = await pool().fetch("SELECT * FROM scheduled_pushes WHERE enabled = TRUE")
    return [_row_to_dict(r) for r in rows]


async def mark_schedule_fired(schedule_id: int) -> None:
    await pool().execute(
        "UPDATE scheduled_pushes SET last_fired_at = NOW() WHERE id = $1",
        schedule_id,
    )


def _row_to_dict(row: Any) -> dict[str, Any]:
    d = dict(row)
    raw = d.get("tool_args_json")
    if isinstance(raw, str):
        try:
            d["tool_args_json"] = json.loads(raw)
        except json.JSONDecodeError:
            d["tool_args_json"] = {}
    elif raw is None:
        d["tool_args_json"] = {}
    return d
