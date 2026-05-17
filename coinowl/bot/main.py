"""CoinOwl Telegram bot.

v0.3.1 surface:
  /start, /help, /version, /disclaimer — informational
  /price <symbol>                       — current spot price via CoinGecko
  (any other text)                      — routed to the LLM agent
                                          (Gemini Flash → Claude Haiku 4.5 fallback)
  identity questions ("what can you do") — answered locally, no API call
"""

from __future__ import annotations

import asyncio
import html as _html
import io
import re
import time
from typing import Any


def _esc(s: str) -> str:
    return _html.escape(s or "", quote=False)

import secrets
import time as _time

from telethon import Button, TelegramClient, events
from telethon.errors import MessageNotModifiedError
from telethon.sessions import StringSession

from coinowl import __version__
from coinowl.agent import Agent, AgentResult
from coinowl.agent.main import wants_chart
from coinowl.agent.personality import PersonalityWrapper
from coinowl.bot.admin import handle_admin_command
from coinowl.bot.watcher import BackgroundWatcher, drain_pending_for_user
from coinowl.core.config import Settings, load_settings
from coinowl.core.logging import get_logger
from coinowl.db import close_db, init_db
from coinowl.db import quota as db_quota
from coinowl.db import users as db_users
from coinowl.db.messages import _init_embedding_client, log_message, recent_messages
from coinowl.data.coingecko import (
    ATTRIBUTION,
    CoinGeckoClient,
    CoinGeckoError,
    CoinGeckoNetworkError,
    CoinGeckoRateLimitError,
    CoinGeckoUnknownCoinError,
)
from coinowl.data.symbols import SYMBOLS, resolve

log = get_logger(__name__)


_START_TEXT = (
    "🦉 Hi! I'm CoinOwl — a crypto analytics bot.\n"
    "\n"
    "Just ask me anything about crypto in plain English (or Georgian, or Russian) — "
    "I'll fetch the real numbers and reply. Examples:\n"
    "  • what's BTC at?\n"
    "  • how did ETH do this week?\n"
    "  • compare SOL and BNB over the last month\n"
    "\n"
    "⚠️ I show stats, not predictions. I'm not a financial advisor and nothing "
    "I say is investment advice. See /disclaimer for the full notice.\n"
    "\n"
    "Fair-use limit: 10 questions per 3-hour window.\n"
    "\n"
    "Type /help for the command list."
)

_HELP_TEXT = (
    f"🦉 CoinOwl v{__version__}\n"
    "\n"
    "Just ask me anything about crypto — I understand plain English, Georgian, "
    "Russian, and other languages. I'll call live data and reply.\n"
    "\n"
    "⚠️ Stats only, not financial advice. See /disclaimer.\n"
    "\n"
    "Commands:\n"
    "  /start — greet\n"
    "  /help — show this message\n"
    "  /version — show bot version\n"
    "  /price &lt;symbol&gt; — quick spot price (e.g. /price BTC)\n"
    "  /disclaimer — read the full 'not financial advice' notice"
)

_VERSION_TEXT = f"🦉 CoinOwl v{__version__}"

_DISCLAIMER_TEXT = (
    "⚠️ Not financial advice\n"
    "\n"
    "CoinOwl provides statistics, historical data, and charts only. "
    "It does NOT provide:\n"
    "  • Price predictions or forecasts\n"
    "  • Buy, sell, or hold recommendations\n"
    "  • Investment, trading, or financial advice\n"
    "\n"
    "CoinOwl is not a financial advisor and is not licensed to give one. "
    "Cryptocurrency markets are highly volatile and you can lose money. "
    "Any trading or investment decisions are your own — do your own research "
    "and, if you're putting meaningful money on the line, consult a licensed "
    "financial advisor.\n"
    "\n"
    "CoinOwl is a tool for analysis. The analysis is on you."
)

_PRICE_USAGE_TEXT = (
    "Usage: /price &lt;symbol&gt;\n"
    "Example: /price BTC\n"
    "\n"
    "Known tickers: " + ", ".join(SYMBOLS.keys()) + "\n"
    "(or pass any CoinGecko coin ID directly, e.g. 'the-open-network')\n"
    "\n"
    "Tip: you can also just ask me in plain English — \"what's BTC at?\""
)


