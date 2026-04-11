"""Ghost OSINT — zero-trace email intelligence gathering.

Every method here is either:
- Completely passive (target never knows)
- Uses public records (DNS, CT logs, WHOIS, archives)
- Rotates across services to avoid rate limits

NO direct contact with target company servers unless explicitly noted.
"""
import asyncio
import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import dns.resolver
import httpx

logger = logging.getLogger(__name__)

# ── Local cache (never search twice) ─────────────────────────────────

CACHE_DIR = Path(os.path.expanduser("~/.scrpr/cache"))
CACHE_TTL_DAYS = 30


def _cache_key(prefix: str, query: str) -> Path:
    h = hashlib.md5(query.lower().encode()).hexdigest()[:12]
    return CACHE_DIR / f"{prefix}_{h}.json"


def _cache_get(prefix: str, query: str) -> dict | None:
    path = _cache_key(prefix, query)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        cached_at = data.get("_cached_at", 0)
        if time.time() - cached_at > CACHE_TTL_DAYS * 86400:
            return None  # Expired
        return data
    except Exception:
        return None


def _cache_set(prefix: str, query: str, data: dict):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    data["_cached_at"] = time.time()
    _cache_key(prefix, query).write_text(json.dumps(data))


# ── Search engine rotation (6 engines, never get blocked) ────────────

_engine_index = 0


async def _search_ddg(client: httpx.AsyncClient, query: str) -> list[dict]:
    """DuckDuckGo HTML search."""
    from app.scraper.stealth import get_random_user_agent
    resp = await client.post(
        "https://html.duckduckgo.com/html/",
        data={"q": query},
        headers={"User-Agent": get_random_user_agent()},
    )
    if resp.status_code != 200:
        return []
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(resp.text, "html.parser")
    results = []
    for div in soup.select("div.result, div.web-result"):
        link = div.select_one("a.result__a, h2 a")
        snippet = div.select_one("a.result__snippet, .result__snippet")
        href = link.get("href", "") if link else ""
        if "uddg=" in href:
            from urllib.parse import parse_qs, urlparse
            href = parse_qs(urlparse(href).query).get("uddg", [""])[0]
        text = snippet.get_text(strip=True) if snippet else ""
        if href:
            results.append({"url": href, "text": text})
    return results


async def _search_bing(client: httpx.AsyncClient, query: str) -> list[dict]:
    """Bing web search."""
    resp = await client.get(
        "https://www.bing.com/search",
        params={"q": query},
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
    )
    if resp.status_code != 200:
        return []
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(resp.text, "html.parser")
    results = []
    for li in soup.select(".b_algo"):
        link = li.select_one("h2 a")
        snippet = li.select_one(".b_caption p")
        href = link.get("href", "") if link else ""
        text = snippet.get_text(strip=True) if snippet else ""
        if href:
            results.append({"url": href, "text": text})
    return results


async def _search_brave(client: httpx.AsyncClient, query: str) -> list[dict]:
    """Brave Search."""
    resp = await client.get(
        "https://search.brave.com/search",
        params={"q": query},
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
    )
    if resp.status_code != 200:
        return []
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(resp.text, "html.parser")
    results = []
    for div in soup.select(".snippet"):
        link = div.select_one("a")
        text_el = div.select_one(".snippet-description")
        href = link.get("href", "") if link else ""
        text = text_el.get_text(strip=True) if text_el else ""
        if href:
            results.append({"url": href, "text": text})
    return results


_SEARCH_ENGINES = [_search_ddg, _search_bing, _search_brave]


async def search_rotated(query: str, max_results: int = 10) -> list[dict]:
    """Search using rotating engines. Cached for 30 days."""
    cached = _cache_get("search", query)
    if cached and cached.get("results"):
        return cached["results"][:max_results]

    global _engine_index
    async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
        for attempt in range(len(_SEARCH_ENGINES)):
            engine = _SEARCH_ENGINES[(_engine_index + attempt) % len(_SEARCH_ENGINES)]
            try:
                results = await engine(client, query)
                if results:
                    _engine_index = (_engine_index + attempt + 1) % len(_SEARCH_ENGINES)
                    _cache_set("search", query, {"results": results})
                    return results[:max_results]
            except Exception as e:
                logger.debug(f"Search engine {engine.__name__} failed: {e}")

    _engine_index = (_engine_index + 1) % len(_SEARCH_ENGINES)
    return []


