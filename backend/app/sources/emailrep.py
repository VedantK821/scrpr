import logging
import httpx
from app.sources.base import EnrichmentSource, SourceResult

logger = logging.getLogger(__name__)

EMAILREP_URL = "https://emailrep.io"


class EmailRepSource(EnrichmentSource):
    """Checks email reputation via emailrep.io (free, 100 queries/day, no API key)."""
    name = "emailrep"
    rate_limit_per_minute = 5  # Be polite — free tier

    async def enrich(self, row_data: dict[str, str], prompt: str) -> SourceResult:
        """Not used as a primary source — use verify() instead."""
        return SourceResult(found=False, source_name=self.name, error="Use as verification, not primary source")

    async def verify(self, email: str) -> dict:
        """Check if an email has been seen online (breach databases, social media, etc.).

        Returns:
            {"exists": bool, "reputation": str, "references": int, "details": dict}
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{EMAILREP_URL}/{email}",
                    headers={"User-Agent": "scrpr/1.0"},
                )
                if resp.status_code == 429:
                    logger.warning("EmailRep rate limited (100/day free tier)")
                    return {"exists": None, "error": "rate_limited"}
                if resp.status_code != 200:
                    return {"exists": None, "error": f"HTTP {resp.status_code}"}

                data = resp.json()
                references = data.get("references", 0)
                reputation = data.get("reputation", "none")
                suspicious = data.get("suspicious", False)

                return {
                    "exists": references > 0,
                    "reputation": reputation,
                    "references": references,
                    "suspicious": suspicious,
                    "details": data.get("details", {}),
                }
        except Exception as e:
            logger.debug(f"EmailRep check failed for {email}: {e}")
            return {"exists": None, "error": str(e)}
