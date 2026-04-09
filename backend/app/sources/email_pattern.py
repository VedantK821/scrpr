import asyncio
import re
from app.sources.base import EnrichmentSource, SourceResult
from app.scraper.email_verifier import EmailVerifier, EmailVerifyStatus

PATTERNS = [
    "{first}.{last}@{domain}",
    "{first}{last}@{domain}",
    "{f}{last}@{domain}",
    "{first}@{domain}",
    "{first}_{last}@{domain}",
    "{last}.{first}@{domain}",
]


class EmailPatternSource(EnrichmentSource):
    name = "email_pattern"
    rate_limit_per_minute = 10  # Lower now because SMTP checks are slow

    def __init__(self):
        self.verifier = EmailVerifier()

    async def enrich(self, row_data: dict[str, str], prompt: str) -> SourceResult:
        full_name = (
            row_data.get("name")
            or row_data.get("full_name")
            or row_data.get("Recruiter")
            or row_data.get("Hiring Contact")
            or ""
        )
        domain = row_data.get("domain") or row_data.get("Domain") or row_data.get("website") or ""
        company = row_data.get("company") or row_data.get("Company") or row_data.get("Name") or ""

        if not full_name:
            return SourceResult(found=False, source_name=self.name, error="No name provided")
        if not domain and not company:
            return SourceResult(found=False, source_name=self.name, error="No domain or company provided")

        # Derive domain from company name if not provided
        if not domain and company:
            # Clean company name to make a domain guess
            clean = re.sub(r'[^a-zA-Z0-9\s]', '', company).strip()
            domain = clean.lower().replace(" ", "") + ".com"

        parts = full_name.lower().split()
        if len(parts) < 2:
            return SourceResult(found=False, source_name=self.name, error="Need first and last name")

        first = re.sub(r'[^a-z]', '', parts[0])
        last = re.sub(r'[^a-z]', '', parts[-1])
        f = first[0] if first else ""
        domain = domain.lower().replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]

        candidates = []
        for pattern in PATTERNS:
            email = pattern.format(first=first, last=last, f=f, domain=domain)
            candidates.append(email)

        # Try to verify each candidate via SMTP
        try:
            # First check if it's a catch-all domain
            is_catch_all = await self.verifier.is_catch_all(domain)

            if is_catch_all:
                # Can't verify individual emails — return best guess
                return SourceResult(
                    found=True,
                    value=candidates[0],  # first.last is most common
                    data={"candidates": candidates, "method": "pattern_catch_all", "verified": False},
                    confidence=0.5,
                    source_name=self.name,
                )

            # Verify candidates until we find a valid one
            for email in candidates:
                result = await self.verifier.verify(email)
                if result.status == EmailVerifyStatus.VALID:
                    return SourceResult(
                        found=True,
                        value=email,
                        data={
                            "candidates": candidates,
                            "method": "pattern_smtp_verified",
                            "verified": True,
                            "mx_host": result.mx_host,
                        },
                        confidence=0.9,  # SMTP verified = high confidence
                        source_name=self.name,
                    )

        except Exception:
            pass  # Fall through to unverified guess

        # No verification possible — return best guess
        return SourceResult(
            found=True,
            value=candidates[0],
            data={"candidates": candidates, "method": "pattern_unverified", "verified": False},
            confidence=0.4,
            source_name=self.name,
        )
