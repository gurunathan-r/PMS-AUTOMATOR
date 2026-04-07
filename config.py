import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_IDS = [
    int(cid.strip())
    for cid in os.getenv("TELEGRAM_CHAT_ID", "0").split(",")
    if cid.strip().lstrip("-").isdigit()
]
REMINDER_TIME = os.getenv("REMINDER_TIME", "18:00")

# iQube PMS URLs
BASE_URL       = "https://iqube.therig.in"
LOGIN_PAGE     = f"{BASE_URL}/me/"
AZURE_AUTH_URL = f"{BASE_URL}/login/azuread-oauth2/"
DAILY_LOG_URL  = f"{BASE_URL}/me/daily_log/create"
LOGOUT_URL     = f"{BASE_URL}/me/user/logout/"

AUTH_STATE_PATH = os.path.join(os.path.dirname(__file__), "auth_state.json")  # legacy, unused


def auth_state_path(chat_id: int) -> str:
    return os.path.join(os.path.dirname(__file__), f"auth_state_{chat_id}.json")
