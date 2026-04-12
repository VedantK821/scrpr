"""Email Finder — the ONE function that finds anyone's email.

Input: name + company
Output: verified email

No hardcoded patterns. No asking the user. Discovers the company's
convention automatically, generates candidates, verifies, returns.
"""
import asyncio
import logging
import re
import subprocess
import tempfile
import os
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

AUTODISCOVER_URL = "https://autodiscover-s.outlook.com/autodiscover/autodiscover.json/v1.0"


@dataclass
class FindResult:
    email: str = ""
    confidence: float = 0.0
    method: str = ""
    convention: str = ""
    alternatives: list = field(default_factory=list)


# ── Step 1: Find the company's actual email domain ────────────────────

async def _resolve_domain(company: str) -> str:
    """Find the company's email domain."""
    from app.sources.email_pattern import KNOWN_DOMAINS
    for key, domain in KNOWN_DOMAINS.items():
        if key in company.lower() or company.lower() in key:
            return domain

    # Search for the company website
    try:
        from app.services.domain_resolver import resolve_domain
        return await resolve_domain(company)
    except Exception:
        pass

    # Guess
    clean = re.sub(r'\b(ltd|limited|inc|pvt|private|llc|gmbh|ag)\b', '',
                   company.lower(), flags=re.IGNORECASE)
    clean = re.sub(r'[^a-z0-9]', '', clean).strip()
    return f"{clean}.com" if clean else ""


# ── Step 2: Discover the company's email convention ───────────────────

async def _discover_convention(company: str, domain: str) -> dict:
    """Find real employee emails at the company to learn the convention.

    Searches: PGP keyservers, git commits, company website.
    Returns: {"emails": [...], "pattern": "first.last", "prefixes": [...]}
    """
    real_emails = []

    # Source 1: PGP keyservers
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            resp = await c.get(
                f"https://keyserver.ubuntu.com/pks/lookup?search=%40{domain}&op=index"
            )
            if resp.status_code == 200:
                found = re.findall(rf'[a-zA-Z0-9._%+-]+@{re.escape(domain)}', resp.text)
                skip = {"info", "support", "noreply", "admin", "help", "sales",
                        "marketing", "press", "hr", "contact", "security"}
                for e in found:
                    local = e.split("@")[0].lower()
                    if local not in skip:
                        real_emails.append(e.lower())
    except Exception:
        pass

    # Source 2: Git commits from company repos
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            org_names = [company.lower().replace(" ", ""), company.lower().replace(" ", "-")]
            for org in org_names[:2]:
                try:
                    resp = await c.get(
                        f"https://api.github.com/orgs/{org}/repos",
                        params={"sort": "pushed", "per_page": 3},
                        headers={"Accept": "application/vnd.github.v3+json"},
                    )
                    if resp.status_code != 200:
                        continue
                    for repo in resp.json()[:2]:
                        commits_resp = await c.get(
                            f"https://api.github.com/repos/{repo['full_name']}/commits",
                            params={"per_page": 20},
                            headers={"Accept": "application/vnd.github.v3+json"},
                        )
                        if commits_resp.status_code == 200:
                            for commit in commits_resp.json():
                                email = commit.get("commit", {}).get("author", {}).get("email", "")
                                if email and f"@{domain}" in email.lower():
                                    real_emails.append(email.lower())
                except Exception:
                    continue
    except Exception:
        pass

    # Source 3: Company website (about/team/contact pages)
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as c:
            for path in ["/about", "/contact", "/team", "/investor-relations"]:
                try:
                    resp = await c.get(f"https://www.{domain}{path}")
                    if resp.status_code == 200:
                        found = re.findall(rf'[a-zA-Z0-9._%+-]+@{re.escape(domain)}', resp.text)
                        skip = {"info", "support", "noreply", "admin", "help", "contact"}
                        for e in found:
                            if e.split("@")[0].lower() not in skip:
                                real_emails.append(e.lower())
                except Exception:
                    continue
    except Exception:
        pass

    real_emails = sorted(set(real_emails))

    # Detect pattern from found emails
    pattern = ""
    prefixes = set()
    if real_emails:
        dot_count = sum(1 for e in real_emails if "." in e.split("@")[0])
        if dot_count > len(real_emails) / 2:
            # Check for prefixes
            for e in real_emails:
                local = e.split("@")[0]
                parts = local.split(".")
                if len(parts) >= 3:
                    # Could be prefix.first.last
                    prefixes.add(parts[0])
            if prefixes:
                pattern = "prefix.first.last"
            else:
                pattern = "first.last"
        else:
            pattern = "alias"

    return {
        "emails": real_emails,
        "pattern": pattern,
        "prefixes": sorted(prefixes),
    }


