import logging
from app.sources.base import EnrichmentSource, SourceResult
from app.scraper.linkedin_scraper import LinkedInScraper

logger = logging.getLogger(__name__)


class LinkedInSource(EnrichmentSource):
    name = "linkedin"
    rate_limit_per_minute = 5  # Be very conservative with LinkedIn

    def __init__(self):
        self.scraper = LinkedInScraper()

    async def enrich(self, row_data: dict[str, str], prompt: str) -> SourceResult:
        company = row_data.get("company") or row_data.get("Company") or row_data.get("Company Name") or ""
        title_hint = row_data.get("title") or row_data.get("Title") or ""
        raw_name = row_data.get("Key Contact") or row_data.get("Contact") or row_data.get("name") or row_data.get("Recruiter") or ""
        if raw_name and (" — " in raw_name or " | " in raw_name or " - " in raw_name):
            from app.services.contact_parser import extract_name
            name = extract_name(raw_name)
        else:
            name = raw_name

        if not company:
            return SourceResult(found=False, source_name=self.name, error="No company provided")

        # Build search query
        search_parts = []
        if name:
            search_parts.append(name)
        if title_hint:
            search_parts.append(title_hint)
        else:
            # Extract role hint from prompt
            search_parts.append("campus recruitment head")
        search_parts.append(company)
        query = " ".join(search_parts)

        # Search LinkedIn
        results = await self.scraper.search_people(query, max_results=3)

        if not results:
            return SourceResult(found=False, source_name=self.name, error="No LinkedIn results found")

        # Return the top result
        top = results[0]
        return SourceResult(
            found=True,
            value=f"{top['name']} - {top['title']}",
            data={
                "name": top["name"],
                "title": top["title"],
                "linkedin_url": top["linkedin_url"],
                "all_results": results,
            },
            confidence=0.75,
            source_name=self.name,
        )

    async def health_check(self) -> bool:
        return self.scraper.is_available()
