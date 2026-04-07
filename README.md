# PMS Daily Log Automator

A Telegram bot that automates daily log submission to [iQube PMS](https://iqube.therig.in). The bot collects your log details via Telegram, logs in to the PMS on your behalf using Playwright, fills the form, and submits it.

## Features

- Daily reminder at a configured time
- Step-by-step log collection via Telegram
- Microsoft Azure AD login (credentials encrypted at rest)
- Per-user isolated sessions and credentials (multiple users supported)
- No screenshots — fully text-based interaction

## Requirements

- Python 3.9+
- A Telegram bot token (from [@BotFather](https://t.me/BotFather))
- Your Telegram chat ID (from [@userinfobot](https://t.me/userinfobot))

## Setup

### 1. Clone the repo

```bash
git clone <repo-url>
cd PMS-AUTOMATOR
```

### 2. Configure environment

```bash
cp .env.example .env
nano .env
```

Fill in:

```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=123456789              # comma-separate for multiple users
REMINDER_TIME=18:00                     # 24-hour format
```

### 3. Run

```bash
chmod +x run.sh
./run.sh
```

The script will:
- Create a virtual environment
- Install dependencies
- Install Playwright's Chromium browser
- Validate your `.env`
- Start the bot

## Bot Commands

| Command | Description |
|---|---|
| `/start` | Show status and available commands |
| `/login` | Authenticate with Microsoft (opens login flow) |
| `/submitlog` | Fill and submit today's daily log |
| `/setcredentials` | (Optional) Save Microsoft credentials for auto-login |
| `/clearcredentials` | Delete stored credentials |
| `/status` | Check session and credential status |
| `/cancel` | Cancel the current operation |
| `/help` | Show command list |

## Usage

### First time

1. Start the bot: `./run.sh`
2. Open Telegram and send `/login`
3. Enter your Microsoft email and password when prompted
4. Your password is deleted from Telegram immediately after use
5. Session is saved — you're ready to submit logs

### Submitting a log

Send `/submitlog` and follow the prompts:

1. **Activities done** — what you worked on
2. **Time spent** — whole number of hours (1–24)
3. **Location** — iQube / Home/Hostel / Other
4. **Description** — brief summary of your work

Review the summary and press **Submit**.

### Multiple users

Add multiple chat IDs comma-separated in `.env`:

```env
TELEGRAM_CHAT_ID=111111111,222222222,333333333
```

Each user has their own isolated credentials and session.

### Session expiry

Sessions expire after inactivity or when you log out of the PMS in your browser. If a submission fails with a session error, run `/login` again.

### Auto-login (optional)

To enable fully automated login without manual `/login` each time:

```
/setcredentials
```

Credentials are encrypted using Fernet (AES-128) and stored in `credentials/{chat_id}.enc`. The encryption key lives in `.secret.key`. Both are gitignored.

## Project Structure

```
PMS-AUTOMATOR/
├── main.py          # Entry point
├── bot.py           # Telegram bot handlers and conversations
├── automator.py     # Playwright form-filling and submission
├── auth_flow.py     # Microsoft login relay (headless browser)
├── credentials.py   # Encrypted per-user credential storage
├── config.py        # Environment config and URL constants
├── setup_auth.py    # Manual browser session setup (legacy)
├── run.sh           # Automated setup and launch script
├── requirements.txt
├── .env.example
└── .gitignore
```

## Security

- Credentials are encrypted with Fernet (AES-128-CBC + HMAC-SHA256)
- Passwords sent via Telegram are deleted immediately
- Sessions and credentials are stored per-user and gitignored
- Nothing sensitive is logged or committed
