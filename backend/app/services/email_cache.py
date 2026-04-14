import logging
import re
from collections import Counter
from datetime import datetime, timedelta
from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import async_session
from app.models.email_cache import EmailCache

logger = logging.getLogger(__name__)

# ── Pattern detection ────────────────────────────────────────────────

# Known email patterns with templates
PATTERNS = {
    "first.last": "{first}.{last}",
    "last.first": "{last}.{first}",
    "first": "{first}",
    "first.l": "{first}.{li}",
    "f.last": "{fi}.{last}",
    "firstlast": "{first}{last}",
    "lastfirst": "{last}{first}",
    "flast": "{fi}{last}",
    "firstl": "{first}{li}",
    "first.middle.last": "{first}.{middle}.{last}",
    "first.mi.last": "{first}.{mi}.{last}",
}


def detect_pattern(email: str, person_name: str) -> str | None:
    """Detect which email pattern was used for a person.

    Args:
        email: The verified email (e.g., "jane.doe@acme.co")
        person_name: The person's name (e.g., "Jane Doe")

    Returns:
        Pattern name (e.g., "first.last") or None if unknown.
    """
    local = email.split("@")[0].lower()
    parts = person_name.lower().strip().split()
    if len(parts) < 2:
        return None

    first = parts[0]
    last = parts[-1]
    middle = parts[1] if len(parts) > 2 else ""

    checks = {
        "first.last": f"{first}.{last}",
        "last.first": f"{last}.{first}",
        "first": first,
        "first.l": f"{first}.{last[0]}",
        "f.last": f"{first[0]}.{last}",
        "firstlast": f"{first}{last}",
        "lastfirst": f"{last}{first}",
        "flast": f"{first[0]}{last}",
        "firstl": f"{first}{last[0]}",
    }
    if middle:
        checks["first.middle.last"] = f"{first}.{middle}.{last}"
        checks["first.mi.last"] = f"{first}.{middle[0]}.{last}"

    for pattern_name, expected in checks.items():
        if local == expected:
            return pattern_name

    return None


def generate_from_pattern(pattern: str, person_name: str, domain: str) -> str:
    """Generate an email address from a pattern and person name."""
    parts = person_name.lower().strip().split()
    if len(parts) < 2:
        return ""

    first = parts[0]
    last = parts[-1]
    middle = parts[1] if len(parts) > 2 else ""
    fi = first[0]
    li = last[0]
    mi = middle[0] if middle else ""

    template = PATTERNS.get(pattern, "")
    if not template:
        return ""

    try:
        local = template.format(
            first=first, last=last, middle=middle,
            fi=fi, li=li, mi=mi,
        )
        return f"{local}@{domain}"
    except (KeyError, IndexError):
        return ""

# Cache entries older than this are considered stale (re-verify)
CACHE_TTL_DAYS = 90


