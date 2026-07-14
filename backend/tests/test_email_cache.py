import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from tests.conftest import TestSession
from app.services.email_cache import EmailCacheService, CACHE_TTL_DAYS
from app.sources.base import SourceResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def patch_cache_session():
    """Patch async_session in the email_cache service to use the test SQLite DB."""
    with patch("app.services.email_cache.async_session", TestSession):
        yield


# ---------------------------------------------------------------------------
# store + lookup (round-trip)
# ---------------------------------------------------------------------------

class TestEmailCacheRoundTrip:
    @pytest.mark.asyncio
    async def test_store_and_lookup(self, patch_cache_session):
        """Storing an email and looking it up returns the cached entry."""
        svc = EmailCacheService()
        await svc.store(
            person_name="John Doe",
            company="Acme Corp",
            email="john.doe@acme.com",
            source="hunter",
            confidence=0.8,
            verified=False,
        )

        result = await svc.lookup("John Doe", "Acme Corp")
        assert result is not None
        assert result.email == "john.doe@acme.com"
        assert result.source == "hunter"
        assert result.confidence == pytest.approx(0.8)

    @pytest.mark.asyncio
    async def test_lookup_is_case_insensitive(self, patch_cache_session):
        """Lookup normalizes case for person name and company."""
        svc = EmailCacheService()
        await svc.store(
            person_name="Jane Smith",
            company="TechCorp",
            email="jane@techcorp.io",
            source="apollo",
            confidence=0.9,
        )

        result = await svc.lookup("JANE SMITH", "techcorp")
        assert result is not None
        assert result.email == "jane@techcorp.io"

    @pytest.mark.asyncio
    async def test_lookup_unknown_person_returns_none(self, patch_cache_session):
        """lookup returns None when no entry exists for the person+company."""
        svc = EmailCacheService()
        result = await svc.lookup("Nobody Here", "Ghost Corp")
        assert result is None

    @pytest.mark.asyncio
    async def test_store_sets_domain_from_email_when_not_provided(self, patch_cache_session):
        """When domain is not passed, it is derived from the email address."""
        svc = EmailCacheService()
        entry = await svc.store(
            person_name="Alice",
            company="StartupX",
            email="alice@startupx.com",
            source="web_scrape",
            confidence=0.5,
        )
        assert entry.domain == "startupx.com"

    @pytest.mark.asyncio
    async def test_store_verified_sets_last_verified_at(self, patch_cache_session):
        """Storing a verified email sets last_verified_at."""
        svc = EmailCacheService()
        entry = await svc.store(
            person_name="Bob",
            company="VerifyMe",
            email="bob@verifyme.com",
            source="smtp_verified",
            confidence=1.0,
            verified=True,
        )
        assert entry.last_verified_at is not None

    @pytest.mark.asyncio
    async def test_store_unverified_leaves_last_verified_at_null(self, patch_cache_session):
        """Storing an unverified email leaves last_verified_at as None."""
        svc = EmailCacheService()
        entry = await svc.store(
            person_name="Carol",
            company="MaybeMe",
            email="carol@maybeme.com",
            source="email_pattern",
            confidence=0.4,
            verified=False,
        )
        assert entry.last_verified_at is None


# ---------------------------------------------------------------------------
# Stale entry handling
# ---------------------------------------------------------------------------

class TestStaleCacheEntries:
    @pytest.mark.asyncio
    async def test_lookup_returns_none_for_stale_entry(self, patch_cache_session):
        """A cache entry older than CACHE_TTL_DAYS is treated as stale and returns None."""
        svc = EmailCacheService()
        await svc.store(
            person_name="Old Guy",
            company="Past Corp",
            email="old@past.com",
            source="hunter",
            confidence=0.7,
        )

        # Move "now" forward past TTL
        future_now = datetime.now() + timedelta(days=CACHE_TTL_DAYS + 1)
        with patch("app.services.email_cache.datetime") as mock_dt:
            mock_dt.now.return_value = future_now
            result = await svc.lookup("Old Guy", "Past Corp")

        assert result is None

    @pytest.mark.asyncio
    async def test_lookup_returns_entry_within_ttl(self, patch_cache_session):
        """A cache entry within TTL is returned normally."""
        svc = EmailCacheService()
        await svc.store(
            person_name="Fresh Person",
            company="New Co",
            email="fresh@newco.com",
            source="apollo",
            confidence=0.85,
        )

        # Move "now" forward but stay within TTL
        recent_now = datetime.now() + timedelta(days=CACHE_TTL_DAYS - 1)
        with patch("app.services.email_cache.datetime") as mock_dt:
            mock_dt.now.return_value = recent_now
            result = await svc.lookup("Fresh Person", "New Co")

        assert result is not None
        assert result.email == "fresh@newco.com"


