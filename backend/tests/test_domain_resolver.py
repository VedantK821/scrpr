import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.domain_resolver import (
    resolve_domain, _extract_domain, _is_social_domain, _guess_domain, _domain_cache
)


class TestExtractDomain:
    def test_simple_url(self):
        assert _extract_domain("https://www.zapier.com/about") == "zapier.com"

    def test_no_www(self):
        assert _extract_domain("https://tcs.com") == "tcs.com"

    def test_subdomain(self):
        assert _extract_domain("https://careers.google.com") == "careers.google.com"

    def test_invalid(self):
        assert _extract_domain("not a url") == ""


class TestIsSocialDomain:
    def test_linkedin(self):
        assert _is_social_domain("linkedin.com") is True

    def test_linkedin_subdomain(self):
        assert _is_social_domain("in.linkedin.com") is True

    def test_company_domain(self):
        assert _is_social_domain("zapier.com") is False

    def test_wikipedia(self):
        assert _is_social_domain("en.wikipedia.org") is True


class TestGuessDomain:
    def test_simple(self):
        assert _guess_domain("Zapier") == "zapier.com"

    def test_strips_ltd(self):
        assert _guess_domain("DevBay Ltd") == "devbay.com"

    def test_strips_technologies(self):
        assert _guess_domain("HCL Technologies") == "hcl.com"

    def test_empty(self):
        assert _guess_domain("") == ""


class TestResolveDomain:
    @pytest.fixture(autouse=True)
    def clear_cache(self):
        _domain_cache.clear()
        yield
        _domain_cache.clear()

    @pytest.mark.asyncio
    async def test_known_domain(self):
        """Known domains resolve instantly without search."""
        result = await resolve_domain("TCS")
        assert result == "tcs.com"

    @pytest.mark.asyncio
    async def test_known_domain_case_insensitive(self):
        result = await resolve_domain("Wipro")
        assert result == "wipro.com"

    @pytest.mark.asyncio
    async def test_empty_company(self):
        result = await resolve_domain("")
        assert result == ""

    @pytest.mark.asyncio
    async def test_caches_result(self):
        await resolve_domain("TCS")
        assert "tcs" in _domain_cache
