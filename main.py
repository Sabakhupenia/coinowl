"""Entry point: `python main.py` runs the Telegram bot."""

from dotenv import load_dotenv

from coinowl.bot.main import run

if __name__ == "__main__":
    load_dotenv()
    run()
