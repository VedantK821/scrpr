import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.email_sender import EmailSender, SendResult


class TestSendNoSmtp:
    @pytest.mark.asyncio
    async def test_send_returns_error_when_smtp_not_configured(self):
        """When smtp_host/user/pass are empty, return error without connecting."""
        sender = EmailSender()
        with patch("app.services.email_sender.settings") as mock_settings:
            mock_settings.smtp_host = ""
            mock_settings.smtp_port = 587
            mock_settings.smtp_user = ""
            mock_settings.smtp_pass = ""
            result = await sender.send(
                to="bob@example.com",
                subject="Test",
                body="Hello",
            )
        assert result.success is False
        assert "not configured" in result.error.lower()

    @pytest.mark.asyncio
    async def test_send_returns_error_when_only_host_set(self):
        """Missing user still triggers SMTP not configured."""
        sender = EmailSender()
        with patch("app.services.email_sender.settings") as mock_settings:
            mock_settings.smtp_host = "smtp.example.com"
            mock_settings.smtp_port = 587
            mock_settings.smtp_user = ""
            mock_settings.smtp_pass = ""
            result = await sender.send(
                to="bob@example.com",
                subject="Test",
                body="Hello",
            )
        assert result.success is False


class TestSendWithSmtp:
    @pytest.mark.asyncio
    async def test_send_succeeds_with_mocked_smtp(self):
        """When SMTP is configured and the server accepts the message, return success."""
        sender = EmailSender()

        with patch("app.services.email_sender.settings") as mock_settings, \
             patch("app.services.email_sender.smtplib.SMTP") as mock_smtp_cls:

            mock_settings.smtp_host = "smtp.example.com"
            mock_settings.smtp_port = 587
            mock_settings.smtp_user = "user@example.com"
            mock_settings.smtp_pass = "secret"

            # Set up the SMTP context manager mock
            mock_server = MagicMock()
            mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
            mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

            result = await sender.send(
                to="recipient@example.com",
                subject="Hello",
                body="World",
            )

        assert result.success is True
        assert result.error == ""

    @pytest.mark.asyncio
    async def test_send_bounced_on_recipients_refused(self):
        """SMTPRecipientsRefused maps to bounced error."""
        import smtplib
        sender = EmailSender()

        with patch("app.services.email_sender.settings") as mock_settings, \
             patch.object(sender, "_send_smtp", side_effect=smtplib.SMTPRecipientsRefused({})):

            mock_settings.smtp_host = "smtp.example.com"
            mock_settings.smtp_port = 587
            mock_settings.smtp_user = "user@example.com"
            mock_settings.smtp_pass = "secret"

            result = await sender.send(
                to="bad@example.com",
                subject="Hi",
                body="Test",
            )

        assert result.success is False
        assert "bounced" in result.error.lower()

    @pytest.mark.asyncio
    async def test_send_auth_error(self):
        """SMTPAuthenticationError maps to authentication error."""
        import smtplib
        sender = EmailSender()

        with patch("app.services.email_sender.settings") as mock_settings, \
             patch.object(sender, "_send_smtp", side_effect=smtplib.SMTPAuthenticationError(535, b"Auth failed")):

            mock_settings.smtp_host = "smtp.example.com"
            mock_settings.smtp_port = 587
            mock_settings.smtp_user = "user@example.com"
            mock_settings.smtp_pass = "wrong"

            result = await sender.send(
                to="recipient@example.com",
                subject="Hi",
                body="Test",
            )

        assert result.success is False
        assert "authentication" in result.error.lower()


class TestSendBatch:
    @pytest.mark.asyncio
    async def test_send_batch_sends_all_emails(self):
        """send_batch sends every email in the list."""
        sender = EmailSender(delay_seconds=0.0)

        emails = [
            {"to": "a@example.com", "subject": "Sub A", "body": "Body A"},
            {"to": "b@example.com", "subject": "Sub B", "body": "Body B"},
        ]

        with patch.object(sender, "send", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = SendResult(success=True)
            with patch("app.services.email_sender.asyncio.sleep", new_callable=AsyncMock):
                results = await sender.send_batch(emails)

        assert len(results) == 2
        assert all(r.success for r in results)
        assert mock_send.call_count == 2

    @pytest.mark.asyncio
    async def test_send_batch_sleeps_between_sends(self):
        """send_batch waits between emails but not after the last one."""
        sender = EmailSender(delay_seconds=5.0)

        emails = [
            {"to": "a@example.com", "subject": "A", "body": "A"},
            {"to": "b@example.com", "subject": "B", "body": "B"},
            {"to": "c@example.com", "subject": "C", "body": "C"},
        ]

        with patch.object(sender, "send", new_callable=AsyncMock) as mock_send, \
             patch("app.services.email_sender.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_send.return_value = SendResult(success=True)
            await sender.send_batch(emails)

        # 3 emails → 2 sleeps (not after the last)
        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(5.0)

    @pytest.mark.asyncio
    async def test_send_batch_no_sleep_for_single_email(self):
        """send_batch does not sleep when only one email is sent."""
        sender = EmailSender(delay_seconds=30.0)

        emails = [{"to": "a@example.com", "subject": "A", "body": "A"}]

        with patch.object(sender, "send", new_callable=AsyncMock) as mock_send, \
             patch("app.services.email_sender.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_send.return_value = SendResult(success=True)
            await sender.send_batch(emails)

        assert mock_sleep.call_count == 0