def _build_client(settings: Settings) -> TelegramClient:
    # When TELEGRAM_SESSION_STRING is set (Railway / stateless deploys), hydrate
    # auth from the env var so we don't depend on a *.session file surviving
    # container restarts. Local dev falls back to the named SQLite file session.
    session: Any
    if settings.telegram_session_string:
        session = StringSession(settings.telegram_session_string)
        log.info("Using TELEGRAM_SESSION_STRING for Telethon auth (stateless mode)")
    else:
        session = "coinowl_bot"
    return TelegramClient(
        session=session,
        api_id=settings.telegram_api_id,
        api_hash=settings.telegram_api_hash,
    )


_IDENTITY_RE = re.compile(
    r"\b(what (can|do) you do|who are you|what are you|how (do|can) (i|you) use)\b",
    re.IGNORECASE,
)

_YES_RE = re.compile(
    r"^\s*(yes|sure|ok|okay|yep|yeah|please|go ahead"
    r"|კი|კარგი|კარგია"
    r"|да|ок|хорошо|давай)\s*[!.,?]*\s*$",
    re.IGNORECASE,
)

_FOLLOW_UP_PERIODS = {
    1: "in the last 24 hours",
    7: "this week",
    30: "this month",
    90: "in the last 3 months",
}


def _expand_follow_up(ctx: dict) -> str:
    period = _FOLLOW_UP_PERIODS.get(ctx["days"], f"over the last {ctx['days']} days")
    return f"how did {ctx['symbol']} do {period}?"


_APOLOGY_RE = re.compile(
    r"\b(sorry|apologi[sz]e|failed|can'?t|couldn'?t|trouble|please try again|"
    r"ბოდიში|შემიძლია|უკაცრავად|"
    r"извини|простите|не получилось|не смог)\b",
    re.IGNORECASE,
)


def _looks_like_apology(last_reply: str) -> bool:
    return bool(_APOLOGY_RE.search(last_reply))


def _yes_preamble(last_offer: str) -> str:
    return (
        f"Earlier you replied: \"{last_offer}\"\n"
        "The user has now answered: \"yes\". "
        "Fulfill the offer you made (call a tool if needed). "
        "If you offered an HTML chart, call get_chart_html."
    )


_TOOL_STATUS = {
    "get_price": "🔎 Looking up {symbol} price...",
    "get_market_chart": "📊 Fetching {symbol} {days}d history...",
    "get_chart": "🎨 Rendering {symbol} chart...",
    "get_chart_html": "🎨 Building interactive HTML...",
}


def _tool_status(name: str, args: dict[str, Any]) -> str:
    template = _TOOL_STATUS.get(name)
    if template is None:
        return f"⚙️ {name}..."
    symbol = str(args.get("symbol", "")).upper() or "…"
    days = args.get("days", "")
    return template.format(symbol=symbol, days=days)


