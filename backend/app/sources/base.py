from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SourceResult:
    """Result from an enrichment source."""
    found: bool
    value: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    source_name: str = ""
    error: str = ""


class EnrichmentSource(ABC):
    """Base class for all enrichment sources."""
    name: str = "base"
    rate_limit_per_minute: int = 60

    @abstractmethod
    async def enrich(self, row_data: dict[str, str], prompt: str) -> SourceResult:
        """Try to find the requested data. Return SourceResult."""
        ...

    async def health_check(self) -> bool:
        """Is this source currently available?"""
        return True
