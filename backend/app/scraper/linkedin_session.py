import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

LINKEDIN_COOKIES_FILE = "linkedin_cookies.json"


class LinkedInSession:
    """Manages LinkedIn browser session with persistent cookies."""

    def __init__(self, cookies_dir: str | None = None):
        self.cookies_dir = cookies_dir or os.path.join(os.path.expanduser("~"), ".scrpr")
        os.makedirs(self.cookies_dir, exist_ok=True)
        self.cookies_path = os.path.join(self.cookies_dir, LINKEDIN_COOKIES_FILE)

    def has_session(self) -> bool:
        """Check if we have saved LinkedIn cookies."""
        return os.path.exists(self.cookies_path)

    def get_cookies(self) -> list[dict]:
        """Load saved cookies."""
        if not self.has_session():
            return []
        try:
            with open(self.cookies_path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []

    def save_cookies(self, cookies: list[dict]) -> None:
        """Save cookies to disk."""
        with open(self.cookies_path, "w") as f:
            json.dump(cookies, f, indent=2)
        logger.info(f"LinkedIn cookies saved to {self.cookies_path}")

    def clear_session(self) -> None:
        """Delete saved cookies."""
        if os.path.exists(self.cookies_path):
            os.remove(self.cookies_path)
            logger.info("LinkedIn session cleared")

    def get_li_at_cookie(self) -> str | None:
        """Get the li_at session cookie value."""
        for cookie in self.get_cookies():
            if cookie.get("name") == "li_at":
                return cookie.get("value")
        return None

    async def login_interactive(self) -> bool:
        """Open a browser window for the user to log into LinkedIn manually.
        After login, captures and saves the cookies."""
        try:
            from patchright.async_api import async_playwright
        except ImportError:
            from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)  # Visible browser for login
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            )
            page = await context.new_page()
            await page.goto("https://www.linkedin.com/login")

            logger.info("Waiting for user to log into LinkedIn...")
            # Wait for the user to log in — detected by URL changing to feed
            try:
                await page.wait_for_url("**/feed/**", timeout=120000)  # 2 min to log in
            except Exception:
                # They might land on a different page after login
                import asyncio
                await asyncio.sleep(5)

            # Check if logged in by looking for the li_at cookie
            cookies = await context.cookies()
            li_at = next((c for c in cookies if c["name"] == "li_at"), None)

            if li_at:
                self.save_cookies(cookies)
                logger.info("LinkedIn login successful!")
                await browser.close()
                return True
            else:
                logger.warning("LinkedIn login failed — no li_at cookie found")
                await browser.close()
                return False

    def import_from_browser(self, browser_name: str = "auto") -> bool:
        """Auto-import li_at cookie from a local browser's cookie store.

        Supports: floorp, firefox, chrome, edge.
        Set browser_name="auto" to try all in order.
        """
        import platform
        import shutil
        import sqlite3
        import tempfile

        browsers_to_try = [browser_name] if browser_name != "auto" else ["floorp", "firefox", "chrome", "edge"]

        appdata = os.environ.get("APPDATA", "")
        localappdata = os.environ.get("LOCALAPPDATA", "")

        # Map browser names to their cookie DB paths (Windows)
        cookie_paths = {
            "floorp": os.path.join(appdata, "Floorp", "Profiles"),
            "firefox": os.path.join(appdata, "Mozilla", "Firefox", "Profiles"),
            "chrome": os.path.join(localappdata, "Google", "Chrome", "User Data", "Default", "Cookies"),
            "edge": os.path.join(localappdata, "Microsoft", "Edge", "User Data", "Default", "Cookies"),
        }

        for browser in browsers_to_try:
            try:
                if browser in ("floorp", "firefox"):
                    # Firefox-based: find profile dir with cookies.sqlite
                    profiles_dir = cookie_paths.get(browser, "")
                    if not os.path.isdir(profiles_dir):
                        continue

                    # Find the default-release profile
                    cookie_db = None
                    for profile_dir in os.listdir(profiles_dir):
                        candidate = os.path.join(profiles_dir, profile_dir, "cookies.sqlite")
                        if os.path.exists(candidate):
                            cookie_db = candidate
                            if "default-release" in profile_dir:
                                break  # Prefer default-release

                    if not cookie_db:
                        continue

                    # Copy DB to temp (browser may have it locked)
                    tmp = tempfile.mktemp(suffix=".sqlite")
                    shutil.copy2(cookie_db, tmp)

                    try:
                        conn = sqlite3.connect(tmp)
                        cursor = conn.execute(
                            "SELECT value FROM moz_cookies WHERE host LIKE '%linkedin.com' AND name = 'li_at' LIMIT 1"
                        )
                        row = cursor.fetchone()
                        conn.close()
                    finally:
                        os.unlink(tmp)

                    if row and row[0]:
                        li_at_value = row[0]
                        self.save_cookies([{
                            "name": "li_at",
                            "value": li_at_value,
                            "domain": ".linkedin.com",
                            "path": "/",
                            "httpOnly": True,
                            "secure": True,
                            "sameSite": "None",
                        }])
                        logger.info(f"LinkedIn cookie imported from {browser}!")
                        return True

                elif browser in ("chrome", "edge"):
                    # Chromium-based: cookies are encrypted on Windows (DPAPI)
                    # For now, log that it requires the cookie method instead
                    logger.info(f"{browser} cookies are encrypted on Windows — use cookie method or Floorp/Firefox")
                    continue

            except Exception as e:
                logger.warning(f"Failed to import from {browser}: {e}")
                continue

        return False

    async def set_cookie_direct(self, li_at_value: str) -> None:
        """Set the li_at cookie directly (user provides it from their browser)."""
        cookies = [
            {
                "name": "li_at",
                "value": li_at_value,
                "domain": ".linkedin.com",
                "path": "/",
                "httpOnly": True,
                "secure": True,
                "sameSite": "None",
            }
        ]
        self.save_cookies(cookies)
        logger.info("LinkedIn cookie set directly")
