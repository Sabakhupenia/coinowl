"""CoinOwl Telegram bot.

v0.1.0 surface: /start, /help, /version commands + plain echo for any other
text. v1 replaces the echo with LLM-routed text or chart replies.
"""

from __future__ import annotations

import asyncio

from telethon import TelegramClient, events

from coinowl import __version__
from coinowl.core.config import Settings, load_settings
from coinowl.core.logging import get_logger

log = get_logger(__name__)


_START_TEXT = (
    "🦉 Hi! I'm CoinOwl — a crypto analytics bot.\n"
    "\n"
    "Right now I'm in early-access mode. Soon I'll answer crypto questions "
    "inline or send you charts directly in chat.\n"
    "\n"
    "Type /help to see what I can do today."
)

_HELP_TEXT = (
    f"🦉 CoinOwl v{__version__}\n"
    "\n"
    "Early-access mode — chart and analysis features land soon.\n"
    "\n"
    "Commands:\n"
    "  /start — greet\n"
    "  /help — show this message\n"
    "  /version — show bot version\n"
    "\n"
    "Send any other message and I'll echo it back for now."
)

_VERSION_TEXT = f"🦉 CoinOwl v{__version__}"


def _build_client(settings: Settings) -> TelegramClient:
    return TelegramClient(
        session="coinowl_bot",
        api_id=settings.telegram_api_id,
        api_hash=settings.telegram_api_hash,
    )


def _is_not_command(event: events.NewMessage.Event) -> bool:
    # Lets the echo handler ignore /start, /help, /version, and any unknown
    # slash-commands so it doesn't double-reply alongside the command handlers.
    return not (event.raw_text or "").startswith("/")


async def _amain() -> None:
    settings = load_settings()
    client = _build_client(settings)

    @client.on(events.NewMessage(pattern=r"^/start(?:\s|$|@)"))
    async def start(event: events.NewMessage.Event) -> None:
        await event.reply(_START_TEXT)

    @client.on(events.NewMessage(pattern=r"^/help(?:\s|$|@)"))
    async def help_(event: events.NewMessage.Event) -> None:
        await event.reply(_HELP_TEXT)

    @client.on(events.NewMessage(pattern=r"^/version(?:\s|$|@)"))
    async def version(event: events.NewMessage.Event) -> None:
        await event.reply(_VERSION_TEXT)

    @client.on(events.NewMessage(func=_is_not_command))
    async def echo(event: events.NewMessage.Event) -> None:
        text = event.raw_text or ""
        log.info("echo from %s: %r", event.sender_id, text)
        await event.reply(f"🦉 echo: {text}")

    await client.start(bot_token=settings.telegram_bot_token)
    log.info("CoinOwl bot is up. Send it a message on Telegram.")
    await client.run_until_disconnected()


def run() -> None:
    asyncio.run(_amain())