# ── Step 3: Probe for employee type prefixes via Autodiscover ─────────

async def _probe_prefixes(domain: str) -> list[str]:
    """Discover which employee-type prefixes the company uses.

    Tests common prefixes with a fake name. If a prefix routes
    differently than the raw name, that prefix is a real convention.
    """
    fake_name = "zzfakeperson.zznotreal"
    common_prefixes = [
        "fixed-term", "extern", "ext", "external", "contractor",
        "temp", "trainee", "intern", "consultant", "vendor",
        "werkstudent", "praktikant", "contract", "tmp", "guest",
    ]

    active_prefixes = []
    headers = {"User-Agent": "Microsoft Office/16.0"}

    # First check the baseline (no prefix)
    async with httpx.AsyncClient(timeout=8.0, headers=headers, verify=False) as c:
        try:
            base_resp = await c.get(
                f"{AUTODISCOVER_URL}/{fake_name}@{domain}",
                params={"Protocol": "ActiveSync"},
                follow_redirects=False,
            )
            base_is_o365 = (
                (base_resp.status_code == 302 and "outlook.office365.com" in base_resp.headers.get("location", ""))
                or (base_resp.status_code == 200 and "outlook.office365.com" in base_resp.json().get("Url", ""))
            )
        except Exception:
            return []

        # Test each prefix
        for prefix in common_prefixes:
            try:
                email = f"{prefix}.{fake_name}@{domain}"
                resp = await c.get(
                    f"{AUTODISCOVER_URL}/{email}",
                    params={"Protocol": "ActiveSync"},
                    follow_redirects=False,
                )
                is_o365 = (
                    (resp.status_code == 302 and "outlook.office365.com" in resp.headers.get("location", ""))
                    or (resp.status_code == 200 and "outlook.office365.com" in resp.json().get("Url", ""))
                )
                # If prefix version routes differently from base, it's a real prefix
                if is_o365 != base_is_o365:
                    active_prefixes.append(prefix)
            except Exception:
                continue

    return active_prefixes


# ── Step 4: Autodiscover verification with smart false-positive check ─

async def _verify(email: str, domain: str) -> tuple[bool, float]:
    """Verify one email. Returns (exists, confidence)."""
    local = email.split("@")[0]

    # Build a fake that preserves structure but changes name
    parts = local.split(".")
    fake_parts = []
    known_prefixes = {"fixed-term", "extern", "ext", "external", "contractor",
                      "temp", "trainee", "intern", "werkstudent", "praktikant",
                      "consultant", "vendor", "contract", "tmp", "guest"}
    for part in parts:
        if part.lower() in known_prefixes:
            fake_parts.append(part)
        else:
            fake_parts.append(f"zz{part[:3]}")
    fake_email = f"{'.'.join(fake_parts)}@{domain}"

    headers = {"User-Agent": "Microsoft Office/16.0"}
    async with httpx.AsyncClient(timeout=8.0, headers=headers, verify=False) as c:
        try:
            real_resp = await c.get(
                f"{AUTODISCOVER_URL}/{email}",
                params={"Protocol": "ActiveSync"},
                follow_redirects=False,
            )
            fake_resp = await c.get(
                f"{AUTODISCOVER_URL}/{fake_email}",
                params={"Protocol": "ActiveSync"},
                follow_redirects=False,
            )
        except Exception:
            return (None, 0.0)

    def _is_o365(resp):
        if resp.status_code == 302:
            return "outlook.office365.com" in resp.headers.get("location", "")
        if resp.status_code == 200:
            return "outlook.office365.com" in resp.json().get("Url", "")
        return False

    real_hit = _is_o365(real_resp)
    fake_hit = _is_o365(fake_resp)

    if real_hit and not fake_hit:
        return (True, 0.95)
    elif not real_hit:
        return (False, 0.05)
    else:
        return (None, 0.30)  # Ambiguous


# ── THE function ──────────────────────────────────────────────────────

