"""
Playwright automation for iQube PMS daily log submission.

Flow:
  1. Navigate to /me/daily_log/create (uses cached session)
  2. If session expired, prompt user to /login again
  3. Fill: activities_done, time_spent, location, description
  4. Submit the daily log form
  5. Logout via /me/user/logout/
  6. Clear session file
"""

import os
import logging
from urllib.parse import urlparse
from playwright.async_api import async_playwright, Page
from config import AZURE_AUTH_URL, DAILY_LOG_URL, auth_state_path
from credentials import load_credentials

logger = logging.getLogger(__name__)

LOGOUT_URL = "https://iqube.therig.in/me/user/logout/"


def _clear_session(chat_id: int):
    path = auth_state_path(chat_id)
    if os.path.exists(path):
        os.remove(path)
        logger.info(f"Session cleared for {chat_id}.")


async def _microsoft_login(page: Page, email: str, password: str) -> bool:
    """Full Microsoft login using stored credentials."""
    try:
        await page.goto(AZURE_AUTH_URL, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_selector("input[type='email']", timeout=10000)
        await page.fill("input[type='email']", email)
        await page.click("input[type='submit']")
        await page.wait_for_load_state("networkidle", timeout=15000)

        await page.wait_for_selector("input[type='password']", timeout=10000)
        await page.fill("input[type='password']", password)
        await page.click("input[type='submit']")
        await page.wait_for_load_state("networkidle", timeout=20000)

        try:
            await page.wait_for_selector("input[type='submit']", timeout=6000)
            await page.click("input[type='submit']")
            await page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass

        return "iqube.therig.in" in page.url
    except Exception as e:
        logger.error(f"Microsoft login error: {e}")
        return False


async def submit_daily_log(chat_id: int, activities: str, hours: str, location: str, description: str) -> dict:
    """Login → fill form → submit → logout → clear session."""
    session_path = auth_state_path(chat_id)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        if os.path.exists(session_path):
            context = await browser.new_context(storage_state=session_path)
            logger.info(f"Loaded cached session for {chat_id}.")
        else:
            context = await browser.new_context()

        page = await context.new_page()

        try:
            await page.goto(DAILY_LOG_URL, wait_until="domcontentloaded", timeout=30000)
            logger.info(f"Initial URL: {page.url}")

            def on_form_page(url: str) -> bool:
                return "/daily_log/create" in urlparse(url).path

            if not on_form_page(page.url):
                logger.info("Session expired or missing — trying stored credentials")
                creds = load_credentials(chat_id)
                if not creds:
                    await browser.close()
                    return {
                        "success": False,
                        "message": "Session expired. Use /login to authenticate again.",
                    }

                ok = await _microsoft_login(page, creds["email"], creds["password"])
                if not ok:
                    await browser.close()
                    _clear_session(chat_id)
                    return {
                        "success": False,
                        "message": "Login failed. Use /login or update credentials via /setcredentials.",
                    }

                await page.goto(DAILY_LOG_URL, wait_until="domcontentloaded", timeout=30000)

            if not on_form_page(page.url):
                await browser.close()
                _clear_session(chat_id)
                return {
                    "success": False,
                    "message": f"Session expired. Use /login to authenticate again.",
                }

            logger.info("Waiting for form to load...")
            await page.wait_for_selector("#id_activities_done", state="attached", timeout=60000)

            logger.info("Waiting for CKEditor...")
            await page.wait_for_function(
                """() => typeof CKEDITOR !== 'undefined' &&
                         CKEDITOR.instances['id_description'] &&
                         CKEDITOR.instances['id_description'].status === 'ready'""",
                timeout=30000,
            )
            logger.info("Form ready.")

            # Fill activities
            await page.evaluate(f"""() => {{
                const el = document.querySelector('#id_activities_done');
                el.removeAttribute('disabled'); el.removeAttribute('readonly');
                el.value = {repr(activities)};
                el.dispatchEvent(new Event('input', {{bubbles: true}}));
                el.dispatchEvent(new Event('change', {{bubbles: true}}));
            }}""")

            # Fill hours
            await page.evaluate(f"""() => {{
                const el = document.querySelector('#id_time_spent');
                el.removeAttribute('disabled'); el.removeAttribute('readonly');
                el.value = {repr(str(hours))};
                el.dispatchEvent(new Event('input', {{bubbles: true}}));
                el.dispatchEvent(new Event('change', {{bubbles: true}}));
            }}""")

            # Fill location
            await page.evaluate(f"""() => {{
                const sel = document.querySelector('#id_location');
                const opt = Array.from(sel.options).find(
                    o => o.value.toLowerCase() === {repr(location.lower())} ||
                         o.text.toLowerCase().includes({repr(location.lower())})
                );
                if (opt) {{
                    sel.value = opt.value;
                    sel.dispatchEvent(new Event('change', {{bubbles: true}}));
                }}
            }}""")

            # Fill description via CKEditor
            await page.evaluate(f"""() => {{
                CKEDITOR.instances['id_description'].setData({repr(description)});
                CKEDITOR.instances['id_description'].updateElement();
            }}""")

            # Submit via form.submit() — btn.click() is intercepted by page JS
            submitted = await page.evaluate("""() => {
                if (typeof CKEDITOR !== 'undefined') {
                    for (const k in CKEDITOR.instances) CKEDITOR.instances[k].updateElement();
                }
                const field = document.querySelector('#id_activities_done');
                if (!field) return false;
                const form = field.closest('form');
                if (!form) return false;
                form.submit();
                return true;
            }""")

            if not submitted:
                await page.goto(LOGOUT_URL, wait_until="networkidle", timeout=10000)
                await browser.close()
                _clear_session(chat_id)
                return {"success": False, "message": "Could not find the daily log form to submit."}

            await page.wait_for_load_state("networkidle", timeout=15000)
            logger.info(f"Post-submit URL: {page.url}")

            is_success = "/me/daily_log/" in page.url and "/create" not in page.url
            page_error = None
            if not is_success:
                err_text = await page.evaluate("""() => {
                    const el = document.querySelector('ul.errorlist li, .messages li, .alert');
                    return el ? el.innerText.trim() : null;
                }""")
                page_error = err_text or f"Unexpected page: {page.url}"
            logger.info(f"Submit result — success={is_success}, error={page_error}")

            await page.goto(LOGOUT_URL, wait_until="networkidle", timeout=10000)
            await browser.close()
            _clear_session(chat_id)

            if page_error:
                return {"success": False, "message": f"Form error: {page_error}"}

            return {"success": True, "message": "Daily log submitted successfully!"}

        except Exception as e:
            logger.exception(f"Automation error: {e}")
            try:
                await page.goto(LOGOUT_URL, wait_until="networkidle", timeout=10000)
            except Exception:
                pass
            await browser.close()
            _clear_session(chat_id)
            return {"success": False, "message": f"Error: {str(e)}"}
