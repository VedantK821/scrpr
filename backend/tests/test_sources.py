import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.sources.base import EnrichmentSource, SourceResult
from app.sources.ai_agent import AIAgentSource, format_agent_data
from app.sources.hunter import HunterSource
from app.sources.apollo import ApolloSource
from app.sources.email_pattern import EmailPatternSource
from app.sources import get_source_by_name, get_all_sources
from app.services.enrichment_router import WaterfallEngine
from app.services.quota_tracker import QuotaTracker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_agent_result(success=True, data=None, confidence=0.85, error=None):
    from app.agent.loop import AgentResult
    return AgentResult(
        success=success,
        data={"email": "john@example.com"} if data is None else data,
        confidence=confidence,
        error=error,
    )


# ---------------------------------------------------------------------------
# AIAgentSource
# ---------------------------------------------------------------------------

class TestAIAgentSource:
    @pytest.mark.asyncio
    async def test_enrich_success(self):
        source = AIAgentSource()
        mock_result = make_agent_result(success=True, data={"email": "test@example.com"}, confidence=0.9)

        with patch("app.sources.ai_agent.AgentLoop") as MockLoop:
            mock_loop = MagicMock()
            mock_loop.run = AsyncMock(return_value=mock_result)
            MockLoop.return_value = mock_loop

            result = await source.enrich({"name": "John Doe"}, "Find email")

        assert result.found is True
        assert result.source_name == "ai_agent"
        assert result.confidence == 0.9
        assert result.value is not None
        assert "test@example.com" in result.value

    @pytest.mark.asyncio
    async def test_enrich_failure(self):
        source = AIAgentSource()
        mock_result = make_agent_result(success=False, data={}, confidence=0.0, error="No pages found")

        with patch("app.sources.ai_agent.AgentLoop") as MockLoop:
            mock_loop = MagicMock()
            mock_loop.run = AsyncMock(return_value=mock_result)
            MockLoop.return_value = mock_loop

            result = await source.enrich({}, "Find email")

        assert result.found is False
        assert result.error == "No pages found"
        assert result.source_name == "ai_agent"

    @pytest.mark.asyncio
    async def test_enrich_no_data_value_is_none(self):
        source = AIAgentSource()
        mock_result = make_agent_result(success=False, data={}, confidence=0.0, error=None)

        with patch("app.sources.ai_agent.AgentLoop") as MockLoop:
            mock_loop = MagicMock()
            mock_loop.run = AsyncMock(return_value=mock_result)
            MockLoop.return_value = mock_loop

            result = await source.enrich({}, "Find something")

        # Empty dict is falsy, so value should be None
        assert result.value is None

    @pytest.mark.asyncio
    async def test_enrich_passes_context_to_agent(self):
        source = AIAgentSource()
        mock_result = make_agent_result()
        row_data = {"company": "Acme", "name": "Jane Smith"}

        with patch("app.sources.ai_agent.AgentLoop") as MockLoop:
            mock_loop = MagicMock()
            mock_loop.run = AsyncMock(return_value=mock_result)
            MockLoop.return_value = mock_loop

            await source.enrich(row_data, "Find email for Jane")

        mock_loop.run.assert_called_once_with(prompt="Find email for Jane", context=row_data)

    @pytest.mark.asyncio
    async def test_health_check_always_true(self):
        source = AIAgentSource()
        assert await source.health_check() is True

    def test_name_and_rate_limit(self):
        source = AIAgentSource()
        assert source.name == "ai_agent"
        assert source.rate_limit_per_minute == 10


# ---------------------------------------------------------------------------
# format_agent_data
# ---------------------------------------------------------------------------

class TestFormatAgentData:
    def test_formats_contact_with_all_fields(self):
        data = {"full_name": "Rajesh Kumar", "title": "VP HR", "linkedin_url": "linkedin.com/in/rajesh"}
        assert format_agent_data(data) == "Rajesh Kumar — VP HR — linkedin.com/in/rajesh"

    def test_formats_contact_name_and_title_only(self):
        data = {"full_name": "Alice Smith", "title": "CTO"}
        assert format_agent_data(data) == "Alice Smith — CTO"

    def test_formats_contact_name_only(self):
        data = {"full_name": "Bob Jones"}
        assert format_agent_data(data) == "Bob Jones"

    def test_formats_summary_data(self):
        data = {"summary": "TCS is a global IT services company"}
        assert format_agent_data(data) == "TCS is a global IT services company"

    def test_formats_generic_data_with_pipe_join(self):
        data = {"field1": "value1", "field2": "value2"}
        result = format_agent_data(data)
        assert "value1" in result
        assert "value2" in result

    def test_empty_dict_returns_empty_string(self):
        assert format_agent_data({}) == ""

    def test_skips_empty_values_in_contact(self):
        data = {"full_name": "Alice", "title": "", "linkedin_url": "linkedin.com/in/alice"}
        assert format_agent_data(data) == "Alice — linkedin.com/in/alice"


