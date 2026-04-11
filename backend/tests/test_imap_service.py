import pytest
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone

from app.services.imap_service import (
    IMAPService, DetectedReply, DetectedBounce,
    _is_auto_reply, _decode_subject, _parse_bounce,
)


class TestIsAutoReply:
    def test_auto_submitted_header(self):
        msg = email.message.Message()
        msg["Auto-Submitted"] = "auto-replied"
        assert _is_auto_reply(msg) is True

    def test_out_of_office_subject(self):
        msg = email.message.Message()
        msg["Subject"] = "Out of Office: Re: Your inquiry"
        assert _is_auto_reply(msg) is True

    def test_normal_reply(self):
        msg = email.message.Message()
        msg["Subject"] = "Re: Let's connect"
        assert _is_auto_reply(msg) is False

    def test_precedence_bulk(self):
        msg = email.message.Message()
        msg["Precedence"] = "bulk"
        assert _is_auto_reply(msg) is True

    def test_auto_submitted_no(self):
        msg = email.message.Message()
        msg["Auto-Submitted"] = "no"
        assert _is_auto_reply(msg) is False


class TestDecodeSubject:
    def test_plain_subject(self):
        assert _decode_subject("Hello World") == "Hello World"

    def test_empty_subject(self):
        assert _decode_subject("") == ""


class TestParseBounce:
    def test_plain_text_hard_bounce(self):
        msg = MIMEText("The email address user@example.com does not exist. 550 User unknown.")
        msg["From"] = "mailer-daemon@example.com"
        msg["Subject"] = "Mail delivery failed"

        bounce = _parse_bounce(msg)
        assert bounce is not None
        assert bounce.original_recipient == "user@example.com"
        assert bounce.bounce_type == "hard"

    def test_soft_bounce_quota(self):
        msg = MIMEText("Mailbox for user@example.com is full. 452 try again later.")
        bounce = _parse_bounce(msg)
        assert bounce is not None
        assert bounce.bounce_type == "soft"

    def test_non_bounce_message(self):
        msg = MIMEText("Just a regular email, nothing bouncy here.")
        bounce = _parse_bounce(msg)
        assert bounce is None


class TestIMAPService:
    def test_not_configured(self):
        service = IMAPService()
        assert service.is_configured() is False

    def test_configured(self):
        service = IMAPService(host="imap.gmail.com", username="user", password="pass")
        assert service.is_configured() is True

    @pytest.mark.asyncio
    async def test_find_replies_not_configured(self):
        service = IMAPService()
        result = await service.find_replies({"<msg@id>"})
        assert result == []

    @pytest.mark.asyncio
    async def test_find_bounces_not_configured(self):
        service = IMAPService()
        result = await service.find_bounces()
        assert result == []
