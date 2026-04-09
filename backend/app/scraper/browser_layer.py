from bs4 import BeautifulSoup

from .http_layer import ScrapeResult
from .stealth import get_random_user_agent

# Try to import from patchright, fall back to playwright
try:
    from patchright.async_api import async_playwright
except ImportError:
    from playwright.async_api import async_playwright


class BrowserScraper:
    """Scrapes content using a headless browser with JavaScript execution."""

    async def scrape(self, url: str) -> ScrapeResult:
        """
        Scrape a URL using a headless Chromium browser.

        Returns a ScrapeResult with the rendered page content.
        """
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent=get_random_user_agent(),
                    viewport={"width": 1920, "height": 1080}
                )
                page = await context.new_page()

                try:
                    # Load page with domcontentloaded
                    await page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=15000
                    )

                    # Try to wait for network idle (catch errors for partial loads)
                    try:
                        await page.wait_for_load_state("networkidle", timeout=5000)
                    except Exception:
                        # Some pages may not reach full networkidle; continue with current state
                        pass

                    # Get page content
                    html = await page.content()
                    soup = BeautifulSoup(html, "html.parser")

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
                        html=html,
                        title=title,
                        status_code=200,
                        layer="browser"
                    )

                finally:
                    await context.close()
                    await browser.close()

        except Exception as e:
            return ScrapeResult(
                url=url,
                success=False,
                error=f"Browser scraping failed: {str(e)}",
                layer="browser"
            )
