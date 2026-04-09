import json
import os
import pytest
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

from app.scraper.linkedin_session import LinkedInSession
from app.scraper.linkedin_scraper import LinkedInScraper
from app.sources.linkedin import LinkedInSource


# ---------------------------------------------------------------------------
# LinkedInSession tests
# ---------------------------------------------------------------------------

class TestLinkedInSession:

    def make_session(self, tmp_path):
        """Create a session using a temp directory."""
        return LinkedInSession(cookies_dir=str(tmp_path))

    def test_has_session_returns_false_when_no_cookies(self, tmp_path):
        session = self.make_session(tmp_path)
        assert session.has_session() is False

    def test_has_session_returns_true_after_save(self, tmp_path):
        session = self.make_session(tmp_path)
        session.save_cookies([{"name": "li_at", "value": "abc123"}])
        assert session.has_session() is True

    def test_save_and_get_cookies_roundtrip(self, tmp_path):
        session = self.make_session(tmp_path)
        cookies = [{"name": "li_at", "value": "mytoken"}, {"name": "other", "value": "val"}]
        session.save_cookies(cookies)
        loaded = session.get_cookies()
        assert loaded == cookies

    def test_get_cookies_returns_empty_when_no_file(self, tmp_path):
        session = self.make_session(tmp_path)
        assert session.get_cookies() == []

    def test_get_cookies_returns_empty_on_corrupt_json(self, tmp_path):
        session = self.make_session(tmp_path)
        # Write garbage to the file
        with open(session.cookies_path, "w") as f:
            f.write("NOT VALID JSON {{{{")
        assert session.get_cookies() == []

    def test_get_li_at_cookie_extracts_value(self, tmp_path):
        session = self.make_session(tmp_path)
        session.save_cookies([
            {"name": "bcookie", "value": "other"},
            {"name": "li_at", "value": "MY_SESSION_TOKEN"},
        ])
        assert session.get_li_at_cookie() == "MY_SESSION_TOKEN"

    def test_get_li_at_cookie_returns_none_when_absent(self, tmp_path):
        session = self.make_session(tmp_path)
        session.save_cookies([{"name": "bcookie", "value": "something"}])
        assert session.get_li_at_cookie() is None

    def test_get_li_at_cookie_returns_none_with_no_session(self, tmp_path):
        session = self.make_session(tmp_path)
        assert session.get_li_at_cookie() is None

    def test_clear_session_removes_file(self, tmp_path):
        session = self.make_session(tmp_path)
        session.save_cookies([{"name": "li_at", "value": "token"}])
        assert session.has_session() is True
        session.clear_session()
        assert session.has_session() is False

    def test_clear_session_no_error_when_no_file(self, tmp_path):
        session = self.make_session(tmp_path)
        # Should not raise
        session.clear_session()

    @pytest.mark.asyncio
    async def test_set_cookie_direct_saves_li_at(self, tmp_path):
        session = self.make_session(tmp_path)
        await session.set_cookie_direct("DIRECT_COOKIE_VALUE_12345")
        assert session.has_session() is True
        li_at = session.get_li_at_cookie()
        assert li_at == "DIRECT_COOKIE_VALUE_12345"

    @pytest.mark.asyncio
    async def test_set_cookie_direct_stores_correct_domain(self, tmp_path):
        session = self.make_session(tmp_path)
        await session.set_cookie_direct("somevalue")
        cookies = session.get_cookies()
        assert len(cookies) == 1
        assert cookies[0]["domain"] == ".linkedin.com"
        assert cookies[0]["name"] == "li_at"

    def test_cookies_dir_created_automatically(self, tmp_path):
        nested = str(tmp_path / "deep" / "nested" / "dir")
        session = LinkedInSession(cookies_dir=nested)
        assert os.path.isdir(nested)


# ---------------------------------------------------------------------------
# LinkedInScraper tests
# ---------------------------------------------------------------------------

