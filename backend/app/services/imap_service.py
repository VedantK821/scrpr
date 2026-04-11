"""IMAP service for reply detection and bounce tracking.

Connects to user's inbox, finds replies to sent sequence emails
by matching In-Reply-To headers against stored Message-IDs.
Detects bounces from DSN (Delivery Status Notification) messages.
"""
import asyncio
import email
import imaplib
import logging
import ssl
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.header import decode_header
from email.utils import parsedate_to_datetime

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class DetectedReply:
    """A reply to a sent sequence email."""
    original_message_id: str  # The Message-ID we sent
    from_email: str
    subject: str
    received_at: datetime
    is_auto_reply: bool = False


@dataclass
class DetectedBounce:
    """A bounced email."""
    original_recipient: str
    bounce_type: str  # "hard" or "soft"
    reason: str
    diagnostic_code: str = ""
    received_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


AUTO_REPLY_INDICATORS = [
    "auto-submitted",
    "x-auto-response-suppress",
    "x-autorespond",
    "precedence: bulk",
    "precedence: auto_reply",
]

AUTO_REPLY_SUBJECTS = [
    "out of office",
    "automatic reply",
    "auto-reply",
    "autoreply",
    "away from office",
    "on vacation",
    "i am currently out",
]


class IMAPService:
    """Connects to IMAP inbox to detect replies and bounces."""

    def __init__(
        self,
        host: str = "",
        port: int = 993,
        username: str = "",
        password: str = "",
    ):
        self.host = host or getattr(settings, "imap_host", "")
        self.port = port or getattr(settings, "imap_port", 993)
        self.username = username or getattr(settings, "imap_user", "")
        self.password = password or getattr(settings, "imap_pass", "")

    def is_configured(self) -> bool:
        """Check if IMAP settings are available."""
        return bool(self.host and self.username and self.password)

    async def test_connection(self) -> dict:
        """Test IMAP connection. Returns {"success": bool, "error": str}."""
        if not self.is_configured():
            return {"success": False, "error": "IMAP not configured"}
        loop = asyncio.get_event_loop()
        try:
            def _test():
                ctx = ssl.create_default_context()
                conn = imaplib.IMAP4_SSL(self.host, self.port, ssl_context=ctx)
                conn.login(self.username, self.password)
                conn.select("INBOX", readonly=True)
                status, count = conn.search(None, "ALL")
                total = len(count[0].split()) if count[0] else 0
                conn.logout()
                return total
            total = await loop.run_in_executor(None, _test)
            return {"success": True, "error": "", "total_messages": total}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def find_replies(
        self,
        sent_message_ids: set[str],
        since: datetime | None = None,
    ) -> list[DetectedReply]:
        """Search inbox for replies to our sent emails.

        Args:
            sent_message_ids: Set of Message-ID headers from emails we sent.
            since: Only check messages received after this time. Defaults to 24h ago.

        Returns:
            List of detected replies matched by In-Reply-To header.
        """
        if not self.is_configured() or not sent_message_ids:
            return []

        if since is None:
            since = datetime.now(timezone.utc) - timedelta(hours=24)

        loop = asyncio.get_event_loop()

        def _search():
            replies = []
            ctx = ssl.create_default_context()
            conn = imaplib.IMAP4_SSL(self.host, self.port, ssl_context=ctx)
            conn.login(self.username, self.password)
            conn.select("INBOX", readonly=True)

            # Search for messages since the given date
            date_str = since.strftime("%d-%b-%Y")
            status, data = conn.search(None, f'(SINCE {date_str})')

            if status != "OK" or not data[0]:
                conn.logout()
                return replies

            msg_nums = data[0].split()

            for num in msg_nums:
                try:
                    # Fetch headers only (efficient)
                    status, msg_data = conn.fetch(num, "(RFC822.HEADER)")
                    if status != "OK" or not msg_data[0]:
                        continue

                    raw_header = msg_data[0][1]
                    msg = email.message_from_bytes(raw_header)

                    # Check In-Reply-To header
                    in_reply_to = msg.get("In-Reply-To", "").strip()
                    references = msg.get("References", "").strip()

                    # Match against our sent Message-IDs
                    matched_id = None
                    if in_reply_to in sent_message_ids:
                        matched_id = in_reply_to
                    elif references:
                        for ref in references.split():
                            if ref.strip() in sent_message_ids:
                                matched_id = ref.strip()
                                break

                    if not matched_id:
                        continue

                    # Check if auto-reply
                    is_auto = _is_auto_reply(msg)

                    # Parse sender and date
                    from_email = email.utils.parseaddr(msg.get("From", ""))[1]
                    try:
                        received_at = parsedate_to_datetime(msg.get("Date", ""))
                    except Exception:
                        received_at = datetime.now(timezone.utc)

                    subject = _decode_subject(msg.get("Subject", ""))

                    replies.append(DetectedReply(
                        original_message_id=matched_id,
                        from_email=from_email,
                        subject=subject,
                        received_at=received_at,
                        is_auto_reply=is_auto,
                    ))
                except Exception as e:
                    logger.debug(f"Error parsing message {num}: {e}")
                    continue

            conn.logout()
            return replies

        return await loop.run_in_executor(None, _search)

    async def find_bounces(
        self,
        since: datetime | None = None,
    ) -> list[DetectedBounce]:
        """Search inbox for bounce/DSN messages.

        Looks for multipart/report messages with delivery-status content type.
        """
        if not self.is_configured():
            return []

        if since is None:
            since = datetime.now(timezone.utc) - timedelta(hours=24)

        loop = asyncio.get_event_loop()

        def _search():
            bounces = []
            ctx = ssl.create_default_context()
            conn = imaplib.IMAP4_SSL(self.host, self.port, ssl_context=ctx)
            conn.login(self.username, self.password)
            conn.select("INBOX", readonly=True)

            date_str = since.strftime("%d-%b-%Y")
            # Search for potential bounce messages
            status, data = conn.search(None, f'(SINCE {date_str} SUBJECT "Delivery" OR SUBJECT "Undeliverable" OR SUBJECT "Mail delivery failed")')

            if status != "OK" or not data[0]:
                # Try broader search
                status, data = conn.search(None, f'(SINCE {date_str} FROM "mailer-daemon" OR FROM "postmaster")')

            if status != "OK" or not data[0]:
                conn.logout()
                return bounces

            msg_nums = data[0].split()

            for num in msg_nums[:50]:  # Limit to 50 bounce messages per check
                try:
                    status, msg_data = conn.fetch(num, "(RFC822)")
                    if status != "OK" or not msg_data[0]:
                        continue

                    raw = msg_data[0][1]
                    msg = email.message_from_bytes(raw)

                    bounce = _parse_bounce(msg)
                    if bounce:
                        bounces.append(bounce)
                except Exception as e:
                    logger.debug(f"Error parsing bounce message {num}: {e}")
                    continue

            conn.logout()
            return bounces

        return await loop.run_in_executor(None, _search)


