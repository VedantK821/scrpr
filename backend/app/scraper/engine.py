import asyncio
from typing import List

from .api_layer import ApiScraper
from .browser_layer import BrowserScraper
from .http_layer import HttpScraper, ScrapeResult
from .stealth import get_random_delay
from .linkedin_scraper import LinkedInScraper


class ScrapingEngine:
    """
    3-layer scraping engine that tries multiple methods to fetch web content.

    Layers: HTTP -> Browser -> API
    For LinkedIn URLs: uses the LinkedIn scraper directly (requires saved session).
    """

    def __init__(self):
        """Initialize the scraping engine with all three scrapers."""
        self.http = HttpScraper()
        self.browser = BrowserScraper()
        self.api = ApiScraper()
        self.linkedin = LinkedInScraper()

    async def scrape(
        self,
        url: str,
        skip_http: bool = False
    ) -> ScrapeResult:
        """
        Scrape a URL using the 3-layer fallback strategy.

        Tries layers in order (HTTP -> Browser -> API), returns first successful
        result with non-empty text. Includes brief delay between layers.

        Args:
            url: URL to scrape
            skip_http: If True, skip the HTTP layer and start with browser

        Returns:
            ScrapeResult from the first successful layer or failure from API layer
        """
        # For LinkedIn URLs, use the LinkedIn scraper directly (generic HTTP always fails)
        if "linkedin.com" in url and self.linkedin.is_available():
            result = await self.linkedin.scrape_profile(url)
            if result.success:
                return result

        layers = []

        if not skip_http:
            layers.append(("http", self.http.scrape))

        # Browser layer disabled — Playwright crashes poison the event loop
        # HTTP handles 95% of pages. API layer is the fallback.
        layers.extend([
            ("api", self.api.scrape)
        ])

        last_result = None

        for layer_name, scraper_method in layers:
            result = await scraper_method(url)
            last_result = result

            # Return if successful and has content
            if result.success and result.text:
                return result

            # Add delay before trying next layer
            if layer_name != layers[-1][0]:  # Don't delay after last layer
                await asyncio.sleep(get_random_delay())

        # Return the last result (which failed)
        return last_result if last_result else ScrapeResult(
            url=url,
            success=False,
            error="All scraping layers failed"
        )

    async def scrape_many(
        self,
        urls: List[str],
        concurrency: int = 10,
        skip_http: bool = False
    ) -> List[ScrapeResult]:
        """
        Scrape multiple URLs concurrently with concurrency control.

        Args:
            urls: List of URLs to scrape
            concurrency: Maximum number of concurrent scrapes
            skip_http: If True, skip the HTTP layer

        Returns:
            List of ScrapeResult objects in the same order as input URLs
        """
        semaphore = asyncio.Semaphore(concurrency)

        async def scrape_with_semaphore(url: str) -> ScrapeResult:
            async with semaphore:
                return await self.scrape(url, skip_http=skip_http)

        results = await asyncio.gather(
            *[scrape_with_semaphore(url) for url in urls],
            return_exceptions=False
        )

        return results
