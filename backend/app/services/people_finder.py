"""People Finder — discover people at a company by role/seniority.

Sources (all free, no login required):
1. Google-dorked LinkedIn profiles (site:linkedin.com/in)
2. Company website team/about pages
3. GitHub organization members (for tech companies)
4. PGP keyserver employee discovery

All sources return structured PersonResult objects.
"""
import asyncio
import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus, urlparse

import httpx
from bs4 import BeautifulSoup

from app.scraper.stealth import get_random_user_agent, get_random_delay

logger = logging.getLogger(__name__)

CACHE_DIR = Path(os.path.expanduser("~/.scrpr/cache/people"))
CACHE_TTL_DAYS = 7


@dataclass
class PersonResult:
    name: str
    title: str = ""
    company: str = ""
    linkedin_url: str = ""
    source: str = ""
    confidence: float = 0.5

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "title": self.title,
            "company": self.company,
            "linkedin_url": self.linkedin_url,
            "source": self.source,
            "confidence": self.confidence,
        }


# ── Cache ────────────────────────────────────────────────────────────

def _cache_key(company: str, roles: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    h = hashlib.md5(f"{company}:{roles}".lower().encode()).hexdigest()[:12]
    return CACHE_DIR / f"people_{h}.json"


def _cache_get(company: str, roles: str) -> list[dict] | None:
    path = _cache_key(company, roles)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        ts = data.get("ts", 0)
        if (datetime.now(timezone.utc).timestamp() - ts) > CACHE_TTL_DAYS * 86400:
            return None
        return data.get("results", [])
    except Exception:
        return None


def _cache_set(company: str, roles: str, results: list[dict]):
    path = _cache_key(company, roles)
    path.write_text(json.dumps({
        "ts": datetime.now(timezone.utc).timestamp(),
        "company": company,
        "roles": roles,
        "results": results,
    }))


# ── Search engine helpers ────────────────────────────────────────────

async def _search_ddg(query: str) -> list[dict]:
    """Search DuckDuckGo HTML, return list of {title, url, snippet}."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            resp = await c.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers={"User-Agent": get_random_user_agent()},
            )
            soup = BeautifulSoup(resp.text, "html.parser")
            results = []
            for r in soup.select(".result"):
                title_el = r.select_one(".result__title a")
                snippet_el = r.select_one(".result__snippet")
                if title_el:
                    url = title_el.get("href", "")
                    # DDG wraps URLs in a redirect — extract real URL
                    if "uddg=" in url:
                        from urllib.parse import parse_qs, urlparse as _urlparse
                        # Fix scheme-less URLs (//duckduckgo.com/...)
                        if url.startswith("//"):
                            url = "https:" + url
                        parsed = _urlparse(url)
                        url = parse_qs(parsed.query).get("uddg", [url])[0]
                    results.append({
                        "title": title_el.get_text(strip=True),
                        "url": url,
                        "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
                    })
            return results
    except Exception as e:
        logger.warning(f"DDG search failed: {e}")
        return []


async def _search_bing(query: str) -> list[dict]:
    """Search Bing, return list of {title, url, snippet}."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            resp = await c.get(
                "https://www.bing.com/search",
                params={"q": query},
                headers={"User-Agent": get_random_user_agent()},
            )
            soup = BeautifulSoup(resp.text, "html.parser")
            results = []
            for li in soup.select("#b_results .b_algo"):
                link = li.select_one("h2 a")
                snippet = li.select_one(".b_caption p")
                if link:
                    results.append({
                        "title": link.get_text(strip=True),
                        "url": link.get("href", ""),
                        "snippet": snippet.get_text(strip=True) if snippet else "",
                    })
            return results
    except Exception as e:
        logger.warning(f"Bing search failed: {e}")
        return []


# ── Source 1: LinkedIn Google Dorks ──────────────────────────────────

