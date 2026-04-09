import httpx
from app.config import settings
from app.sources.base import EnrichmentSource, SourceResult


class HunterSource(EnrichmentSource):
    name = "hunter"
    rate_limit_per_minute = 15

    async def enrich(self, row_data: dict[str, str], prompt: str) -> SourceResult:
        # Extract domain from row_data
        domain = row_data.get("domain") or row_data.get("website") or ""
        company = row_data.get("company") or row_data.get("Company") or ""
        full_name = row_data.get("name") or row_data.get("full_name") or ""

        if not domain and not company:
            return SourceResult(found=False, source_name=self.name, error="No domain or company provided")

        api_key = getattr(settings, 'hunter_api_key', '')
        if not api_key:
            return SourceResult(found=False, source_name=self.name, error="Hunter API key not configured")

        params = {"api_key": api_key}
        if domain:
            params["domain"] = domain
        if company:
            params["company"] = company
        if full_name:
            # Split name into first/last
            parts = full_name.split(maxsplit=1)
            if len(parts) >= 1:
                params["first_name"] = parts[0]
            if len(parts) >= 2:
                params["last_name"] = parts[1]

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get("https://api.hunter.io/v2/email-finder", params=params)
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                email = data.get("email")
                if email:
                    return SourceResult(
                        found=True, value=email, data=data,
                        confidence=data.get("score", 0) / 100.0,
                        source_name=self.name,
                    )
            return SourceResult(found=False, source_name=self.name, error="Hunter returned no email")
        except Exception as e:
            return SourceResult(found=False, source_name=self.name, error=str(e))

    async def health_check(self) -> bool:
        return bool(getattr(settings, 'hunter_api_key', ''))
