"""Mine employee emails from GitHub organization repositories."""
import logging
import os
import re
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
# Filter out bot/system emails
SKIP_EMAILS = {
    "noreply@github.com",
    "actions@github.com",
    "dependabot@github.com",
}
SKIP_PATTERNS = [
    r".*noreply.*",
    r".*\+.*@.*",  # Plus-addressed emails (user+tag@)
    r"\d+\+.*@users\.noreply\.github\.com",  # GitHub noreply
    r".*bot.*@.*",
    r".*dependabot.*",
    r".*renovate.*",
]


@dataclass
class MineResult:
    company: str
    domain: str = ""
    emails: list[str] = field(default_factory=list)
    pattern: str = ""  # e.g., "first.last", "firstlast", "first"
    repos_scanned: int = 0
    commits_scanned: int = 0


def _get_headers() -> dict:
    """Get GitHub API headers with optional auth token."""
    headers = {"Accept": "application/vnd.github.v3+json"}
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        headers["Authorization"] = f"token {token}"
    return headers


def _is_real_email(email: str) -> bool:
    """Filter out bot/system/noreply emails."""
    email_lower = email.lower()
    if email_lower in SKIP_EMAILS:
        return False
    for pattern in SKIP_PATTERNS:
        if re.match(pattern, email_lower):
            return False
    if "@users.noreply.github.com" in email_lower:
        return False
    return True


def _detect_pattern(emails: list[str], domain: str) -> str:
    """Detect the most common email pattern from a set of emails at a domain.

    Returns pattern name like 'first.last', 'firstlast', 'first', 'flast', etc.
    """
    # This is a heuristic — look at the local part structure
    patterns = {}
    for email in emails:
        local = email.split("@")[0].lower()
        if "." in local:
            parts = local.split(".")
            if len(parts) == 2:
                patterns["first.last"] = patterns.get("first.last", 0) + 1
            elif len(parts) > 2:
                patterns["first.middle.last"] = patterns.get("first.middle.last", 0) + 1
        elif "_" in local:
            patterns["first_last"] = patterns.get("first_last", 0) + 1
        elif "-" in local:
            patterns["first-last"] = patterns.get("first-last", 0) + 1
        elif len(local) <= 5:
            patterns["short"] = patterns.get("short", 0) + 1
        else:
            patterns["firstlast"] = patterns.get("firstlast", 0) + 1

    if not patterns:
        return ""
    return max(patterns, key=patterns.get)


async def mine_github_emails(company: str, expected_domain: str = "") -> MineResult:
    """Search GitHub for a company's org and mine employee emails from commits.

    Args:
        company: Company name to search for (e.g., "Zapier", "Slack")
        expected_domain: Expected email domain (e.g., "zapier.com").
                        If provided, only emails at this domain are returned.

    Returns:
        MineResult with found emails, detected pattern, and stats.
    """
    result = MineResult(company=company, domain=expected_domain)
    headers = _get_headers()

    async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
        # Step 1: Search for the company's GitHub organization
        try:
            search_resp = await client.get(
                f"{GITHUB_API}/search/users",
                params={"q": f"{company} type:org", "per_page": 3},
            )
            if search_resp.status_code != 200:
                logger.warning(f"GitHub org search failed: {search_resp.status_code}")
                return result

            orgs = search_resp.json().get("items", [])
            if not orgs:
                logger.info(f"No GitHub orgs found for '{company}'")
                return result
        except Exception as e:
            logger.warning(f"GitHub org search error: {e}")
            return result

        all_emails = set()

        # Step 2: For each org, get their repos
        for org in orgs[:2]:  # Check top 2 matching orgs
            org_login = org["login"]
            try:
                repos_resp = await client.get(
                    f"{GITHUB_API}/orgs/{org_login}/repos",
                    params={"sort": "pushed", "per_page": 5, "type": "public"},
                )
                if repos_resp.status_code != 200:
                    continue
                repos = repos_resp.json()
            except Exception:
                continue

            # Step 3: For each repo, get recent commits
            for repo in repos[:5]:
                repo_name = repo.get("full_name", "")
                result.repos_scanned += 1

                try:
                    commits_resp = await client.get(
                        f"{GITHUB_API}/repos/{repo_name}/commits",
                        params={"per_page": 30},
                    )
                    if commits_resp.status_code != 200:
                        continue
                    commits = commits_resp.json()
                except Exception:
                    continue

                for commit in commits:
                    result.commits_scanned += 1
                    # Extract author email
                    author = commit.get("commit", {}).get("author", {})
                    email = author.get("email", "")

                    if not email or not _is_real_email(email):
                        continue

                    # Filter to expected domain if provided
                    if expected_domain:
                        if email.lower().endswith(f"@{expected_domain.lower()}"):
                            all_emails.add(email.lower())
                    else:
                        all_emails.add(email.lower())

        result.emails = sorted(all_emails)

        # Detect the email pattern from found emails
        if result.emails and expected_domain:
            result.pattern = _detect_pattern(result.emails, expected_domain)
            logger.info(
                f"GitHub miner: found {len(result.emails)} emails at {expected_domain}, "
                f"pattern='{result.pattern}' (scanned {result.repos_scanned} repos, "
                f"{result.commits_scanned} commits)"
            )

    return result
