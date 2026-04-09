from dataclasses import dataclass
from app.config import settings


@dataclass
class ProviderConfig:
    name: str
    model: str
    api_base: str | None = None
    api_key: str | None = None


def get_providers() -> list[ProviderConfig]:
    providers = []
    providers.append(ProviderConfig(name="ollama", model="ollama/llama3:8b", api_base=settings.ollama_base_url))
    if settings.gemini_api_key:
        providers.append(ProviderConfig(name="gemini", model="gemini/gemini-2.0-flash", api_key=settings.gemini_api_key))
    if settings.anthropic_api_key:
        providers.append(ProviderConfig(name="anthropic", model="anthropic/claude-haiku-4-5-20251001", api_key=settings.anthropic_api_key))
    if settings.openai_api_key:
        providers.append(ProviderConfig(name="openai", model="openai/gpt-4o-mini", api_key=settings.openai_api_key))
    return providers