# ---------------------------------------------------------------------------
# Update with higher confidence
# ---------------------------------------------------------------------------

class TestCacheUpdate:
    @pytest.mark.asyncio
    async def test_store_updates_existing_with_higher_confidence(self, patch_cache_session):
        """Storing the same email again with higher confidence updates the record."""
        svc = EmailCacheService()
        await svc.store(
            person_name="Dave",
            company="Update Inc",
            email="dave@update.com",
            source="email_pattern",
            confidence=0.4,
        )

        await svc.store(
            person_name="Dave",
            company="Update Inc",
            email="dave@update.com",
            source="smtp_verified",
            confidence=0.95,
            verified=True,
        )

        result = await svc.lookup("Dave", "Update Inc")
        assert result is not None
        assert result.confidence == pytest.approx(0.95)
        assert result.source == "smtp_verified"
        assert result.verified is True

    @pytest.mark.asyncio
    async def test_store_does_not_downgrade_confidence(self, patch_cache_session):
        """Storing the same email again with lower confidence keeps the original."""
        svc = EmailCacheService()
        await svc.store(
            person_name="Eve",
            company="Keep High",
            email="eve@keephigh.com",
            source="smtp_verified",
            confidence=0.95,
            verified=True,
        )

        await svc.store(
            person_name="Eve",
            company="Keep High",
            email="eve@keephigh.com",
            source="email_pattern",
            confidence=0.3,
        )

        result = await svc.lookup("Eve", "Keep High")
        assert result is not None
        assert result.confidence == pytest.approx(0.95)
        assert result.source == "smtp_verified"

    @pytest.mark.asyncio
    async def test_store_merges_extra_data_on_update(self, patch_cache_session):
        """Higher-confidence update merges extra_data rather than replacing it."""
        svc = EmailCacheService()
        await svc.store(
            person_name="Frank",
            company="Merge Co",
            email="frank@merge.com",
            source="hunter",
            confidence=0.5,
            extra_data={"title": "Engineer"},
        )

        await svc.store(
            person_name="Frank",
            company="Merge Co",
            email="frank@merge.com",
            source="apollo",
            confidence=0.85,
            extra_data={"linkedin_url": "https://linkedin.com/in/frank"},
        )

        result = await svc.lookup("Frank", "Merge Co")
        assert result is not None
        assert result.extra_data is not None
        assert result.extra_data.get("title") == "Engineer"
        assert result.extra_data.get("linkedin_url") == "https://linkedin.com/in/frank"


# ---------------------------------------------------------------------------
# lookup_by_domain
# ---------------------------------------------------------------------------

class TestLookupByDomain:
    @pytest.mark.asyncio
    async def test_lookup_by_domain_returns_multiple_entries(self, patch_cache_session):
        """lookup_by_domain returns all cached emails for a domain."""
        svc = EmailCacheService()
        await svc.store("Alice", "Domain Corp", "alice@domcorp.com", "hunter", 0.8, domain="domcorp.com")
        await svc.store("Bob", "Domain Corp", "bob@domcorp.com", "apollo", 0.7, domain="domcorp.com")
        await svc.store("Carol", "Other Co", "carol@otherdomain.com", "hunter", 0.6, domain="otherdomain.com")

        results = await svc.lookup_by_domain("domcorp.com")
        emails = [r.email for r in results]
        assert "alice@domcorp.com" in emails
        assert "bob@domcorp.com" in emails
        assert "carol@otherdomain.com" not in emails

    @pytest.mark.asyncio
    async def test_lookup_by_domain_returns_empty_list_for_unknown_domain(self, patch_cache_session):
        """lookup_by_domain returns an empty list when domain is not cached."""
        svc = EmailCacheService()
        results = await svc.lookup_by_domain("nodomain.xyz")
        assert results == []

    @pytest.mark.asyncio
    async def test_lookup_by_domain_ordered_by_confidence_desc(self, patch_cache_session):
        """lookup_by_domain returns entries ordered by confidence descending."""
        svc = EmailCacheService()
        await svc.store("Low", "Ordered Co", "low@ordered.com", "email_pattern", 0.3, domain="ordered.com")
        await svc.store("High", "Ordered Co", "high@ordered.com", "smtp_verified", 0.95, domain="ordered.com")
        await svc.store("Mid", "Ordered Co", "mid@ordered.com", "hunter", 0.6, domain="ordered.com")

        results = await svc.lookup_by_domain("ordered.com")
        confidences = [r.confidence for r in results]
        assert confidences == sorted(confidences, reverse=True)


