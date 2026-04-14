"""Email Verifier V2 — multi-oracle verification engine.

Seven oracles covering ~95% of organizations:
1. Autodiscover Oracle — Microsoft 365 cloud (HTTPS, no SMTP needed)
2. Autodiscover Redirect Oracle — Hybrid Exchange (302 target discrimination)
3. GCT DomainType Oracle — Federated M365 (DomainType=3 vs 4)
4. Google SMTP Oracle — Google Workspace (port 25 RCPT TO)
5. Zoho Accounts Oracle — Indian Government / mgovcloud (user lookup API)
6. SMTP mgovcloud Oracle — Indian Government mailboxes (port 25 with STARTTLS)
7. Direct SMTP — Other providers (catch-all detection)
"""
import asyncio
import logging
import socket
import ssl as _ssl

import dns.resolver
import httpx

logger = logging.getLogger(__name__)

AUTODISCOVER_URL = "https://autodiscover-s.outlook.com/autodiscover/autodiscover.json/v1.0"
ZOHO_ACCOUNTS_URL = "https://accounts.mgovcloud.in"
GOV_DOMAINS = {"gov.in", "nic.in", "mha.gov.in", "mha.nic.in"}
MGOVCLOUD_MX = {"mx.mgovcloud.in", "mx2.mgovcloud.in", "mx3.mgovcloud.in"}


# ── Provider detection ────────────────────────────────────────────────

async def detect_provider(domain: str) -> str:
    """Detect email provider from MX records.

    Returns: 'google', 'microsoft', 'indian_gov', or 'other'.
    """
    # Check Indian government domains first (before DNS)
    if domain in GOV_DOMAINS or domain.endswith((".gov.in", ".nic.in")):
        return "indian_gov"

    loop = asyncio.get_event_loop()
    try:
        def _mx():
            return [str(r.exchange).rstrip(".").lower() for r in dns.resolver.resolve(domain, "MX")]
        records = await loop.run_in_executor(None, _mx)
        for r in records:
            if "google" in r or "googlemail" in r or "aspmx" in r:
                return "google"
            if "outlook" in r or "microsoft" in r or "protection.outlook" in r:
                return "microsoft"
            if "mgovcloud" in r:
                return "indian_gov"
        return "other"
    except Exception:
        return "unknown"


# ── Oracle 1: Autodiscover (Microsoft 365) ────────────────────────────

async def verify_autodiscover(email: str) -> dict:
    """Verify email via Autodiscover V2 with redirect-target discrimination.

    Three-way oracle:
    - 200 → outlook.office365.com in Url = EXISTS (cloud)
    - 200 → eas.outlook.com in Url = NOT_FOUND
    - 302 → autodiscover.{company}.com = EXISTS (hybrid/on-prem)
    """
    try:
        async with httpx.AsyncClient(timeout=15.0, verify=False) as c:
            # Step 1: Check redirect target WITHOUT following (hybrid detection)
            resp_raw = await c.get(
                f"{AUTODISCOVER_URL}/{email}",
                params={"Protocol": "ActiveSync"},
                headers={"User-Agent": "Microsoft Office/16.0"},
                follow_redirects=False,
            )
            if resp_raw.status_code == 302:
                location = resp_raw.headers.get("location", "")
                company_domain = email.split("@")[1]
                # 302 to company's own autodiscover = hybrid EXISTS
                if f"autodiscover.{company_domain}" in location:
                    return {"exists": True, "method": "autodiscover_hybrid", "confidence": 0.90}

            # Step 2: Follow redirects for cloud check
            resp = await c.get(
                f"{AUTODISCOVER_URL}/{email}",
                params={"Protocol": "ActiveSync"},
                headers={"User-Agent": "Microsoft Office/16.0"},
                follow_redirects=True,
            )
            if resp.status_code == 200:
                url = resp.json().get("Url", "")
                if "outlook.office365.com" in url:
                    return {"exists": True, "method": "autodiscover", "confidence": 0.95}
                elif "eas.outlook.com" in url:
                    return {"exists": False, "method": "autodiscover", "confidence": 0.95}
            return {"exists": None, "method": "autodiscover", "confidence": 0.0}
    except httpx.TimeoutException:
        # Timeout after redirect to company autodiscover = likely hybrid EXISTS
        return {"exists": True, "method": "autodiscover_hybrid_timeout", "confidence": 0.70}
    except Exception:
        return {"exists": None, "method": "autodiscover_error", "confidence": 0.0}


# ── Oracle 1b: GCT DomainType (Federated M365) ──────────────────────

