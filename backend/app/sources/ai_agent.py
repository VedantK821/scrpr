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


TITLE_WORDS = {
    "director", "manager", "head", "vp", "chief", "officer", "lead",
    "senior", "coordinator", "specialist", "recruiter", "president",
    "associate", "analyst", "executive", "supervisor", "administrator",
    "partner", "consultant", "advisor", "strategist",
}


def validate_contact_name(data: dict) -> dict:
    """Check if full_name is actually a job title. Add name_confidence score."""
    name = data.get("full_name", "")
    if not name:
        data["name_confidence"] = 0.0
        return data

    # Commas in a name are a strong signal it's a title ("Director, Talent Acquisition")
    has_comma = "," in name
    words = set(name.lower().replace(",", " ").replace("-", " ").split())
    title_overlap = words & TITLE_WORDS

    # Comma + any title word = almost certainly a title, not a name
    if has_comma and title_overlap:
        data["name_confidence"] = 0.1
        data["_warning"] = f"full_name looks like a title: '{name}'"
    # If more than half the words are title words, it's a title
    elif len(title_overlap) > len(words) / 2:
        data["name_confidence"] = 0.1
        data["_warning"] = f"full_name looks like a title: '{name}'"
    # Some title words present but could be ambiguous
    elif title_overlap and len(words) > 2:
        data["name_confidence"] = 0.4
    else:
        data["name_confidence"] = 0.9
    return data


class AIAgentSource(EnrichmentSource):
    name = "ai_agent"
    rate_limit_per_minute = 10

    async def enrich(self, row_data: dict[str, str], prompt: str) -> SourceResult:
        agent = AgentLoop(max_loops=2, timeout=120.0)
        result = await agent.run(prompt=prompt, context=row_data)
        data = validate_contact_name(result.data) if result.data else {}
        return SourceResult(
            found=result.success,
            value=format_agent_data(data) if data else None,
            data=data,
            confidence=result.confidence,
            source_name=self.name,
            error=result.error or "",
        )
