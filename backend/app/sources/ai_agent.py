from app.agent.loop import AgentLoop
from app.sources.base import EnrichmentSource, SourceResult


class AIAgentSource(EnrichmentSource):
    name = "ai_agent"
    rate_limit_per_minute = 10  # Conservative — each run involves multiple web requests

    async def enrich(self, row_data: dict[str, str], prompt: str) -> SourceResult:
        agent = AgentLoop(max_loops=3, timeout=45.0)
        result = await agent.run(prompt=prompt, context=row_data)
        return SourceResult(
            found=result.success,
            value=str(result.data) if result.data else None,
            data=result.data,
            confidence=result.confidence,
            source_name=self.name,
            error=result.error or "",
        )
