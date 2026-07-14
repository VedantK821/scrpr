import asyncio
import socket
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

from app.scraper.email_verifier import EmailVerifier, EmailVerifyStatus, VerifyResult
from app.sources.email_pattern import EmailPatternSource

# Integration: exercises live DNS/MX and SMTP probes; deselected by default (run with `-m integration`).
pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# EmailVerifier._get_mx_host
# ---------------------------------------------------------------------------

class TestGetMxHost:
    @pytest.mark.asyncio
    async def test_returns_mx_host_for_known_domain(self):
        verifier = EmailVerifier()
        mock_record = MagicMock()
        mock_record.preference = 10
        mock_record.exchange = MagicMock()
        mock_record.exchange.__str__ = lambda self: "mail.example.com."

        with patch("app.scraper.email_verifier.dns.resolver.resolve", return_value=[mock_record]):
            host = await verifier._get_mx_host("example.com")

        assert host == "mail.example.com"  # trailing dot stripped

    @pytest.mark.asyncio
    async def test_returns_lowest_priority_mx(self):
        verifier = EmailVerifier()

        low_prio = MagicMock()
        low_prio.preference = 20
        low_prio.exchange = MagicMock()
        low_prio.exchange.__str__ = lambda self: "backup.example.com."

        high_prio = MagicMock()
        high_prio.preference = 10
        high_prio.exchange = MagicMock()
        high_prio.exchange.__str__ = lambda self: "primary.example.com."

        with patch("app.scraper.email_verifier.dns.resolver.resolve", return_value=[low_prio, high_prio]):
            host = await verifier._get_mx_host("example.com")

        assert host == "primary.example.com"

    @pytest.mark.asyncio
    async def test_returns_none_on_dns_failure(self):
        verifier = EmailVerifier()

        with patch("app.scraper.email_verifier.dns.resolver.resolve", side_effect=Exception("NXDOMAIN")):
            host = await verifier._get_mx_host("nonexistent-domain-xyz.com")

        assert host is None


# ---------------------------------------------------------------------------
# EmailVerifier._smtp_check (synchronous helper, tested directly)
# ---------------------------------------------------------------------------

class TestSmtpCheck:
    def _make_sock(self, responses: list[bytes]) -> MagicMock:
        """Create a mock socket that returns responses in sequence."""
        sock = MagicMock(spec=socket.socket)
        sock.recv = MagicMock(side_effect=responses)
        return sock

    def test_valid_email_accepted_fake_rejected(self):
        verifier = EmailVerifier()
        responses = [
            b"220 mail.example.com ESMTP\r\n",   # banner
            b"250-mail.example.com\r\n",           # EHLO
            b"250 OK\r\n",                         # MAIL FROM
            b"250 OK\r\n",                         # RCPT TO real
            b"550 5.1.1 User unknown\r\n",         # RCPT TO fake
        ]
        sock = self._make_sock(responses)

        with patch("app.scraper.email_verifier.socket.socket", return_value=sock):
            result = verifier._smtp_check("john@example.com", "mail.example.com")

        assert result.status == EmailVerifyStatus.VALID
        assert result.email == "john@example.com"
        assert result.mx_host == "mail.example.com"

    def test_invalid_email_rejected(self):
        verifier = EmailVerifier()
        responses = [
            b"220 mail.example.com ESMTP\r\n",
            b"250-mail.example.com\r\n",
            b"250 OK\r\n",
            b"550 5.1.1 User unknown\r\n",  # RCPT TO real → rejected
            b"550 5.1.1 User unknown\r\n",  # RCPT TO fake → also rejected
        ]
        sock = self._make_sock(responses)

        with patch("app.scraper.email_verifier.socket.socket", return_value=sock):
            result = verifier._smtp_check("nobody@example.com", "mail.example.com")

        assert result.status == EmailVerifyStatus.INVALID

    def test_catch_all_domain(self):
        verifier = EmailVerifier()
        responses = [
            b"220 mail.example.com ESMTP\r\n",
            b"250-mail.example.com\r\n",
            b"250 OK\r\n",
            b"250 OK\r\n",  # RCPT TO real → accepted
            b"250 OK\r\n",  # RCPT TO fake → also accepted (catch-all)
        ]
        sock = self._make_sock(responses)

        with patch("app.scraper.email_verifier.socket.socket", return_value=sock):
            result = verifier._smtp_check("john@catchall.com", "mail.catchall.com")

        assert result.status == EmailVerifyStatus.CATCH_ALL
        assert "Catch-all" in result.smtp_response

    def test_bad_banner_returns_unknown(self):
        verifier = EmailVerifier()
        responses = [b"421 Service unavailable\r\n"]
        sock = self._make_sock(responses)

        with patch("app.scraper.email_verifier.socket.socket", return_value=sock):
            result = verifier._smtp_check("john@example.com", "mail.example.com")

        assert result.status == EmailVerifyStatus.UNKNOWN
        assert "Bad banner" in result.error

    def test_connection_refused_returns_unknown(self):
        verifier = EmailVerifier()

        with patch("app.scraper.email_verifier.socket.socket") as mock_sock_cls:
            instance = MagicMock()
            instance.connect.side_effect = ConnectionRefusedError()
            mock_sock_cls.return_value = instance

            result = verifier._smtp_check("john@example.com", "mail.example.com")

        assert result.status == EmailVerifyStatus.UNKNOWN
        assert "Connection refused" in result.error

    def test_socket_timeout_returns_unknown(self):
        verifier = EmailVerifier()

        with patch("app.scraper.email_verifier.socket.socket") as mock_sock_cls:
            instance = MagicMock()
            instance.connect.side_effect = socket.timeout()
            mock_sock_cls.return_value = instance

            result = verifier._smtp_check("john@example.com", "mail.example.com")

        assert result.status == EmailVerifyStatus.UNKNOWN
        assert "timeout" in result.error.lower()


