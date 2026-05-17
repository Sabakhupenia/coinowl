"""Pending-notification queue DAO.

Each scheduled-push fire writes one row here. The unique-index-on-undelivered
guarantees at most one queued row per (user, schedule) — a subsequent fire
overwrites the payload via UPSERT so the user comes back to "where things
stand now," not a stack of stale digests.

Price alerts never go through this queue — they push to Telegram immediately.
"""

from __future__ import annotations

import json
from typing import Any

from coinowl.db.pool import pool


async def enqueue(
    *,
    user_id: int,
    schedule_id: int,
    payload: dict[str, Any],
) -> None:
    """UPSERT into pending_notifications keyed on (user, schedule) where
    delivered_at IS NULL — see migration 002 for the partial unique index."""
    await pool().execute(
        """
        INSERT INTO pending_notifications (user_id, schedule_id, payload_json)
        VALUES ($1, $2, $3::jsonb)
        ON CONFLICT (user_id, schedule_id) WHERE delivered_at IS NULL
        DO UPDATE SET
            payload_json = EXCLUDED.payload_json,
            fired_at     = NOW()
        """,
        user_id,
        schedule_id,
        json.dumps(payload),
    )


async def peek_pending(user_id: int) -> list[dict[str, Any]]:
    """Read undelivered items without marking — used to decide whether the
    chat handler needs to draw a prefix message before answering."""
    rows = await pool().fetch(
        """
        SELECT pn.id, pn.schedule_id, pn.payload_json, pn.fired_at,
               sp.original_phrasing, sp.tool_name
          FROM pending_notifications pn
          JOIN scheduled_pushes sp ON sp.id = pn.schedule_id
         WHERE pn.user_id = $1 AND pn.delivered_at IS NULL
         ORDER BY pn.fired_at ASC
        """,
        user_id,
    )
    return [_row_to_dict(r) for r in rows]


async def mark_delivered(notification_ids: list[int]) -> None:
    if not notification_ids:
        return
    await pool().execute(
        "UPDATE pending_notifications SET delivered_at = NOW() WHERE id = ANY($1::bigint[])",
        notification_ids,
    )


def _row_to_dict(row: Any) -> dict[str, Any]:
    d = dict(row)
    raw = d.get("payload_json")
    if isinstance(raw, str):
        try:
            d["payload_json"] = json.loads(raw)
        except json.JSONDecodeError:
            d["payload_json"] = {}
    elif raw is None:
        d["payload_json"] = {}
    return d
