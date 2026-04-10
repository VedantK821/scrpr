import logging
from enum import StrEnum
from litellm import acompletion
from app.llm.providers import get_providers, ProviderConfig

logger = logging.getLogger(__name__)


class TaskComplexity(StrEnum):
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"


class LLMRouter:
    def __init__(self):
        self.providers = get_providers()

    def _get_chain(self, complexity: TaskComplexity) -> list[ProviderConfig]:
        local = [p for p in self.providers if p.name == "ollama"]
        api = [p for p in self.providers if p.name not in ("ollama",)]
        if complexity == TaskComplexity.SIMPLE:
            return local + api
        elif complexity == TaskComplexity.MODERATE:
            return api[:1] + local + api[1:]
        else:
            return api + local

    async def complete(
        self,
        prompt: str,
        complexity: TaskComplexity = TaskComplexity.MODERATE,
        system_prompt: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 2000,
        response_format: dict | None = None,
    ) -> str:
        chain = self._get_chain(complexity)
        if not chain:
            raise RuntimeError("No LLM providers configured")
        last_error = None
        for provider in chain:
            try:
                result = await self._call_provider(
                    provider.name,
                    prompt,
                    model=provider.model,
                    api_base=provider.api_base,
                    api_key=provider.api_key,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format=response_format,
                    complexity=complexity,
                )
                return result
            except Exception as e:
                logger.warning(f"Provider {provider.name} failed: {e}")
                last_error = e
        raise RuntimeError(f"All LLM providers failed. Last error: {last_error}")

    async def _call_provider(
        self,
        provider: str,
        prompt: str,
        model: str = "",
        api_base: str | None = None,
        api_key: str | None = None,
        system_prompt: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 2000,
        response_format: dict | None = None,
        complexity: TaskComplexity = TaskComplexity.MODERATE,
    ) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if api_base:
            kwargs["api_base"] = api_base
        if api_key:
            kwargs["api_key"] = api_key
        if response_format:
            kwargs["response_format"] = response_format
        # For Ollama qwen3: MUST pass think=false as top-level extra_body param
        # Without this, qwen3 puts ALL output into "thinking" field and returns empty content
        # LiteLLM cannot read the thinking field, so content is always empty with think enabled
        if provider in ("ollama", "ollama_heavy") and "qwen" in model.lower():
            kwargs["extra_body"] = {"think": False}

        response = await acompletion(**kwargs)
        content = response.choices[0].message.content

        # Fallback: if content is empty, check for thinking/reasoning content
        if not content:
            msg = response.choices[0].message
            # LiteLLM may store thinking in different fields
            thinking = getattr(msg, 'reasoning_content', None) or getattr(msg, 'thinking', None)
            if thinking:
                content = thinking

        return content or ""
