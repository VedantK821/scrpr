import asyncio
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dataclasses import dataclass, field
from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class SendResult:
    success: bool
    error: str = field(default="")


class EmailSender:
    """Sends emails via SMTP with rate limiting."""

    def __init__(self, delay_seconds: float = 30.0):
        self.delay = delay_seconds

    async def send(self, to: str, subject: str, body: str, from_email: str | None = None) -> SendResult:
        """Send a single email via SMTP."""
        smtp_host = settings.smtp_host
        smtp_port = settings.smtp_port
        smtp_user = settings.smtp_user
        smtp_pass = settings.smtp_pass

        if not all([smtp_host, smtp_user, smtp_pass]):
            return SendResult(success=False, error="SMTP not configured")

        sender = from_email or smtp_user

        msg = MIMEMultipart("alternative")
        msg["From"] = sender
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        try:
            # Run SMTP in executor to avoid blocking event loop
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._send_smtp, smtp_host, smtp_port, smtp_user, smtp_pass, sender, to, msg)
            return SendResult(success=True)
        except smtplib.SMTPRecipientsRefused:
            return SendResult(success=False, error="Recipient refused (bounced)")
        except smtplib.SMTPAuthenticationError:
            return SendResult(success=False, error="SMTP authentication failed")
        except Exception as e:
            return SendResult(success=False, error=str(e))

    def _send_smtp(self, host, port, user, password, sender, to, msg):
        with smtplib.SMTP(host, int(port)) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(sender, to, msg.as_string())

    async def send_batch(self, emails: list[dict]) -> list[SendResult]:
        """Send a batch of emails with rate limiting."""
        results = []
        for i, email in enumerate(emails):
            result = await self.send(
                to=email["to"],
                subject=email["subject"],
                body=email["body"],
            )
            results.append(result)
            # Rate limit: wait between sends (except after the last one)
            if i < len(emails) - 1:
                await asyncio.sleep(self.delay)
        return results