def _is_auto_reply(msg: email.message.Message) -> bool:
    """Detect auto-reply / out-of-office messages."""
    # Check headers
    for header_name in ("Auto-Submitted", "X-Auto-Response-Suppress", "X-Autorespond", "Precedence"):
        value = msg.get(header_name, "").lower()
        if value and value not in ("no",):
            return True

    # Check subject
    subject = _decode_subject(msg.get("Subject", "")).lower()
    return any(indicator in subject for indicator in AUTO_REPLY_SUBJECTS)


def _decode_subject(raw_subject: str) -> str:
    """Decode email subject header."""
    try:
        decoded_parts = decode_header(raw_subject)
        parts = []
        for part, charset in decoded_parts:
            if isinstance(part, bytes):
                parts.append(part.decode(charset or "utf-8", errors="replace"))
            else:
                parts.append(part)
        return " ".join(parts)
    except Exception:
        return raw_subject


def _parse_bounce(msg: email.message.Message) -> DetectedBounce | None:
    """Parse a bounce/DSN message to extract the bounced recipient."""
    content_type = msg.get_content_type()

    # Method 1: Parse multipart/report DSN
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "message/delivery-status":
                dsn_text = part.get_payload(decode=True)
                if isinstance(dsn_text, bytes):
                    dsn_text = dsn_text.decode("utf-8", errors="replace")
                elif isinstance(dsn_text, list):
                    # delivery-status can be a list of message objects
                    dsn_text = str(dsn_text)

                recipient = ""
                action = ""
                diagnostic = ""

                for line in str(dsn_text).split("\n"):
                    line = line.strip()
                    if line.lower().startswith("final-recipient:"):
                        recipient = line.split(";")[-1].strip()
                    elif line.lower().startswith("action:"):
                        action = line.split(":")[-1].strip().lower()
                    elif line.lower().startswith("diagnostic-code:"):
                        diagnostic = line.split(";")[-1].strip()

                if recipient and action in ("failed", "delayed"):
                    bounce_type = "hard" if action == "failed" else "soft"
                    return DetectedBounce(
                        original_recipient=recipient,
                        bounce_type=bounce_type,
                        reason=action,
                        diagnostic_code=diagnostic,
                    )

    # Method 2: Parse plain text bounce (common format)
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    body = payload.decode("utf-8", errors="replace")
                    break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            body = payload.decode("utf-8", errors="replace")

    if body:
        # Look for email addresses in the bounce message
        import re
        emails_found = re.findall(r'[\w.+-]+@[\w-]+\.[\w.-]+', body)
        if emails_found:
            # Common bounce keywords
            is_hard = any(w in body.lower() for w in ["does not exist", "user unknown", "no such user", "invalid", "rejected", "550"])
            is_soft = any(w in body.lower() for w in ["full", "quota", "temporarily", "try again", "452"])

            if is_hard or is_soft:
                return DetectedBounce(
                    original_recipient=emails_found[0],
                    bounce_type="hard" if is_hard else "soft",
                    reason=body[:200],
                )

    return None