# ---------------------------------------------------------------------------
# HunterSource
# ---------------------------------------------------------------------------

class TestHunterSource:
    @pytest.mark.asyncio
    async def test_enrich_returns_email_on_success(self):
        source = HunterSource()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {"email": "john.doe@example.com", "score": 82}
        }

        with patch("app.sources.hunter.settings") as mock_settings, \
             patch("app.sources.hunter.httpx.AsyncClient") as MockClient:
            mock_settings.hunter_api_key = "test_key"
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await source.enrich(
                {"domain": "example.com", "name": "John Doe"},
                "Find email"
            )

        assert result.found is True
        assert result.value == "john.doe@example.com"
        assert result.confidence == pytest.approx(0.82)
        assert result.source_name == "hunter"

    @pytest.mark.asyncio
    async def test_enrich_no_email_in_response(self):
        source = HunterSource()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {}}

        with patch("app.sources.hunter.settings") as mock_settings, \
             patch("app.sources.hunter.httpx.AsyncClient") as MockClient:
            mock_settings.hunter_api_key = "test_key"
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await source.enrich({"domain": "example.com"}, "Find email")

        assert result.found is False
        assert result.source_name == "hunter"

    @pytest.mark.asyncio
    async def test_enrich_no_domain_or_company(self):
        source = HunterSource()
        with patch("app.sources.hunter.settings") as mock_settings:
            mock_settings.hunter_api_key = "test_key"
            result = await source.enrich({"name": "John Doe"}, "Find email")

        assert result.found is False
        assert "No domain or company" in result.error

    @pytest.mark.asyncio
    async def test_enrich_no_api_key(self):
        source = HunterSource()
        with patch("app.sources.hunter.settings") as mock_settings:
            mock_settings.hunter_api_key = ""
            result = await source.enrich({"domain": "example.com"}, "Find email")

        assert result.found is False
        assert "API key not configured" in result.error

    @pytest.mark.asyncio
    async def test_enrich_http_exception(self):
        source = HunterSource()
        import httpx

        with patch("app.sources.hunter.settings") as mock_settings, \
             patch("app.sources.hunter.httpx.AsyncClient") as MockClient:
            mock_settings.hunter_api_key = "test_key"
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await source.enrich({"domain": "example.com"}, "Find email")

        assert result.found is False
        assert result.error != ""

    @pytest.mark.asyncio
    async def test_health_check_with_key(self):
        source = HunterSource()
        with patch("app.sources.hunter.settings") as mock_settings:
            mock_settings.hunter_api_key = "somekey"
            assert await source.health_check() is True

    @pytest.mark.asyncio
    async def test_health_check_without_key(self):
        source = HunterSource()
        with patch("app.sources.hunter.settings") as mock_settings:
            mock_settings.hunter_api_key = ""
            assert await source.health_check() is False

    @pytest.mark.asyncio
    async def test_enrich_uses_company_when_no_domain(self):
        source = HunterSource()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"email": "ceo@acme.com", "score": 70}}

        with patch("app.sources.hunter.settings") as mock_settings, \
             patch("app.sources.hunter.httpx.AsyncClient") as MockClient:
            mock_settings.hunter_api_key = "key"
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await source.enrich({"Company": "Acme Corp"}, "Find email")

        assert result.found is True
        # Verify company param was sent
        call_kwargs = mock_client.get.call_args
        params = call_kwargs[1].get("params", call_kwargs[0][1] if len(call_kwargs[0]) > 1 else {})
        assert "company" in params


# ---------------------------------------------------------------------------
# ApolloSource
# ---------------------------------------------------------------------------

