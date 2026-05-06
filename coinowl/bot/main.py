"""Telethon echo bot — v0 sanity check that the Telegram pipe is wired.

Replaced in v1 by handlers that route messages through the LLM agent.
"""

from __future__ import annotations

import asyncio

from telethon import TelegramClient, events

from coinowl.core.config import Settings, load_settings
from coinowl.core.logging import get_logger

log = get_logger(__name__)


def _build_client(settings: Settings) -> TelegramClient:
    return TelegramClient(
        session="coinowl_bot",
        api_id=settings.telegram_api_id,
        api_hash=settings.telegram_api_hash,
    )


async def _amain() -> None:
    settings = load_settings()
    client = _build_client(settings)

    @client.on(events.NewMessage)
    async def echo(event: events.NewMessage.Event) -> None:
        text = event.raw_text or ""
        log.info("echo from %s: %r", event.sender_id, text)
        await event.reply(f"🦉 echo: {text}")

    await client.start(bot_token=settings.telegram_bot_token)
    log.info("CoinOwl bot is up. Send it a message on Telegram.")
    await client.run_until_disconnected()


def run() -> None:
    asyncio.run(_amain())
