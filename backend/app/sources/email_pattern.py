import re
import logging
from app.sources.base import EnrichmentSource, SourceResult
from app.scraper.email_verifier import EmailVerifier, EmailVerifyStatus
from app.services.email_cache import EmailCacheService

logger = logging.getLogger(__name__)

# Ordered by frequency in the real world (first.last is ~48% of companies)
ALL_PATTERNS = [
    "{first}.{last}@{domain}",
    "{first}{last}@{domain}",
    "{f}{last}@{domain}",
    "{f}.{last}@{domain}",
    "{first}_{last}@{domain}",
    "{first}-{last}@{domain}",
    "{last}.{first}@{domain}",
    "{last}{first}@{domain}",
    "{last}{f}@{domain}",
    "{last}_{first}@{domain}",
    "{first}@{domain}",
    "{last}@{domain}",
    "{f}{l}@{domain}",
    "{first}.{l}@{domain}",
    "{first}{middle}.{last}@{domain}",
    "{f}{middle}{last}@{domain}",
]

# Common company name → actual domain mappings (Indian companies + global MNCs)
KNOWN_DOMAINS = {
    "tcs": "tcs.com",
    "tata consultancy services": "tcs.com",
    "infosys": "infosys.com",
    "wipro": "wipro.com",
    "hcl": "hcltech.com",
    "hcl technologies": "hcltech.com",
    "reliance": "ril.com",
    "reliance industries": "ril.com",
    "mahindra": "mahindra.com",
    "tech mahindra": "techmahindra.com",
    "larsen & toubro": "larsentoubro.com",
    "l&t": "larsentoubro.com",
    "bajaj": "bajaj.com",
    "hdfc bank": "hdfcbank.com",
    "icici bank": "icicibank.com",
    "axis bank": "axisbank.com",
    "kotak mahindra": "kotak.com",
    "state bank of india": "sbi.co.in",
    "sbi": "sbi.co.in",
    "hindustan unilever": "hul.co.in",
    "itc": "itcportal.com",
    "asian paints": "asianpaints.com",
    "mckinsey": "mckinsey.com",
    "bcg": "bcg.com",
    "bain": "bain.com",
    "deloitte": "deloitte.com",
    "pwc": "pwc.com",
    "ey": "ey.com",
    "ernst & young": "ey.com",
    "kpmg": "kpmg.com",
    "accenture": "accenture.com",
    "capgemini": "capgemini.com",
    "cognizant": "cognizant.com",
    "ibm": "ibm.com",
    "google": "google.com",
    "microsoft": "microsoft.com",
    "amazon": "amazon.com",
    "meta": "meta.com",
    "apple": "apple.com",
    "oracle": "oracle.com",
    "salesforce": "salesforce.com",
    "adobe": "adobe.com",
    "dell": "dell.com",
    "hp": "hp.com",
    "samsung": "samsung.com",
    "sony": "sony.com",
    "goldman sachs": "gs.com",
    "jp morgan": "jpmorgan.com",
    "morgan stanley": "morganstanley.com",
    "deutsche bank": "db.com",
    "barclays": "barclays.com",
    "hsbc": "hsbc.com",
    "unilever": "unilever.com",
    "nestle": "nestle.com",
    "procter & gamble": "pg.com",
    "p&g": "pg.com",
}


def _resolve_domain(company: str, raw_domain: str) -> str:
    """Resolve company name to actual email domain."""
    if raw_domain:
        d = raw_domain.lower().replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]
        if d:
            return d

    if not company:
        return ""

    # Check known domains first
    company_lower = company.lower().strip()
    for key, domain in KNOWN_DOMAINS.items():
        if key in company_lower or company_lower in key:
            return domain

    # Fallback: clean and guess
    # Try removing common suffixes, but keep at least the core name
    clean = re.sub(r'\b(ltd|limited|inc|incorporated|pvt|private|corporation|llp|llc)\b', '', company_lower, flags=re.IGNORECASE)
    clean = re.sub(r'[^a-z0-9\s]', '', clean).strip()
    clean = re.sub(r'\s+', '', clean)
    if clean:
        return f"{clean}.com"
    # If everything was stripped, just use the raw company name
    fallback = re.sub(r'[^a-z0-9]', '', company_lower)
    return f"{fallback}.com" if fallback else ""


def _parse_name(full_name: str) -> dict:
    """Parse a full name into first, middle, last, and initial components."""
    parts = full_name.strip().lower().split()
    # Remove common titles/suffixes
    skip = {"mr", "mrs", "ms", "dr", "prof", "sir", "shri", "smt", "jr", "sr", "ii", "iii"}
    parts = [p for p in parts if p.rstrip(".") not in skip]

    if not parts:
        return {}

    first = re.sub(r'[^a-z]', '', parts[0])

    if len(parts) == 1:
        return {"first": first, "last": "", "middle": "", "f": first[0] if first else "", "l": ""}

    last = re.sub(r'[^a-z]', '', parts[-1])
    middle = re.sub(r'[^a-z]', '', parts[1]) if len(parts) > 2 else ""

    return {
        "first": first,
        "last": last,
        "middle": middle,
        "f": first[0] if first else "",
        "l": last[0] if last else "",
        "m": middle[0] if middle else "",
    }


