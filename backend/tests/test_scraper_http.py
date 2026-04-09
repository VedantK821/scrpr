import pytest
from unittest.mock import AsyncMock, patch

from app.scraper.http_layer import HttpScraper, ScrapeResult


class TestHttpScraper:
    """Test HTTP layer scraper."""

    @pytest.mark.asyncio
    async def test_http_scraper_success(self):
        """Test successful HTTP scraping with valid HTML."""
        scraper = HttpScraper()

        # Mock response
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html; charset=utf-8"}
        mock_response.text = """
        <html>
            <head><title>Test Page</title></head>
            <body>
                <h1>Hello World</h1>
                <p>Test content</p>
            </body>
        </html>
        """

        with patch("app.scraper.http_layer.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            result = await scraper.scrape("https://example.com")

            assert result.success is True
            assert result.url == "https://example.com"
            assert result.status_code == 200
            assert result.layer == "http"
            assert "Hello World" in result.text
            assert "Test Page" in result.title
            assert result.error == ""

    @pytest.mark.asyncio
    async def test_http_scraper_404_error(self):
        """Test HTTP scraper with 404 status code."""
        scraper = HttpScraper()

        mock_response = AsyncMock()
        mock_response.status_code = 404

        with patch("app.scraper.http_layer.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            result = await scraper.scrape("https://example.com/notfound")

            assert result.success is False
            assert result.status_code == 404
            assert "HTTP 404" in result.error

    @pytest.mark.asyncio
    async def test_http_scraper_non_html_content(self):
        """Test HTTP scraper with non-HTML content type."""
        scraper = HttpScraper()

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}

        with patch("app.scraper.http_layer.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            result = await scraper.scrape("https://api.example.com/data")

            assert result.success is False
            assert "not HTML" in result.error

    @pytest.mark.asyncio
    async def test_http_scraper_timeout(self):
        """Test HTTP scraper with timeout error."""
        scraper = HttpScraper()

        with patch("app.scraper.http_layer.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get.side_effect = Exception("Request timeout")
            mock_client_class.return_value = mock_client

            result = await scraper.scrape("https://example.com")

            assert result.success is False
            assert "error" in result.error.lower() or "timeout" in result.error.lower()

    @pytest.mark.asyncio
    async def test_http_scraper_removes_script_tags(self):
        """Test that HTTP scraper removes script and style tags."""
        scraper = HttpScraper()

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.text = """
        <html>
            <head>
                <title>Test</title>
                <style>body { color: red; }</style>
            </head>
            <body>
                <h1>Content</h1>
                <script>console.log('should not appear')</script>
                <p>Visible text</p>
            </body>
        </html>
        """

        with patch("app.scraper.http_layer.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            result = await scraper.scrape("https://example.com")

            assert result.success is True
            assert "Visible text" in result.text
            assert "should not appear" not in result.text
            assert "color: red" not in result.text

    def test_scrape_result_dataclass(self):
        """Test ScrapeResult dataclass."""
        result = ScrapeResult(
            url="https://example.com",
            success=True,
            text="Test",
            html="<html>Test</html>",
            title="Test Page",
            status_code=200
        )

        assert result.url == "https://example.com"
        assert result.success is True
        assert result.text == "Test"
        assert result.layer == "http"
        assert result.error == ""
