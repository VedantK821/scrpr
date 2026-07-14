import pytest
from unittest.mock import AsyncMock, patch

from app.scraper.engine import ScrapingEngine
from app.scraper.http_layer import ScrapeResult


class TestScrapingEngine:
    """Test the 3-layer scraping engine."""

    @pytest.fixture
    async def engine(self):
        """Create a scraping engine instance."""
        return ScrapingEngine()

    @pytest.mark.asyncio
    async def test_engine_scrape_http_success(self, engine):
        """Test that engine returns successful HTTP result."""
        success_result = ScrapeResult(
            url="https://example.com",
            success=True,
            text="Content from HTTP",
            html="<html>Content</html>",
            layer="http"
        )

        with patch.object(engine.http, "scrape", new_callable=AsyncMock) as mock_http:
            mock_http.return_value = success_result

            result = await engine.scrape("https://example.com")

            assert result.success is True
            assert result.text == "Content from HTTP"
            assert result.layer == "http"
            mock_http.assert_called_once()

    @pytest.mark.skip(
        reason="Browser layer intentionally disabled in ScrapingEngine for "
        "event-loop stability (see app/scraper/engine.py). Re-enable this test "
        "when the Patchright stealth layer is restored."
    )
    @pytest.mark.asyncio
    async def test_engine_scrape_fallback_to_browser(self, engine):
        """Test that engine falls back to browser when HTTP fails (browser layer currently disabled)."""
        http_failure = ScrapeResult(
            url="https://example.com",
            success=False,
            error="HTTP error",
            layer="http"
        )
        browser_success = ScrapeResult(
            url="https://example.com",
            success=True,
            text="Content from Browser",
            html="<html>Content</html>",
            layer="browser"
        )

        with patch.object(engine.http, "scrape", new_callable=AsyncMock) as mock_http, \
             patch.object(engine.browser, "scrape", new_callable=AsyncMock) as mock_browser, \
             patch("app.scraper.engine.get_random_delay", return_value=0):
            mock_http.return_value = http_failure
            mock_browser.return_value = browser_success

            result = await engine.scrape("https://example.com")

            assert result.success is True
            assert result.text == "Content from Browser"
            assert result.layer == "browser"
            mock_http.assert_called_once()
            mock_browser.assert_called_once()

    @pytest.mark.asyncio
    async def test_engine_scrape_fallback_to_api(self, engine):
        """Test that engine falls back to the API layer when HTTP fails."""
        http_failure = ScrapeResult(
            url="https://example.com",
            success=False,
            error="HTTP error",
            layer="http"
        )
        api_success = ScrapeResult(
            url="https://example.com",
            success=True,
            text="Content from API",
            html="<html>Content</html>",
            layer="api"
        )

        with patch.object(engine.http, "scrape", new_callable=AsyncMock) as mock_http, \
             patch.object(engine.api, "scrape", new_callable=AsyncMock) as mock_api, \
             patch("app.scraper.engine.get_random_delay", return_value=0):
            mock_http.return_value = http_failure
            mock_api.return_value = api_success

            result = await engine.scrape("https://example.com")

            assert result.success is True
            assert result.text == "Content from API"
            assert result.layer == "api"
            mock_http.assert_called_once()
            mock_api.assert_called_once()

    @pytest.mark.asyncio
    async def test_engine_scrape_all_layers_fail(self, engine):
        """Test that engine returns failure when all layers fail."""
        failure = ScrapeResult(
            url="https://example.com",
            success=False,
            error="All failed",
            layer="api"
        )

        with patch.object(engine.http, "scrape", new_callable=AsyncMock) as mock_http, \
             patch.object(engine.browser, "scrape", new_callable=AsyncMock) as mock_browser, \
             patch.object(engine.api, "scrape", new_callable=AsyncMock) as mock_api, \
             patch("app.scraper.engine.get_random_delay", return_value=0):
            mock_http.return_value = ScrapeResult(
                url="https://example.com",
                success=False,
                error="HTTP error",
                layer="http"
            )
            mock_browser.return_value = ScrapeResult(
                url="https://example.com",
                success=False,
                error="Browser error",
                layer="browser"
            )
            mock_api.return_value = failure

            result = await engine.scrape("https://example.com")

            assert result.success is False
            assert result.layer == "api"

    @pytest.mark.asyncio
    async def test_engine_scrape_skip_http(self, engine):
        """Test that engine skips the HTTP layer when skip_http=True."""
        api_success = ScrapeResult(
            url="https://example.com",
            success=True,
            text="Content from API",
            layer="api"
        )

        with patch.object(engine.http, "scrape", new_callable=AsyncMock) as mock_http, \
             patch.object(engine.api, "scrape", new_callable=AsyncMock) as mock_api, \
             patch("app.scraper.engine.get_random_delay", return_value=0):
            mock_api.return_value = api_success

            result = await engine.scrape("https://example.com", skip_http=True)

            assert result.success is True
            assert result.layer == "api"
            mock_http.assert_not_called()
            mock_api.assert_called_once()

    @pytest.mark.asyncio
    async def test_engine_scrape_many(self, engine):
        """Test scraping multiple URLs concurrently."""
        urls = ["https://example1.com", "https://example2.com", "https://example3.com"]

        results = [
            ScrapeResult(url=url, success=True, text=f"Content {i}", layer="http")
            for i, url in enumerate(urls)
        ]

        with patch.object(engine, "scrape", new_callable=AsyncMock) as mock_scrape:
            mock_scrape.side_effect = results

            results_list = await engine.scrape_many(urls, concurrency=3)

            assert len(results_list) == 3
            assert all(r.success for r in results_list)
            assert mock_scrape.call_count == 3

    @pytest.mark.asyncio
    async def test_engine_scrape_http_empty_text(self, engine):
        """Test that engine falls back to API when HTTP returns empty text."""
        http_empty = ScrapeResult(
            url="https://example.com",
            success=True,
            text="",  # Empty text, should trigger fallback
            html="<html></html>",
            layer="http"
        )
        api_success = ScrapeResult(
            url="https://example.com",
            success=True,
            text="Content from API",
            html="<html>Content</html>",
            layer="api"
        )

        with patch.object(engine.http, "scrape", new_callable=AsyncMock) as mock_http, \
             patch.object(engine.api, "scrape", new_callable=AsyncMock) as mock_api, \
             patch("app.scraper.engine.get_random_delay", return_value=0):
            mock_http.return_value = http_empty
            mock_api.return_value = api_success

            result = await engine.scrape("https://example.com")

            assert result.success is True
            assert result.text == "Content from API"
            assert result.layer == "api"
            mock_api.assert_called_once()
