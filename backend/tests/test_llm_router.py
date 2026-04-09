import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.llm.router import LLMRouter, TaskComplexity
from app.llm.providers import ProviderConfig


def make_providers():
    return [
        ProviderConfig(name="ollama", model="ollama/llama3:8b", api_base="http://localhost:11434"),
        ProviderConfig(name="gemini", model="gemini/gemini-2.0-flash", api_key="fake-gemini"),
        ProviderConfig(name="anthropic", model="anthropic/claude-haiku-4-5-20251001", api_key="fake-anthropic"),
    ]


class TestLLMRouterChain:
    def test_simple_routes_ollama_first(self):
        router = LLMRouter()
        router.providers = make_providers()
        chain = router._get_chain(TaskComplexity.SIMPLE)
        assert chain[0].name == "ollama"

    def test_complex_routes_api_first(self):
        router = LLMRouter()
        router.providers = make_providers()
        chain = router._get_chain(TaskComplexity.COMPLEX)
        assert chain[0].name != "ollama"
        # ollama should be last
        assert chain[-1].name == "ollama"

    def test_moderate_routes_first_api_then_local(self):
        router = LLMRouter()
        router.providers = make_providers()
        chain = router._get_chain(TaskComplexity.MODERATE)
        # First element should be first api provider
        assert chain[0].name == "gemini"
        # ollama should appear somewhere in the middle
        ollama_idx = next(i for i, p in enumerate(chain) if p.name == "ollama")
        assert 0 < ollama_idx < len(chain)

    def test_simple_with_only_ollama(self):
        router = LLMRouter()
        router.providers = [ProviderConfig(name="ollama", model="ollama/llama3:8b", api_base="http://localhost:11434")]
        chain = router._get_chain(TaskComplexity.SIMPLE)
        assert len(chain) == 1
        assert chain[0].name == "ollama"

    def test_complex_with_only_ollama(self):
        router = LLMRouter()
        router.providers = [ProviderConfig(name="ollama", model="ollama/llama3:8b", api_base="http://localhost:11434")]
        chain = router._get_chain(TaskComplexity.COMPLEX)
        # With only ollama, api is empty, so chain is [] + [ollama] = [ollama]
        assert chain[0].name == "ollama"


class TestLLMRouterComplete:
    @pytest.mark.asyncio
    async def test_complete_success_first_provider(self):
        router = LLMRouter()
        router.providers = make_providers()
        router._call_provider = AsyncMock(return_value="Hello from LLM")
        result = await router.complete("Say hello", complexity=TaskComplexity.SIMPLE)
        assert result == "Hello from LLM"
        # Should only call once (first provider succeeded)
        assert router._call_provider.call_count == 1

    @pytest.mark.asyncio
    async def test_complete_fallback_when_first_fails(self):
        router = LLMRouter()
        router.providers = make_providers()
        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("First provider failed")
            return "Fallback response"

        router._call_provider = AsyncMock(side_effect=side_effect)
        result = await router.complete("Test prompt", complexity=TaskComplexity.SIMPLE)
        assert result == "Fallback response"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_complete_raises_when_all_fail(self):
        router = LLMRouter()
        router.providers = make_providers()
        router._call_provider = AsyncMock(side_effect=RuntimeError("Provider failed"))
        with pytest.raises(RuntimeError, match="All LLM providers failed"):
            await router.complete("Test prompt")

    @pytest.mark.asyncio
    async def test_complete_raises_when_no_providers(self):
        router = LLMRouter()
        router.providers = []
        with pytest.raises(RuntimeError, match="No LLM providers configured"):
            await router.complete("Test prompt")

    @pytest.mark.asyncio
    async def test_complete_passes_correct_args_to_provider(self):
        router = LLMRouter()
        router.providers = [ProviderConfig(name="ollama", model="ollama/llama3:8b", api_base="http://localhost:11434")]
        router._call_provider = AsyncMock(return_value="result")
        await router.complete(
            "my prompt",
            complexity=TaskComplexity.SIMPLE,
            system_prompt="be helpful",
            temperature=0.5,
            max_tokens=100,
        )
        call_kwargs = router._call_provider.call_args
        assert call_kwargs.kwargs["system_prompt"] == "be helpful"
        assert call_kwargs.kwargs["temperature"] == 0.5
        assert call_kwargs.kwargs["max_tokens"] == 100

    @pytest.mark.asyncio
    async def test_simple_tries_ollama_then_api_on_failure(self):
        router = LLMRouter()
        router.providers = make_providers()
        call_order = []

        async def side_effect(provider, *args, **kwargs):
            call_order.append(provider)
            if provider == "ollama":
                raise RuntimeError("Ollama down")
            return "API response"

        router._call_provider = AsyncMock(side_effect=side_effect)
        result = await router.complete("Test", complexity=TaskComplexity.SIMPLE)
        assert result == "API response"
        assert call_order[0] == "ollama"
        assert call_order[1] != "ollama"

    @pytest.mark.asyncio
    async def test_complex_tries_api_first(self):
        router = LLMRouter()
        router.providers = make_providers()
        call_order = []

        async def side_effect(provider, *args, **kwargs):
            call_order.append(provider)
            return "response"

        router._call_provider = AsyncMock(side_effect=side_effect)
        await router.complete("Test", complexity=TaskComplexity.COMPLEX)
        assert call_order[0] != "ollama"
