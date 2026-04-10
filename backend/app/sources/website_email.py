import re
import logging
from app.sources.base import EnrichmentSource, SourceResult
from app.scraper.engine import ScrapingEngine

logger = logging.getLogger(__name__)

# Pages most likely to contain team/contact emails
CONTACT_PATHS = [
    "/contact", "/contact-us", "/about", "/about-us",
    "/team", "/our-team", "/people", "/leadership",
    "/company", "/careers", "/jobs",
]

# Regex for extracting emails from page text
EMAIL_REGEX = re.compile(
    r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b'
)

# Emails to skip (generic/noreply)
SKIP_PREFIXES = {
    "noreply", "no-reply", "donotreply", "do-not-reply",
    "info", "support", "hello", "contact", "admin", "webmaster",
    "sales", "marketing", "press", "media", "privacy",
    "abuse", "postmaster", "mailer-daemon", "help",
}


def _resolve_website(company: str, domain: str) -> str:
    """Get the base website URL for a company."""
    if domain:
        d = domain.lower().replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]
        if d:
            return f"https://www.{d}"

    # Fallback: guess from company name
    from app.sources.email_pattern import _resolve_domain
    guessed = _resolve_domain(company, "")
    return f"https://www.{guessed}" if guessed else ""


def _is_personal_email(email: str) -> bool:
    """Check if an email looks like a personal (non-generic) work email."""
    local = email.split("@")[0].lower()
    if local in SKIP_PREFIXES:
        return False
    # Personal emails usually have dots, underscores, or are short names
    if any(c in local for c in "._%+-"):
        return True
    # Short local parts are more likely to be personal (e.g., "john@company.com")
    if len(local) <= 15:
        return True
    return True


class WebsiteEmailSource(EnrichmentSource):
    name = "website_email"
    rate_limit_per_minute = 10

    def __init__(self):
        self.engine = ScrapingEngine()

    async def enrich(self, row_data: dict[str, str], prompt: str) -> SourceResult:
        company = (
            row_data.get("company") or row_data.get("Company")
            or row_data.get("Company Name") or row_data.get("Name") or ""
        )
        domain = row_data.get("domain") or row_data.get("Domain") or row_data.get("website") or ""

        if not company and not domain:
            return SourceResult(found=False, source_name=self.name, error="No company or domain")

        base_url = _resolve_website(company, domain)
        if not base_url:
            return SourceResult(found=False, source_name=self.name, error="Could not resolve website")

        all_emails = set()
        pages_checked = 0

        for path in CONTACT_PATHS:
            url = f"{base_url}{path}"
            try:
                result = await self.engine.scrape(url)
                pages_checked += 1
                if result.success and result.text:
                    found = EMAIL_REGEX.findall(result.text)
                    # Filter to same domain and personal emails
                    expected_domain = base_url.replace("https://www.", "").replace("http://www.", "").split("/")[0]
                    for email in found:
                        email_domain = email.split("@")[1].lower()
                        if email_domain == expected_domain and _is_personal_email(email):
                            all_emails.add(email.lower())
            except Exception as e:
                logger.debug(f"Failed to scrape {url}: {e}")

            if all_emails:
                break  # Found emails, no need to check more pages

        if not all_emails:
            return SourceResult(
                found=False, source_name=self.name,
                error=f"No personal emails found on {pages_checked} pages",
            )

        # Return the first personal email found
        email = sorted(all_emails)[0]
        return SourceResult(
            found=True, value=email,
            data={
                "all_emails": sorted(all_emails),
                "method": "website_scrape",
                "verified": False,
                "pages_checked": pages_checked,
            },
            confidence=0.8,  # Published on company website = high confidence
            source_name=self.name,
        )
