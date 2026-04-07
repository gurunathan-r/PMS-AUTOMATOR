"""
Entry point: starts the Telegram bot and daily reminder scheduler.

Run: python main.py
"""

import logging
import os
from bot import build_app, start_scheduler
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_IDS, REMINDER_TIME, AUTH_STATE_PATH

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def check_config():
    errors = []
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "your_bot_token_here":
        errors.append("TELEGRAM_BOT_TOKEN not set in .env")
    if not TELEGRAM_CHAT_IDS:
        errors.append("TELEGRAM_CHAT_ID not set in .env")
    if errors:
        for e in errors:
            logger.error(e)
        raise SystemExit("Fix .env config and try again.")

    if not os.path.exists(AUTH_STATE_PATH):
        logger.warning(
            "auth_state.json not found. Run `python setup_auth.py` first to set up Microsoft login."
        )


def main():
    check_config()

    app = build_app()
    scheduler = start_scheduler(app)

    logger.info(f"Bot started. Reminder set for {REMINDER_TIME} daily.")
    logger.info("Send /start on Telegram to verify the bot is running.")

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
