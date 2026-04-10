from app.agent.loop import AgentLoop
from app.sources.base import EnrichmentSource, SourceResult


def format_agent_data(data: dict) -> str:
    """Format extracted agent data as a human-readable string."""
    if not data:
        return ""
    # Contact data: "Name — Title — LinkedIn"
    if "full_name" in data:
        parts = [data["full_name"]]
        if data.get("title"):
            parts.append(data["title"])
        if data.get("linkedin_url"):
            parts.append(data["linkedin_url"])
        return " — ".join(parts)
    # Known single-value fields
    for key in ("summary", "description", "answer", "result", "value"):
        if data.get(key):
            return str(data[key])
    # Fallback: join all non-empty values
    values = [str(v) for v in data.values() if v]
    return " | ".join(values) if values else ""


class AIAgentSource(EnrichmentSource):
    name = "ai_agent"
    rate_limit_per_minute = 10

    async def enrich(self, row_data: dict[str, str], prompt: str) -> SourceResult:
        agent = AgentLoop(max_loops=2, timeout=120.0)
        result = await agent.run(prompt=prompt, context=row_data)
        return SourceResult(
            found=result.success,
            value=format_agent_data(result.data) if result.data else None,
            data=result.data,
            confidence=result.confidence,
            source_name=self.name,
            error=result.error or "",
        )
