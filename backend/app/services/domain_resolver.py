"""Resolve company name to actual website domain via web search."""
import logging
import re
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.sources.email_pattern import KNOWN_DOMAINS

logger = logging.getLogger(__name__)

# Domains that are ABOUT companies, not the company's own site
SOCIAL_DOMAINS = {
    "linkedin.com", "facebook.com", "twitter.com", "instagram.com",
    "youtube.com", "tiktok.com", "pinterest.com",
    "wikipedia.org", "crunchbase.com", "glassdoor.com", "indeed.com",
    "bloomberg.com", "reuters.com", "forbes.com",
    "github.com", "stackoverflow.com",
    "google.com", "bing.com", "duckduckgo.com",
    "amazon.com",  # Usually the marketplace, not the company site
}

# Cache resolved domains
_domain_cache: dict[str, str] = {}


async def resolve_domain(company: str) -> str:
    """Resolve a company name to its actual email domain.

    Strategy:
    1. Check KNOWN_DOMAINS map (instant, most reliable)
    2. Search DuckDuckGo for the company
    3. Extract the real website URL from search results
    4. Return the domain

    Args:
        company: Company name (e.g., "Zapier", "TCS", "DevBay")

    Returns:
        Domain string (e.g., "zapier.com") or empty string if not found.
    """
    if not company:
        return ""

    company_clean = company.strip()
    cache_key = company_clean.lower()

    if cache_key in _domain_cache:
        return _domain_cache[cache_key]

    # Step 1: Check known domains first
    for key, domain in KNOWN_DOMAINS.items():
        if key in cache_key or cache_key in key:
            _domain_cache[cache_key] = domain
            return domain

    # Step 2: Search DuckDuckGo
    domain = await _search_for_domain(company_clean)
    if domain:
        _domain_cache[cache_key] = domain
        logger.info(f"Resolved '{company}' -> {domain} (via search)")
        return domain

    # Step 3: Fallback — guess from company name
    fallback = _guess_domain(company_clean)
    if fallback:
        _domain_cache[cache_key] = fallback
        logger.info(f"Resolved '{company}' -> {fallback} (guessed)")
    return fallback


async def _search_for_domain(company: str) -> str:
    """Search DuckDuckGo for company and extract website domain."""
    from app.scraper.stealth import get_random_user_agent

    headers = {"User-Agent": get_random_user_agent()}
    query = f"{company} official website"

    try:
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=10.0) as client:
            resp = await client.post(
                "https://html.duckduckgo.com/html/",
                data={"q": query},
            )
            if resp.status_code != 200:
                return ""

            soup = BeautifulSoup(resp.text, "html.parser")

            for result_div in soup.select("div.result, div.web-result"):
                link = result_div.select_one("a.result__a, a.result__url, h2 a")
                if not link:
                    continue

                href = link.get("href", "")
                # DuckDuckGo sometimes wraps URLs
                if "uddg=" in href:
                    import urllib.parse
                    parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                    href = parsed.get("uddg", [""])[0]

                if not href.startswith("http"):
                    continue

                domain = _extract_domain(href)
                if domain and not _is_social_domain(domain):
                    return domain

    except Exception as e:
        logger.debug(f"Domain search failed for '{company}': {e}")

    return ""


def _extract_domain(url: str) -> str:
    """Extract clean domain from URL."""
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        # Remove www. prefix
        if host.startswith("www."):
            host = host[4:]
        return host.lower()
    except Exception:
        return ""


def _is_social_domain(domain: str) -> bool:
    """Check if domain is a social/news site rather than the company's own site."""
    for social in SOCIAL_DOMAINS:
        if domain == social or domain.endswith(f".{social}"):
            return True
    return False


def _guess_domain(company: str) -> str:
    """Last resort: guess domain from company name."""
    clean = re.sub(r'\b(ltd|limited|inc|incorporated|pvt|private|corporation|llp|llc|technologies|tech)\b', '',
                   company.lower(), flags=re.IGNORECASE)
    clean = re.sub(r'[^a-z0-9\s]', '', clean).strip()
    clean = re.sub(r'\s+', '', clean)
    if clean:
        return f"{clean}.com"
    return ""
