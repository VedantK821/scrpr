"""Email Verifier V2 — dual oracle verification engine.

Two oracles that cover ~85% of companies:
1. Autodiscover Oracle — Microsoft 365 companies (HTTPS, no SMTP needed)
2. Google SMTP Oracle — Google Workspace companies (port 25 RCPT TO)

For companies on neither (self-hosted, other providers):
3. Direct SMTP verification (when port 25 works and not catch-all)
4. Fallback: pattern + MX confirmation (low confidence)
"""
import asyncio
import logging
import socket

import dns.resolver
import httpx

logger = logging.getLogger(__name__)

AUTODISCOVER_URL = "https://autodiscover-s.outlook.com/autodiscover/autodiscover.json/v1.0"


# ── Provider detection ────────────────────────────────────────────────

async def detect_provider(domain: str) -> str:
    """Detect email provider from MX records. Returns 'google', 'microsoft', or 'other'."""
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
        return "other"
    except Exception:
        return "unknown"


# ── Oracle 1: Autodiscover (Microsoft 365) ────────────────────────────

async def verify_autodiscover(email: str) -> dict:
    """Verify email via Autodiscover V2. Works for Microsoft 365 tenants."""
    try:
        async with httpx.AsyncClient(timeout=10.0, verify=False) as c:
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
    except Exception:
        return {"exists": None, "method": "autodiscover_error", "confidence": 0.0}


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
    Returns: {"email", "exists", "confidence", "method", "provider"}
    """
    domain = email.split("@")[1]
    provider = await detect_provider(domain)

    if provider == "microsoft":
        result = await verify_autodiscover(email)
        result["provider"] = "microsoft"
        result["email"] = email
        return result

    elif provider == "google":
        result = await verify_google_smtp(email)
        result["provider"] = "google"
        result["email"] = email
        return result

    else:
        # Try direct SMTP as fallback
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
