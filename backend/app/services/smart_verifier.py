"""
Multi-signal email verification engine.

Verifies emails using free public endpoints — no SMTP port 25 needed:
- Microsoft 365: GetCredentialType API (free, any IP)
- Google Workspace: MX-based detection
- Gravatar: avatar existence check
- GitHub: user search by email
- DNS: MX + SPF provider detection

Compound confidence scoring combines signals for honest accuracy.
"""
import asyncio
import hashlib
import logging
from dataclasses import dataclass, field
from enum import StrEnum

import dns.resolver
import httpx

logger = logging.getLogger(__name__)


class EmailProvider(StrEnum):
    MICROSOFT = "microsoft"
    GOOGLE = "google"
    OTHER = "other"
    UNKNOWN = "unknown"


@dataclass
class VerificationResult:
    email: str
    confidence: float = 0.0
    verified: bool = False
    provider: str = ""
    method: str = ""
    signals: dict = field(default_factory=dict)

    def __post_init__(self):
        self.verified = self.confidence >= 0.80


# ── Provider detection ────────────────────────────────────────────────

_provider_cache: dict[str, EmailProvider] = {}


async def detect_provider(domain: str) -> EmailProvider:
    """Detect email provider via DNS MX + SPF records."""
    if domain in _provider_cache:
        return _provider_cache[domain]

    provider = EmailProvider.UNKNOWN
    loop = asyncio.get_event_loop()

    # Check MX records
    try:
        def _mx_lookup():
            answers = dns.resolver.resolve(domain, "MX")
            return [str(r.exchange).lower() for r in answers]

        mx_hosts = await loop.run_in_executor(None, _mx_lookup)
        for host in mx_hosts:
            if "google" in host or "googlemail" in host or "aspmx" in host:
                provider = EmailProvider.GOOGLE
                break
            elif "outlook" in host or "microsoft" in host or "protection.outlook" in host:
                provider = EmailProvider.MICROSOFT
                break
        if provider == EmailProvider.UNKNOWN:
            provider = EmailProvider.OTHER  # Has MX, but not Google/Microsoft
    except Exception:
        pass

    # Double-check with SPF if MX was inconclusive
    if provider == EmailProvider.OTHER or provider == EmailProvider.UNKNOWN:
        try:
            def _txt_lookup():
                answers = dns.resolver.resolve(domain, "TXT")
                return [str(r) for r in answers]

            txt_records = await loop.run_in_executor(None, _txt_lookup)
            spf = " ".join(txt_records).lower()
            if "_spf.google.com" in spf or "google.com" in spf:
                provider = EmailProvider.GOOGLE
            elif "spf.protection.outlook.com" in spf or "microsoft.com" in spf:
                provider = EmailProvider.MICROSOFT
        except Exception:
            pass

    _provider_cache[domain] = provider
    logger.info(f"Provider for {domain}: {provider}")
    return provider


# ── Microsoft 365 verification ────────────────────────────────────────

O365_URL = "https://login.microsoftonline.com/common/GetCredentialType"
_o365_semaphore = asyncio.Semaphore(5)  # Max 5 concurrent O365 requests


async def verify_o365(email: str) -> dict:
    """Check if email exists in Microsoft 365 / Azure AD.

    IMPORTANT: Only reliable for non-federated domains (DomainType != 4).
    Federated domains always return IfExistsResult=0 regardless of whether
    the user exists — this is a false positive.

    Returns: {"exists": True/False/None, "throttled": bool, "federated": bool}
    """
    async with _o365_semaphore:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    O365_URL,
                    json={"Username": email},
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                        "Content-Type": "application/json",
                    },
                )
                if resp.status_code != 200:
                    return {"exists": None, "throttled": False, "federated": False, "error": f"HTTP {resp.status_code}"}

                data = resp.json()
                result_code = data.get("IfExistsResult", -1)

                # Check for federated domain — these ALWAYS return 0, so the result is useless
                domain_type = data.get("EstsProperties", {}).get("DomainType", 0)
                is_federated = domain_type == 4 or "Federation" in str(data.get("Credentials", {}))

                if is_federated:
                    logger.info(f"O365: {email} domain is federated (DomainType={domain_type}), cannot verify")
                    return {"exists": None, "throttled": False, "federated": True}

                if result_code == 0:
                    logger.info(f"O365: {email} EXISTS (DomainType={domain_type})")
                    return {"exists": True, "throttled": False, "federated": False}
                elif result_code == 1:
                    logger.debug(f"O365: {email} does not exist")
                    return {"exists": False, "throttled": False, "federated": False}
                elif result_code in (5, 6):
                    logger.warning(f"O365: throttled for {email}")
                    return {"exists": None, "throttled": True, "federated": False}
                else:
                    return {"exists": None, "throttled": False, "federated": False, "result_code": result_code}

        except Exception as e:
            logger.debug(f"O365 check failed for {email}: {e}")
            return {"exists": None, "throttled": False, "federated": False, "error": str(e)}


