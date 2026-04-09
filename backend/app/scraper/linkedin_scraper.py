import asyncio
import logging
import re
from bs4 import BeautifulSoup

from app.scraper.http_layer import ScrapeResult
from app.scraper.linkedin_session import LinkedInSession
from app.scraper.stealth import get_random_user_agent, get_random_delay

logger = logging.getLogger(__name__)


class LinkedInScraper:
    """Scrapes LinkedIn profiles using saved session cookies."""

    def __init__(self):
        self.session = LinkedInSession()

    def is_available(self) -> bool:
        return self.session.has_session()

    async def scrape_profile(self, profile_url: str) -> ScrapeResult:
        """Scrape a LinkedIn profile page using Patchright with saved cookies."""
        if not self.is_available():
            return ScrapeResult(url=profile_url, success=False, error="LinkedIn session not configured", layer="linkedin")

        try:
            try:
                from patchright.async_api import async_playwright
            except ImportError:
                from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent=get_random_user_agent(),
                    viewport={"width": 1920, "height": 1080},
                    locale="en-US",
                )

                # Load saved cookies
                cookies = self.session.get_cookies()
                if cookies:
                    # Filter to LinkedIn cookies only
                    li_cookies = [c for c in cookies if "linkedin.com" in c.get("domain", "")]
                    if li_cookies:
                        await context.add_cookies(li_cookies)

                page = await context.new_page()

                # Navigate to profile
                await page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(get_random_delay(2.0, 4.0))  # Wait for dynamic content

                # Check if we're on a login page (session expired)
                if "/login" in page.url or "authwall" in page.url:
                    await browser.close()
                    return ScrapeResult(
                        url=profile_url, success=False,
                        error="LinkedIn session expired — need to re-login",
                        layer="linkedin",
                    )

                html = await page.content()
                title = await page.title()

                # Parse the profile
                soup = BeautifulSoup(html, "html.parser")

                # Remove noise
                for tag in soup(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()

                text = soup.get_text(separator="\n", strip=True)

                await browser.close()

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

        search_url = f"https://www.linkedin.com/search/results/people/?keywords={query}&origin=GLOBAL_SEARCH_HEADER"

        try:
            try:
                from patchright.async_api import async_playwright
            except ImportError:
                from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent=get_random_user_agent(),
                    viewport={"width": 1920, "height": 1080},
                )
                cookies = self.session.get_cookies()
                li_cookies = [c for c in cookies if "linkedin.com" in c.get("domain", "")]
                if li_cookies:
                    await context.add_cookies(li_cookies)

                page = await context.new_page()
                await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(get_random_delay(3.0, 5.0))

                if "/login" in page.url:
                    await browser.close()
                    return []

                html = await page.content()
                soup = BeautifulSoup(html, "html.parser")

                results = []
                # LinkedIn people search result cards
                for card in soup.select("div.entity-result__item, li.reusable-search__result-container"):
                    name_el = card.select_one("span.entity-result__title-text a span[aria-hidden='true'], span.entity-result__title-text")
                    title_el = card.select_one("div.entity-result__primary-subtitle, div.entity-result__summary")
                    link_el = card.select_one("a.app-aware-link[href*='/in/']")

                    name = name_el.get_text(strip=True) if name_el else ""
                    job_title = title_el.get_text(strip=True) if title_el else ""
                    profile_link = link_el.get("href", "") if link_el else ""

                    if profile_link:
                        # Clean the URL
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
                return results

        except Exception as e:
            logger.error(f"LinkedIn search failed: {e}")
            return []
