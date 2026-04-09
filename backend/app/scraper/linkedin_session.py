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