async def verify_gct_domaintype(email: str) -> dict:
    """Verify via GetCredentialType DomainType field.

    For federated M365 tenants where Autodiscover fails per-account:
    - DomainType=3 + CertAuth=True = managed account EXISTS
    - DomainType=4 + FederationRedirectUrl = federated fallback = NOT_FOUND
    Works even when ThrottleStatus=1.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            resp = await c.post(
                "https://login.microsoftonline.com/common/GetCredentialType",
                json={"Username": email, "isOtherIdpSupported": True, "checkPhones": True},
            )
            data = resp.json()
            dt = data.get("EstsProperties", {}).get("DomainType")
            cert_auth = data.get("Credentials", {}).get("CertAuthParams") is not None
            fed_url = data.get("Credentials", {}).get("FederationRedirectUrl", "")

            if dt == 3 and cert_auth:
                return {"exists": True, "method": "gct_domaintype", "confidence": 0.90}
            elif dt == 4 and fed_url:
                return {"exists": False, "method": "gct_domaintype", "confidence": 0.85}
            return {"exists": None, "method": "gct_domaintype", "confidence": 0.0}
    except Exception:
        return {"exists": None, "method": "gct_error", "confidence": 0.0}


# ── Oracle 5: Zoho Accounts (Indian Government) ─────────────────────

_zoho_csrf_cache: dict = {}


async def verify_zoho_accounts(email: str) -> dict:
    """Verify via Zoho Accounts lookup on mgovcloud.in.

    Works for Indian government emails (gov.in, nic.in, *.gov.in).
    Returns org name on success. Rate limits after ~50 requests.
    """
    try:
        async with httpx.AsyncClient(timeout=15.0, verify=False) as c:
            # Get CSRF cookie
            if "csrf" not in _zoho_csrf_cache:
                resp = await c.get(
                    f"{ZOHO_ACCOUNTS_URL}/signin",
                    params={"servicename": "ZOHOMail", "serviceurl": "https://mail.mgovcloud.in"},
                )
                for cookie in c.cookies.jar:
                    if "iamcsr" in cookie.name:
                        _zoho_csrf_cache["csrf"] = cookie.value
                        break

            csrf = _zoho_csrf_cache.get("csrf", "")
            if not csrf:
                return {"exists": None, "method": "zoho_no_csrf", "confidence": 0.0}

            resp = await c.post(
                f"{ZOHO_ACCOUNTS_URL}/signin/v2/lookup/{email}",
                data={
                    "LOGIN_ID": email,
                    "servicename": "ZOHOMail",
                    "serviceurl": "https://mail.mgovcloud.in",
                },
                headers={
                    "X-ZCSRF-TOKEN": f"iamcsrcoo={csrf}",
                    "X-Requested-With": "XMLHttpRequest",
                    "Origin": ZOHO_ACCOUNTS_URL,
                    "Referer": f"{ZOHO_ACCOUNTS_URL}/signin?servicename=ZOHOMail",
                },
            )
            data = resp.json()
            if data.get("status_code") == 201:
                org = data.get("lookup", {}).get("org_name", "")
                return {"exists": True, "method": "zoho_accounts", "confidence": 0.95, "org": org}
            elif "HIP" in data.get("message", ""):
                logger.warning("Zoho oracle rate limited (HIP REQUIRED)")
                return {"exists": None, "method": "zoho_rate_limited", "confidence": 0.0}
            return {"exists": False, "method": "zoho_accounts", "confidence": 0.90}
    except Exception:
        return {"exists": None, "method": "zoho_error", "confidence": 0.0}


# ── Oracle 6: SMTP mgovcloud (Indian Government mailboxes) ───────────

async def verify_smtp_mgovcloud(email: str) -> dict:
    """Verify Indian gov mailbox via SMTP on smtp.mgovcloud.in.

    Uses STARTTLS on port 25. 250=EXISTS, 550=NOT_FOUND.
    Has anti-enumeration (goes accept-all after many requests).
    """
    loop = asyncio.get_event_loop()

    def _check():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(10)
            s.connect(("smtp.mgovcloud.in", 25))
            s.recv(1024)
            s.sendall(b"EHLO scrpr.dev\r\n")
            s.recv(4096)
            s.sendall(b"STARTTLS\r\n")
            s.recv(1024)
            ctx = _ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = _ssl.CERT_NONE
            s = ctx.wrap_socket(s, server_hostname="smtp.mgovcloud.in")
            s.sendall(b"EHLO scrpr.dev\r\n")
            s.recv(4096)

            s.sendall(b"MAIL FROM:<verify@scrpr.dev>\r\n")
            s.recv(1024)
            s.sendall(f"RCPT TO:<{email}>\r\n".encode())
            resp = s.recv(1024).decode(errors="ignore").strip()
            s.sendall(b"QUIT\r\n")
            s.close()

            code = resp[:3]
            if code == "250":
                return {"exists": True, "method": "smtp_mgovcloud", "confidence": 0.85}
            elif code == "550":
                return {"exists": False, "method": "smtp_mgovcloud", "confidence": 0.85}
            return {"exists": None, "method": f"smtp_mgovcloud_{code}", "confidence": 0.0}
        except Exception:
            return {"exists": None, "method": "smtp_mgovcloud_error", "confidence": 0.0}

    return await loop.run_in_executor(None, _check)


# ── Oracle 2: Google SMTP (Google Workspace) ──────────────────────────

async def verify_google_smtp(email: str) -> dict:
    """Verify email via SMTP RCPT TO on Google's MX. Works for Google Workspace."""
    domain = email.split("@")[1]
    loop = asyncio.get_event_loop()

    try:
        def _get_google_mx():
            records = dns.resolver.resolve(domain, "MX")
            for r in sorted(records, key=lambda x: x.preference):
                host = str(r.exchange).rstrip(".").lower()
                if "google" in host or "aspmx" in host:
                    return host
            return None
        mx = await loop.run_in_executor(None, _get_google_mx)
    except Exception:
        return {"exists": None, "method": "google_no_mx", "confidence": 0.0}

    if not mx:
        return {"exists": None, "method": "not_google", "confidence": 0.0}

    def _smtp_check():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(10)
            s.connect((mx, 25))
            s.recv(1024)
            s.sendall(b"EHLO scrpr.dev\r\n")
            s.recv(4096)
            s.sendall(b"MAIL FROM:<verify@scrpr.dev>\r\n")
            s.recv(1024)
            s.sendall(f"RCPT TO:<{email}>\r\n".encode())
            resp = s.recv(1024).decode(errors="ignore").strip()
            s.sendall(b"QUIT\r\n")
            s.close()
            code = resp[:3]
            if code == "250":
                return {"exists": True, "method": "google_smtp", "confidence": 0.95}
            elif code in ("550", "553", "551"):
                return {"exists": False, "method": "google_smtp", "confidence": 0.95}
            else:
                return {"exists": None, "method": f"google_smtp_{code}", "confidence": 0.0}
        except Exception as e:
            return {"exists": None, "method": "google_smtp_error", "confidence": 0.0, "error": str(e)[:40]}

    return await loop.run_in_executor(None, _smtp_check)