class TestApolloSource:
    @pytest.mark.asyncio
    async def test_enrich_success_with_email(self):
        source = ApolloSource()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "people": [{
                "name": "Jane Smith",
                "title": "CTO",
                "email": "jane@startup.io",
                "linkedin_url": "https://linkedin.com/in/janesmith",
                "organization": {"name": "Startup Inc"},
            }]
        }

        with patch("app.sources.apollo.settings") as mock_settings, \
             patch("app.sources.apollo.httpx.AsyncClient") as MockClient:
            mock_settings.apollo_api_key = "apollo_key"
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await source.enrich(
                {"company": "Startup Inc", "title": "CTO"},
                "Find CTO email"
            )

        assert result.found is True
        assert result.value == "jane@startup.io"
        assert result.confidence == pytest.approx(0.8)
        assert result.source_name == "apollo"
        assert result.data["name"] == "Jane Smith"
        assert result.data["organization"] == "Startup Inc"

    @pytest.mark.asyncio
    async def test_enrich_person_without_email(self):
        source = ApolloSource()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "people": [{
                "name": "Bob Jones",
                "title": "VP",
                "email": None,
                "linkedin_url": "",
                "organization": {"name": "Corp"},
            }]
        }

        with patch("app.sources.apollo.settings") as mock_settings, \
             patch("app.sources.apollo.httpx.AsyncClient") as MockClient:
            mock_settings.apollo_api_key = "apollo_key"
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await source.enrich({"company": "Corp"}, "Find email")

        assert result.found is False
        assert result.confidence == pytest.approx(0.3)

    @pytest.mark.asyncio
    async def test_enrich_no_api_key(self):
        source = ApolloSource()
        with patch("app.sources.apollo.settings") as mock_settings:
            mock_settings.apollo_api_key = ""
            result = await source.enrich({"company": "Corp"}, "Find email")

        assert result.found is False
        assert "API key not configured" in result.error

    @pytest.mark.asyncio
    async def test_enrich_no_company_or_domain(self):
        source = ApolloSource()
        with patch("app.sources.apollo.settings") as mock_settings:
            mock_settings.apollo_api_key = "key"
            result = await source.enrich({"name": "Jane"}, "Find email")

        assert result.found is False
        assert "No company or domain" in result.error

    @pytest.mark.asyncio
    async def test_enrich_empty_people_list(self):
        source = ApolloSource()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"people": []}

        with patch("app.sources.apollo.settings") as mock_settings, \
             patch("app.sources.apollo.httpx.AsyncClient") as MockClient:
            mock_settings.apollo_api_key = "key"
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await source.enrich({"company": "Corp"}, "Find email")

        assert result.found is False
        assert "no results" in result.error.lower()

    @pytest.mark.asyncio
    async def test_enrich_http_exception(self):
        source = ApolloSource()
        import httpx

        with patch("app.sources.apollo.settings") as mock_settings, \
             patch("app.sources.apollo.httpx.AsyncClient") as MockClient:
            mock_settings.apollo_api_key = "key"
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=httpx.ConnectError("Failed"))
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await source.enrich({"company": "Corp"}, "Find email")

        assert result.found is False
        assert result.error != ""

    @pytest.mark.asyncio
    async def test_health_check_with_key(self):
        source = ApolloSource()
        with patch("app.sources.apollo.settings") as mock_settings:
            mock_settings.apollo_api_key = "key"
            assert await source.health_check() is True

    @pytest.mark.asyncio
    async def test_health_check_without_key(self):
        source = ApolloSource()
        with patch("app.sources.apollo.settings") as mock_settings:
            mock_settings.apollo_api_key = ""
            assert await source.health_check() is False

    @pytest.mark.asyncio
    async def test_enrich_with_domain(self):
        source = ApolloSource()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "people": [{
                "name": "Alice",
                "title": "",
                "email": "alice@corp.com",
                "linkedin_url": "",
                "organization": {"name": "Corp"},
            }]
        }

        with patch("app.sources.apollo.settings") as mock_settings, \
             patch("app.sources.apollo.httpx.AsyncClient") as MockClient:
            mock_settings.apollo_api_key = "key"
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await source.enrich({"domain": "corp.com"}, "Find email")

        assert result.found is True
        assert result.value == "alice@corp.com"


# ---------------------------------------------------------------------------
# EmailPatternSource
# ---------------------------------------------------------------------------