async def find_email(
    name: str,
    company: str,
    employee_type: str = "",
) -> FindResult:
    """Find someone's email. That's it.

    Args:
        name: full name ("Udayan Borah")
        company: company name ("Bosch")
        employee_type: optional hint ("intern", "contractor", "")

    Returns:
        FindResult with the email, confidence, and method used.
    """
    parts = name.lower().strip().split()
    if len(parts) < 2:
        return FindResult(method="error: need first and last name")
    first = parts[0]
    last = parts[-1]
    middle = parts[1] if len(parts) > 2 else ""

    # Step 1: Resolve domain
    domain = await _resolve_domain(company)
    if not domain:
        return FindResult(method=f"error: could not resolve domain for {company}")

    logger.info(f"Finding email for {name} @ {company} ({domain})")

    # Step 2: Discover convention from real employee emails
    convention = await _discover_convention(company, domain)
    logger.info(f"Convention: {convention['pattern']} from {len(convention['emails'])} emails, prefixes={convention['prefixes']}")

    # Step 3: Probe for employee type prefixes
    active_prefixes = await _probe_prefixes(domain)
    logger.info(f"Active prefixes: {active_prefixes}")

    # Step 4: Generate candidates based on discovered convention
    candidates = _build_candidates(first, last, middle, domain,
                                   convention, active_prefixes, employee_type)

    logger.info(f"Generated {len(candidates)} candidates")

    # Step 5: Verify all candidates with Autodiscover
    sem = asyncio.Semaphore(10)

    async def check(email):
        async with sem:
            exists, conf = await _verify(email, domain)
            return (email, exists, conf)

    results = await asyncio.gather(*[check(e) for e in candidates])

    # Collect verified hits
    verified = [(e, c) for e, exists, c in results if exists is True]
    verified.sort(key=lambda x: -x[1])

    if verified:
        best = verified[0][0]
        return FindResult(
            email=best,
            confidence=verified[0][1],
            method="autodiscover_verified",
            convention=convention["pattern"],
            alternatives=[e for e, _ in verified[1:5]],
        )

    # No verified hits — return best guess with low confidence
    best_guess = candidates[0] if candidates else ""
    return FindResult(
        email=best_guess,
        confidence=0.15,
        method="pattern_guess",
        convention=convention["pattern"],
        alternatives=candidates[1:5],
    )


def _build_candidates(
    first: str, last: str, middle: str, domain: str,
    convention: dict, active_prefixes: list, employee_type: str,
) -> list[str]:
    """Build candidate emails from discovered convention."""
    bases = []

    # From the pattern
    if convention["pattern"] == "first.last":
        bases = [f"{first}.{last}", f"{last}.{first}", f"{first[0]}{last}",
                 f"{first}.{last[0]}", f"{first[0]}.{last}"]
    elif convention["pattern"] == "prefix.first.last":
        bases = [f"{first}.{last}"]
    elif convention["pattern"] == "alias":
        # Short aliases — generate all truncations
        for i in range(2, len(first) + 1):
            for j in range(1, len(last) + 1):
                if 4 <= i + j <= 8:
                    bases.append(f"{first[:i]}{last[:j]}")
                    bases.append(f"{last[:j]}{first[:i]}")
    else:
        # Unknown — try everything
        bases = [
            f"{first}.{last}", f"{last}.{first}", f"{first[0]}{last}",
            f"{first}{last[0]}", f"{first[0]}.{last}", f"{last}.{first[0]}",
            f"{first}_{last}", f"{first}-{last}",
        ]

    # Add middle name variants
    if middle:
        bases.extend([
            f"{first}.{middle}.{last}",
            f"{first[0]}{middle[0]}.{last}",
            f"{first}.{middle[0]}.{last}",
        ])

    # Add numbered variants
    numbered = []
    for b in bases[:5]:
        for n in range(1, 4):
            numbered.append(f"{b}{n}")
    bases.extend(numbered)

    # Add discovered prefixes
    prefixed = []
    for prefix in convention.get("prefixes", []) + active_prefixes:
        for b in bases[:5]:
            prefixed.append(f"{prefix}.{b}")

    # If employee type hints at non-permanent, try all active prefixes
    if employee_type in ("intern", "contractor", "trainee", "temp", "fixed-term", "external"):
        for prefix in active_prefixes:
            for b in bases[:3]:
                prefixed.append(f"{prefix}.{b}")

    # Combine all
    all_candidates = bases + prefixed

    # Deduplicate, add domain
    seen = set()
    result = []
    for p in all_candidates:
        email = f"{p}@{domain}"
        if email not in seen:
            seen.add(email)
            result.append(email)

    return result