# ── Oracle 3: Direct SMTP (other providers) ───────────────────────────

async def verify_direct_smtp(email: str) -> dict:
    """Try SMTP verification on any MX. May fail (blocked, catch-all, etc)."""
    domain = email.split("@")[1]
    loop = asyncio.get_event_loop()

    try:
        def _get_mx():
            records = dns.resolver.resolve(domain, "MX")
            return str(sorted(records, key=lambda x: x.preference)[0].exchange).rstrip(".")
        mx = await loop.run_in_executor(None, _get_mx)
    except Exception:
        return {"exists": None, "method": "no_mx", "confidence": 0.0}

    def _check():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(10)
            s.connect((mx, 25))
            banner = s.recv(1024).decode(errors="ignore")
            if not banner.startswith("220"):
                s.close()
                return {"exists": None, "method": "smtp_rejected", "confidence": 0.0}

            s.sendall(b"EHLO scrpr.dev\r\n")
            s.recv(4096)
            s.sendall(b"MAIL FROM:<verify@scrpr.dev>\r\n")
            r1 = s.recv(1024).decode(errors="ignore")
            if not r1.startswith("250"):
                s.close()
                return {"exists": None, "method": "smtp_mail_rejected", "confidence": 0.0}

            # Test the real email
            s.sendall(f"RCPT TO:<{email}>\r\n".encode())
            real_resp = s.recv(1024).decode(errors="ignore").strip()

            # Test a fake to detect catch-all
            s.sendall(b"RSET\r\n")
            s.recv(1024)
            s.sendall(b"MAIL FROM:<verify@scrpr.dev>\r\n")
            s.recv(1024)
            fake = f"zzfake99999@{domain}"
            s.sendall(f"RCPT TO:<{fake}>\r\n".encode())
            fake_resp = s.recv(1024).decode(errors="ignore").strip()

            s.sendall(b"QUIT\r\n")
            s.close()

            real_ok = real_resp[:3] == "250"
            fake_ok = fake_resp[:3] == "250"

            if fake_ok:
                return {"exists": None, "method": "catch_all", "confidence": 0.0}
            elif real_ok:
                return {"exists": True, "method": "smtp_verified", "confidence": 0.90}
            else:
                return {"exists": False, "method": "smtp_rejected", "confidence": 0.90}

        except Exception as e:
            return {"exists": None, "method": "smtp_error", "confidence": 0.0, "error": str(e)[:40]}

    return await loop.run_in_executor(None, _check)


