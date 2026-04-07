#!/bin/bash

set -e

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$DIR/.venv"

log()  { echo -e "${CYAN}[PMS]${NC} $1"; }
ok()   { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
fail() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

cd "$DIR"

# ── 1. Python check ─────────────────────────────────────────────────────────
log "Checking Python..."
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    fail "Python not found. Install Python 3.10+ and try again."
fi

PYVER=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYMAJ=$($PYTHON -c "import sys; print(sys.version_info.major)")
PYMIN=$($PYTHON -c "import sys; print(sys.version_info.minor)")

if [ "$PYMAJ" -lt 3 ] || { [ "$PYMAJ" -eq 3 ] && [ "$PYMIN" -lt 9 ]; }; then
    fail "Python 3.9+ required. Found: $PYVER"
fi
ok "Python $PYVER"

# ── 2. Virtual environment ───────────────────────────────────────────────────
if [ ! -d "$VENV" ]; then
    log "Creating virtual environment..."
    $PYTHON -m venv "$VENV"
    ok "Virtual environment created at .venv"
else
    ok "Virtual environment exists"
fi

PYTHON="$VENV/bin/python"
PIP="$VENV/bin/pip"

# ── 3. Install dependencies ──────────────────────────────────────────────────
log "Installing dependencies..."
$PIP install --quiet --upgrade pip
$PIP install --quiet -r requirements.txt
ok "Dependencies installed"

# ── 4. Playwright browsers ───────────────────────────────────────────────────
log "Installing/verifying Playwright Chromium..."
"$VENV/bin/playwright" install chromium
ok "Playwright Chromium ready"

# ── 5. Environment config ────────────────────────────────────────────────────
if [ ! -f "$DIR/.env" ]; then
    log "Creating .env from template..."
    cp "$DIR/.env.example" "$DIR/.env"
    warn ".env created — please fill in your Telegram bot token and chat ID."
    echo ""
    echo "  Edit .env with your values:"
    echo "    TELEGRAM_BOT_TOKEN=  (get from @BotFather on Telegram)"
    echo "    TELEGRAM_CHAT_ID=    (get from @userinfobot on Telegram)"
    echo "    REMINDER_TIME=18:00  (24hr format)"
    echo ""
    read -p "Press ENTER after editing .env to continue, or Ctrl+C to exit..."
fi

# Validate required .env values
source "$DIR/.env" 2>/dev/null || true
if [ -z "$TELEGRAM_BOT_TOKEN" ] || [ "$TELEGRAM_BOT_TOKEN" = "your_bot_token_here" ]; then
    fail "TELEGRAM_BOT_TOKEN not set in .env. Edit the file and try again."
fi
if [ -z "$TELEGRAM_CHAT_ID" ] || [ "$TELEGRAM_CHAT_ID" = "your_chat_id_here" ]; then
    fail "TELEGRAM_CHAT_ID not set in .env. Edit the file and try again."
fi
ok ".env config loaded"

# ── 6. Credentials check ─────────────────────────────────────────────────────
if [ ! -f "$DIR/credentials.enc" ]; then
    warn "No credentials saved yet."
    echo ""
    echo "  You can set credentials two ways:"
    echo "    A) Start the bot now and use /setcredentials on Telegram (recommended)"
    echo "    B) Skip for now — you'll be prompted when the bot runs"
    echo ""
fi

# ── 7. Auth session check ────────────────────────────────────────────────────
if [ ! -f "$DIR/auth_state.json" ]; then
    warn "No browser session found (auth_state.json missing)."
    echo ""
    echo "  Run the login setup to create a session:"
    echo "    $VENV/bin/python setup_auth.py"
    echo ""
    read -p "Run setup_auth.py now? [y/N] " RUN_SETUP
    if [[ "$RUN_SETUP" =~ ^[Yy]$ ]]; then
        log "Starting browser login setup..."
        "$PYTHON" setup_auth.py
    else
        warn "Skipping. Run 'python setup_auth.py' before submitting logs."
    fi
fi

# ── 8. Start the bot ─────────────────────────────────────────────────────────
echo ""
ok "All checks passed. Starting PMS Daily Log Bot..."
echo ""
echo "  Send /start on Telegram to verify the bot is running."
echo "  Press Ctrl+C to stop."
echo ""

"$PYTHON" main.py
