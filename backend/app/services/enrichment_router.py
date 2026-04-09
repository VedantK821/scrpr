import logging
from app.sources.base import EnrichmentSource, SourceResult

logger = logging.getLogger(__name__)


class WaterfallEngine:
    """Chains enrichment sources. First hit wins."""

    def __init__(self, sources: list[EnrichmentSource]):
        self.sources = sources
        from app.services.email_cache import EmailCacheService
        self.cache = EmailCacheService()

    async def run(self, row_data: dict[str, str], prompt: str) -> SourceResult:
        # Extract person name and company from row data (handles various column naming conventions)
        person_name = (
            row_data.get("name")
            or row_data.get("Recruiter")
            or row_data.get("Hiring Contact")
            or ""
        )
        company = (
            row_data.get("company")
            or row_data.get("Company")
            or row_data.get("Name")
            or ""
        )

        # Check cache first — instant, free, no API call
        if person_name and company:
            try:
                cached = await self.cache.lookup(person_name, company)
                if cached:
                    logger.info(f"Waterfall: cache hit for {person_name}@{company} → {cached.email}")
                    return SourceResult(
                        found=True,
                        value=cached.email,
                        data={"cached": True, "source": cached.source, "verified": cached.verified},
                        confidence=cached.confidence,
                        source_name="cache",
                    )
            except Exception as e:
                logger.warning(f"Waterfall: cache lookup failed ({e}), continuing with sources")

        # Run waterfall as normal
        for source in self.sources:
            logger.info(f"Waterfall: trying {source.name}")
            try:
                healthy = await source.health_check()
                if not healthy:
                    logger.info(f"Waterfall: {source.name} not available, skipping")
                    continue

                result = await source.enrich(row_data, prompt)
                if result.found and result.value:
                    logger.info(f"Waterfall: {source.name} found result: {result.value[:50]}")

                    # Cache the result for future lookups
                    if person_name and company and "@" in result.value:
                        try:
                            await self.cache.store(
                                person_name=person_name,
                                company=company,
                                email=result.value,
                                source=result.source_name,
                                confidence=result.confidence,
                                verified=result.data.get("verified", False),
                                extra_data={k: v for k, v in result.data.items() if k not in ("cached",)},
                            )
                        except Exception as e:
                            logger.warning(f"Waterfall: failed to cache result from {source.name} ({e})")

                    return result
                logger.info(f"Waterfall: {source.name} returned no result")
            except Exception as e:
                logger.error(f"Waterfall: {source.name} raised {e}")
                continue

        return SourceResult(found=False, source_name="waterfall", error="All sources exhausted")

    @staticmethod
    def from_config(source_names: list[str]) -> "WaterfallEngine":
        """Build waterfall from a list of source names."""
        from app.sources import get_source_by_name
        sources = [get_source_by_name(name) for name in source_names if get_source_by_name(name)]
        return WaterfallEngine(sources)