async def batch_verify_o365(candidates: list[str]) -> str | None:
    """Try all email candidates against O365. Return the one that exists."""
    tasks = [verify_o365(email) for email in candidates]
    results = await asyncio.gather(*tasks)

    for email, result in zip(candidates, results):
        if result.get("exists") is True:
            return email

    # If throttled, retry the throttled ones sequentially with delay
    throttled = [(email, r) for email, r in zip(candidates, results) if r.get("throttled")]
    for email, _ in throttled:
        await asyncio.sleep(2.0)
        result = await verify_o365(email)
        if result.get("exists") is True:
            return email

    return None


# ── Gravatar check ────────────────────────────────────────────────────

async def check_gravatar(email: str) -> bool:
    """Check if email has a Gravatar avatar. If yes, it's a real email."""
    email_hash = hashlib.md5(email.strip().lower().encode()).hexdigest()
    url = f"https://www.gravatar.com/avatar/{email_hash}?d=404&s=1"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.head(url)
            exists = resp.status_code == 200
            if exists:
                logger.info(f"Gravatar: {email} has avatar")
            return exists
    except Exception:
        return False


# ── GitHub user search ────────────────────────────────────────────────

async def check_github_user(email: str) -> bool:
    """Check if email is associated with a GitHub account."""
    import os
    token = os.environ.get("GITHUB_TOKEN", "")
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"

    try:
        async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
            resp = await client.get(
                f"https://api.github.com/search/users?q={email}+in:email"
            )
            if resp.status_code == 200:
                count = resp.json().get("total_count", 0)
                if count > 0:
                    logger.info(f"GitHub: {email} found ({count} users)")
                return count > 0
            elif resp.status_code == 403:
                logger.warning("GitHub: rate limited")
    except Exception as e:
        logger.debug(f"GitHub check failed for {email}: {e}")
    return False


# ── DNS MX check ──────────────────────────────────────────────────────

async def has_mx_records(domain: str) -> bool:
    """Check if domain has MX records (accepts email)."""
    loop = asyncio.get_event_loop()
    try:
        def _lookup():
            dns.resolver.resolve(domain, "MX")
            return True
        return await loop.run_in_executor(None, _lookup)
    except Exception:
        return False


# ── Compound scoring ──────────────────────────────────────────────────

SIGNAL_WEIGHTS = {
    "o365_exists": 0.90,
    "google_provider": 0.10,  # Domain is Google = MX confirmed, pattern likely standard
    "gravatar": 0.15,
    "github_user": 0.15,
    "github_commit": 0.95,
    "website_published": 0.90,
    "mx_valid": 0.10,
    "pattern_learned": 0.20,
}


async def score_email(
    email: str,
    domain: str,
    provider: EmailProvider | None = None,
    skip_o365: bool = False,
    extra_signals: dict | None = None,
) -> VerificationResult:
    """Score an email's likelihood of being real using all available signals.

    Returns VerificationResult with compound confidence score.
    """
    if provider is None:
        provider = await detect_provider(domain)

    signals = {}
    confidence = 0.0

    # Provider-specific verification
    if provider == EmailProvider.MICROSOFT and not skip_o365:
        result = await verify_o365(email)
        if result.get("exists") is True:
            signals["o365_exists"] = True
            confidence = max(confidence, SIGNAL_WEIGHTS["o365_exists"])
        elif result.get("exists") is False:
            # O365 says it doesn't exist — strong negative signal
            return VerificationResult(
                email=email, confidence=0.05, provider=provider,
                method="o365_rejected", signals={"o365_exists": False},
            )

    if provider == EmailProvider.GOOGLE:
        signals["google_provider"] = True
        confidence += SIGNAL_WEIGHTS["google_provider"]

    # MX check
    mx_ok = await has_mx_records(domain)
    if mx_ok:
        signals["mx_valid"] = True
        confidence += SIGNAL_WEIGHTS["mx_valid"]
    else:
        # No MX = domain doesn't accept email at all
        return VerificationResult(
            email=email, confidence=0.0, provider=provider,
            method="no_mx", signals={"mx_valid": False},
        )

    # Cross-reference signals (run in parallel)
    gravatar_task = check_gravatar(email)
    github_task = check_github_user(email)
    gravatar_ok, github_ok = await asyncio.gather(gravatar_task, github_task)

    if gravatar_ok:
        signals["gravatar"] = True
        confidence += SIGNAL_WEIGHTS["gravatar"]
    if github_ok:
        signals["github_user"] = True
        confidence += SIGNAL_WEIGHTS["github_user"]

    # Extra signals from caller (e.g., website_published, github_commit, pattern_learned)
    if extra_signals:
        for signal_name, signal_value in extra_signals.items():
            if signal_value and signal_name in SIGNAL_WEIGHTS:
                signals[signal_name] = True
                confidence += SIGNAL_WEIGHTS[signal_name]

    confidence = min(confidence, 0.99)

    # Determine method label
    if "o365_exists" in signals:
        method = "o365_verified"
    elif "website_published" in signals:
        method = "website_verified"
    elif "github_commit" in signals:
        method = "github_commit_verified"
    elif "gravatar" in signals or "github_user" in signals:
        method = "cross_ref_verified"
    elif mx_ok:
        method = "mx_confirmed_pattern"
    else:
        method = "unverified"

    return VerificationResult(
        email=email,
        confidence=confidence,
        provider=provider,
        method=method,
        signals=signals,
    )
