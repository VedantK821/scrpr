import asyncio
import logging
import random
import re
from datetime import datetime, date
from bs4 import BeautifulSoup

from app.scraper.http_layer import ScrapeResult
from app.scraper.linkedin_session import LinkedInSession
from app.scraper.stealth import get_random_user_agent, get_random_delay

logger = logging.getLogger(__name__)

# Daily safety limits — LinkedIn flags accounts that view too many profiles
DAILY_PROFILE_LIMIT = 40  # LinkedIn free accounts can view ~80/day, we stay at half
DAILY_SEARCH_LIMIT = 15   # Searches are more heavily monitored
MIN_DELAY_BETWEEN_ACTIONS = 3.0  # Minimum seconds between ANY LinkedIn action
MAX_DELAY_BETWEEN_ACTIONS = 8.0  # Maximum random delay


class LinkedInScraper:
    """Scrapes LinkedIn profiles using saved session cookies.

    Safety features:
    - Daily limits on profile views and searches
    - Random delays mimicking human browsing
    - Random scroll behavior on pages
    - Session reuse (single browser context per batch)
    - Automatic stop if session expires
    """

    def __init__(self):
        self.session = LinkedInSession()
        self._daily_profile_count = 0
        self._daily_search_count = 0
        self._last_count_date = date.today()
        self._last_action_time = 0.0

    def is_available(self) -> bool:
        return self.session.has_session()

    def _reset_daily_counts_if_needed(self):
        if date.today() != self._last_count_date:
            self._daily_profile_count = 0
            self._daily_search_count = 0
            self._last_count_date = date.today()

    def _can_view_profile(self) -> bool:
        self._reset_daily_counts_if_needed()
        return self._daily_profile_count < DAILY_PROFILE_LIMIT

    def _can_search(self) -> bool:
        self._reset_daily_counts_if_needed()
        return self._daily_search_count < DAILY_SEARCH_LIMIT

    def get_daily_usage(self) -> dict:
        self._reset_daily_counts_if_needed()
        return {
            "profiles_viewed": self._daily_profile_count,
            "profiles_limit": DAILY_PROFILE_LIMIT,
            "searches_done": self._daily_search_count,
            "searches_limit": DAILY_SEARCH_LIMIT,
        }

    async def _human_delay(self):
        """Wait a random amount of time to mimic human browsing."""
        # Enforce minimum time between actions
        import time
        elapsed = time.time() - self._last_action_time
        if elapsed < MIN_DELAY_BETWEEN_ACTIONS:
            await asyncio.sleep(MIN_DELAY_BETWEEN_ACTIONS - elapsed)
        # Add random jitter
        await asyncio.sleep(get_random_delay(MIN_DELAY_BETWEEN_ACTIONS, MAX_DELAY_BETWEEN_ACTIONS))
        self._last_action_time = time.time()

    async def _simulate_human_behavior(self, page):
        """Scroll and move mouse like a real user."""
        try:
            # Random scroll down
            scroll_amount = random.randint(200, 600)
            await page.evaluate(f"window.scrollBy(0, {scroll_amount})")
            await asyncio.sleep(get_random_delay(0.5, 1.5))

            # Sometimes scroll back up a bit
            if random.random() > 0.6:
                await page.evaluate(f"window.scrollBy(0, -{random.randint(50, 150)})")
                await asyncio.sleep(get_random_delay(0.3, 0.8))

            # Random mouse movement
            x = random.randint(100, 800)
            y = random.randint(100, 500)
            await page.mouse.move(x, y)
        except Exception:
            pass  # Not critical if simulation fails

    async def _create_context(self, playwright):
        """Create a stealth browser context with LinkedIn cookies."""
        browser = await playwright.chromium.launch(headless=True)

        # Randomize viewport slightly (real users have different screen sizes)
        width = random.choice([1366, 1440, 1536, 1920])
        height = random.choice([768, 900, 864, 1080])

        context = await browser.new_context(
            user_agent=get_random_user_agent(),
            viewport={"width": width, "height": height},
            locale=random.choice(["en-US", "en-GB", "en-IN"]),
            timezone_id="Asia/Kolkata",
            geolocation=None,
        )

        # Load saved cookies
        cookies = self.session.get_cookies()
        if cookies:
            li_cookies = [c for c in cookies if "linkedin.com" in c.get("domain", "")]
            if li_cookies:
                await context.add_cookies(li_cookies)

        return browser, context

    async def scrape_profile(self, profile_url: str) -> ScrapeResult:
        """Scrape a LinkedIn profile page."""
        if not self.is_available():
            return ScrapeResult(url=profile_url, success=False, error="LinkedIn session not configured", layer="linkedin")

        if not self._can_view_profile():
            return ScrapeResult(
                url=profile_url, success=False,
                error=f"Daily profile limit reached ({DAILY_PROFILE_LIMIT}). Resets tomorrow.",
                layer="linkedin",
            )

        await self._human_delay()

        try:
            try:
                from patchright.async_api import async_playwright
            except ImportError:
                from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser, context = await self._create_context(p)
                page = await context.new_page()

                await page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(get_random_delay(2.0, 4.0))

                # Check if session expired
                if "/login" in page.url or "authwall" in page.url:
                    await browser.close()
                    self.session.clear_session()
                    return ScrapeResult(
                        url=profile_url, success=False,
                        error="LinkedIn session expired — reconnect via /api/linkedin/import-browser",
                        layer="linkedin",
                    )

                # Simulate human behavior
                await self._simulate_human_behavior(page)

                html = await page.content()
                title = await page.title()

                soup = BeautifulSoup(html, "html.parser")
                for tag in soup(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()
                text = soup.get_text(separator="\n", strip=True)

                await browser.close()
                self._daily_profile_count += 1

                if not text.strip() or len(text) < 100:
                    return ScrapeResult(url=profile_url, success=False, error="Empty or minimal profile content", layer="linkedin")

                return ScrapeResult(
                    url=profile_url, success=True, text=text, html=html,
                    title=title, status_code=200, layer="linkedin",
                )

        except Exception as e:
            return ScrapeResult(url=profile_url, success=False, error=f"LinkedIn scrape error: {e}", layer="linkedin")

    async def search_people(self, query: str, max_results: int = 5) -> list[dict]:
        """Search LinkedIn for people matching a query."""
        if not self.is_available():
            return []

        if not self._can_search():
            logger.warning(f"Daily LinkedIn search limit reached ({DAILY_SEARCH_LIMIT})")
            return []

        await self._human_delay()

        # URL-encode the query properly
        from urllib.parse import quote
        search_url = f"https://www.linkedin.com/search/results/people/?keywords={quote(query)}&origin=GLOBAL_SEARCH_HEADER"

        try:
            try:
                from patchright.async_api import async_playwright
            except ImportError:
                from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser, context = await self._create_context(p)
                page = await context.new_page()

                await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(get_random_delay(3.0, 5.0))

                if "/login" in page.url or "authwall" in page.url:
                    await browser.close()
                    self.session.clear_session()
                    return []

                # Simulate reading the page
                await self._simulate_human_behavior(page)

                html = await page.content()
                soup = BeautifulSoup(html, "html.parser")

                results = []
                for card in soup.select("div.entity-result__item, li.reusable-search__result-container"):
                    name_el = card.select_one("span.entity-result__title-text a span[aria-hidden='true'], span.entity-result__title-text")
                    title_el = card.select_one("div.entity-result__primary-subtitle, div.entity-result__summary")
                    link_el = card.select_one("a.app-aware-link[href*='/in/']")

                    name = name_el.get_text(strip=True) if name_el else ""
                    job_title = title_el.get_text(strip=True) if title_el else ""
                    profile_link = link_el.get("href", "") if link_el else ""

                    if profile_link:
                        profile_link = profile_link.split("?")[0]

                    if name:
                        results.append({
                            "name": name,
                            "title": job_title,
                            "linkedin_url": profile_link,
                        })

                    if len(results) >= max_results:
                        break

                await browser.close()
                self._daily_search_count += 1
                return results

        except Exception as e:
            logger.error(f"LinkedIn search failed: {e}")
            return []
