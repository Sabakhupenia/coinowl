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
import re

from telethon import TelegramClient, events

from coinowl import __version__
from coinowl.agent import Agent, AgentResult
from coinowl.core.config import Settings, load_settings
from coinowl.core.logging import get_logger
from coinowl.core.quota import QuotaTracker
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
    "  /price <symbol> — quick spot price (e.g. /price BTC)\n"
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
    "Usage: /price <symbol>\n"
    "Example: /price BTC\n"
    "\n"
    "Known tickers: " + ", ".join(SYMBOLS.keys()) + "\n"
    "(or pass any CoinGecko coin ID directly, e.g. 'the-open-network')\n"
    "\n"
    "Tip: you can also just ask me in plain English — \"what's BTC at?\""
)


def _build_client(settings: Settings) -> TelegramClient:
    return TelegramClient(
        session="coinowl_bot",
        api_id=settings.telegram_api_id,
        api_hash=settings.telegram_api_hash,
    )


_IDENTITY_RE = re.compile(
    r"\b(what (can|do) you do|who are you|what are you|how (do|can) (i|you) use)\b",
    re.IGNORECASE,
)

_YES_RE = re.compile(
    r"^\s*(yes|sure|ok|okay|yep|yeah|please|go ahead|კი|да|ок)\s*[!.,?]*\s*$",
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


def _is_not_command(event: events.NewMessage.Event) -> bool:
    # Slash-commands have dedicated handlers; everything else goes to the LLM.
    return not (event.raw_text or "").startswith("/")


async def _amain() -> None:
    settings = load_settings()
    client = _build_client(settings)

    async with CoinGeckoClient(api_key=settings.coingecko_api_key) as cg:
        agent = Agent(
            gemini_api_key=settings.gemini_api_key,
            gemini_model=settings.gemini_model,
            anthropic_api_key=settings.anthropic_api_key,
            coingecko=cg,
        )
        quota = QuotaTracker()
        follow_up_store: dict[int, dict] = {}

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
                    f"I don't recognize {arg!r}. Try a known ticker (see /price) "
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
                f"🦉 {arg.upper()}  ${value:,.2f}\n"
                f"\n"
                f"{ATTRIBUTION}"
            )

        @client.on(events.NewMessage(func=_is_not_command))
        async def chat(event: events.NewMessage.Event) -> None:
            text = (event.raw_text or "").strip()
            if not text:
                return  # ignore stickers / empty / media-only messages
            log.info("chat from {}: {!r}", event.sender_id, text)
            if _IDENTITY_RE.search(text):
                await event.reply(_HELP_TEXT)
                return
            allowed, remaining = quota.check_and_consume(event.sender_id)
            if not allowed:
                await event.reply(
                    "You've used all 10 questions for this 3-hour window. "
                    "Come back later!"
                )
                return
            # Expand short affirmations ("yes", "კი", "да") to the last follow-up query
            uid = event.sender_id
            if _YES_RE.match(text) and uid in follow_up_store:
                text = _expand_follow_up(follow_up_store.pop(uid))
                log.info("expanded follow-up for {}: {!r}", uid, text)
            async with client.action(event.chat_id, "typing"):
                result: AgentResult = await agent.reply(text)
            # Update follow-up context for the next "yes"
            if result.chart_context:
                follow_up_store[uid] = result.chart_context
            else:
                follow_up_store.pop(uid, None)
            reply_text = result.text
            if remaining <= 3:
                reply_text += f"\n\n_({remaining} question{'s' if remaining != 1 else ''} remaining in this 3-hour window)_"
            if result.chart_png:
                import io
                await client.send_file(
                    event.chat_id,
                    io.BytesIO(result.chart_png),
                    caption=reply_text,
                    reply_to=event.id,
                    force_document=False,
                )
            else:
                await event.reply(reply_text)

        await client.start(bot_token=settings.telegram_bot_token)
        log.info("CoinOwl bot is up. Send it a message on Telegram.")
        await client.run_until_disconnected()


def run() -> None:
    asyncio.run(_amain())
