"""Entry point: `python main.py` runs the Telegram bot."""

from dotenv import load_dotenv

from coinowl.bot.main import run
from coinowl.core.logging import configure_logging

if __name__ == "__main__":
    load_dotenv()
    configure_logging()
    run()
