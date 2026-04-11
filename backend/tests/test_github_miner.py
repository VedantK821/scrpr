import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.github_email_miner import (
    mine_github_emails, _is_real_email, _detect_pattern, MineResult
)


class TestIsRealEmail:
    def test_normal_email(self):
        assert _is_real_email("john.doe@company.com") is True

    def test_noreply(self):
        assert _is_real_email("noreply@github.com") is False

    def test_github_noreply(self):
        assert _is_real_email("12345+user@users.noreply.github.com") is False

    def test_bot_email(self):
        assert _is_real_email("dependabot@github.com") is False

    def test_renovate_bot(self):
        assert _is_real_email("renovate-bot@company.com") is False

    def test_plus_addressed(self):
        assert _is_real_email("user+tag@company.com") is False

    def test_actions(self):
        assert _is_real_email("actions@github.com") is False


class TestDetectPattern:
    def test_first_dot_last(self):
        emails = ["john.doe@co.com", "jane.smith@co.com", "bob.jones@co.com"]
        assert _detect_pattern(emails, "co.com") == "first.last"

    def test_firstlast_no_dot(self):
        emails = ["johndoe@co.com", "janesmith@co.com"]
        assert _detect_pattern(emails, "co.com") == "firstlast"

    def test_underscore(self):
        emails = ["john_doe@co.com", "jane_smith@co.com"]
        assert _detect_pattern(emails, "co.com") == "first_last"

    def test_empty(self):
        assert _detect_pattern([], "co.com") == ""


class TestMineGithubEmails:
    @pytest.mark.asyncio
    async def test_returns_mine_result(self):
        """mine_github_emails returns a MineResult even when no results found."""
        with patch("app.services.github_email_miner.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            # Org search returns empty
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"items": []}
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            result = await mine_github_emails("SomeCompany", "somecompany.com")
            assert isinstance(result, MineResult)
            assert result.emails == []
            assert result.company == "SomeCompany"

    @pytest.mark.asyncio
    async def test_filters_to_expected_domain(self):
        """Only returns emails matching the expected domain."""
        # This test verifies the domain filtering logic
        with patch("app.services.github_email_miner.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()

            # Org search
            org_resp = MagicMock()
            org_resp.status_code = 200
            org_resp.json.return_value = {"items": [{"login": "testorg"}]}

            # Repos
            repos_resp = MagicMock()
            repos_resp.status_code = 200
            repos_resp.json.return_value = [{"full_name": "testorg/repo1"}]

            # Commits with mixed domains
            commits_resp = MagicMock()
            commits_resp.status_code = 200
            commits_resp.json.return_value = [
                {"commit": {"author": {"email": "alice@target.com"}}},
                {"commit": {"author": {"email": "bob@otherdomain.com"}}},
                {"commit": {"author": {"email": "carol@target.com"}}},
                {"commit": {"author": {"email": "noreply@github.com"}}},
            ]

            mock_client.get = AsyncMock(side_effect=[org_resp, repos_resp, commits_resp])
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            result = await mine_github_emails("Target", "target.com")
            assert "alice@target.com" in result.emails
            assert "carol@target.com" in result.emails
            assert "bob@otherdomain.com" not in result.emails
            assert "noreply@github.com" not in result.emails
            assert result.pattern == "short"  # "alice" and "carol" are short
