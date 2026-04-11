import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.linkedin_outreach import LinkedInOutreach, ConnectionResult, MAX_REQUESTS_PER_DAY


class TestLinkedInOutreach:
    def test_check_limits_fresh(self):
        outreach = LinkedInOutreach()
        assert outreach._check_limits() is None

    def test_check_limits_daily_exceeded(self):
        outreach = LinkedInOutreach()
        outreach._sent_today = MAX_REQUESTS_PER_DAY
        error = outreach._check_limits()
        assert error is not None
        assert "Daily limit" in error

    def test_get_limits(self):
        outreach = LinkedInOutreach()
        limits = outreach.get_limits()
        assert limits["sent_today"] == 0
        assert limits["max_per_day"] == MAX_REQUESTS_PER_DAY
        assert limits["remaining_today"] == MAX_REQUESTS_PER_DAY

    @pytest.mark.asyncio
    async def test_send_not_available(self):
        outreach = LinkedInOutreach()
        with patch.object(outreach.scraper, "is_available", return_value=False):
            result = await outreach.send_connection_request("https://linkedin.com/in/test")
        assert result.success is False
        assert "not available" in result.error

    @pytest.mark.asyncio
    async def test_send_rate_limited(self):
        outreach = LinkedInOutreach()
        outreach._sent_today = MAX_REQUESTS_PER_DAY
        result = await outreach.send_connection_request("https://linkedin.com/in/test")
        assert result.success is False
        assert "limit" in result.error.lower()
