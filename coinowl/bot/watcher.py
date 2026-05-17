"""Background watcher for v0.7.3 alerts and scheduled pushes.

One asyncio task started at bot startup. Every WATCHER_TICK_SECONDS it:
  - Fetches all active price alerts, hits CoinGecko once per unique coin,
    fires personality-wrapped pushes for any threshold crosses, marks the
    alert as fired (and disables non-recurring alerts).
  - Walks active scheduled_pushes, evaluates each cron_expr, and UPSERTs into
    pending_notifications for the schedules whose next_fire ≤ now. The
    queue's partial-unique-index collapses repeated fires for the same
    schedule while the user is offline.

The watcher does NOT actually run scheduled tools — execution is deferred
until the user next messages the bot. `drain_pending_for_user()` does that,
called from the chat handler before any LLM reply.
"""

from __future__ import annotations

import asyncio
import io
from datetime import datetime, timezone
from typing import Any

from croniter import croniter
from telethon import TelegramClient

from coinowl.agent.main import execute_tool
from coinowl.agent.personality import PersonalityWrapper
from coinowl.core.logging import get_logger
from coinowl.data.coingecko import CoinGeckoClient, CoinGeckoError
from coinowl.db import alerts as db_alerts
from coinowl.db import notifications as db_notifs
from coinowl.db import schedules as db_sched

log = get_logger(__name__)

WATCHER_TICK_SECONDS = 30
# Recurring alerts respect a cooldown so a price hovering above the threshold
# doesn't ping the user every tick. For v0.7.3 a fixed cooldown is enough;
# proper state-transition semantics is a future refinement.
RECURRING_ALERT_COOLDOWN_SECONDS = 3600