def _parse_search_result(result: dict, company: str) -> PersonResult | None:
    """Parse a search result for a person — works with LinkedIn, Bloomberg, Crunchbase, etc."""
    url = result.get("url", "")
    title_text = result.get("title", "")
    snippet = result.get("snippet", "")

    # Identify source type
    is_linkedin = "linkedin.com/in/" in url
    is_bloomberg = "bloomberg.com/profile/person" in url
    is_crunchbase = "crunchbase.com/person" in url

    if not (is_linkedin or is_bloomberg or is_crunchbase):
        return None

    # Parse name from title — format is usually "Name - Title at Company | Site"
    parts = re.split(r"\s*[-–—|:]\s*", title_text)
    if not parts:
        return None

    name = parts[0].strip()
    # Remove site names from end
    parts = [p for p in parts[1:] if not any(w in p.lower() for w in ["linkedin", "bloomberg", "crunchbase", "profile"])]
    job_title = parts[0].strip() if parts else ""

    # Clean name
    name = re.sub(r"[.…·]+$", "", name).strip()
    # Remove common prefixes
    name = re.sub(r"^(Mr\.|Mrs\.|Ms\.|Dr\.)\s*", "", name).strip()

    if not _is_person_name(name):
        return None

    linkedin_url = url.split("?")[0] if is_linkedin else ""

    return PersonResult(
        name=name,
        title=job_title,
        company=company,
        linkedin_url=linkedin_url,
        source="linkedin_dork" if is_linkedin else "web_profile",
        confidence=0.75 if is_linkedin else 0.7,
    )


async def find_via_linkedin_dork(
    company: str,
    roles: list[str] | None = None,
    location: str = "",
    count: int = 10,
) -> list[PersonResult]:
    """Find people at a company via Google-dorked LinkedIn profiles."""
    role_query = " OR ".join(f'"{r}"' for r in roles) if roles else ""
    location_query = f'"{location}"' if location else ""

    # Build queries — keep simple, DDG/Bing struggle with complex dorks
    queries = []
    if roles:
        for role in roles[:3]:
            queries.append(f"{company} {role} linkedin.com/in {location_query}".strip())
    else:
        queries.append(f"{company} leadership linkedin.com/in")
        queries.append(f"{company} team linkedin.com/in")

    results = []
    seen_urls = set()

    for query in queries:
        # Bing first (returns more LinkedIn results than DDG)
        search_results = await _search_bing(query)
        if len(search_results) < 3:
            await asyncio.sleep(get_random_delay(1.0, 2.0))
            search_results.extend(await _search_ddg(query))

        for sr in search_results:
            person = _parse_search_result(sr, company)
            if person and person.linkedin_url not in seen_urls:
                seen_urls.add(person.linkedin_url)
                results.append(person)
                if len(results) >= count:
                    break

        if len(results) >= count:
            break
        await asyncio.sleep(get_random_delay(1.0, 2.0))

    return results[:count]


# ── Source 2: Company Website Team Pages ─────────────────────────────

TEAM_PAGE_PATHS = [
    "/about", "/about-us", "/team", "/our-team", "/leadership",
    "/people", "/about/team", "/about/leadership", "/company/team",
    "/about/people", "/management", "/founders",
]


async def find_via_company_website(
    company: str,
    domain: str = "",
    count: int = 10,
) -> list[PersonResult]:
    """Scrape company website team/about pages for people."""
    if not domain:
        from app.services.domain_resolver import resolve_domain
        domain = await resolve_domain(company)
    if not domain:
        return []

    results = []
    async with httpx.AsyncClient(
        timeout=10.0, follow_redirects=True, verify=False,
        headers={"User-Agent": get_random_user_agent()},
    ) as c:
        for path in TEAM_PAGE_PATHS:
            if len(results) >= count:
                break
            try:
                resp = await c.get(f"https://{domain}{path}")
                if resp.status_code != 200:
                    continue
                people = _extract_people_from_html(resp.text, company)
                for p in people:
                    if p.name not in {r.name for r in results}:
                        results.append(p)
            except Exception:
                continue

    return results[:count]