def _make_unverified_source():
    """Return an EmailPatternSource whose verifier always fails (falls through to unverified guess)."""
    from unittest.mock import AsyncMock
    from app.scraper.email_verifier import VerifyResult, EmailVerifyStatus
    source = EmailPatternSource()
    # is_catch_all raises so the except branch is taken → unverified fallback
    source.verifier.is_catch_all = AsyncMock(side_effect=Exception("network unavailable"))
    return source


class TestEmailPatternSource:
    @pytest.mark.asyncio
    async def test_generates_correct_patterns(self):
        source = _make_unverified_source()
        result = await source.enrich(
            {"name": "John Doe", "domain": "example.com"},
            "Find email"
        )

        assert result.found is True
        assert result.value == "john.doe@example.com"  # first pattern (most common)
        candidates = result.data["candidates"]
        assert "john.doe@example.com" in candidates
        assert "johndoe@example.com" in candidates
        assert "jdoe@example.com" in candidates
        assert "j.doe@example.com" in candidates
        assert "john_doe@example.com" in candidates

    @pytest.mark.asyncio
    async def test_no_name_returns_failure(self):
        source = EmailPatternSource()
        result = await source.enrich({"domain": "example.com"}, "Find email")

        assert result.found is False
        assert "No name" in result.error

    @pytest.mark.asyncio
    async def test_no_domain_or_company_returns_failure(self):
        source = EmailPatternSource()
        result = await source.enrich({"name": "John Doe"}, "Find email")

        assert result.found is False
        assert "No domain or company" in result.error

    @pytest.mark.asyncio
    async def test_single_name_returns_failure(self):
        source = EmailPatternSource()
        result = await source.enrich(
            {"name": "Madonna", "domain": "example.com"},
            "Find email"
        )

        assert result.found is False
        assert "first and last name" in result.error

    @pytest.mark.asyncio
    async def test_derives_domain_from_company(self):
        source = _make_unverified_source()
        result = await source.enrich(
            {"name": "Alice Brown", "Company": "Tech Corp"},
            "Find email"
        )

        assert result.found is True
        assert "@techcorp.com" in result.value

    @pytest.mark.asyncio
    async def test_strips_protocol_from_domain(self):
        source = _make_unverified_source()
        result = await source.enrich(
            {"name": "Bob Smith", "website": "https://www.acme.com/about"},
            "Find email"
        )

        assert result.found is True
        assert "@acme.com" in result.value
        assert "https" not in result.value
        assert "www" not in result.value

    @pytest.mark.asyncio
    async def test_uses_recruiter_field_for_name(self):
        source = _make_unverified_source()
        result = await source.enrich(
            {"Recruiter": "Carol White", "domain": "jobs.com"},
            "Find email"
        )

        assert result.found is True
        assert "carol" in result.value

    @pytest.mark.asyncio
    async def test_confidence_is_moderate_when_unverified(self):
        source = _make_unverified_source()
        result = await source.enrich(
            {"name": "Test User", "domain": "test.com"},
            "Find email"
        )

        assert result.confidence == pytest.approx(0.4)

    @pytest.mark.asyncio
    async def test_method_label_unverified_in_data(self):
        source = _make_unverified_source()
        result = await source.enrich(
            {"name": "Test User", "domain": "test.com"},
            "Find email"
        )

        assert result.data["method"] == "pattern_unverified"

    @pytest.mark.asyncio
    async def test_special_chars_stripped_from_name(self):
        source = _make_unverified_source()
        result = await source.enrich(
            {"name": "O'Brien Smith", "domain": "co.com"},
            "Find email"
        )

        assert result.found is True
        # Special chars should be removed from email
        assert "'" not in result.value

    @pytest.mark.asyncio
    async def test_health_check_always_true(self):
        source = EmailPatternSource()
        assert await source.health_check() is True

    @pytest.mark.asyncio
    async def test_uses_key_contact_field(self):
        """EmailPatternSource should accept 'Key Contact' as a name source."""
        source = _make_unverified_source()
        row_data = {"Key Contact": "Alice Smith", "Company": "TCS"}
        result = await source.enrich(row_data, "Find email")
        assert result.found is True
        assert "alice" in result.value
        assert "tcs.com" in result.value

    @pytest.mark.asyncio
    async def test_parses_structured_contact_for_name(self):
        """EmailPatternSource should extract name from structured contact value."""
        source = _make_unverified_source()
        row_data = {"Key Contact": "Alice Smith — CTO — linkedin.com/in/alice", "Company": "TCS"}
        result = await source.enrich(row_data, "Find email")
        assert result.found is True
        assert "alice" in result.value
        assert "tcs.com" in result.value


