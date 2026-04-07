"""
Headless Microsoft login relay.

Playwright runs on the server in headless mode.
No screenshots are taken or sent.
Password is used once in the browser and never stored.
"""

import logging
from playwright.async_api import async_playwright, Playwright, Browser, BrowserContext, Page
from config import AZURE_AUTH_URL, auth_state_path

logger = logging.getLogger(__name__)

_sessions: dict[int, tuple[Playwright, Browser, BrowserContext, Page]] = {}


async def login_start(chat_id: int) -> None:
    await login_abort(chat_id)
    p = await async_playwright().start()
    browser = await p.chromium.launch(headless=True)
    context = await browser.new_context()
    page = await context.new_page()
    await page.goto(AZURE_AUTH_URL, wait_until="domcontentloaded", timeout=20000)
    await page.wait_for_selector("input[type='email']", timeout=15000)
    _sessions[chat_id] = (p, browser, context, page)
    logger.info(f"Login session started for {chat_id}")


async def login_submit_email(chat_id: int, email: str) -> None:
    _, _, _, page = _sessions[chat_id]
    await page.fill("input[type='email']", email)
    await page.click("input[type='submit']")
    await page.wait_for_load_state("networkidle", timeout=15000)


async def login_submit_password(chat_id: int, password: str) -> bool:
    """Returns True if now on PMS dashboard."""
    _, _, _, page = _sessions[chat_id]
    await page.fill("input[type='password']", password)
    await page.click("input[type='submit']")
    await page.wait_for_load_state("networkidle", timeout=20000)
    # Auto-handle "Stay signed in?"
    try:
        await page.wait_for_selector("input[type='submit']", timeout=5000)
        await page.click("input[type='submit']")
        await page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass
    return _is_on_pms(page.url)


async def login_submit_code(chat_id: int, code: str) -> bool:
    """Fill an MFA/OTP code. Returns True if now on PMS dashboard."""
    _, _, _, page = _sessions[chat_id]
    for selector in ["input[name='otc']", "input[type='tel']", "input[type='number']", "input[type='text']"]:
        el = await page.query_selector(selector)
        if el and await el.is_visible():
            await el.fill(code)
            break
    for selector in ["input[type='submit']", "button[type='submit']"]:
        el = await page.query_selector(selector)
        if el and await el.is_visible():
            await el.click()
            break
    await page.wait_for_load_state("networkidle", timeout=15000)
    return _is_on_pms(page.url)


async def login_save_session(chat_id: int) -> bool:
    if chat_id not in _sessions:
        return False
    p, browser, context, page = _sessions.pop(chat_id)
    try:
        if _is_on_pms(page.url):
            await context.storage_state(path=auth_state_path(chat_id))
            logger.info(f"Session saved for {chat_id}")
            await browser.close()
            await p.stop()
            return True
    except Exception as e:
        logger.error(f"Failed to save session for {chat_id}: {e}")
    await browser.close()
    await p.stop()
    return False


async def login_abort(chat_id: int):
    if chat_id in _sessions:
        p, browser, _, _ = _sessions.pop(chat_id)
        try:
            await browser.close()
            await p.stop()
        except Exception:
            pass


def _is_on_pms(url: str) -> bool:
    return "iqube.therig.in" in url and "login" not in url and "azuread" not in url