# ---------------------------------------------------------------------------
# lookup_by_email
# ---------------------------------------------------------------------------

class TestLookupByEmail:
    @pytest.mark.asyncio
    async def test_lookup_by_email_returns_entry(self, patch_cache_session):
        """lookup_by_email returns the cached entry for a known email."""
        svc = EmailCacheService()
        await svc.store("Grace", "Email Co", "grace@emailco.com", "hunter", 0.8)

        result = await svc.lookup_by_email("grace@emailco.com")
        assert result is not None
        assert result.person_name == "Grace"

    @pytest.mark.asyncio
    async def test_lookup_by_email_case_insensitive(self, patch_cache_session):
        """lookup_by_email normalizes the email to lowercase."""
        svc = EmailCacheService()
        await svc.store("Heidi", "Cap Co", "heidi@capco.com", "apollo", 0.75)

        result = await svc.lookup_by_email("HEIDI@CAPCO.COM")
        assert result is not None
        assert result.email == "heidi@capco.com"

    @pytest.mark.asyncio
    async def test_lookup_by_email_returns_none_for_unknown(self, patch_cache_session):
        """lookup_by_email returns None for an email not in the cache."""
        svc = EmailCacheService()
        result = await svc.lookup_by_email("nobody@nowhere.com")
        assert result is None


# ---------------------------------------------------------------------------
# get_stats
# ---------------------------------------------------------------------------

class TestGetStats:
    @pytest.mark.asyncio
    async def test_stats_returns_correct_counts(self, patch_cache_session):
        """get_stats returns accurate total, verified, and domain counts."""
        svc = EmailCacheService()
        await svc.store("Ivan", "Stats Co", "ivan@stats.com", "hunter", 0.7, domain="stats.com")
        await svc.store("Judy", "Stats Co", "judy@stats.com", "smtp_verified", 1.0, verified=True, domain="stats.com")
        await svc.store("Karl", "Other Co", "karl@other.com", "apollo", 0.6, domain="other.com")

        stats = await svc.get_stats()
        assert stats["total_emails"] == 3
        assert stats["verified_emails"] == 1
        assert stats["unique_domains"] == 2

    @pytest.mark.asyncio
    async def test_stats_empty_cache_returns_zeros(self, patch_cache_session):
        """get_stats returns zeros when the cache is empty."""
        svc = EmailCacheService()
        stats = await svc.get_stats()
        assert stats["total_emails"] == 0
        assert stats["verified_emails"] == 0
        assert stats["unique_domains"] == 0


# ---------------------------------------------------------------------------
# WaterfallEngine cache integration
# ---------------------------------------------------------------------------