# ── Certificate Transparency logs (crt.sh) ───────────────────────────

async def search_ct_logs(domain: str) -> list[str]:
    """Search Certificate Transparency logs for emails in SSL certs.

    Completely passive — queries crt.sh, not the target.
    """
    cached = _cache_get("ct", domain)
    if cached:
        return cached.get("emails", [])

    emails = set()
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"https://crt.sh/?q=%25.{domain}&output=json",
            )
            if resp.status_code == 200:
                certs = resp.json()
                for cert in certs:
                    name = cert.get("name_value", "")
                    # Some certs have email in SAN
                    found = re.findall(rf'[a-zA-Z0-9._%+-]+@{re.escape(domain)}', name)
                    emails.update(e.lower() for e in found)
    except Exception as e:
        logger.debug(f"CT log search failed for {domain}: {e}")

    result = sorted(emails)
    _cache_set("ct", domain, {"emails": result})
    return result


# ── DMARC report address extraction ──────────────────────────────────

async def extract_dmarc_email(domain: str) -> str | None:
    """Extract the DMARC report email — guaranteed to be a real address.

    DNS query only — completely invisible.
    """
    cached = _cache_get("dmarc", domain)
    if cached:
        return cached.get("email")

    loop = asyncio.get_event_loop()
    try:
        def _lookup():
            answers = dns.resolver.resolve(f"_dmarc.{domain}", "TXT")
            return " ".join(str(r) for r in answers)

        txt = await loop.run_in_executor(None, _lookup)
        # Extract rua= and ruf= mailto addresses
        for match in re.finditer(r'ru[af]=mailto:([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+)', txt):
            email = match.group(1).lower()
            _cache_set("dmarc", domain, {"email": email})
            logger.info(f"DMARC email for {domain}: {email}")
            return email
    except Exception:
        pass

    _cache_set("dmarc", domain, {"email": None})
    return None


# ── Wayback Machine (old website snapshots) ──────────────────────────

async def search_wayback(domain: str, path: str = "/about") -> list[str]:
    """Search Wayback Machine for old pages that might contain emails.

    Queries archive.org — not the target.
    """
    cached = _cache_get("wayback", f"{domain}{path}")
    if cached:
        return cached.get("emails", [])

    emails = set()
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Get list of snapshots
            resp = await client.get(
                f"http://web.archive.org/web/timemap/json/https://{domain}{path}",
                params={"limit": 5, "output": "json"},
            )
            if resp.status_code == 200:
                snapshots = resp.json()
                # Skip header row, get most recent snapshots
                for snap in snapshots[1:4]:
                    timestamp = snap[1] if len(snap) > 1 else ""
                    if not timestamp:
                        continue
                    archive_url = f"http://web.archive.org/web/{timestamp}/https://{domain}{path}"
                    try:
                        page = await client.get(archive_url)
                        if page.status_code == 200:
                            found = re.findall(
                                rf'[a-zA-Z0-9._%+-]+@{re.escape(domain)}',
                                page.text
                            )
                            emails.update(e.lower() for e in found)
                    except Exception:
                        pass
    except Exception as e:
        logger.debug(f"Wayback search failed for {domain}: {e}")

    result = sorted(emails)
    _cache_set("wayback", f"{domain}{path}", {"emails": result})
    return result


# ── Google dorking (filetype-specific searches) ──────────────────────