class TestLinkedInScraper:

    def test_is_available_returns_false_when_no_session(self, tmp_path):
        scraper = LinkedInScraper()
        # Patch the session to use a temp dir with no cookies
        scraper.session = LinkedInSession(cookies_dir=str(tmp_path))
        assert scraper.is_available() is False

    def test_is_available_returns_true_when_session_exists(self, tmp_path):
        scraper = LinkedInScraper()
        scraper.session = LinkedInSession(cookies_dir=str(tmp_path))
        scraper.session.save_cookies([{"name": "li_at", "value": "token"}])
        assert scraper.is_available() is True

    @pytest.mark.asyncio
    async def test_scrape_profile_returns_error_when_no_session(self, tmp_path):
        scraper = LinkedInScraper()
        scraper.session = LinkedInSession(cookies_dir=str(tmp_path))
        result = await scraper.scrape_profile("https://www.linkedin.com/in/johndoe")
        assert result.success is False
        assert "not configured" in result.error
        assert result.layer == "linkedin"

    @pytest.mark.asyncio
    async def test_search_people_returns_empty_when_no_session(self, tmp_path):
        scraper = LinkedInScraper()
        scraper.session = LinkedInSession(cookies_dir=str(tmp_path))
        results = await scraper.search_people("John Doe Acme Corp")
        assert results == []


# ---------------------------------------------------------------------------
# LinkedInSource tests
# ---------------------------------------------------------------------------

