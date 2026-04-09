import asyncio
from dataclasses import dataclass, field
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from .stealth import get_random_user_agent


@dataclass
class ScrapeResult:
    """Represents the result of a scraping operation."""
    url: str
    success: bool
    text: str = ""
    html: str = ""
    title: str = ""
    error: str = ""
    status_code: int = 0
    layer: str = "http"


class HttpScraper:
    """Scrapes content using HTTP requests without JavaScript execution."""

    async def scrape(self, url: str) -> ScrapeResult:
        """
        Scrape a URL using httpx.

        Returns a ScrapeResult with the page content or error details.
        """
        try:
            headers = {"User-Agent": get_random_user_agent()}
            async with httpx.AsyncClient(
                timeout=15.0,
                verify=False,
                follow_redirects=True
            ) as client:
                response = await client.get(url, headers=headers)

                # Check for error status codes
                if response.status_code >= 400:
                    return ScrapeResult(
                        url=url,
                        success=False,
                        status_code=response.status_code,
                        error=f"HTTP {response.status_code}",
                        layer="http"
                    )

                # Check for non-HTML content
                content_type = response.headers.get("content-type", "").lower()
                if "text/html" not in content_type:
                    return ScrapeResult(
                        url=url,
                        success=False,
                        status_code=response.status_code,
                        error="Content-Type is not HTML",
                        layer="http"
                    )

                # Parse HTML
                soup = BeautifulSoup(response.text, "html.parser")

                # Remove script, style, nav, footer, header tags
                for tag in soup.find_all(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()

                # Extract text and title
                text = soup.get_text(separator="\n", strip=True)
                title_tag = soup.find("title")
                title = title_tag.get_text(strip=True) if title_tag else ""

                return ScrapeResult(
                    url=url,
                    success=True,
                    text=text,
                    html=response.text,
                    title=title,
                    status_code=response.status_code,
                    layer="http"
                )

        except asyncio.TimeoutError:
            return ScrapeResult(
                url=url,
                success=False,
                error="Request timeout (15s)",
                layer="http"
            )
        except httpx.HTTPError as e:
            return ScrapeResult(
                url=url,
                success=False,
                error=f"HTTP error: {str(e)}",
                layer="http"
            )
        except Exception as e:
            return ScrapeResult(
                url=url,
                success=False,
                error=f"Unexpected error: {str(e)}",
                layer="http"
            )