class TestWaterfallCacheIntegration:
    @pytest.mark.asyncio
    async def test_waterfall_returns_cached_result_without_calling_sources(self):
        """When cache returns a hit, waterfall skips all sources entirely."""
        from app.services.enrichment_router import WaterfallEngine
        from app.models.email_cache import EmailCache

        mock_entry = MagicMock(spec=EmailCache)
        mock_entry.email = "cached@example.com"
        mock_entry.source = "hunter"
        mock_entry.verified = True
        mock_entry.confidence = 0.9

        mock_source = MagicMock()
        mock_source.name = "hunter"
        mock_source.health_check = AsyncMock(return_value=True)
        mock_source.enrich = AsyncMock(return_value=SourceResult(found=True, value="live@example.com"))

        mock_cache = AsyncMock()
        mock_cache.lookup = AsyncMock(return_value=mock_entry)

        engine = WaterfallEngine([mock_source])
        engine.cache = mock_cache

        result = await engine.run({"name": "John Doe", "company": "ACME"}, "Find email")

        assert result.found is True
        assert result.value == "cached@example.com"
        assert result.source_name == "cache"
        assert result.data["cached"] is True
        # Source should never have been called
        mock_source.enrich.assert_not_called()

    @pytest.mark.asyncio
    async def test_waterfall_stores_result_in_cache_after_source_hit(self):
        """When a source returns a result, waterfall stores it in the cache."""
        from app.services.enrichment_router import WaterfallEngine

        mock_source = MagicMock()
        mock_source.name = "hunter"
        mock_source.health_check = AsyncMock(return_value=True)
        mock_source.enrich = AsyncMock(return_value=SourceResult(
            found=True,
            value="live@example.com",
            source_name="hunter",
            confidence=0.8,
            data={"verified": True},  # engine caches verified emails only
        ))

        mock_cache = AsyncMock()
        mock_cache.lookup = AsyncMock(return_value=None)  # Cache miss
        mock_cache.store = AsyncMock()

        engine = WaterfallEngine([mock_source])
        engine.cache = mock_cache

        row_data = {"name": "Alice", "company": "Acme"}
        result = await engine.run(row_data, "Find email")

        assert result.found is True
        assert result.value == "live@example.com"
        # Cache store must have been called
        mock_cache.store.assert_called_once()
        call_kwargs = mock_cache.store.call_args.kwargs
        assert call_kwargs["person_name"] == "Alice"
        assert call_kwargs["company"] == "Acme"
        assert call_kwargs["email"] == "live@example.com"
        assert call_kwargs["source"] == "hunter"

    @pytest.mark.asyncio
    async def test_waterfall_skips_cache_when_no_name_or_company(self):
        """When row data has no person/company, cache lookup is skipped."""
        from app.services.enrichment_router import WaterfallEngine

        mock_source = MagicMock()
        mock_source.name = "hunter"
        mock_source.health_check = AsyncMock(return_value=True)
        mock_source.enrich = AsyncMock(return_value=SourceResult(
            found=True, value="x@y.com", source_name="hunter", confidence=0.5, data={}
        ))

        mock_cache = AsyncMock()
        mock_cache.lookup = AsyncMock(return_value=None)

        engine = WaterfallEngine([mock_source])
        engine.cache = mock_cache

        # No "name" or "company" keys
        result = await engine.run({"email": "x@y.com"}, "Find email")

        assert result.found is True
        mock_cache.lookup.assert_not_called()

    @pytest.mark.asyncio
    async def test_waterfall_cache_failure_does_not_block_sources(self):
        """If cache lookup raises an exception, waterfall still tries sources."""
        from app.services.enrichment_router import WaterfallEngine

        mock_source = MagicMock()
        mock_source.name = "hunter"
        mock_source.health_check = AsyncMock(return_value=True)
        mock_source.enrich = AsyncMock(return_value=SourceResult(
            found=True, value="fallback@example.com", source_name="hunter", confidence=0.7, data={}
        ))

        mock_cache = AsyncMock()
        mock_cache.lookup = AsyncMock(side_effect=Exception("DB is down"))
        mock_cache.store = AsyncMock()

        engine = WaterfallEngine([mock_source])
        engine.cache = mock_cache

        result = await engine.run({"name": "Bob", "company": "Corp"}, "Find email")

        assert result.found is True
        assert result.value == "fallback@example.com"
        assert result.source_name == "hunter"


# ---------------------------------------------------------------------------
# Cache API endpoints
# ---------------------------------------------------------------------------

class TestEmailCacheAPI:
    @pytest.mark.asyncio
    async def test_cache_stats_endpoint(self, client, patch_cache_session):
        """GET /api/email-cache/stats returns total, verified, and unique_domains."""
        response = await client.get("/api/email-cache/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total_emails" in data
        assert "verified_emails" in data
        assert "unique_domains" in data
        assert data["total_emails"] == 0

    @pytest.mark.asyncio
    async def test_cache_search_by_email(self, client, patch_cache_session):
        """GET /api/email-cache/search?q=<email> returns matching cached entries."""
        svc = EmailCacheService()
        await svc.store("Search Test", "Test Corp", "search@testcorp.com", "hunter", 0.8)

        response = await client.get("/api/email-cache/search?q=search@testcorp.com")
        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 1
        assert data["results"][0]["email"] == "search@testcorp.com"

    @pytest.mark.asyncio
    async def test_cache_search_by_domain(self, client, patch_cache_session):
        """GET /api/email-cache/search?q=<domain> returns all entries for that domain."""
        svc = EmailCacheService()
        await svc.store("X User", "Domain Test", "x@domaintest.net", "apollo", 0.7, domain="domaintest.net")
        await svc.store("Y User", "Domain Test", "y@domaintest.net", "hunter", 0.6, domain="domaintest.net")

        response = await client.get("/api/email-cache/search?q=domaintest.net")
        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 2

    @pytest.mark.asyncio
    async def test_cache_search_empty_results(self, client, patch_cache_session):
        """GET /api/email-cache/search with no matches returns empty results list."""
        response = await client.get("/api/email-cache/search?q=nobody@nowhere.xyz")
        assert response.status_code == 200
        data = response.json()
        assert data["results"] == []