class TestLinkedInSource:

    @pytest.mark.asyncio
    async def test_enrich_returns_error_when_no_company(self):
        source = LinkedInSource()
        result = await source.enrich({"name": "John Doe"}, "Find recruiter")
        assert result.found is False
        assert result.source_name == "linkedin"
        assert "No company" in result.error

    @pytest.mark.asyncio
    async def test_enrich_returns_error_when_no_company_any_case(self):
        source = LinkedInSource()
        result = await source.enrich({}, "Find recruiter")
        assert result.found is False
        assert "No company" in result.error

    @pytest.mark.asyncio
    async def test_enrich_returns_not_found_when_search_empty(self):
        source = LinkedInSource()
        with patch.object(source.scraper, "search_people", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = []
            result = await source.enrich({"company": "Acme Corp"}, "Find recruiter")
        assert result.found is False
        assert "No LinkedIn results found" in result.error

    @pytest.mark.asyncio
    async def test_enrich_returns_top_result_on_success(self):
        source = LinkedInSource()
        fake_results = [
            {"name": "Jane Smith", "title": "HR Manager", "linkedin_url": "https://linkedin.com/in/janesmith"},
            {"name": "Bob Jones", "title": "Recruiter", "linkedin_url": "https://linkedin.com/in/bobjones"},
        ]
        with patch.object(source.scraper, "search_people", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = fake_results
            result = await source.enrich({"company": "Acme Corp"}, "Find recruiter")

        assert result.found is True
        assert result.source_name == "linkedin"
        assert result.confidence == pytest.approx(0.75)
        assert "Jane Smith" in result.value
        assert result.data["name"] == "Jane Smith"
        assert result.data["title"] == "HR Manager"
        assert result.data["linkedin_url"] == "https://linkedin.com/in/janesmith"
        assert len(result.data["all_results"]) == 2

    @pytest.mark.asyncio
    async def test_enrich_uses_company_field_case_insensitive(self):
        source = LinkedInSource()
        with patch.object(source.scraper, "search_people", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = [{"name": "Alice", "title": "VP", "linkedin_url": ""}]
            result = await source.enrich({"Company": "BigCorp"}, "Find someone")
        assert result.found is True

    @pytest.mark.asyncio
    async def test_enrich_builds_query_with_name_and_title(self):
        source = LinkedInSource()
        with patch.object(source.scraper, "search_people", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = [{"name": "Test", "title": "Dir", "linkedin_url": ""}]
            await source.enrich(
                {"company": "TechCo", "name": "John", "title": "Director"},
                "Find contact"
            )
        call_args = mock_search.call_args
        query = call_args[0][0]
        assert "John" in query
        assert "Director" in query
        assert "TechCo" in query

    @pytest.mark.asyncio
    async def test_enrich_inserts_role_hint_when_no_title(self):
        source = LinkedInSource()
        with patch.object(source.scraper, "search_people", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = [{"name": "Test", "title": "HR", "linkedin_url": ""}]
            await source.enrich({"company": "Corp"}, "Find campus recruiter")
        query = mock_search.call_args[0][0]
        assert "campus recruitment head" in query

    @pytest.mark.asyncio
    async def test_health_check_reflects_scraper_availability(self, tmp_path):
        source = LinkedInSource()
        source.scraper.session = LinkedInSession(cookies_dir=str(tmp_path))
        # No cookies saved — should be False
        assert await source.health_check() is False
        # Save cookies — should be True
        source.scraper.session.save_cookies([{"name": "li_at", "value": "token"}])
        assert await source.health_check() is True

    def test_name_and_rate_limit(self):
        source = LinkedInSource()
        assert source.name == "linkedin"
        assert source.rate_limit_per_minute == 5


# ---------------------------------------------------------------------------
# LinkedIn API endpoint tests
# ---------------------------------------------------------------------------

class TestLinkedInAPI:

    @pytest.mark.asyncio
    async def test_status_endpoint_returns_disconnected(self, client, tmp_path):
        """Status endpoint returns connected=False when no session."""
        with patch("app.api.linkedin.session") as mock_session:
            mock_session.has_session.return_value = False
            mock_session.get_li_at_cookie.return_value = None
            response = await client.get("/api/linkedin/status")

        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is False
        assert data["has_cookie"] is False

    @pytest.mark.asyncio
    async def test_status_endpoint_returns_connected(self, client, tmp_path):
        """Status endpoint returns connected=True when session exists."""
        with patch("app.api.linkedin.session") as mock_session:
            mock_session.has_session.return_value = True
            mock_session.get_li_at_cookie.return_value = "some_token"
            response = await client.get("/api/linkedin/status")

        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is True
        assert data["has_cookie"] is True

    @pytest.mark.asyncio
    async def test_connect_cookie_success(self, client):
        """Posting a valid li_at cookie connects LinkedIn."""
        with patch("app.api.linkedin.session") as mock_session:
            mock_session.set_cookie_direct = AsyncMock()
            response = await client.post(
                "/api/linkedin/connect-cookie",
                json={"li_at": "A" * 20}
            )

        assert response.status_code == 200
        assert response.json()["success"] is True

    @pytest.mark.asyncio
    async def test_connect_cookie_rejects_short_value(self, client):
        """Posting a too-short li_at value is rejected."""
        response = await client.post(
            "/api/linkedin/connect-cookie",
            json={"li_at": "short"}
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_disconnect_clears_session(self, client):
        """Disconnect endpoint calls clear_session."""
        with patch("app.api.linkedin.session") as mock_session:
            mock_session.clear_session = MagicMock()
            response = await client.post("/api/linkedin/disconnect")

        assert response.status_code == 200
        assert response.json()["success"] is True

    @pytest.mark.asyncio
    async def test_search_endpoint_requires_query(self, client):
        """Search endpoint rejects empty query."""
        response = await client.post("/api/linkedin/search", json={})
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_search_endpoint_returns_results(self, client):
        """Search endpoint returns LinkedIn results."""
        fake_results = [{"name": "Alice", "title": "CTO", "linkedin_url": "https://linkedin.com/in/alice"}]
        with patch("app.api.linkedin.LinkedInScraper") as MockScraper:
            mock_scraper = MagicMock()
            mock_scraper.search_people = AsyncMock(return_value=fake_results)
            MockScraper.return_value = mock_scraper
            response = await client.post("/api/linkedin/search", json={"query": "Alice CTO"})

        assert response.status_code == 200
        data = response.json()
        assert data["results"] == fake_results