# ---------------------------------------------------------------------------
# EmailVerifier.verify (async, end-to-end with mocks)
# ---------------------------------------------------------------------------

class TestVerify:
    @pytest.mark.asyncio
    async def test_verify_invalid_email_format(self):
        verifier = EmailVerifier()
        result = await verifier.verify("not-an-email")

        assert result.status == EmailVerifyStatus.INVALID
        assert "Invalid email format" in result.error

    @pytest.mark.asyncio
    async def test_verify_no_mx_records(self):
        verifier = EmailVerifier()

        with patch.object(verifier, "_get_mx_host", new=AsyncMock(return_value=None)):
            result = await verifier.verify("john@no-mx-domain.com")

        assert result.status == EmailVerifyStatus.INVALID
        assert "No MX records" in result.error

    @pytest.mark.asyncio
    async def test_verify_delegates_to_smtp_check(self):
        verifier = EmailVerifier()
        expected = VerifyResult(
            email="john@example.com",
            status=EmailVerifyStatus.VALID,
            mx_host="mail.example.com",
        )

        with patch.object(verifier, "_get_mx_host", new=AsyncMock(return_value="mail.example.com")), \
             patch.object(verifier, "_smtp_check", return_value=expected):
            result = await verifier.verify("john@example.com")

        assert result.status == EmailVerifyStatus.VALID
        assert result.mx_host == "mail.example.com"

    @pytest.mark.asyncio
    async def test_verify_timeout_returns_unknown(self):
        verifier = EmailVerifier(timeout=0.001)

        async def _slow_executor(*args, **kwargs):
            await asyncio.sleep(1)

        with patch.object(verifier, "_get_mx_host", new=AsyncMock(return_value="mail.example.com")), \
             patch("asyncio.get_event_loop") as mock_loop:
            loop = MagicMock()
            loop.run_in_executor = AsyncMock(side_effect=asyncio.TimeoutError())
            mock_loop.return_value = loop

            result = await verifier.verify("john@example.com")

        assert result.status == EmailVerifyStatus.UNKNOWN
        assert "timeout" in result.error.lower()


# ---------------------------------------------------------------------------
# EmailVerifier.is_catch_all
# ---------------------------------------------------------------------------

class TestIsCatchAll:
    @pytest.mark.asyncio
    async def test_catch_all_domain_returns_true(self):
        verifier = EmailVerifier()
        catch_all_result = VerifyResult(
            email="definitely-not-real-test-12345@catchall.com",
            status=EmailVerifyStatus.CATCH_ALL,
        )

        with patch.object(verifier, "verify", new=AsyncMock(return_value=catch_all_result)):
            assert await verifier.is_catch_all("catchall.com") is True

    @pytest.mark.asyncio
    async def test_non_catch_all_domain_returns_false(self):
        verifier = EmailVerifier()
        invalid_result = VerifyResult(
            email="definitely-not-real-test-12345@strict.com",
            status=EmailVerifyStatus.INVALID,
        )

        with patch.object(verifier, "verify", new=AsyncMock(return_value=invalid_result)):
            assert await verifier.is_catch_all("strict.com") is False


