import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass

from app.sources.website_email import WebsiteEmailSource, _resolve_website, _is_personal_email


class TestResolveWebsite:
    def test_from_domain(self):
        assert _resolve_website("TCS", "tcs.com") == "https://www.tcs.com"

    def test_from_domain_with_protocol(self):
        assert _resolve_website("TCS", "https://www.tcs.com/careers") == "https://www.tcs.com"

    def test_from_company_name_fallback(self):
        result = _resolve_website("Google", "")
        assert "google.com" in result

    def test_empty_returns_empty(self):
        assert _resolve_website("", "") == ""


class TestIsPersonalEmail:
    def test_personal_email(self):
        assert _is_personal_email("john.doe@company.com") is True

    def test_generic_noreply(self):
        assert _is_personal_email("noreply@company.com") is False

    def test_generic_info(self):
        assert _is_personal_email("info@company.com") is False

    def test_generic_support(self):
        assert _is_personal_email("support@company.com") is False

    def test_short_name(self):
        assert _is_personal_email("alice@company.com") is True


@dataclass
class FakeScrapeResult:
    success: bool
    text: str = ""


class TestWebsiteEmailSource:
    @pytest.mark.asyncio
    async def test_finds_email_on_contact_page(self):
        source = WebsiteEmailSource()
        fake_text = "Contact us at john.doe@example.com for inquiries."

        with patch.object(source.engine, "scrape", new_callable=AsyncMock) as mock_scrape:
            mock_scrape.return_value = FakeScrapeResult(success=True, text=fake_text)
            result = await source.enrich({"Company": "Example", "domain": "example.com"}, "Find email")

        assert result.found is True
        assert result.value == "john.doe@example.com"
        assert result.confidence == 0.8

    @pytest.mark.asyncio
    async def test_skips_generic_emails(self):
        source = WebsiteEmailSource()
        fake_text = "Email us at info@example.com or noreply@example.com"

        with patch.object(source.engine, "scrape", new_callable=AsyncMock) as mock_scrape:
            mock_scrape.return_value = FakeScrapeResult(success=True, text=fake_text)
            result = await source.enrich({"Company": "Example", "domain": "example.com"}, "Find email")

        assert result.found is False

    @pytest.mark.asyncio
    async def test_no_company_returns_error(self):
        source = WebsiteEmailSource()
        result = await source.enrich({}, "Find email")
        assert result.found is False
        assert "No company" in result.error

    @pytest.mark.asyncio
    async def test_no_emails_on_pages(self):
        source = WebsiteEmailSource()

        with patch.object(source.engine, "scrape", new_callable=AsyncMock) as mock_scrape:
            mock_scrape.return_value = FakeScrapeResult(success=True, text="No emails here!")
            result = await source.enrich({"Company": "Example", "domain": "example.com"}, "Find email")

        assert result.found is False

    @pytest.mark.asyncio
    async def test_filters_to_same_domain(self):
        source = WebsiteEmailSource()
        fake_text = "john@example.com is here, also bob@otherdomain.com"

        with patch.object(source.engine, "scrape", new_callable=AsyncMock) as mock_scrape:
            mock_scrape.return_value = FakeScrapeResult(success=True, text=fake_text)
            result = await source.enrich({"Company": "Example", "domain": "example.com"}, "Find email")

        assert result.found is True
        assert result.value == "john@example.com"
        assert "bob@otherdomain.com" not in result.data.get("all_emails", [])
