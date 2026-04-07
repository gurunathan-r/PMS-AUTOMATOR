"""
Telegram bot: sends daily reminders and handles log submission via Playwright.
Supports encrypted credential storage and step-by-step log collection.
"""

import logging
import os
from telegram import Update, Bot, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_IDS, REMINDER_TIME, auth_state_path
from automator import submit_daily_log
from auth_flow import login_start, login_submit_email, login_submit_password, login_submit_code, login_save_session, login_abort
from credentials import save_credentials, load_credentials, credentials_exist, clear_credentials

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Conversation states ──────────────────────────────────────────────────────
WAITING_EMAIL, WAITING_PASSWORD = range(2)
LOG_ACTIVITIES, LOG_HOURS, LOG_LOCATION, LOG_DESCRIPTION, LOG_CONFIRM = range(4, 9)
LOGIN_EMAIL, LOGIN_PASSWORD, LOGIN_MFA = range(10, 13)


def is_authorized(update: Update) -> bool:
    return update.effective_chat.id in TELEGRAM_CHAT_IDS


# ── General commands ─────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    chat_id = update.effective_chat.id
    creds_status = "Credentials saved" if credentials_exist(chat_id) else "No credentials — use /setcredentials"
    session_status = "Active" if os.path.exists(auth_state_path(chat_id)) else "None — use /login"
    await update.message.reply_text(
        "PMS Daily Log Bot\n\n"
        f"Session : {session_status}\n"
        f"Credentials: {creds_status}\n\n"
        "Commands:\n"
        "/login           — Authenticate via Microsoft (no credentials stored)\n"
        "/submitlog       — Fill and submit today's log\n"
        "/setcredentials  — (Optional) Save login for full automation\n"
        "/status          — Check session and credential status\n"
        "/help            — Show this message"
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    await update.message.reply_text(
        "Commands:\n"
        "/login            — Authenticate via Microsoft (opens browser, no creds stored)\n"
        "/submitlog        — Fill and submit today's log\n"
        "/setcredentials   — (Optional) Save Microsoft credentials for full automation\n"
        "/clearcredentials — Delete stored credentials\n"
        "/status           — Check session and credential status\n"
        "/cancel           — Cancel current operation\n"
        "/help             — Show this message"
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    import os
    from config import auth_state_path
    chat_id = update.effective_chat.id
    creds = load_credentials(chat_id)
    session_exists = os.path.exists(auth_state_path(chat_id))
    lines = []
    if creds:
        lines.append(f"Credentials: saved ({creds['email']})")
    else:
        lines.append("Credentials: not set — use /setcredentials")
    lines.append(
        "Session: active (cached)" if session_exists
        else "Session: none — will auto-login on next /submitlog"
    )
    await update.message.reply_text("\n".join(lines))


# ── Microsoft login conversation (screenshot relay) ───────────────────────────

async def cmd_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return ConversationHandler.END
    await update.message.reply_text("Enter your Microsoft email address:")
    return LOGIN_EMAIL


async def login_received_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return ConversationHandler.END
    if not update.message or not update.message.text:
        return LOGIN_EMAIL
    chat_id = update.effective_chat.id
    await update.message.reply_text("Please wait...")
    try:
        await login_start(chat_id)
        await login_submit_email(chat_id, update.message.text.strip())
    except Exception as e:
        await update.message.reply_text(f"Error: {e}\nUse /login to try again.")
        await login_abort(chat_id)
        return ConversationHandler.END
    await update.message.reply_text(
        "Enter your Microsoft password:\n(Your message will be deleted immediately)"
    )
    return LOGIN_PASSWORD


async def login_received_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return ConversationHandler.END
    if not update.message or not update.message.text:
        return LOGIN_PASSWORD
    chat_id = update.effective_chat.id
    password = update.message.text.strip()
    try:
        await update.message.delete()
    except Exception:
        logger.warning("Could not delete password message.")
    await update.effective_chat.send_message("Signing in...")
    try:
        _, logged_in = await login_submit_password(chat_id, password)
    except Exception as e:
        await update.effective_chat.send_message(f"Error: {e}\nUse /login to try again.")
        await login_abort(chat_id)
        return ConversationHandler.END
    if logged_in:
        await login_save_session(chat_id)
        await update.effective_chat.send_message("Logged in! You can now use /submitlog.")
        return ConversationHandler.END
    await update.effective_chat.send_message(
        "Additional verification required.\n\n"
        "If prompted for a code, send it here.\n"
        "If using an authenticator app, approve it then send /done."
    )
    return LOGIN_MFA


async def login_received_mfa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return ConversationHandler.END
    if not update.message or not update.message.text:
        return LOGIN_MFA
    chat_id = update.effective_chat.id
    try:
        _, logged_in = await login_submit_code(chat_id, update.message.text.strip())
    except Exception as e:
        await update.message.reply_text(f"Error: {e}\nUse /login to try again.")
        await login_abort(chat_id)
        return ConversationHandler.END
    if logged_in:
        await login_save_session(chat_id)
        await update.message.reply_text("Logged in! You can now use /submitlog.")
        return ConversationHandler.END
    await update.message.reply_text("Send the code or /done once approved on your authenticator.")
    return LOGIN_MFA


async def login_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return ConversationHandler.END
    saved = await login_save_session(update.effective_chat.id)
    if saved:
        await update.message.reply_text("Logged in! You can now use /submitlog.")
        return ConversationHandler.END
    await update.message.reply_text("Not on PMS yet. Approve on your authenticator then try /done again.")
    return LOGIN_MFA


async def login_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return ConversationHandler.END
    await login_abort(update.effective_chat.id)
    await update.message.reply_text("Login cancelled.")
    return ConversationHandler.END


# ── Log submission conversation ───────────────────────────────────────────────

async def cmd_submitlog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return ConversationHandler.END
    chat_id = update.effective_chat.id

    # Check for an active session — if none, ask user to /login first
    has_session = os.path.exists(auth_state_path(chat_id))
    has_creds = credentials_exist(chat_id)
    if not has_session and not has_creds:
        await update.message.reply_text(
            "No active session found.\n\n"
            "Use /login to authenticate with Microsoft first.\n"
            "A browser will open on this machine — log in and come back."
        )
        return ConversationHandler.END

    context.user_data.clear()
    await update.message.reply_text(
        "Let's fill your daily log. You can /cancel at any time.\n\n"
        "Step 1/4 — Activities done:\n"
        "What activities did you do today?"
    )
    return LOG_ACTIVITIES


async def log_received_activities(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return ConversationHandler.END
    if not update.message or not update.message.text:
        return LOG_ACTIVITIES
    context.user_data["activities"] = update.message.text.strip()
    await update.message.reply_text(
        "Step 2/4 — Time spent:\n"
        "How many hours did you spend? (whole number, e.g. 3)"
    )
    return LOG_HOURS


async def log_received_hours(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return ConversationHandler.END
    if not update.message or not update.message.text:
        return LOG_HOURS
    hours = update.message.text.strip()
    if not hours.isdigit() or int(hours) < 1 or int(hours) > 24:
        await update.message.reply_text("Please enter a valid whole number of hours (1-24):")
        return LOG_HOURS
    context.user_data["hours"] = hours
    location_keyboard = ReplyKeyboardMarkup(
        [["iQube", "Home/Hostel", "Other"]],
        one_time_keyboard=True,
        resize_keyboard=True,
    )
    await update.message.reply_text(
        "Step 3/4 — Location:\nWhere did you work from?",
        reply_markup=location_keyboard,
    )
    return LOG_LOCATION


# Map user input to the exact select option values on the PMS form
LOCATION_MAP = {
    "iqube":        "iQube",
    "home/hostel":  "Home/Hostel",
    "home":         "Home/Hostel",
    "hostel":       "Home/Hostel",
    "other":        "Other",
}

async def log_received_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return ConversationHandler.END
    if not update.message or not update.message.text:
        return LOG_LOCATION
    raw = update.message.text.strip().lower()
    location_value = LOCATION_MAP.get(raw)
    if not location_value:
        location_keyboard = ReplyKeyboardMarkup(
            [["iQube", "Home/Hostel", "Other"]],
            one_time_keyboard=True,
            resize_keyboard=True,
        )
        await update.message.reply_text(
            "Please choose a valid location:",
            reply_markup=location_keyboard,
        )
        return LOG_LOCATION
    context.user_data["location"] = location_value
    await update.message.reply_text(
        "Step 4/4 — Description:\n"
        "Give a brief description of your work today:",
        reply_markup=ReplyKeyboardRemove(),
    )
    return LOG_DESCRIPTION


async def log_received_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return ConversationHandler.END
    if not update.message or not update.message.text:
        return LOG_DESCRIPTION

    context.user_data["description"] = update.message.text.strip()
    data = context.user_data

    # Validate all keys are present
    required = ["activities", "hours", "location", "description"]
    missing = [k for k in required if not data.get(k)]
    if missing:
        await update.message.reply_text(
            f"Something went wrong (missing: {', '.join(missing)}). Please start over with /submitlog"
        )
        context.user_data.clear()
        return ConversationHandler.END

    summary = (
        "Here's what I'll submit:\n\n"
        f"Activities : {data['activities']}\n"
        f"Hours      : {data['hours']}\n"
        f"Location   : {data['location'].capitalize()}\n"
        f"Description: {data['description']}"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Submit", callback_data="log_submit"),
            InlineKeyboardButton("Cancel", callback_data="log_cancel"),
        ]
    ])
    await update.message.reply_text(summary, reply_markup=keyboard)
    return LOG_CONFIRM


async def log_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "log_cancel":
        await query.edit_message_text("Cancelled. Log not submitted.")
        context.user_data.clear()
        return ConversationHandler.END

    # User pressed Submit
    data = context.user_data
    await query.edit_message_text(query.message.text + "\n\nSubmitting now...")

    try:
        result = await submit_daily_log(
            chat_id=query.message.chat_id,
            activities=data["activities"],
            hours=data["hours"],
            location=data["location"],
            description=data["description"],
        )
    except Exception as e:
        logger.exception("submit_daily_log raised an exception")
        await query.edit_message_text(query.message.text + f"\n\n[FAIL] Unexpected error: {e}")
        context.user_data.clear()
        return ConversationHandler.END

    status = "OK" if result["success"] else "FAIL"
    await query.edit_message_text(query.message.text + f"\n\n[{status}] {result['message']}")
    context.user_data.clear()
    return ConversationHandler.END


async def log_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return ConversationHandler.END
    context.user_data.clear()
    await update.message.reply_text("Log submission cancelled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


# ── Credential setup conversation ─────────────────────────────────────────────

async def cmd_setcredentials(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return ConversationHandler.END
    chat_id = update.effective_chat.id
    if credentials_exist(chat_id):
        creds = load_credentials(chat_id)
        await update.message.reply_text(
            f"Credentials already saved for: {creds['email']}\n\n"
            "Send your new Microsoft email to update, or /cancel to keep existing."
        )
    else:
        await update.message.reply_text(
            "Let's save your Microsoft login credentials.\n"
            "They'll be encrypted and stored locally.\n\n"
            "Send your Microsoft email address:"
        )
    return WAITING_EMAIL


async def received_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return ConversationHandler.END
    email = update.message.text.strip()
    if "@" not in email:
        await update.message.reply_text("That doesn't look like a valid email. Try again:")
        return WAITING_EMAIL
    context.user_data["pending_email"] = email
    await update.message.reply_text(
        f"Got it: {email}\n\n"
        "Now send your Microsoft password.\n"
        "I'll delete your message immediately after saving."
    )
    return WAITING_PASSWORD


async def received_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return ConversationHandler.END
    password = update.message.text.strip()
    try:
        await update.message.delete()
    except Exception:
        logger.warning("Could not delete password message — delete it manually.")
    email = context.user_data.pop("pending_email", None)
    if not email:
        await update.message.reply_text("Something went wrong. Try /setcredentials again.")
        return ConversationHandler.END
    save_credentials(update.effective_chat.id, email, password)
    logger.info(f"Credentials saved for {email} (chat {update.effective_chat.id})")
    await update.effective_chat.send_message(
        f"Credentials saved and encrypted.\nEmail: {email}\n\n"
        "Run python setup_auth.py to save your browser session."
    )
    return ConversationHandler.END


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return ConversationHandler.END
    context.user_data.clear()
    await update.message.reply_text("Cancelled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


async def cmd_clearcredentials(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    chat_id = update.effective_chat.id
    if not credentials_exist(chat_id):
        await update.message.reply_text("No credentials stored.")
        return
    clear_credentials(chat_id)
    await update.message.reply_text("Credentials deleted.")


# ── Scheduler ─────────────────────────────────────────────────────────────────

async def send_daily_reminder(bot: Bot):
    for chat_id in TELEGRAM_CHAT_IDS:
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    "Daily log reminder!\n\n"
                    "Use /submitlog to fill and submit today's log."
                )
            )
        except Exception as e:
            logger.warning(f"Could not send reminder to {chat_id}: {e}")
    logger.info(f"Daily reminder sent to {len(TELEGRAM_CHAT_IDS)} chat(s).")


# ── Global error handler ──────────────────────────────────────────────────────

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Unhandled exception:", exc_info=context.error)


# ── App builder ───────────────────────────────────────────────────────────────

def build_app() -> Application:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Log submission conversation
    log_conv = ConversationHandler(
        entry_points=[CommandHandler("submitlog", cmd_submitlog)],
        states={
            LOG_ACTIVITIES:  [MessageHandler(filters.TEXT & ~filters.COMMAND, log_received_activities)],
            LOG_HOURS:       [MessageHandler(filters.TEXT & ~filters.COMMAND, log_received_hours)],
            LOG_LOCATION:    [MessageHandler(filters.TEXT & ~filters.COMMAND, log_received_location)],
            LOG_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, log_received_description)],
            LOG_CONFIRM:     [CallbackQueryHandler(log_confirm, pattern="^log_(submit|cancel)$")],
        },
        fallbacks=[CommandHandler("cancel", log_cancel)],
    )

    # Credential setup conversation
    creds_conv = ConversationHandler(
        entry_points=[CommandHandler("setcredentials", cmd_setcredentials)],
        states={
            WAITING_EMAIL:    [MessageHandler(filters.TEXT & ~filters.COMMAND, received_email)],
            WAITING_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_password)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
    )

    # Microsoft login conversation
    login_conv = ConversationHandler(
        entry_points=[CommandHandler("login", cmd_login)],
        states={
            LOGIN_EMAIL:    [MessageHandler(filters.TEXT & ~filters.COMMAND, login_received_email)],
            LOGIN_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, login_received_password)],
            LOGIN_MFA:      [
                MessageHandler(filters.TEXT & ~filters.COMMAND, login_received_mfa),
                CommandHandler("done", login_done),
            ],
        },
        fallbacks=[CommandHandler("cancel", login_cancel)],
    )

    app.add_handler(login_conv)
    app.add_handler(log_conv)
    app.add_handler(creds_conv)
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("clearcredentials", cmd_clearcredentials))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_error_handler(error_handler)

    return app


def start_scheduler(app: Application) -> AsyncIOScheduler:
    hour, minute = map(int, REMINDER_TIME.split(":"))
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        send_daily_reminder,
        trigger="cron",
        hour=hour,
        minute=minute,
        args=[app.bot],
    )
    scheduler.start()
    logger.info(f"Reminder scheduled at {REMINDER_TIME} every day.")
    return scheduler
