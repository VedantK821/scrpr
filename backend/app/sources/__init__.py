from app.sources.base import EnrichmentSource, SourceResult
from app.sources.ai_agent import AIAgentSource
from app.sources.hunter import HunterSource
from app.sources.apollo import ApolloSource
from app.sources.email_pattern import EmailPatternSource
from app.sources.linkedin import LinkedInSource
from app.sources.website_email import WebsiteEmailSource

_SOURCES: dict[str, type[EnrichmentSource]] = {
    "ai_agent": AIAgentSource,
    "hunter": HunterSource,
    "apollo": ApolloSource,
    "email_pattern": EmailPatternSource,
    "linkedin": LinkedInSource,
    "website_email": WebsiteEmailSource,
}


def get_source_by_name(name: str) -> EnrichmentSource | None:
    cls = _SOURCES.get(name)
    return cls() if cls else None


def get_all_sources() -> list[EnrichmentSource]:
    return [cls() for cls in _SOURCES.values()]


__all__ = [
    "EnrichmentSource",
    "SourceResult",
    "AIAgentSource",
    "HunterSource",
    "ApolloSource",
    "EmailPatternSource",
    "LinkedInSource",
    "WebsiteEmailSource",
    "get_source_by_name",
    "get_all_sources",
]