class StreamingReply:
    """Progressive Telegram reply: send placeholder, edit while bot is working.

    Telegram throttles message edits to roughly 1/sec per message; this class
    debounces edits via a single pending task so we never exceed that.
    """

    _PLACEHOLDER = "🦉 ..."
    _MIN_INTERVAL = 1.0

    def __init__(self, event: events.NewMessage.Event, client: TelegramClient) -> None:
        self._event = event
        self._client = client
        self._msg: Any = None
        self._current_display = ""
        self._last_edit_ts = 0.0
        self._pending_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._buffer = ""
        self._status = ""
        self._finalized = False

    async def start(self) -> None:
        self._msg = await self._event.reply(self._PLACEHOLDER)
        self._current_display = self._PLACEHOLDER
        self._last_edit_ts = time.monotonic()

    async def on_progress(self, ev: dict[str, Any]) -> None:
        t = ev.get("type")
        if t == "tool_call_start":
            self._status = _tool_status(ev.get("tool", ""), ev.get("args") or {})
            await self._schedule_edit()
        elif t == "tool_call_done":
            # keep the status line until text starts arriving; nothing to do
            pass
        elif t == "text_delta":
            delta = ev.get("delta", "")
            if delta:
                self._buffer += delta
                self._status = ""  # text now takes precedence over status
                await self._schedule_edit()

    def _render(self) -> str:
        # Bot is in HTML parse mode; LLM-streamed and tool-derived strings must
        # be escaped. `finalize()` receives already-formatted text from callers
        # and is exempt from re-escaping.
        if self._buffer:
            return _esc(self._buffer)
        if self._status:
            return _esc(self._status)
        return self._PLACEHOLDER

    async def _edit_now(self) -> None:
        if self._msg is None or self._finalized:
            return
        text = self._render()
        if text == self._current_display:
            return
        try:
            await self._msg.edit(text)
            self._current_display = text
            self._last_edit_ts = time.monotonic()
        except MessageNotModifiedError:
            self._current_display = text
        except Exception as exc:  # noqa: BLE001 — never let edit failures break the turn
            log.warning("streaming edit failed: {}", exc)

    async def _schedule_edit(self) -> None:
        async with self._lock:
            wait = self._last_edit_ts + self._MIN_INTERVAL - time.monotonic()
            if wait <= 0:
                if self._pending_task and not self._pending_task.done():
                    self._pending_task.cancel()
                    self._pending_task = None
                await self._edit_now()
                return
            if self._pending_task and not self._pending_task.done():
                return
            self._pending_task = asyncio.create_task(self._delayed_edit(wait))

    async def _delayed_edit(self, wait: float) -> None:
        try:
            await asyncio.sleep(wait)
            await self._edit_now()
        except asyncio.CancelledError:
            return

    async def finalize(self, text: str) -> None:
        self._finalized = True
        if self._pending_task and not self._pending_task.done():
            self._pending_task.cancel()
        if self._msg is None:
            return
        if text:
            if text != self._current_display:
                try:
                    await self._msg.edit(text)
                except MessageNotModifiedError:
                    pass
                except Exception as exc:  # noqa: BLE001
                    log.warning("streaming finalize edit failed: {}", exc)
        else:
            try:
                await self._msg.delete()
            except Exception as exc:  # noqa: BLE001
                log.warning("streaming placeholder delete failed: {}", exc)


def _is_not_command(event: events.NewMessage.Event) -> bool:
    # Slash-commands have dedicated handlers; everything else goes to the LLM.
    return not (event.raw_text or "").startswith("/")


def _recent_conversation_block(turns: list[dict]) -> str | None:
    """Format the user's last N chat turns (newest-last) as system context.

    Returned in chronological order so the LLM reads them as a conversation
    flowing forward. The current user message isn't logged yet so it won't
    appear here — only prior turns.
    """
    if not turns:
        return None
    # turns come newest-first from DAO; flip to chronological
    ordered = list(reversed(turns))
    lines = ["## RECENT CONVERSATION (oldest → newest)"]
    for t in ordered:
        role = t["role"]
        # Trim each line so we don't blow the system-prompt budget on a long reply
        body = (t["content"] or "").strip().replace("\n", " ")
        if len(body) > 400:
            body = body[:400] + "…"
        lines.append(f"- {role}: {body}")
    return "\n".join(lines)


def _user_context_block(db_user: dict, *, remaining: int) -> str | None:
    if not db_user.get("onboarded") or not db_user.get("display_name"):
        return None
    langs = ", ".join(db_user.get("preferred_languages") or ["en"])
    watched = db_user.get("watched_coins") or []
    timezone = db_user.get("timezone") or "Asia/Tbilisi"
    parts = [
        "## CURRENT USER",
        f"Name: {db_user['display_name']}",
        f"Preferred languages: {langs}",
        f"Timezone: {timezone}",
        f"Quota: {remaining} of 10 messages remaining in the current 3-hour rolling window.",
    ]
    if watched:
        parts.append(f"Watchlist: {', '.join(watched)}")
    if remaining == 0:
        parts.append(
            "THIS IS THE USER'S LAST MESSAGE in the current window. Do NOT add a "
            "follow-up offer (no 'shall I check anything else?', no 'want me to look "
            "at X too?'). Deliver a complete answer and stop."
        )
    parts.append(
        "Address them by name naturally — sprinkle it in once or twice, not every sentence."
    )
    return "\n".join(parts)