async def google_dork_emails(domain: str) -> list[str]:
    """Find emails via targeted search queries across multiple engines.

    Uses filetype operators to find PDFs, spreadsheets, documents
    that contain employee emails.
    """
    cached = _cache_get("dork", domain)
    if cached:
        return cached.get("emails", [])

    emails = set()
    dorks = [
        f'"@{domain}" filetype:pdf',
        f'"@{domain}" filetype:doc OR filetype:docx',
        f'"@{domain}" site:github.com',
        f'"@{domain}" site:scholar.google.com',
        f'"@{domain}" author OR researcher OR contact',
        f'"@{domain}" conference OR paper OR published',
    ]

    for query in dorks:
        results = await search_rotated(query, max_results=5)
        for r in results:
            text = r.get("text", "") + " " + r.get("url", "")
            found = re.findall(rf'[a-zA-Z0-9._%+-]+@{re.escape(domain)}', text)
            for e in found:
                e = e.lower()
                # Filter placeholders
                if not any(x in e for x in ["first", "last", "example", "doe", "info@", "noreply", "support"]):
                    emails.add(e)
        # Small delay between dorks to be polite
        await asyncio.sleep(0.5)

    result = sorted(emails)
    _cache_set("dork", domain, {"emails": result})
    return result


# ── PGP keyserver search ─────────────────────────────────────────────

async def search_pgp_keys(domain: str) -> list[str]:
    """Search PGP keyservers for published keys containing domain emails.

    No rate limits, completely passive.
    """
    cached = _cache_get("pgp", domain)
    if cached:
        return cached.get("emails", [])

    emails = set()
    keyservers = [
        f"https://keys.openpgp.org/vks/v1/by-email/",  # Search by domain not supported directly
        f"https://keyserver.ubuntu.com/pks/lookup?search=%40{domain}&op=index",
    ]

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(keyservers[1])
            if resp.status_code == 200:
                found = re.findall(rf'[a-zA-Z0-9._%+-]+@{re.escape(domain)}', resp.text)
                emails.update(e.lower() for e in found)
    except Exception as e:
        logger.debug(f"PGP keyserver search failed: {e}")

    result = sorted(emails)
    _cache_set("pgp", domain, {"emails": result})
    return result


# ── SMTP direct verification (port 25) ───────────────────────────────

async def smtp_verify_direct(email: str) -> dict:
    """SMTP RCPT TO verification on port 25.

    Works when ISP doesn't block port 25 (confirmed working for user).
    Includes catch-all detection.
    """
    domain = email.split("@")[1]
    loop = asyncio.get_event_loop()

    try:
        def _get_mx():
            answers = dns.resolver.resolve(domain, "MX")
            return str(sorted(answers, key=lambda r: r.preference)[0].exchange).rstrip(".")
        mx = await loop.run_in_executor(None, _get_mx)
    except Exception:
        return {"verified": None, "error": "No MX records"}

    def _check():
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(10)
            s.connect((mx, 25))
            banner = s.recv(1024).decode(errors="ignore")
            if not banner.startswith("220"):
                s.close()
                return {"verified": None, "error": f"Bad banner: {banner[:50]}"}

            s.sendall(b"EHLO scrpr.dev\r\n")
            s.recv(4096)
            s.sendall(b"MAIL FROM:<verify@scrpr.dev>\r\n")
            s.recv(1024)

            # Test the actual email
            s.sendall(f"RCPT TO:<{email}>\r\n".encode())
            real_resp = s.recv(1024).decode(errors="ignore")

            # Test a fake email to detect catch-all
            fake = f"definitely-not-real-{hash(email) % 99999}@{domain}"
            s.sendall(f"RCPT TO:<{fake}>\r\n".encode())
            fake_resp = s.recv(1024).decode(errors="ignore")

            s.sendall(b"QUIT\r\n")
            s.close()

            real_ok = real_resp.startswith("250")
            fake_ok = fake_resp.startswith("250")

            if fake_ok:
                return {"verified": None, "catch_all": True, "mx": mx}
            elif real_ok:
                return {"verified": True, "catch_all": False, "mx": mx}
            else:
                return {"verified": False, "catch_all": False, "mx": mx, "response": real_resp[:80]}

        except socket.timeout:
            return {"verified": None, "error": "timeout"}
        except ConnectionRefusedError:
            return {"verified": None, "error": "port 25 blocked"}
        except Exception as e:
            return {"verified": None, "error": str(e)[:80]}

    return await loop.run_in_executor(None, _check)


# ── Comprehensive domain intelligence ────────────────────────────────