class EmailCacheService:
    """Local cache of verified email addresses. Grows over time like Apollo's database."""

    async def lookup(self, person_name: str, company: str) -> EmailCache | None:
        """Check cache for a known email. Returns None if not found or stale."""
        async with async_session() as db:
            # Normalize for lookup
            name_lower = person_name.lower().strip()
            company_lower = company.lower().strip()

            result = await db.execute(
                select(EmailCache)
                .where(
                    sa_func.lower(EmailCache.person_name) == name_lower,
                    sa_func.lower(EmailCache.company) == company_lower,
                )
                .order_by(EmailCache.confidence.desc())
                .limit(1)
            )
            entry = result.scalar_one_or_none()

            if entry:
                # Check if stale
                if entry.created_at and (datetime.now() - entry.created_at.replace(tzinfo=None)) > timedelta(days=CACHE_TTL_DAYS):
                    logger.info(f"Cache hit for {person_name}@{company} but stale ({CACHE_TTL_DAYS}+ days old)")
                    return None
                logger.info(f"Cache HIT: {person_name}@{company} → {entry.email} (confidence: {entry.confidence})")
                return entry

            return None

    async def lookup_by_email(self, email: str) -> EmailCache | None:
        """Check if we've seen this email before."""
        async with async_session() as db:
            result = await db.execute(
                select(EmailCache).where(EmailCache.email == email.lower().strip()).limit(1)
            )
            return result.scalar_one_or_none()

    async def lookup_by_domain(self, domain: str) -> list[EmailCache]:
        """Get all cached emails for a domain (useful for pattern detection)."""
        async with async_session() as db:
            result = await db.execute(
                select(EmailCache)
                .where(EmailCache.domain == domain.lower().strip())
                .order_by(EmailCache.confidence.desc())
            )
            return list(result.scalars().all())

    async def store(
        self,
        person_name: str,
        company: str,
        email: str,
        source: str,
        confidence: float = 0.0,
        verified: bool = False,
        domain: str = "",
        extra_data: dict | None = None,
    ) -> EmailCache:
        """Store a found email in the cache."""
        async with async_session() as db:
            # Check if we already have this exact email
            existing = await db.execute(
                select(EmailCache).where(EmailCache.email == email.lower().strip()).limit(1)
            )
            entry = existing.scalar_one_or_none()

            if entry:
                # Update if new data is higher confidence
                if confidence > entry.confidence:
                    entry.confidence = confidence
                    entry.source = source
                    entry.verified = verified or entry.verified
                    if extra_data:
                        entry.extra_data = {**(entry.extra_data or {}), **extra_data}
                    if verified:
                        entry.last_verified_at = datetime.now()
                    await db.commit()
                    logger.info(f"Cache UPDATED: {email} (confidence: {confidence})")
                return entry

            # New entry
            entry = EmailCache(
                person_name=person_name.strip(),
                company=company.strip(),
                domain=domain.lower().strip() or email.split("@")[-1],
                email=email.lower().strip(),
                verified=verified,
                source=source,
                confidence=confidence,
                extra_data=extra_data,
                last_verified_at=datetime.now() if verified else None,
            )
            db.add(entry)
            await db.commit()
            await db.refresh(entry)
            logger.info(f"Cache STORED: {person_name}@{company} → {email} (source: {source})")
            return entry

    async def detect_domain_pattern(self, domain: str) -> str | None:
        """Detect the most common email pattern for a domain from cached emails.

        Returns the pattern name (e.g., "first.last") or None.
        """
        entries = await self.lookup_by_domain(domain)
        if not entries:
            return None

        patterns = []
        for entry in entries:
            if entry.person_name and entry.email:
                p = detect_pattern(entry.email, entry.person_name)
                if p:
                    patterns.append(p)

        if not patterns:
            return None

        # Return the most common pattern
        counter = Counter(patterns)
        best, count = counter.most_common(1)[0]
        logger.info(f"Domain {domain} pattern: {best} ({count}/{len(entries)} entries)")
        return best

    async def generate_candidates_from_pattern(
        self, person_name: str, domain: str
    ) -> list[str]:
        """Generate email candidates using the known pattern for a domain.

        If we've seen verified emails at this domain before, use the
        detected pattern to generate the most likely candidate FIRST,
        followed by other common patterns.

        Returns list of candidate emails, best guess first.
        """
        known_pattern = await self.detect_domain_pattern(domain)
        candidates = []

        if known_pattern:
            best = generate_from_pattern(known_pattern, person_name, domain)
            if best:
                candidates.append(best)
                logger.info(f"Pattern-first candidate for {person_name}@{domain}: {best} (pattern: {known_pattern})")

        # Add all other patterns as fallback
        for pattern_name in PATTERNS:
            if pattern_name != known_pattern:
                email = generate_from_pattern(pattern_name, person_name, domain)
                if email and email not in candidates:
                    candidates.append(email)

        return candidates

    async def get_stats(self) -> dict:
        """Get cache statistics."""
        async with async_session() as db:
            total = await db.execute(select(sa_func.count(EmailCache.id)))
            verified_count = await db.execute(
                select(sa_func.count(EmailCache.id)).where(EmailCache.verified == True)
            )
            domains = await db.execute(select(sa_func.count(sa_func.distinct(EmailCache.domain))))
            return {
                "total_emails": total.scalar() or 0,
                "verified_emails": verified_count.scalar() or 0,
                "unique_domains": domains.scalar() or 0,
            }