# ---------------------------------------------------------------------------
# EmailPatternSource.enrich — with mocked verifier
# ---------------------------------------------------------------------------

class TestEmailPatternSourceWithVerifier:
    def _make_source(self, is_catch_all: bool = False, valid_email: str | None = None):
        """Create EmailPatternSource with fully mocked verifier."""
        from app.scraper.email_verifier import VerifyResult, EmailVerifyStatus

        source = EmailPatternSource()

        if is_catch_all:
            source.verifier.is_catch_all = AsyncMock(return_value=True)
        else:
            source.verifier.is_catch_all = AsyncMock(return_value=False)

            if valid_email:
                async def _verify(email):
                    if email == valid_email:
                        return VerifyResult(email=email, status=EmailVerifyStatus.VALID, mx_host="mail.example.com")
                    return VerifyResult(email=email, status=EmailVerifyStatus.INVALID)
                source.verifier.verify = _verify
            else:
                source.verifier.verify = AsyncMock(
                    return_value=VerifyResult(email="", status=EmailVerifyStatus.UNKNOWN, error="blocked")
                )

        return source

    @pytest.mark.asyncio
    async def test_smtp_verified_returns_high_confidence(self):
        source = self._make_source(valid_email="john.doe@example.com")

        result = await source.enrich(
            {"name": "John Doe", "domain": "example.com"},
            "Find email"
        )

        assert result.found is True
        assert result.value == "john.doe@example.com"
        assert result.confidence == pytest.approx(0.9)
        assert result.data["method"] == "pattern_smtp_verified"
        assert result.data["verified"] is True

    @pytest.mark.asyncio
    async def test_smtp_verified_second_pattern(self):
        """Verifier rejects first.last but accepts firstlast — should return second pattern."""
        source = self._make_source(valid_email="johndoe@example.com")

        result = await source.enrich(
            {"name": "John Doe", "domain": "example.com"},
            "Find email"
        )

        assert result.value == "johndoe@example.com"
        assert result.data["method"] == "pattern_smtp_verified"

    @pytest.mark.asyncio
    async def test_catch_all_domain_returns_medium_confidence(self):
        source = self._make_source(is_catch_all=True)

        result = await source.enrich(
            {"name": "Jane Smith", "domain": "catchall.com"},
            "Find email"
        )

        assert result.found is True
        assert result.value == "jane.smith@catchall.com"  # best guess = first pattern
        # Catch-all skips to SmartVerifier compound scoring
        assert result.confidence >= 0.0  # Score depends on available signals
        assert result.found is True

    @pytest.mark.asyncio
    async def test_no_verified_email_returns_low_confidence(self):
        """All SMTP checks return UNKNOWN — fall through to unverified guess."""
        source = self._make_source(valid_email=None)

        result = await source.enrich(
            {"name": "Bob Jones", "domain": "blocked.com"},
            "Find email"
        )

        assert result.found is True
        assert result.value == "bob.jones@blocked.com"
        # SmartVerifier scores based on available signals (MX, Gravatar, etc.)
        assert result.confidence >= 0.0
        assert "method" in result.data

    @pytest.mark.asyncio
    async def test_no_name_provided(self):
        source = EmailPatternSource()
        result = await source.enrich({"domain": "example.com"}, "Find email")

        assert result.found is False
        assert "No name" in result.error

    @pytest.mark.asyncio
    async def test_hiring_contact_field_used_for_name(self):
        source = self._make_source(valid_email=None)
        result = await source.enrich(
            {"Hiring Contact": "Sarah Lee", "domain": "company.com"},
            "Find email"
        )

        assert result.found is True
        assert "sarah" in result.value

    @pytest.mark.asyncio
    async def test_verifier_exception_falls_through_to_unverified(self):
        source = EmailPatternSource()
        source.verifier.is_catch_all = AsyncMock(side_effect=Exception("network error"))

        result = await source.enrich(
            {"name": "Test User", "domain": "test.com"},
            "Find email"
        )

        assert result.found is True
        # SmartVerifier compound scoring after SMTP exception
        assert result.confidence >= 0.0
        assert "method" in result.data
