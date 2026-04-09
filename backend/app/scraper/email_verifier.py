import asyncio
import dns.resolver  # pip install dnspython
import logging
import socket
from dataclasses import dataclass
from enum import StrEnum

logger = logging.getLogger(__name__)


class EmailVerifyStatus(StrEnum):
    VALID = "valid"           # Server accepted the recipient
    INVALID = "invalid"       # Server rejected the recipient (550)
    CATCH_ALL = "catch_all"   # Server accepts everything (can't confirm)
    UNKNOWN = "unknown"       # Couldn't determine (timeout, blocked, etc.)


@dataclass
class VerifyResult:
    email: str
    status: EmailVerifyStatus
    mx_host: str = ""
    smtp_response: str = ""
    error: str = ""


class EmailVerifier:
    """Verifies email addresses via DNS MX lookup + SMTP RCPT TO handshake."""

    def __init__(self, timeout: float = 10.0, from_email: str = "verify@scrpr.dev"):
        self.timeout = timeout
        self.from_email = from_email

    async def verify(self, email: str) -> VerifyResult:
        """Verify if an email address exists without sending a message."""
        domain = email.split("@")[-1] if "@" in email else ""
        if not domain:
            return VerifyResult(email=email, status=EmailVerifyStatus.INVALID, error="Invalid email format")

        # Step 1: DNS MX lookup
        mx_host = await self._get_mx_host(domain)
        if not mx_host:
            return VerifyResult(email=email, status=EmailVerifyStatus.INVALID, error=f"No MX records for {domain}")

        # Step 2: SMTP handshake (run in executor to not block event loop)
        loop = asyncio.get_event_loop()
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, self._smtp_check, email, mx_host),
                timeout=self.timeout,
            )
            return result
        except asyncio.TimeoutError:
            return VerifyResult(email=email, status=EmailVerifyStatus.UNKNOWN, mx_host=mx_host, error="SMTP timeout")

    async def verify_batch(self, emails: list[str]) -> list[VerifyResult]:
        """Verify multiple emails with concurrency limit."""
        semaphore = asyncio.Semaphore(3)  # Max 3 concurrent SMTP connections

        async def _verify(email):
            async with semaphore:
                result = await self.verify(email)
                await asyncio.sleep(1.0)  # Be polite to mail servers
                return result

        return await asyncio.gather(*[_verify(e) for e in emails])

    async def _get_mx_host(self, domain: str) -> str | None:
        """Get the primary MX server for a domain."""
        loop = asyncio.get_event_loop()
        try:
            def _lookup():
                answers = dns.resolver.resolve(domain, "MX")
                # Sort by priority (lowest = highest priority)
                records = sorted(answers, key=lambda r: r.preference)
                return str(records[0].exchange).rstrip(".")
            return await loop.run_in_executor(None, _lookup)
        except Exception as e:
            logger.debug(f"MX lookup failed for {domain}: {e}")
            return None

    def _smtp_check(self, email: str, mx_host: str) -> VerifyResult:
        """Perform SMTP RCPT TO check."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            sock.connect((mx_host, 25))

            # Read banner
            banner = sock.recv(1024).decode(errors="ignore")
            if not banner.startswith("220"):
                sock.close()
                return VerifyResult(email=email, status=EmailVerifyStatus.UNKNOWN, mx_host=mx_host, error=f"Bad banner: {banner[:100]}")

            # EHLO
            sock.sendall(b"EHLO scrpr.dev\r\n")
            sock.recv(1024)

            # MAIL FROM
            sock.sendall(f"MAIL FROM:<{self.from_email}>\r\n".encode())
            sock.recv(1024)

            # RCPT TO — this is the actual check
            sock.sendall(f"RCPT TO:<{email}>\r\n".encode())
            response = sock.recv(1024).decode(errors="ignore")

            # Check for catch-all: try a definitely-fake address
            fake_email = f"definitely-not-real-{id(self)}@{email.split('@')[1]}"
            sock.sendall(f"RCPT TO:<{fake_email}>\r\n".encode())
            fake_response = sock.recv(1024).decode(errors="ignore")

            # QUIT
            sock.sendall(b"QUIT\r\n")
            sock.close()

            # Analyze responses
            real_accepted = response.startswith("250")
            fake_accepted = fake_response.startswith("250")

            if fake_accepted:
                # Server accepts everything — catch-all domain
                return VerifyResult(email=email, status=EmailVerifyStatus.CATCH_ALL, mx_host=mx_host, smtp_response="Catch-all server")
            elif real_accepted:
                # Server accepted real email but rejected fake — email is valid!
                return VerifyResult(email=email, status=EmailVerifyStatus.VALID, mx_host=mx_host, smtp_response=response[:100])
            else:
                # Server rejected the email
                return VerifyResult(email=email, status=EmailVerifyStatus.INVALID, mx_host=mx_host, smtp_response=response[:100])

        except socket.timeout:
            return VerifyResult(email=email, status=EmailVerifyStatus.UNKNOWN, mx_host=mx_host, error="Connection timeout")
        except ConnectionRefusedError:
            return VerifyResult(email=email, status=EmailVerifyStatus.UNKNOWN, mx_host=mx_host, error="Connection refused (port 25 blocked)")
        except Exception as e:
            return VerifyResult(email=email, status=EmailVerifyStatus.UNKNOWN, mx_host=mx_host, error=str(e))

    async def is_catch_all(self, domain: str) -> bool:
        """Check if a domain is a catch-all (accepts any email)."""
        fake = f"definitely-not-real-test-12345@{domain}"
        result = await self.verify(fake)
        return result.status == EmailVerifyStatus.CATCH_ALL