# ---------------------------------------------------------------------------
# WaterfallEngine
# ---------------------------------------------------------------------------

def make_mock_source(name, found, value=None, healthy=True, raises=False):
    source = MagicMock(spec=EnrichmentSource)
    source.name = name
    source.health_check = AsyncMock(return_value=healthy)

    if raises:
        source.enrich = AsyncMock(side_effect=Exception(f"{name} exploded"))
    else:
        source.enrich = AsyncMock(return_value=SourceResult(
            found=found,
            value=value,
            source_name=name,
        ))
    return source


class TestWaterfallEngine:
    @pytest.mark.asyncio
    async def test_returns_first_hit(self):
        s1 = make_mock_source("s1", found=False)
        s2 = make_mock_source("s2", found=True, value="found@example.com")
        s3 = make_mock_source("s3", found=True, value="also_found@example.com")

        engine = WaterfallEngine([s1, s2, s3])
        result = await engine.run({}, "Find email")

        assert result.found is True
        assert result.value == "found@example.com"
        assert result.source_name == "s2"
        # s3 should never be called
        s3.enrich.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_failure_when_all_fail(self):
        s1 = make_mock_source("s1", found=False)
        s2 = make_mock_source("s2", found=False)

        engine = WaterfallEngine([s1, s2])
        result = await engine.run({}, "Find email")

        assert result.found is False
        assert result.source_name == "waterfall"
        assert "exhausted" in result.error.lower()

    @pytest.mark.asyncio
    async def test_skips_unhealthy_source(self):
        s1 = make_mock_source("s1", found=True, value="val", healthy=False)
        s2 = make_mock_source("s2", found=True, value="backup@example.com")

        engine = WaterfallEngine([s1, s2])
        result = await engine.run({}, "Find email")

        assert result.found is True
        assert result.source_name == "s2"
        s1.enrich.assert_not_called()

    @pytest.mark.asyncio
    async def test_continues_after_exception(self):
        s1 = make_mock_source("s1", found=True, value="x", raises=True)
        s2 = make_mock_source("s2", found=True, value="safe@example.com")

        engine = WaterfallEngine([s1, s2])
        result = await engine.run({}, "Find email")

        assert result.found is True
        assert result.value == "safe@example.com"

    @pytest.mark.asyncio
    async def test_empty_sources_returns_failure(self):
        engine = WaterfallEngine([])
        result = await engine.run({}, "Find email")

        assert result.found is False
        assert result.source_name == "waterfall"

    @pytest.mark.asyncio
    async def test_found_true_but_no_value_continues(self):
        # found=True but value=None should not be counted as a hit
        s1 = make_mock_source("s1", found=True, value=None)
        s2 = make_mock_source("s2", found=True, value="real@example.com")

        engine = WaterfallEngine([s1, s2])
        result = await engine.run({}, "Find email")

        assert result.value == "real@example.com"
        assert result.source_name == "s2"

    def test_from_config_builds_waterfall(self):
        engine = WaterfallEngine.from_config(["email_pattern", "hunter", "apollo"])
        assert len(engine.sources) == 3
        names = [s.name for s in engine.sources]
        assert "email_pattern" in names
        assert "hunter" in names
        assert "apollo" in names

    def test_from_config_ignores_unknown_names(self):
        engine = WaterfallEngine.from_config(["email_pattern", "nonexistent_source"])
        assert len(engine.sources) == 1
        assert engine.sources[0].name == "email_pattern"

    @pytest.mark.asyncio
    async def test_passes_row_data_and_prompt_to_source(self):
        s1 = make_mock_source("s1", found=True, value="x@y.com")
        row_data = {"company": "ACME", "name": "Wile E Coyote"}
        prompt = "Find contact email"

        engine = WaterfallEngine([s1])
        await engine.run(row_data, prompt)

        s1.enrich.assert_called_once_with(row_data, prompt)

    @pytest.mark.asyncio
    async def test_resolves_key_contact_column_name(self):
        """Waterfall should find person name from 'Key Contact' row_data key."""
        s1 = make_mock_source("s1", found=True, value="test@tcs.com")
        engine = WaterfallEngine([s1])
        row_data = {"Key Contact": "Rajesh Kumar", "Company": "TCS"}
        await engine.run(row_data, "Find email")
        s1.enrich.assert_called_once_with(row_data, "Find email")

    @pytest.mark.asyncio
    async def test_parses_structured_contact_value(self):
        """Waterfall should extract name from 'Name — Title — URL' format."""
        s1 = make_mock_source("s1", found=True, value="test@tcs.com")
        engine = WaterfallEngine([s1])
        row_data = {"Key Contact": "Rajesh Kumar — VP HR — linkedin.com/in/rajesh", "Company": "TCS"}
        result = await engine.run(row_data, "Find email")
        assert result.found is True


