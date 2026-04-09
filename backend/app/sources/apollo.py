import httpx
from app.config import settings
from app.sources.base import EnrichmentSource, SourceResult


class ApolloSource(EnrichmentSource):
    name = "apollo"
    rate_limit_per_minute = 10

    async def enrich(self, row_data: dict[str, str], prompt: str) -> SourceResult:
        api_key = getattr(settings, 'apollo_api_key', '')
        if not api_key:
            return SourceResult(found=False, source_name=self.name, error="Apollo API key not configured")

        company = row_data.get("company") or row_data.get("Company") or ""
        title = row_data.get("title") or row_data.get("Title") or ""
        domain = row_data.get("domain") or row_data.get("website") or ""

        if not company and not domain:
            return SourceResult(found=False, source_name=self.name, error="No company or domain provided")

        payload = {
            "api_key": api_key,
            "q_organization_name": company,
            "page": 1,
            "per_page": 3,
        }
        if title:
            payload["person_titles"] = [title]
        if domain:
            payload["q_organization_domains"] = domain

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post("https://api.apollo.io/api/v1/mixed_people/search", json=payload)
            if resp.status_code == 200:
                people = resp.json().get("people", [])
                if people:
                    person = people[0]
                    email = person.get("email")
                    return SourceResult(
                        found=bool(email),
                        value=email,
                        data={
                            "name": person.get("name", ""),
                            "title": person.get("title", ""),
                            "email": email,
                            "linkedin_url": person.get("linkedin_url", ""),
                            "organization": person.get("organization", {}).get("name", ""),
                        },
                        confidence=0.8 if email else 0.3,
                        source_name=self.name,
                    )
            return SourceResult(found=False, source_name=self.name, error="Apollo returned no results")
        except Exception as e:
            return SourceResult(found=False, source_name=self.name, error=str(e))

    async def health_check(self) -> bool:
        return bool(getattr(settings, 'apollo_api_key', ''))