# ── THE VERIFY FUNCTION ───────────────────────────────────────────────

async def verify_email(email: str) -> dict:
    """Verify any email using the best available oracle.

    Automatically detects the provider and routes to the right oracle.
    Falls back through multiple oracles if the primary returns inconclusive.
    Returns: {"email", "exists", "confidence", "method", "provider"}
    """
    domain = email.split("@")[1]
    provider = await detect_provider(domain)

    if provider == "indian_gov":
        # Try Zoho Accounts first (fastest, leaks org name)
        result = await verify_zoho_accounts(email)
        if result["exists"] is not None:
            result["provider"] = "indian_gov"
            result["email"] = email
            return result
        # Fallback to SMTP mgovcloud
        result = await verify_smtp_mgovcloud(email)
        result["provider"] = "indian_gov"
        result["email"] = email
        return result

    elif provider == "google":
        result = await verify_google_smtp(email)
        result["provider"] = "google"
        result["email"] = email
        return result

    # For Microsoft AND unknown providers: try Autodiscover first.
    # Many companies (TCS, Bosch, etc.) use M365 with custom MX records
    # that don't match the "microsoft" pattern in detect_provider.
    result = await verify_autodiscover(email)
    if result["exists"] is not None:
        result["provider"] = provider
        result["email"] = email
        return result

    # Autodiscover inconclusive — try GCT DomainType for federated M365
    if provider == "microsoft":
        result = await verify_gct_domaintype(email)
        if result["exists"] is not None:
            result["provider"] = "microsoft"
            result["email"] = email
            return result

    # Final fallback: direct SMTP with catch-all detection
    result = await verify_direct_smtp(email)
    result["provider"] = provider
    result["email"] = email
    return result


async def verify_batch(emails: list[str]) -> list[dict]:
    """Verify multiple emails in parallel."""
    sem = asyncio.Semaphore(10)

    async def _check(email):
        async with sem:
            return await verify_email(email)

    return await asyncio.gather(*[_check(e) for e in emails])


# ── FIND + VERIFY: the complete function ──────────────────────────────

async def find_and_verify(
    name: str,
    company: str,
    domain: str = "",
) -> dict:
    """Find someone's email. Name + company in, verified email out.

    1. Resolves domain
    2. Detects provider
    3. Generates candidates
    4. Verifies all candidates
    5. Returns best verified hit

    Returns: {"email", "exists", "confidence", "method", "provider", "alternatives"}
    """
    # Resolve domain
    if not domain:
        from app.services.domain_resolver import resolve_domain
        domain = await resolve_domain(company)
        if not domain:
            return {"email": "", "exists": None, "confidence": 0, "method": "no_domain"}

    provider = await detect_provider(domain)

    # Parse name
    parts = name.lower().strip().split()
    if len(parts) < 2:
        return {"email": "", "exists": None, "confidence": 0, "method": "need_full_name"}

    first = parts[0]
    last = parts[-1]
    middle = parts[1] if len(parts) > 2 else ""
    fi = first[0]
    li = last[0]
    mi = middle[0] if middle else ""

    # Generate candidates
    candidates = [
        f"{first}.{last}@{domain}",
        f"{last}.{first}@{domain}",
        f"{first}@{domain}",
        f"{last}@{domain}",
        f"{fi}{last}@{domain}",
        f"{first}{li}@{domain}",
        f"{fi}.{last}@{domain}",
        f"{first}.{li}@{domain}",
        f"{last}.{fi}@{domain}",
        f"{fi}{li}@{domain}",
        f"{first}{last}@{domain}",
        f"{last}{first}@{domain}",
    ]
    if middle:
        candidates.extend([
            f"{first}.{middle}.{last}@{domain}",
            f"{fi}{mi}.{last}@{domain}",
            f"{fi}{mi}{last}@{domain}",
        ])

    # Verify all
    results = await verify_batch(candidates)

    # Find verified hits
    verified = [r for r in results if r.get("exists") is True]
    not_found = [r for r in results if r.get("exists") is False]

    if verified:
        best = verified[0]
        return {
            "email": best["email"],
            "exists": True,
            "confidence": best["confidence"],
            "method": best["method"],
            "provider": provider,
            "alternatives": [r["email"] for r in verified[1:]],
        }

    # No verified hits
    return {
        "email": candidates[0],
        "exists": None,
        "confidence": 0.15,
        "method": "pattern_guess",
        "provider": provider,
        "candidates_tried": len(candidates),
        "rejected": len(not_found),
    }