def _onboarding_wrap(
    original_text: str,
    *,
    prior_user_messages: list[str] | None = None,
    last_bot_reply: str | None = None,
) -> str:
    history_block = ""
    if prior_user_messages and len(prior_user_messages) > 1:
        # all except the current message
        earlier = prior_user_messages[:-1]
        history_block += (
            "\n\nPREVIOUS USER MESSAGES DURING THIS ONBOARDING:\n"
            + "\n".join(f'- "{m}"' for m in earlier)
        )
    if last_bot_reply:
        history_block += f"\n\nYOUR PREVIOUS REPLY: \"{last_bot_reply}\""
    return (
        "<onboarding>\n"
        f"This user is being onboarded. Their latest message: \"{original_text}\"."
        f"{history_block}\n"
        "\n"
        "Your task: collect THREE pieces of info before doing anything else —\n"
        "  (1) preferred display name to call them by\n"
        "  (2) at least one language they want the bot to use (en, ka, ru, …)\n"
        "  (3) which crypto coins they want on their watchlist (uppercase tickers "
        "like BTC, ETH, SOL — up to 10)\n"
        "\n"
        "PROGRESS TRACKING — IMPORTANT:\n"
        "Read the conversation above. If the user has ALREADY given their name, "
        "language(s), or coin list in any earlier message, REMEMBER those values. "
        "Ask ONLY for whichever piece is still missing — do not re-ask for ones "
        "already provided. When reminding them about a missing field, lead with "
        "the ⚠️ emoji: \"⚠️ I still need your name — what should I call you?\" / "
        "\"⚠️ Which language(s) should I use?\" / \"⚠️ Which coins do you want to "
        "track? (e.g. BTC, ETH, SOL — up to 10).\"\n"
        "\n"
        "LANGUAGE RULE — STRICT: write your reply ENTIRELY in the language of "
        "the latest message above. If it's in Georgian (ქართული alphabet, e.g. "
        "\"ჰი\", \"გამარჯობა\"), reply WHOLLY in Georgian — every sentence. Same "
        "for Russian (Cyrillic). Do NOT mix English explanations into a "
        "non-English reply. Only technical tokens like 'BTC', 'ETH' stay as-is.\n"
        "\n"
        "When you have ALL THREE (name, at least one language, at least one coin), "
        "call set_user_profile(name=..., languages=[...], coins=[...]) and confirm "
        "warmly. In that same confirmation reply, ALSO briefly mention:\n"
        "  • the 10-message / 3-hour-window quota\n"
        "  • that they can chat naturally about crypto (this bot is AI-chat-first),\n"
        "    and that /help, /disclaimer, /price, /version commands exist for "
        "    users who prefer them.\n"
        "Until ALL THREE are collected, do NOT call set_user_profile and do NOT "
        "call any other tools.\n"
        "</onboarding>"
    )


