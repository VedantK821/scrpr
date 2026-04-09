import logging
from datetime import datetime, timedelta
from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import async_session
from app.models.email_cache import EmailCache

logger = logging.getLogger(__name__)

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