# ---------------------------------------------------------------------------
# QuotaTracker
# ---------------------------------------------------------------------------

class TestQuotaTracker:
    def test_can_use_new_source_within_limit(self):
        tracker = QuotaTracker()
        assert tracker.can_use("hunter") is True
        assert tracker.can_use("apollo") is True

    def test_record_use_increments_count(self):
        tracker = QuotaTracker()
        tracker.record_use("hunter")
        tracker.record_use("hunter")
        usage = tracker.get_usage()
        assert usage["hunter"]["used"] == 2

    def test_can_use_returns_false_when_limit_reached(self):
        tracker = QuotaTracker()
        # Exhaust hunter quota (25 uses)
        for _ in range(25):
            tracker.record_use("hunter")
        assert tracker.can_use("hunter") is False

    def test_can_use_unknown_source_returns_true(self):
        tracker = QuotaTracker()
        assert tracker.can_use("unknown_source") is True

    def test_record_use_unknown_source_no_error(self):
        tracker = QuotaTracker()
        tracker.record_use("not_a_real_source")  # Should not raise

    def test_get_usage_returns_all_sources(self):
        tracker = QuotaTracker()
        usage = tracker.get_usage()
        assert "hunter" in usage
        assert "apollo" in usage
        assert "ai_agent" in usage
        assert "email_pattern" in usage

    def test_get_usage_shows_remaining(self):
        tracker = QuotaTracker()
        tracker.record_use("apollo")
        tracker.record_use("apollo")
        usage = tracker.get_usage()
        assert usage["apollo"]["used"] == 2
        assert usage["apollo"]["remaining"] == 58
        assert usage["apollo"]["limit"] == 60

    def test_quota_resets_after_period(self):
        from datetime import datetime, timedelta
        tracker = QuotaTracker()
        # Exhaust the quota
        for _ in range(25):
            tracker.record_use("hunter")
        assert tracker.can_use("hunter") is False

        # Force reset by backdating reset_at
        tracker.quotas["hunter"].reset_at = datetime.now() - timedelta(seconds=1)
        assert tracker.can_use("hunter") is True
        assert tracker.quotas["hunter"].used == 0

    def test_ai_agent_effectively_unlimited(self):
        tracker = QuotaTracker()
        # Use 1000 times — still within "unlimited" limit
        for _ in range(1000):
            tracker.record_use("ai_agent")
        assert tracker.can_use("ai_agent") is True

    def test_independent_instances_dont_share_state(self):
        tracker1 = QuotaTracker()
        tracker2 = QuotaTracker()
        tracker1.record_use("hunter")
        assert tracker2.get_usage()["hunter"]["used"] == 0


# ---------------------------------------------------------------------------
# Sources registry
# ---------------------------------------------------------------------------

class TestSourcesRegistry:
    def test_get_source_by_name_returns_correct_instance(self):
        source = get_source_by_name("email_pattern")
        assert isinstance(source, EmailPatternSource)

    def test_get_source_by_name_unknown_returns_none(self):
        source = get_source_by_name("does_not_exist")
        assert source is None

    def test_get_all_sources_returns_all_five(self):
        sources = get_all_sources()
        names = {s.name for s in sources}
        assert names == {"ai_agent", "hunter", "apollo", "email_pattern", "linkedin"}

    def test_get_source_by_name_returns_new_instance_each_call(self):
        s1 = get_source_by_name("hunter")
        s2 = get_source_by_name("hunter")
        assert s1 is not s2