def _generate_candidates(name_parts: dict, domain: str) -> list[str]:
    """Generate email candidates, ordered by likelihood."""
    if not name_parts.get("first") or not domain:
        return []

    candidates = []
    for pattern in ALL_PATTERNS:
        try:
            # Skip patterns requiring middle name if we don't have one
            if "{middle}" in pattern and not name_parts.get("middle"):
                continue
            email = pattern.format(domain=domain, **name_parts)
            if email and email not in candidates:
                candidates.append(email)
        except KeyError:
            continue
    return candidates


class EmailPatternSource(EnrichmentSource):
    name = "email_pattern"
    rate_limit_per_minute = 10

    def __init__(self):
        self.verifier = EmailVerifier()
        self.cache = EmailCacheService()

    async def enrich(self, row_data: dict[str, str], prompt: str) -> SourceResult:
        from app.services.contact_parser import extract_name

        raw_name = (
            row_data.get("Key Contact")
            or row_data.get("Contact")
            or row_data.get("name") or row_data.get("full_name")
            or row_data.get("Recruiter") or row_data.get("Hiring Contact")
            or ""
        )
        full_name = extract_name(raw_name) if raw_name else ""
        raw_domain = row_data.get("domain") or row_data.get("Domain") or row_data.get("website") or ""
        company = row_data.get("company") or row_data.get("Company") or row_data.get("Name") or ""

        if not full_name:
            return SourceResult(found=False, source_name=self.name, error="No name provided")
        if not raw_domain and not company:
            return SourceResult(found=False, source_name=self.name, error="No domain or company provided")

        # Smart domain resolution
        domain = _resolve_domain(company, raw_domain)
        if not domain:
            return SourceResult(found=False, source_name=self.name, error=f"Could not resolve domain for '{company}'")

        # Parse name (handles titles, middle names, Indian names)
        name_parts = _parse_name(full_name)
        if not name_parts.get("first") or not name_parts.get("last"):
            return SourceResult(found=False, source_name=self.name, error="Need at least first and last name")

        # Step 1: Check if we already know this domain's pattern from cache
        learned_pattern = await self._learn_pattern_from_cache(domain)

        # Step 2: Generate candidates
        candidates = _generate_candidates(name_parts, domain)
        if not candidates:
            return SourceResult(found=False, source_name=self.name, error="Could not generate email candidates")

        # If we learned a pattern, put that format first
        if learned_pattern and learned_pattern in candidates:
            candidates.remove(learned_pattern)
            candidates.insert(0, learned_pattern)

        # Step 3: Try SMTP verification first (works from servers, often blocked from home IPs)
        try:
            is_catch_all = await self.verifier.is_catch_all(domain)

            if is_catch_all:
                best = candidates[0]
                return SourceResult(
                    found=True, value=best,
                    data={"candidates": candidates[:5], "method": "pattern_catch_all", "verified": False, "domain_pattern": "catch_all"},
                    confidence=0.5, source_name=self.name,
                )

            for email in candidates[:8]:
                result = await self.verifier.verify(email)
                if result.status == EmailVerifyStatus.VALID:
                    return SourceResult(
                        found=True, value=email,
                        data={"candidates": candidates[:5], "method": "pattern_smtp_verified", "verified": True, "mx_host": result.mx_host},
                        confidence=0.9, source_name=self.name,
                    )

        except Exception as e:
            logger.debug(f"SMTP verification failed: {e}")

        # Step 4: DNS MX check — confirm domain accepts email
        best = candidates[0]
        mx_host = await self.verifier._get_mx_host(domain)
        has_mx = mx_host is not None

        return SourceResult(
            found=True, value=best,
            data={"candidates": candidates[:5], "method": "pattern_mx_only" if has_mx else "pattern_unverified", "verified": False, "has_mx": has_mx},
            confidence=0.5 if has_mx else 0.3, source_name=self.name,
        )

    async def _learn_pattern_from_cache(self, domain: str) -> str | None:
        """Check the email cache for known emails at this domain to learn the pattern."""
        try:
            cached_emails = await self.cache.lookup_by_domain(domain)
            if not cached_emails:
                return None

            # Find the most common pattern from cached emails
            patterns_seen = {}
            for entry in cached_emails:
                email = entry.email
                name = entry.person_name.lower().split()
                if len(name) < 2:
                    continue
                first = re.sub(r'[^a-z]', '', name[0])
                last = re.sub(r'[^a-z]', '', name[-1])
                local = email.split("@")[0]

                # Detect which pattern this email matches
                if local == f"{first}.{last}":
                    patterns_seen["first.last"] = patterns_seen.get("first.last", 0) + 1
                elif local == f"{first}{last}":
                    patterns_seen["firstlast"] = patterns_seen.get("firstlast", 0) + 1
                elif local == f"{first[0]}{last}":
                    patterns_seen["flast"] = patterns_seen.get("flast", 0) + 1
                elif local == f"{first[0]}.{last}":
                    patterns_seen["f.last"] = patterns_seen.get("f.last", 0) + 1
                elif local == first:
                    patterns_seen["first"] = patterns_seen.get("first", 0) + 1

            if not patterns_seen:
                return None

            # Return the most common pattern
            best_pattern = max(patterns_seen, key=patterns_seen.get)
            logger.info(f"Learned domain pattern for {domain}: {best_pattern} (from {sum(patterns_seen.values())} cached emails)")
            return best_pattern  # This is the pattern name, not the email — caller maps it

        except Exception:
            return None
