"""Telegram-based admin panel for the bot operator.

Gated by `Settings.admin_user_id` — only the single configured Telegram user_id
can invoke `/admin`. Friends opening the bot for testing will never see this
surface even if they type the command. Nothing here is destructive without an
explicit subcommand the admin types.

Subcommands:
  /admin                          — show usage
  /admin users [N]                — top N users by last_seen (default 10)
  /admin info <user_id>           — detailed stats for one user
  /admin setlimit <user_id> <N>   — set quota_override (overrides default 10)
  /admin unsetlimit <user_id>     — clear override (back to default)
  /admin clearquota <user_id>     — wipe quota_log rows for a user (free messages)
"""

from __future__ import annotations

import html as _html
from typing import Any

from coinowl.core.logging import get_logger
from coinowl.db import quota as db_quota
from coinowl.db.pool import pool

log = get_logger(__name__)


_USAGE = (
    "🦉 <b>Admin panel</b>\n"
    "\n"
    "<code>/admin users [N]</code> — list top N users by last_seen (default 10)\n"
    "<code>/admin info &lt;user_id&gt;</code> — detailed stats for one user\n"
    "<code>/admin setlimit &lt;user_id&gt; &lt;N&gt;</code> — override their 3h quota cap\n"
    "<code>/admin unsetlimit &lt;user_id&gt;</code> — clear the override\n"
    "<code>/admin clearquota &lt;user_id&gt;</code> — wipe their quota_log (free messages)"
)


def _esc(s: Any) -> str:
    return _html.escape(str(s) if s is not None else "", quote=False)


async def handle_admin_command(raw_args: str) -> str:
    """Parse and dispatch a `/admin ...` invocation. Returns HTML reply text."""
    parts = raw_args.strip().split()
    if not parts:
        return _USAGE
    sub = parts[0].lower()
    rest = parts[1:]
    if sub in ("users", "list"):
        return await _users_list(rest)
    if sub == "info":
        return await _user_info(rest)
    if sub == "setlimit":
        return await _set_limit(rest)
    if sub == "unsetlimit":
        return await _unset_limit(rest)
    if sub in ("clearquota", "reset"):
        return await _clear_quota(rest)
    return f"Unknown subcommand: <code>{_esc(sub)}</code>\n\n{_USAGE}"


async def _users_list(args: list[str]) -> str:
    try:
        n = int(args[0]) if args else 10
    except ValueError:
        return "Usage: <code>/admin users [N]</code> — N must be an integer."
    n = max(1, min(n, 50))
    rows = await pool().fetch(
        """
        SELECT u.user_id,
               u.telegram_username,
               u.display_name,
               u.preferred_languages,
               u.timezone,
               u.watched_coins,
               u.onboarded,
               u.quota_override,
               u.last_seen_at,
               u.created_at,
               COALESCE(
                 (SELECT COUNT(*) FROM messages m WHERE m.user_id = u.user_id),
                 0
               ) AS msg_count,
               COALESCE(
                 (SELECT COUNT(*) FROM quota_log q
                   WHERE q.user_id = u.user_id
                     AND q.ts > NOW() - INTERVAL '3 hours'),
                 0
               ) AS in_window
          FROM users u
         ORDER BY u.last_seen_at DESC NULLS LAST
         LIMIT $1
        """,
        n,
    )
    if not rows:
        return "No users in the database."
    lines = [f"🦉 <b>Top {len(rows)} users by last_seen</b>"]
    for i, r in enumerate(rows, 1):
        uname = f"@{r['telegram_username']}" if r["telegram_username"] else "(no username)"
        name = r["display_name"] or "—"
        cap = r["quota_override"] if r["quota_override"] is not None else db_quota.DEFAULT_LIMIT
        cap_marker = " <b>(override)</b>" if r["quota_override"] is not None else ""
        seen = r["last_seen_at"].strftime("%Y-%m-%d %H:%M") if r["last_seen_at"] else "never"
        onb = "✓" if r["onboarded"] else "✗"
        lines.append(
            f"\n<b>{i}. {_esc(name)}</b> {_esc(uname)}\n"
            f"   <code>{_esc(r['user_id'])}</code> · seen {_esc(seen)} UTC · onb {onb}\n"
            f"   msgs total {r['msg_count']}, this 3h: {r['in_window']}/{cap}{cap_marker}"
        )
    return "\n".join(lines)