class BackgroundWatcher:
    def __init__(
        self,
        *,
        client: TelegramClient,
        cg: CoinGeckoClient,
        personality: PersonalityWrapper,
    ) -> None:
        self._client = client
        self._cg = cg
        self._personality = personality

    async def run_forever(self) -> None:
        log.info("background watcher started (tick={}s)", WATCHER_TICK_SECONDS)
        while True:
            try:
                await self._tick()
            except asyncio.CancelledError:
                log.info("background watcher cancelled")
                raise
            except Exception as exc:  # noqa: BLE001 — watcher must not die
                log.warning("watcher tick failed: {}", exc)
            await asyncio.sleep(WATCHER_TICK_SECONDS)

    async def _tick(self) -> None:
        await self._tick_alerts()
        await self._tick_schedules()

    async def _tick_alerts(self) -> None:
        alerts = await db_alerts.all_active_alerts()
        if not alerts:
            return
        coin_ids = {a["coin_id"] for a in alerts}
        prices: dict[str, float] = {}
        for cid in coin_ids:
            try:
                prices[cid] = await self._cg.get_price(cid)
            except CoinGeckoError as exc:
                log.warning("watcher price fetch {} failed: {}", cid, exc)
        now = datetime.now(timezone.utc)
        for alert in alerts:
            price = prices.get(alert["coin_id"])
            if price is None:
                continue
            threshold = float(alert["threshold"])
            direction = alert["direction"]
            crossed = (
                (direction == "above" and price >= threshold)
                or (direction == "below" and price <= threshold)
            )
            if not crossed:
                continue
            if alert["recurring"] and alert["last_fired_at"] is not None:
                age = (now - alert["last_fired_at"]).total_seconds()
                if age < RECURRING_ALERT_COOLDOWN_SECONDS:
                    continue
            await self._fire_alert(alert, current_price=price)

    async def _fire_alert(self, alert: dict[str, Any], *, current_price: float) -> None:
        try:
            opener = await self._personality.compose_alert_opener(
                original_phrasing=alert["original_phrasing"],
                symbol=alert["symbol"],
                direction=alert["direction"],
                threshold=float(alert["threshold"]),
                current_price=current_price,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("alert personality wrap failed: {}", exc)
            opener = PersonalityWrapper._fallback_alert(
                symbol=alert["symbol"], direction=alert["direction"]
            )
        emoji = "📈" if alert["direction"] == "above" else "📉"
        body = (
            f"{opener}\n"
            f"\n"
            f"{emoji} {alert['symbol']}: ${current_price:,.2f}\n"
            f"(your watch was: {alert['direction']} ${float(alert['threshold']):,.2f})\n"
            f"\n"
            f"Data: CoinGecko (https://www.coingecko.com)"
        )
        try:
            await self._client.send_message(alert["user_id"], body, parse_mode=None)
        except Exception as exc:  # noqa: BLE001
            log.warning("alert push failed for user {}: {}", alert["user_id"], exc)
            return
        try:
            await db_alerts.mark_alert_fired(alert["id"])
        except Exception as exc:  # noqa: BLE001
            log.warning("mark_alert_fired failed for {}: {}", alert["id"], exc)
        log.info(
            "fired alert {} for user {} ({} {} ${:,.2f}, now ${:,.2f})",
            alert["id"], alert["user_id"],
            alert["symbol"], alert["direction"], float(alert["threshold"]),
            current_price,
        )

    async def _tick_schedules(self) -> None:
        schedules = await db_sched.all_active_schedules()
        if not schedules:
            return
        now = datetime.now(timezone.utc)
        for sched in schedules:
            anchor = sched["last_fired_at"] or sched["created_at"]
            try:
                next_fire = croniter(sched["cron_expr"], anchor).get_next(datetime)
            except Exception as exc:  # noqa: BLE001
                log.warning("bad cron on schedule {}: {}", sched["id"], exc)
                continue
            if next_fire > now:
                continue
            mode = sched.get("delivery_mode") or "push"
            if mode == "push":
                await self._fire_schedule_push(sched)
            else:
                await self._enqueue_schedule_deferred(sched, now=now)

    async def _fire_schedule_push(self, sched: dict[str, Any]) -> None:
        """Real-time-push delivery: re-execute tool, personality-wrap, send."""
        side_effects: dict[str, Any] = {}
        try:
            result = await execute_tool(
                sched["tool_name"],
                dict(sched["tool_args_json"] or {}),
                self._cg,
                side_effects,
                uid=sched["user_id"],
            )
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "schedule {} tool exec failed: {}", sched["id"], exc
            )
            return
        try:
            opener = await self._personality.compose_schedule_opener(
                original_phrasing=sched["original_phrasing"],
                tool_name=sched["tool_name"],
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("schedule personality wrap failed: {}", exc)
            opener = "🦉 Your scheduled summary is ready."
        body_block = _format_scheduled_result(
            sched["tool_name"], result, sched["original_phrasing"]
        )
        text = f"{opener}\n\n{body_block}\n\nData: CoinGecko (https://www.coingecko.com)"
        try:
            await self._client.send_message(sched["user_id"], text, parse_mode=None)
        except Exception as exc:  # noqa: BLE001
            log.warning("schedule push failed for user {}: {}", sched["user_id"], exc)
            return
        for png_key, name_key in (
            ("chart_png", "chart_filename"),
            ("sparkline_png", "sparkline_filename"),
            ("summary_stack_png", "summary_stack_filename"),
            ("summary_comparison_png", "summary_comparison_filename"),
        ):
            data = side_effects.get(png_key)
            if data:
                bio = io.BytesIO(data)
                bio.name = side_effects.get(name_key) or f"{png_key}.png"
                try:
                    await self._client.send_file(sched["user_id"], bio, force_document=False)
                except Exception as exc:  # noqa: BLE001
                    log.warning("schedule png send failed ({}): {}", name_key, exc)
        for html_key, name_key in (
            ("chart_html", "chart_html_filename"),
            ("summary_stack_html", "summary_stack_html_filename"),
            ("summary_comparison_html", "summary_comparison_html_filename"),
        ):
            data = side_effects.get(html_key)
            if data:
                bio = io.BytesIO(data)
                bio.name = side_effects.get(name_key) or f"{html_key}.html"
                try:
                    await self._client.send_file(sched["user_id"], bio, force_document=True)
                except Exception as exc:  # noqa: BLE001
                    log.warning("schedule html send failed ({}): {}", name_key, exc)
        try:
            await db_sched.mark_schedule_fired(sched["id"])
        except Exception as exc:  # noqa: BLE001
            log.warning("mark_schedule_fired failed for {}: {}", sched["id"], exc)
        log.info(
            "pushed schedule {} for user {} (tool={})",
            sched["id"], sched["user_id"], sched["tool_name"],
        )

    async def _enqueue_schedule_deferred(
        self, sched: dict[str, Any], *, now: datetime
    ) -> None:
        try:
            await db_notifs.enqueue(
                user_id=sched["user_id"],
                schedule_id=sched["id"],
                payload={
                    "fired_at": now.isoformat(),
                    "tool_name": sched["tool_name"],
                    "tool_args": sched["tool_args_json"],
                },
            )
            await db_sched.mark_schedule_fired(sched["id"])
            log.info(
                "enqueued (deferred) schedule {} for user {} (tool={})",
                sched["id"], sched["user_id"], sched["tool_name"],
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("schedule enqueue failed for {}: {}", sched["id"], exc)


# ---------------------------------------------------------------------------
# Drain side — invoked from the chat handler before the LLM reply, so any
# scheduled summaries that fired while the user was offline get delivered as
# a single coherent prefix message ("welcome back, here's what was waiting").
# ---------------------------------------------------------------------------


async def drain_pending_for_user(
    *,
    client: TelegramClient,
    cg: CoinGeckoClient,
    personality: PersonalityWrapper,
    uid: int,
    chat_id: int,
) -> bool:
    """Drain any undelivered scheduled pushes for this user.

    Returns True if anything was delivered (caller may want to add a beat
    before sending the actual reply for visual clarity).
    """
    pending = await db_notifs.peek_pending(uid)
    if not pending:
        return False

    items_for_opener = [
        {
            "original_phrasing": p["original_phrasing"],
            "tool_name": p["tool_name"],
            "fired_at": p["fired_at"].isoformat() if p.get("fired_at") else None,
        }
        for p in pending
    ]
    try:
        opener = await personality.compose_batch_opener(items_for_opener)
    except Exception as exc:  # noqa: BLE001
        log.warning("batch opener failed for user {}: {}", uid, exc)
        opener = PersonalityWrapper._fallback_batch(len(pending))

    text_parts: list[str] = [opener, ""]
    files_to_send: list[tuple[bytes, str, bool]] = []  # (bytes, filename, force_document)

    for p in pending:
        side_effects: dict[str, Any] = {}
        try:
            result = await execute_tool(
                p["tool_name"],
                dict(p["payload_json"].get("tool_args") or {}),
                cg,
                side_effects,
                uid=uid,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("drain re-execute {} failed: {}", p["tool_name"], exc)
            text_parts.append(f"— (couldn't run {p['tool_name']} just now; will retry)")
            continue

        text_parts.append(
            _format_scheduled_result(p["tool_name"], result, p["original_phrasing"])
        )

        for png_key, name_key in (
            ("chart_png", "chart_filename"),
            ("sparkline_png", "sparkline_filename"),
            ("summary_stack_png", "summary_stack_filename"),
            ("summary_comparison_png", "summary_comparison_filename"),
        ):
            data = side_effects.get(png_key)
            if data:
                files_to_send.append((data, side_effects.get(name_key) or f"{png_key}.png", False))
        for html_key, name_key in (
            ("chart_html", "chart_html_filename"),
            ("summary_stack_html", "summary_stack_html_filename"),
            ("summary_comparison_html", "summary_comparison_html_filename"),
        ):
            data = side_effects.get(html_key)
            if data:
                files_to_send.append((data, side_effects.get(name_key) or f"{html_key}.html", True))

    text_parts.append("")
    text_parts.append("Data: CoinGecko (https://www.coingecko.com)")
    prefix_text = "\n".join(text_parts).strip()

    try:
        await client.send_message(chat_id, prefix_text, parse_mode=None)
    except Exception as exc:  # noqa: BLE001
        log.warning("prefix send failed for user {}: {}", uid, exc)
        return False
    for data, name, force_doc in files_to_send:
        bio = io.BytesIO(data)
        bio.name = name
        try:
            await client.send_file(chat_id, bio, force_document=force_doc)
        except Exception as exc:  # noqa: BLE001
            log.warning("prefix file send failed ({}): {}", name, exc)

    try:
        await db_notifs.mark_delivered([p["id"] for p in pending])
    except Exception as exc:  # noqa: BLE001
        log.warning("mark_delivered failed for user {}: {}", uid, exc)
    log.info("drained {} pending pushes for user {}", len(pending), uid)
    return True


def _format_scheduled_result(tool_name: str, result: dict[str, Any], original_phrasing: str) -> str:
    """Render a tool's result dict as a plain-text block for prefix delivery.

    Charts are attached separately (not in this string) — this is just the
    stats/numbers that accompany them.
    """
    if "error" in result:
        return f"— (you wanted: \"{original_phrasing}\" — the tool errored: {result['error']})"

    if tool_name == "get_price":
        return f"📊 {result['symbol']}: ${result['price_usd']:,.4f}"

    if tool_name == "get_market_chart":
        pct = result["change_pct"]
        arrow = "📈" if pct >= 0 else "📉"
        return (
            f"📊 {result['symbol']} over {result['days']}d: "
            f"${result['first_price_usd']:,.4f} → ${result['last_price_usd']:,.4f} "
            f"{arrow} {pct:+.2f}%"
        )

    if tool_name in ("get_chart", "get_chart_html"):
        pct = result.get("change_pct")
        arrow = "📈" if (pct is not None and pct >= 0) else "📉"
        bits = [f"📊 {result['symbol']} {result['days']}d chart"]
        if pct is not None:
            bits.append(f"{arrow} {pct:+.2f}%")
        return " ".join(bits)

    if tool_name == "get_top_movers":
        head = (
            f"📊 Top {result['direction']} ({result['window']}):"
        )
        lines = [head]
        for i, m in enumerate(result.get("movers", []), 1):
            lines.append(
                f"  {i}. {m['symbol']}: ${m['price_usd']:,.4f} ({m['change_pct']:+.2f}%)"
            )
        return "\n".join(lines)

    if tool_name == "get_market_summary":
        lines = [f"📊 Watchlist ({result['window']}):"]
        for c in result.get("coins", []):
            if "error" in c:
                lines.append(f"  • {c['symbol']}: (no data)")
                continue
            arrow = "📈" if c["change_pct"] >= 0 else "📉"
            lines.append(
                f"  • {c['symbol']}: ${c['price_usd']:,.4f} {arrow} {c['change_pct']:+.2f}%"
            )
        return "\n".join(lines)

    return f"— {tool_name} fired (no formatter available)"