_NOT_NAMES = {
    # Section/page words
    "team", "about", "leader", "our", "meet", "contact", "board", "company",
    "people", "jobs", "department", "division", "office", "service", "solution",
    "business", "development", "engineering", "operations", "sales", "marketing",
    "technical", "delivery", "process", "improvement", "innovation", "digital",
    "read", "more", "view", "all", "see", "click", "here", "learn", "home",
    # Role/title words — these are titles, not person names
    "vice", "president", "senior", "junior", "chief", "officer", "head",
    "manager", "director", "lead", "executive", "partner", "founder",
    "ceo", "cto", "cfo", "coo", "cio", "vp", "svp", "evp", "avp",
    "analyst", "consultant", "architect", "engineer", "specialist",
    "associate", "assistant", "coordinator", "administrator",
    "global", "regional", "national", "india", "strategy", "product",
    "program", "project", "support", "customer", "human", "resource",
    "finance", "legal", "compliance", "audit", "risk", "media",
    # Action/description words that appear in section headings
    "strengthening", "inspiring", "building", "driving", "leading",
    "transforming", "enabling", "empowering", "accelerating", "delivering",
    "future", "impact", "organizational", "leaders", "excellence",
    "overview", "mission", "vision", "values", "culture", "careers",
    "news", "press", "blog", "events", "awards", "recognition",
}


def _is_person_name(text: str) -> bool:
    """Check if text looks like a person's name."""
    words = text.split()
    if len(words) < 2 or len(words) > 5:
        return False
    if len(text) > 40:
        return False
    # No numbers
    if re.search(r"\d", text):
        return False
    # Each word should start uppercase, no special chars
    for w in words:
        if not w[0].isupper():
            return False
        if re.search(r"[^a-zA-Z.\-']", w):
            return False
    # No organizational words
    if any(w.lower() in _NOT_NAMES for w in words):
        return False
    return True


def _extract_people_from_html(html: str, company: str) -> list[PersonResult]:
    """Extract people names and titles from HTML team pages."""
    soup = BeautifulSoup(html, "html.parser")
    people = []

    # Pattern 1: headings with name, followed by sibling with title
    for heading in soup.select("h2, h3, h4, h5"):
        name = heading.get_text(strip=True)
        if not _is_person_name(name):
            continue

        title = ""
        next_el = heading.find_next_sibling()
        if next_el and next_el.name in ("p", "span", "div"):
            title = next_el.get_text(strip=True)
            if len(title) > 80 or _is_person_name(title):
                title = ""

        people.append(PersonResult(
            name=name, title=title, company=company,
            source="company_website", confidence=0.8,
        ))

    # Pattern 2: structured cards (divs with class containing "card", "member", "person")
    for card in soup.select('[class*="card"], [class*="member"], [class*="person"], [class*="team"]'):
        name_el = card.select_one("h3, h4, h5, strong, [class*='name']")
        title_el = card.select_one("p, span, [class*='title'], [class*='role'], [class*='position']")
        if name_el:
            name = name_el.get_text(strip=True)
            if _is_person_name(name) and name not in {p.name for p in people}:
                title = title_el.get_text(strip=True)[:80] if title_el else ""
                people.append(PersonResult(
                    name=name, title=title, company=company,
                    source="company_website", confidence=0.8,
                ))

    return people


# ── Source 3: GitHub Organization ────────────────────────────────────

async def find_via_github_org(
    company: str,
    org_name: str = "",
    count: int = 10,
) -> list[PersonResult]:
    """Find people from a company's GitHub organization."""
    if not org_name:
        org_name = company.lower().replace(" ", "").replace(".", "")

    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            resp = await c.get(
                f"https://api.github.com/orgs/{org_name}/members",
                params={"per_page": min(count * 2, 30)},
                headers={"Accept": "application/vnd.github.v3+json"},
            )
            if resp.status_code != 200:
                return []

            results = []
            for member in resp.json():
                login = member.get("login", "")
                # Get full profile
                profile = await c.get(
                    f"https://api.github.com/users/{login}",
                    headers={"Accept": "application/vnd.github.v3+json"},
                )
                if profile.status_code == 200:
                    data = profile.json()
                    name = data.get("name") or login
                    if name and name != login:
                        results.append(PersonResult(
                            name=name,
                            title=data.get("bio", "")[:60] if data.get("bio") else "",
                            company=data.get("company", company),
                            source="github_org",
                            confidence=0.6,
                        ))
                        if len(results) >= count:
                            break
                await asyncio.sleep(0.3)

            return results
    except Exception as e:
        logger.warning(f"GitHub org search failed: {e}")
        return []


