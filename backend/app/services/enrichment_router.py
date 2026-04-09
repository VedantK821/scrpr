import logging
from app.sources.base import EnrichmentSource, SourceResult

logger = logging.getLogger(__name__)


class WaterfallEngine:
    """Chains enrichment sources. First hit wins."""

    def __init__(self, sources: list[EnrichmentSource]):
        self.sources = sources

    async def run(self, row_data: dict[str, str], prompt: str) -> SourceResult:
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
