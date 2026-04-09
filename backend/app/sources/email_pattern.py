import re
from app.sources.base import EnrichmentSource, SourceResult

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
    rate_limit_per_minute = 30

    async def enrich(self, row_data: dict[str, str], prompt: str) -> SourceResult:
        full_name = row_data.get("name") or row_data.get("full_name") or row_data.get("Recruiter") or ""
        domain = row_data.get("domain") or row_data.get("website") or ""
        company = row_data.get("company") or row_data.get("Company") or ""

        if not full_name:
            return SourceResult(found=False, source_name=self.name, error="No name provided")
        if not domain and not company:
            return SourceResult(found=False, source_name=self.name, error="No domain or company provided")

        # Derive domain from company name if not provided
        if not domain and company:
            domain = company.lower().replace(" ", "") + ".com"

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

        # Return the most common pattern as best guess
        best = candidates[0]  # first.last@domain is most common
        return SourceResult(
            found=True,
            value=best,
            data={"candidates": candidates, "method": "pattern_generation"},
            confidence=0.4,  # Pattern guesses have moderate confidence
            source_name=self.name,
        )
