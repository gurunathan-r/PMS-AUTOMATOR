"""
First-run / manual session setup.
Opens a headed browser, navigates to the PMS login page,
auto-fills Microsoft credentials if stored, then saves the session.

Run: python setup_auth.py
"""

import asyncio
from playwright.async_api import async_playwright
from config import LOGIN_PAGE, AZURE_AUTH_URL, DAILY_LOG_URL, AUTH_STATE_PATH
from credentials import load_credentials


async def setup():
    creds = load_credentials()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        print(f"Opening PMS login page: {LOGIN_PAGE}")
        await page.goto(LOGIN_PAGE, wait_until="networkidle", timeout=20000)

        # Try to find and click the Azure AD login button
        azure_btn = None
        for selector in [
            "a[href*='azuread-oauth2']",
            "a:has-text('Microsoft')",
            "a:has-text('Azure')",
            "a:has-text('Sign in')",
            "a:has-text('Login')",
            "a.btn",
        ]:
            el = await page.query_selector(selector)
            if el and await el.is_visible():
                azure_btn = el
                print(f"Found login button: {selector}")
                break

        if azure_btn:
            await azure_btn.click()
            await page.wait_for_load_state("networkidle", timeout=15000)
        else:
            print("Could not find login button — navigating directly to Azure auth URL")
            await page.goto(AZURE_AUTH_URL, wait_until="networkidle", timeout=20000)

        # Auto-fill Microsoft credentials if stored
        if creds and ("microsoftonline" in page.url or "login.microsoft" in page.url):
            print(f"Auto-filling credentials for: {creds['email']}")
            try:
                await page.wait_for_selector("input[type='email']", timeout=8000)
                await page.fill("input[type='email']", creds["email"])
                await page.click("input[type='submit'], button[type='submit']")

                await page.wait_for_selector("input[type='password']", timeout=8000)
                await page.fill("input[type='password']", creds["password"])
                await page.click("input[type='submit'], button[type='submit']")

                try:
                    await page.wait_for_selector("input[type='submit']", timeout=6000)
                    await page.click("input[type='submit']")
                except Exception:
                    pass

                await page.wait_for_load_state("networkidle", timeout=20000)
                print(f"Post-login URL: {page.url}")
            except Exception as e:
                print(f"Auto-fill failed: {e}")
                print("Please complete the login manually in the browser.")
        elif not creds:
            print("No credentials stored. Log in manually in the browser.")
            print("(Use /setcredentials in the bot to store credentials for auto-login)")

        input(f"\nPress ENTER once you're logged in and can see the dashboard... ")

        await context.storage_state(path=AUTH_STATE_PATH)
        print(f"Session saved to {AUTH_STATE_PATH}")
        await browser.close()

    print("\nSetup complete! Run: python main.py")


if __name__ == "__main__":
    asyncio.run(setup())
