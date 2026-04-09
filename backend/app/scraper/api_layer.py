import httpx

from app.config import settings

from .http_layer import ScrapeResult


class ApiScraper:
    """Scrapes content using third-party API services."""

    async def scrape(self, url: str) -> ScrapeResult:
        """
        Scrape a URL using configured API services.

        Tries ScraperAPI first, then Browserless, or returns failure if none configured.
        """
        # Check if ScraperAPI is configured
        if settings.scraper_api_key:
            return await self._scrape_with_scraper_api(url)

        # Check if Browserless is configured
        if settings.browserless_api_key:
            return await self._scrape_with_browserless(url)

        # No API keys configured
        return ScrapeResult(
            url=url,
            success=False,
            error="No API scraping keys configured",
            layer="api"
        )

    async def _scrape_with_scraper_api(self, url: str) -> ScrapeResult:
        """Scrape using ScraperAPI."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    "https://api.scraperapi.com",
                    params={
                        "api_key": settings.scraper_api_key,
                        "url": url
                    }
                )

                if response.status_code >= 400:
                    return ScrapeResult(
                        url=url,
                        success=False,
                        status_code=response.status_code,
                        error=f"ScraperAPI error {response.status_code}",
                        layer="api"
                    )

                return ScrapeResult(
                    url=url,
                    success=True,
                    html=response.text,
                    text=response.text[:1000],  # Preview of content
                    status_code=response.status_code,
                    layer="api"
                )

        except Exception as e:
            return ScrapeResult(
                url=url,
                success=False,
                error=f"ScraperAPI error: {str(e)}",
                layer="api"
            )

    async def _scrape_with_browserless(self, url: str) -> ScrapeResult:
        """Scrape using Browserless API."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"https://chrome.browserless.io/content?token={settings.browserless_api_key}",
                    json={"url": url}
                )

                if response.status_code >= 400:
                    return ScrapeResult(
                        url=url,
                        success=False,
                        status_code=response.status_code,
                        error=f"Browserless error {response.status_code}",
                        layer="api"
                    )

                data = response.json()
                return ScrapeResult(
                    url=url,
                    success=True,
                    html=data.get("data", ""),
                    text=data.get("data", "")[:1000],  # Preview of content
                    status_code=response.status_code,
                    layer="api"
                )

        except Exception as e:
            return ScrapeResult(
                url=url,
                success=False,
                error=f"Browserless error: {str(e)}",
                layer="api"
            )
