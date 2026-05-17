"""One-time helper: generate a Telethon StringSession for stateless deploys.

Run locally once after setting TELEGRAM_API_ID / TELEGRAM_API_HASH /
TELEGRAM_BOT_TOKEN in your .env. Copy the printed string into Railway's
(or Fly's, Heroku's, etc.) env var TELEGRAM_SESSION_STRING.

    python scripts/dump_session.py

Treat the output like a password — anyone with it can act as your bot.
Never commit it; never print it in CI logs.
"""

from __future__ import annotations

import asyncio
import os
import sys

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession


async def _main() -> None:
    load_dotenv()
    try:
        api_id = int(os.environ["TELEGRAM_API_ID"])
        api_hash = os.environ["TELEGRAM_API_HASH"]
        bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    except KeyError as exc:
        sys.exit(
            f"Missing required env var {exc.args[0]!r}. "
            f"Set it in .env (or your shell) before running this script."
        )

    # NOT using `async with TelegramClient(...) as client:` — that form calls
    # client.start() with no args first, which triggers the interactive
    # "please enter your phone" prompt before we get a chance to pass
    # bot_token. Explicit connect+disconnect avoids that.
    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.start(bot_token=bot_token)
    try:
        s = client.session.save()
        print()
        print("=" * 70)
        print("Copy the line below into TELEGRAM_SESSION_STRING on your host:")
        print("=" * 70)
        print(s)
        print("=" * 70)
        print()
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(_main())