async def _amain() -> None:
    settings = load_settings()
    await init_db(settings.database_url)
    _init_embedding_client(settings.gemini_api_key)
    client = _build_client(settings)
    client.parse_mode = "html"

    async with CoinGeckoClient(api_key=settings.coingecko_api_key) as cg:
        agent = Agent(
            gemini_api_key=settings.gemini_api_key,
            gemini_model=settings.gemini_model,
            openai_api_key=settings.openai_api_key,
            openai_model=settings.openai_model,
            anthropic_api_key=settings.anthropic_api_key,
            coingecko=cg,
        )
        personality = PersonalityWrapper(
            openai_api_key=settings.openai_api_key,
            gemini_api_key=settings.gemini_api_key,
            openai_model=settings.openai_model,
            gemini_model=settings.gemini_model,
        )
        watcher = BackgroundWatcher(client=client, cg=cg, personality=personality)
        follow_up_store: dict[int, dict] = {}
        last_reply_store: dict[int, str] = {}
        # Per-user list of user messages collected during onboarding. Cleared
        # once the user becomes onboarded. Lets the LLM remember partial info
        # across onboarding turns (e.g. user gave language but not name yet).
        onboarding_history: dict[int, list[str]] = {}
        # Staging area for proposed schedules awaiting the user's delivery-mode
        # tap. Cleared on bot restart (acceptable — users tap within seconds).
        # Each entry: {created_at, user_id, cron_expr, tool_name, tool_args,
        # original_phrasing}. 1h TTL prunes stale proposals.
        pending_schedules: dict[str, dict[str, Any]] = {}

        def _prune_pending_schedules() -> None:
            cutoff = _time.time() - 3600
            stale = [k for k, v in pending_schedules.items() if v["created_at"] < cutoff]
            for k in stale:
                pending_schedules.pop(k, None)

        @client.on(events.NewMessage(pattern=r"^/start(?:\s|$|@)"))
        async def start(event: events.NewMessage.Event) -> None:
            await event.reply(_START_TEXT)

        @client.on(events.NewMessage(pattern=r"^/help(?:\s|$|@)"))
        async def help_(event: events.NewMessage.Event) -> None:
            await event.reply(_HELP_TEXT)

        @client.on(events.NewMessage(pattern=r"^/version(?:\s|$|@)"))
        async def version(event: events.NewMessage.Event) -> None:
            await event.reply(_VERSION_TEXT)

        @client.on(events.NewMessage(pattern=r"^/disclaimer(?:\s|$|@)"))
        async def disclaimer(event: events.NewMessage.Event) -> None:
            await event.reply(_DISCLAIMER_TEXT)

        @client.on(events.NewMessage(pattern=r"^/admin(?:\s+(.*))?$"))
        async def admin(event: events.NewMessage.Event) -> None:
            # Silently ignore for non-admins — friends won't even discover the
            # surface exists. If admin_user_id is unset (env var not provided),
            # /admin is fully disabled.
            if settings.admin_user_id is None or event.sender_id != settings.admin_user_id:
                return
            raw = event.pattern_match.group(1) or ""
            try:
                reply = await handle_admin_command(raw)
            except Exception as exc:  # noqa: BLE001
                log.exception("admin command failed: {}", exc)
                reply = f"⚠️ Admin command errored: {_esc(str(exc))}"
            await event.reply(reply)

        @client.on(events.CallbackQuery(pattern=rb"^sched:"))
        async def schedule_mode_callback(event: events.CallbackQuery.Event) -> None:
            try:
                _, mode_short, token = event.data.decode().split(":", 2)
            except (UnicodeDecodeError, ValueError):
                await event.answer("Invalid button.", alert=False)
                return
            mode = {"push": "push", "def": "deferred"}.get(mode_short)
            if mode is None:
                await event.answer("Invalid button.", alert=False)
                return
            params = pending_schedules.pop(token, None)
            if params is None:
                await event.answer("This proposal expired. Ask again.", alert=True)
                try:
                    await event.edit("⏳ (proposal expired — message me the schedule again)")
                except Exception:  # noqa: BLE001
                    pass
                return
            if params["user_id"] != event.sender_id:
                await event.answer("Not yours.", alert=True)
                return
            from coinowl.db import schedules as db_sched
            try:
                row = await db_sched.create_schedule(
                    user_id=params["user_id"],
                    cron_expr=params["cron_expr"],
                    tool_name=params["tool_name"],
                    tool_args=params["tool_args"],
                    original_phrasing=params["original_phrasing"],
                    delivery_mode=mode,
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("schedule create from button failed: {}", exc)
                await event.answer("Couldn't save — try again.", alert=True)
                return
            from croniter import croniter as _croniter
            from datetime import datetime as _dt, timezone as _tz
            try:
                next_fire = _croniter(row["cron_expr"], _dt.now(_tz.utc)).get_next(_dt)
                next_str = next_fire.strftime("%Y-%m-%d %H:%M UTC")
            except Exception:  # noqa: BLE001
                next_str = "(soon)"
            mode_label = "🔔 notification" if mode == "push" else "📋 history (next visit)"
            await event.answer("Saved.", alert=False)
            try:
                await event.edit(
                    f"✅ Scheduled as {mode_label}\n"
                    f"Next run: {next_str}",
                    buttons=None,
                    parse_mode=None,
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("schedule confirmation edit failed: {}", exc)
            log.info(
                "schedule {} created from button (user={}, mode={}, tool={})",
                row["id"], params["user_id"], mode, params["tool_name"],
            )

        @client.on(events.NewMessage(pattern=r"^/price(?:\s+(\S+))?(?:\s|$|@)"))
        async def price(event: events.NewMessage.Event) -> None:
            arg_match = event.pattern_match.group(1)
            arg = (arg_match or "").strip()
            if not arg:
                await event.reply(_PRICE_USAGE_TEXT)
                return

            coin_id = resolve(arg)
            try:
                value = await cg.get_price(coin_id)
            except CoinGeckoUnknownCoinError:
                await event.reply(
                    f"I don't recognize {_esc(repr(arg))}. Try a known ticker (see /price) "
                    "or a full CoinGecko coin ID."
                )
                return
            except CoinGeckoRateLimitError:
                await event.reply(
                    "CoinGecko is rate-limiting me right now. Try again in a minute.\n"
                    "(If this happens often, set COINGECKO_API_KEY in .env — see README.)"
                )
                return
            except (CoinGeckoNetworkError, CoinGeckoError) as exc:
                log.warning("CoinGecko call failed for {}: {}", coin_id, exc)
                await event.reply("Couldn't reach CoinGecko just now. Try again in a moment.")
                return

            await event.reply(
                f"🦉 {_esc(arg.upper())}  ${value:,.2f}\n"
                f"\n"
                f"{_esc(ATTRIBUTION)}"
            )

        @client.on(events.NewMessage(func=_is_not_command))
        async def chat(event: events.NewMessage.Event) -> None:
            original_text = (event.raw_text or "").strip()
            if not original_text:
                return  # ignore stickers / empty / media-only messages
            log.info("chat from {}: {!r}", event.sender_id, original_text)
            if _IDENTITY_RE.search(original_text):
                await event.reply(_HELP_TEXT)
                return
            uid = event.sender_id
            sender = await event.get_sender()
            tg_username = getattr(sender, "username", None)
            db_user = await db_users.get_or_create_user(uid, tg_username)
            allowed, remaining = await db_quota.check_and_consume(uid)
            if not allowed:
                await event.reply(
                    "You've used all 10 questions for this 3-hour window. "
                    "Come back later!"
                )
                return
            # Drain any scheduled summaries that fired while the user was away.
            # Delivered as a prefix before the bot processes the actual message,
            # so the watcher never interrupts mid-conversation. Onboarding users
            # have no schedules yet — skip the round-trip.
            if db_user.get("onboarded"):
                try:
                    await drain_pending_for_user(
                        client=client,
                        cg=cg,
                        personality=personality,
                        uid=uid,
                        chat_id=event.chat_id,
                    )
                except Exception as exc:  # noqa: BLE001
                    log.warning("drain_pending_for_user failed for {}: {}", uid, exc)
            text = original_text
            # Expand short affirmations ("yes", "კი", "да") — but ONLY for
            # already-onboarded users. During onboarding, "კარგი" might be a
            # courtesy or a yes; the wrap below gives the LLM enough context
            # to decide. Stacking yes-preamble + onboarding wrap is incoherent.
            if db_user.get("onboarded") and _YES_RE.match(text):
                # Hydrate last_reply_store from DB if the in-memory cache was
                # wiped (bot restart). Otherwise the user's "yes" loses all
                # context after every restart.
                if uid not in last_reply_store:
                    try:
                        recent = await recent_messages(uid, limit=4)
                        last_assistant = next(
                            (m for m in recent if m["role"] == "assistant"),
                            None,
                        )
                        if last_assistant:
                            last_reply_store[uid] = last_assistant["content"]
                            log.info("hydrated last_reply_store for {} from DB", uid)
                    except Exception as exc:  # noqa: BLE001
                        log.warning("last_reply hydrate failed: {}", exc)
                last_offer = last_reply_store.get(uid, "")
                # Skip yes-handling if the last reply was an apology/failure
                # message — a courteous "yes/კარგი/да" acknowledges, doesn't
                # request retry. Otherwise we loop on transient failures.
                if last_offer and _looks_like_apology(last_offer):
                    log.info("skipped yes-expand for {}: last reply was apology", uid)
                elif last_offer and wants_chart(last_offer):
                    follow_up_store.pop(uid, None)
                    text = _yes_preamble(last_offer)
                    log.info("expanded yes via last_reply (chart intent) for {}", uid)
                elif uid in follow_up_store:
                    text = _expand_follow_up(follow_up_store.pop(uid))
                    log.info("expanded follow-up for {}: {!r}", uid, text)
                elif last_offer:
                    text = _yes_preamble(last_offer)
                    log.info("expanded yes via last_reply for {}", uid)
            # Onboarding wrap for new users (until they've supplied name+language).
            # We feed the LLM the full onboarding history so it can track which
            # piece(s) the user has already provided and ask only for what's missing.
            if not db_user.get("onboarded"):
                onboarding_history.setdefault(uid, []).append(original_text)
                text = _onboarding_wrap(
                    original_text,
                    prior_user_messages=onboarding_history[uid],
                    last_bot_reply=last_reply_store.get(uid),
                )
                user_context = None
            else:
                onboarding_history.pop(uid, None)  # cleanup if user is already onboarded
                # Fetch the last 6 chat turns from DB and prepend as system context.
                # Cheap (no embedding); the LLM gets recent conversation memory for
                # free, surviving bot restart. For older recall, the LLM can call
                # the recall_past_conversations tool which uses vector search.
                try:
                    recent = await recent_messages(uid, limit=6)
                except Exception as exc:  # noqa: BLE001
                    log.warning("recent_messages fetch failed: {}", exc)
                    recent = []
                # If user long-pressed a prior message and tapped Reply, surface
                # the quoted text so the LLM knows what "this" / "that" refers to.
                reply_block: str | None = None
                if event.message and event.message.is_reply:
                    try:
                        quoted = await event.message.get_reply_message()
                        if quoted and (quoted.raw_text or "").strip():
                            qtext = quoted.raw_text.strip()
                            if len(qtext) > 1500:
                                qtext = qtext[:1500] + "…"
                            reply_block = (
                                "## REPLYING TO\n"
                                "The user used Telegram's Reply feature to quote "
                                "this earlier message. Treat 'this' / 'that' / "
                                "'translate this' references in the user's message "
                                "as pointing to the quoted text below:\n\n"
                                f"{qtext}"
                            )
                    except Exception as exc:  # noqa: BLE001
                        log.warning("reply-message fetch failed for {}: {}", uid, exc)
                blocks = [
                    block for block in (
                        reply_block,
                        _recent_conversation_block(recent),
                        _user_context_block(db_user, remaining=remaining),
                    )
                    if block
                ]
                user_context = "\n\n".join(blocks) if blocks else None
            streaming = StreamingReply(event, client)
            await streaming.start()
            result: AgentResult = await agent.reply(
                text,
                on_progress=streaming.on_progress,
                uid=uid,
                user_context=user_context,
                user_languages=db_user.get("preferred_languages"),
            )
            # Update follow-up context for the next "yes"
            if result.chart_context:
                follow_up_store[uid] = result.chart_context
            else:
                follow_up_store.pop(uid, None)
            last_reply_store[uid] = result.text
            reply_text = _esc(result.text)
            if remaining <= 3:
                reply_text += (
                    f"\n\n<blockquote>{remaining} question"
                    f"{'s' if remaining != 1 else ''} remaining in this 3-hour window"
                    f"</blockquote>"
                )
            if result.chart_png:
                await streaming.finalize("")
                bio = io.BytesIO(result.chart_png)
                bio.name = result.chart_filename or "chart.png"
                await client.send_file(
                    event.chat_id,
                    bio,
                    caption=reply_text,
                    reply_to=event.id,
                    force_document=False,
                )
            elif result.sparkline_png:
                await streaming.finalize("")
                bio = io.BytesIO(result.sparkline_png)
                bio.name = result.sparkline_filename or "spark.png"
                await client.send_file(
                    event.chat_id,
                    bio,
                    caption=reply_text,
                    reply_to=event.id,
                    force_document=False,
                )
            else:
                await streaming.finalize(reply_text)
            if result.chart_html:
                bio_html = io.BytesIO(result.chart_html)
                bio_html.name = result.chart_html_filename or "chart.html"
                await client.send_file(
                    event.chat_id,
                    bio_html,
                    reply_to=event.id,
                    force_document=True,
                )
            if result.summary_stack_png:
                bio_sum = io.BytesIO(result.summary_stack_png)
                bio_sum.name = result.summary_stack_filename or "summary_stack.png"
                await client.send_file(
                    event.chat_id,
                    bio_sum,
                    reply_to=event.id,
                    force_document=False,
                )
            if result.summary_comparison_png:
                bio_cmp = io.BytesIO(result.summary_comparison_png)
                bio_cmp.name = result.summary_comparison_filename or "summary_comparison.png"
                await client.send_file(
                    event.chat_id,
                    bio_cmp,
                    reply_to=event.id,
                    force_document=False,
                )
            if result.summary_stack_html:
                bio_stack_html = io.BytesIO(result.summary_stack_html)
                bio_stack_html.name = result.summary_stack_html_filename or "summary_stack.html"
                await client.send_file(
                    event.chat_id,
                    bio_stack_html,
                    reply_to=event.id,
                    force_document=True,
                )
            if result.summary_comparison_html:
                bio_cmp_html = io.BytesIO(result.summary_comparison_html)
                bio_cmp_html.name = result.summary_comparison_html_filename or "summary_comparison.html"
                await client.send_file(
                    event.chat_id,
                    bio_cmp_html,
                    reply_to=event.id,
                    force_document=True,
                )
            # If the agent staged a schedule proposal, surface inline buttons so
            # the user picks delivery mode with one tap. The schedule row isn't
            # written to DB until they click one.
            if result.schedule_proposal:
                _prune_pending_schedules()
                token = secrets.token_urlsafe(8)
                pending_schedules[token] = {
                    "created_at": _time.time(),
                    **result.schedule_proposal,
                }
                try:
                    await client.send_message(
                        event.chat_id,
                        "Pick how to deliver this:",
                        buttons=[
                            [Button.inline("🔔 Notify me when it fires", f"sched:push:{token}".encode())],
                            [Button.inline("📋 Save for next visit",       f"sched:def:{token}".encode())],
                        ],
                        reply_to=event.id,
                        parse_mode=None,
                    )
                except Exception as exc:  # noqa: BLE001
                    log.warning("failed to send schedule buttons: {}", exc)

            # Fire-and-forget message logging — never block the reply path
            asyncio.create_task(log_message(uid, "user", original_text))
            asyncio.create_task(log_message(
                uid, "assistant", result.text,
                llm_provider=result.provider_used,
                llm_model=result.model_used,
                tool_calls=result.tool_calls_made,
            ))

        await client.start(bot_token=settings.telegram_bot_token)
        log.info("CoinOwl bot is up. Send it a message on Telegram.")
        watcher_task = asyncio.create_task(watcher.run_forever())
        try:
            await client.run_until_disconnected()
        finally:
            watcher_task.cancel()
            try:
                await watcher_task
            except asyncio.CancelledError:
                pass
            except Exception as exc:  # noqa: BLE001
                log.warning("watcher shutdown raised: {}", exc)
            await close_db()


def run() -> None:
    asyncio.run(_amain())
