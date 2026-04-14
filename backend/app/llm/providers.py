from dataclasses import dataclass
from app.config import settings


@dataclass
class ProviderConfig:
    name: str
    model: str
    api_base: str | None = None
    api_key: str | None = None


def get_providers() -> list[ProviderConfig]:
    """Return LLM providers in priority order: cloud APIs first, Ollama as fallback."""
    providers = []
    # Cloud APIs first — higher accuracy
    if settings.gemini_api_key:
        providers.append(ProviderConfig(name="gemini", model="gemini/gemini-2.5-flash", api_key=settings.gemini_api_key))
    if settings.anthropic_api_key:
        providers.append(ProviderConfig(name="anthropic", model="anthropic/claude-haiku-4-5-20251001", api_key=settings.anthropic_api_key))
    if settings.openai_api_key:
        providers.append(ProviderConfig(name="openai", model="openai/gpt-4o-mini", api_key=settings.openai_api_key))
    # Ollama as fallback — free but lower quality
    providers.append(ProviderConfig(name="ollama", model="ollama/qwen3:8b", api_base=settings.ollama_base_url))
    return providers