async def _user_info(args: list[str]) -> str:
    if not args:
        return "Usage: <code>/admin info &lt;user_id&gt;</code>"
    try:
        uid = int(args[0])
    except ValueError:
        return "user_id must be an integer."
    row = await pool().fetchrow(
        "SELECT * FROM users WHERE user_id = $1", uid
    )
    if row is None:
        return f"No user with id <code>{uid}</code>."
    in_window = await db_quota.usage_in_window(uid)
    msg_count = await pool().fetchval(
        "SELECT COUNT(*) FROM messages WHERE user_id = $1", uid
    )
    alert_count = await pool().fetchval(
        "SELECT COUNT(*) FROM alerts WHERE user_id = $1 AND enabled = TRUE", uid
    )
    sched_count = await pool().fetchval(
        "SELECT COUNT(*) FROM scheduled_pushes WHERE user_id = $1 AND enabled = TRUE", uid
    )
    cap = row["quota_override"] if row["quota_override"] is not None else db_quota.DEFAULT_LIMIT
    cap_marker = " (override)" if row["quota_override"] is not None else " (default)"
    uname = f"@{row['telegram_username']}" if row["telegram_username"] else "(no username)"
    langs = ", ".join(row["preferred_languages"] or []) or "—"
    coins = ", ".join(row["watched_coins"] or []) or "—"
    return (
        f"🦉 <b>User {_esc(row['display_name'] or '—')} {_esc(uname)}</b>\n"
        f"<code>{_esc(uid)}</code>\n"
        f"\n"
        f"Languages: {_esc(langs)}\n"
        f"Timezone:  {_esc(row['timezone'])}\n"
        f"Watchlist: {_esc(coins)}\n"
        f"Onboarded: {'✓' if row['onboarded'] else '✗'}\n"
        f"\n"
        f"Quota cap: <b>{cap}{cap_marker}</b> per 3-hour window\n"
        f"Used in current window: {in_window}\n"
        f"Total messages: {msg_count}\n"
        f"\n"
        f"Active alerts: {alert_count}\n"
        f"Active schedules: {sched_count}\n"
        f"\n"
        f"Joined: {row['created_at'].strftime('%Y-%m-%d %H:%M')} UTC\n"
        f"Last seen: {row['last_seen_at'].strftime('%Y-%m-%d %H:%M')} UTC"
    )


async def _set_limit(args: list[str]) -> str:
    if len(args) < 2:
        return "Usage: <code>/admin setlimit &lt;user_id&gt; &lt;N&gt;</code>"
    try:
        uid = int(args[0])
        n = int(args[1])
    except ValueError:
        return "Both arguments must be integers."
    if n < 0 or n > 10_000:
        return "Limit must be between 0 and 10000."
    ok = await db_quota.set_quota_override(uid, n)
    if not ok:
        return f"No user with id <code>{uid}</code>."
    return (
        f"✅ Set quota override for <code>{uid}</code> to <b>{n}</b> "
        f"messages per 3-hour window."
    )


async def _unset_limit(args: list[str]) -> str:
    if not args:
        return "Usage: <code>/admin unsetlimit &lt;user_id&gt;</code>"
    try:
        uid = int(args[0])
    except ValueError:
        return "user_id must be an integer."
    ok = await db_quota.set_quota_override(uid, None)
    if not ok:
        return f"No user with id <code>{uid}</code>."
    return (
        f"✅ Cleared override for <code>{uid}</code> — back to default "
        f"({db_quota.DEFAULT_LIMIT}/3h)."
    )


async def _clear_quota(args: list[str]) -> str:
    if not args:
        return "Usage: <code>/admin clearquota &lt;user_id&gt;</code>"
    try:
        uid = int(args[0])
    except ValueError:
        return "user_id must be an integer."
    removed = await db_quota.clear_quota(uid)
    return f"✅ Removed {removed} quota_log row(s) for <code>{uid}</code>."