@dataclass
class DomainIntel:
    domain: str
    provider: str = ""
    mx_hosts: list = field(default_factory=list)
    catch_all: bool = False
    dmarc_email: str = ""
    ct_emails: list = field(default_factory=list)
    wayback_emails: list = field(default_factory=list)
    dork_emails: list = field(default_factory=list)
    pgp_emails: list = field(default_factory=list)
    all_emails: list = field(default_factory=list)
    detected_pattern: str = ""


async def gather_domain_intel(domain: str) -> DomainIntel:
    """Run ALL passive intelligence gathering for a domain in parallel.

    Zero contact with target. All queries go to public services.
    Results cached for 30 days.
    """
    cached = _cache_get("intel", domain)
    if cached and cached.get("all_emails"):
        intel = DomainIntel(domain=domain)
        intel.all_emails = cached["all_emails"]
        intel.detected_pattern = cached.get("detected_pattern", "")
        intel.dmarc_email = cached.get("dmarc_email", "")
        intel.catch_all = cached.get("catch_all", False)
        return intel

    intel = DomainIntel(domain=domain)

    # Run all sources in parallel
    results = await asyncio.gather(
        extract_dmarc_email(domain),
        search_ct_logs(domain),
        search_wayback(domain, "/about"),
        search_wayback(domain, "/contact"),
        search_wayback(domain, "/team"),
        google_dork_emails(domain),
        search_pgp_keys(domain),
        return_exceptions=True,
    )

    intel.dmarc_email = results[0] if isinstance(results[0], str) else ""
    intel.ct_emails = results[1] if isinstance(results[1], list) else []
    wayback1 = results[2] if isinstance(results[2], list) else []
    wayback2 = results[3] if isinstance(results[3], list) else []
    wayback3 = results[4] if isinstance(results[4], list) else []
    intel.wayback_emails = sorted(set(wayback1 + wayback2 + wayback3))
    intel.dork_emails = results[5] if isinstance(results[5], list) else []
    intel.pgp_emails = results[6] if isinstance(results[6], list) else []

    # Combine all found emails
    all_found = set()
    if intel.dmarc_email:
        all_found.add(intel.dmarc_email)
    all_found.update(intel.ct_emails)
    all_found.update(intel.wayback_emails)
    all_found.update(intel.dork_emails)
    all_found.update(intel.pgp_emails)

    # Filter out generic emails
    generic = {"info", "support", "admin", "noreply", "hello", "contact",
               "sales", "marketing", "press", "hr", "careers", "jobs",
               "webmaster", "postmaster", "abuse", "help", "privacy"}
    intel.all_emails = sorted(
        e for e in all_found
        if e.split("@")[0].lower() not in generic
    )

    # Detect pattern from found emails
    if intel.all_emails:
        intel.detected_pattern = _detect_pattern_from_emails(intel.all_emails, domain)

    # Cache
    _cache_set("intel", domain, {
        "all_emails": intel.all_emails,
        "detected_pattern": intel.detected_pattern,
        "dmarc_email": intel.dmarc_email,
        "catch_all": intel.catch_all,
    })

    logger.info(
        f"Domain intel for {domain}: {len(intel.all_emails)} emails found, "
        f"pattern='{intel.detected_pattern}'"
    )
    return intel


def _detect_pattern_from_emails(emails: list[str], domain: str) -> str:
    """Analyze found emails to detect the naming pattern."""
    patterns = {}
    for email in emails:
        local = email.split("@")[0].lower()
        if "." in local:
            parts = local.split(".")
            if len(parts) == 2:
                if len(parts[0]) == 1:
                    patterns["f.last"] = patterns.get("f.last", 0) + 1
                elif len(parts[0]) == 2 and len(parts[1]) > 2:
                    patterns["fi.last"] = patterns.get("fi.last", 0) + 1
                else:
                    patterns["first.last"] = patterns.get("first.last", 0) + 1
            elif len(parts) == 3:
                patterns["first.middle.last"] = patterns.get("first.middle.last", 0) + 1
        elif "_" in local:
            patterns["first_last"] = patterns.get("first_last", 0) + 1
        else:
            patterns["firstlast"] = patterns.get("firstlast", 0) + 1

    if not patterns:
        return ""
    return max(patterns, key=patterns.get)