# ── Source 4: Web Search for People ──────────────────────────────────

async def find_via_web_search(
    company: str,
    roles: list[str] | None = None,
    count: int = 10,
) -> list[PersonResult]:
    """Find people by searching for company leadership pages and extracting names."""
    queries = [f"{company} leadership team"]
    if roles:
        queries.append(f"{company} {roles[0]}")

    results = []
    seen = set()

    for query in queries:
        search_results = await _search_ddg(query)
        for sr in search_results[:3]:
            url = sr.get("url", "")
            if not url or any(d in url for d in ["linkedin.com", "facebook.com", "twitter.com"]):
                continue
            # Scrape the page for people
            try:
                async with httpx.AsyncClient(
                    timeout=8.0, follow_redirects=True, verify=False,
                    headers={"User-Agent": get_random_user_agent()},
                ) as c:
                    resp = await c.get(url)
                    if resp.status_code == 200:
                        people = _extract_people_from_html(resp.text, company)
                        for p in people:
                            if p.name.lower() not in seen:
                                seen.add(p.name.lower())
                                p.source = "web_search"
                                results.append(p)
            except Exception:
                continue

        if len(results) >= count:
            break

    return results[:count]


# ── Main finder ──────────────────────────────────────────────────────

async def find_people(
    company: str,
    roles: list[str] | None = None,
    department: str = "",
    location: str = "",
    count: int = 10,
    domain: str = "",
) -> list[dict]:
    """Find people at a company using multiple sources.

    Args:
        company: Company name (e.g., "TCS", "Google")
        roles: Role filters (e.g., ["VP", "Director", "Manager"])
        department: Department filter (e.g., "Engineering", "Marketing")
        location: Location filter (e.g., "Bangalore", "India")
        count: Target number of people to find
        domain: Company email domain (optional, for website scraping)

    Returns:
        List of person dicts with name, title, company, linkedin_url, source.
    """
    roles_key = ",".join(sorted(roles)) if roles else ""
    cache_key_str = f"{company}:{roles_key}:{department}:{location}"

    # Check cache
    cached = _cache_get(company, cache_key_str)
    if cached:
        logger.info(f"Cache hit: {len(cached)} people for {company}")
        return cached[:count]

    logger.info(f"Finding people at {company} (roles={roles}, dept={department}, loc={location})")

    # Build role list with department
    search_roles = list(roles or [])
    if department and not roles:
        search_roles = [f"{department} Manager", f"{department} Director", f"{department} Lead"]

    # Run sources in parallel
    tasks = [
        find_via_linkedin_dork(company, search_roles, location, count),
        find_via_company_website(company, domain, count),
        find_via_web_search(company, search_roles, count),
    ]

    all_results = await asyncio.gather(*tasks, return_exceptions=True)

    # Merge and deduplicate
    people: list[PersonResult] = []
    seen_names: set[str] = set()

    for result_list in all_results:
        if isinstance(result_list, Exception):
            logger.warning(f"Source failed: {result_list}")
            continue
        for person in result_list:
            name_key = person.name.lower().strip()
            if name_key not in seen_names:
                seen_names.add(name_key)
                people.append(person)

    # Sort by confidence (highest first)
    people.sort(key=lambda p: p.confidence, reverse=True)
    results = [p.to_dict() for p in people[:count]]

    # Cache results
    if results:
        _cache_set(company, cache_key_str, results)

    logger.info(f"Found {len(results)} people at {company}")
    return results
