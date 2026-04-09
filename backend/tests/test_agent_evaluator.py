import pytest
from unittest.mock import AsyncMock
from app.agent.evaluator import AgentEvaluator, EvalResult
from app.llm.router import LLMRouter


class TestAgentEvaluator:
    @pytest.mark.asyncio
    async def test_evaluate_relevant_page(self):
        router = LLMRouter.__new__(LLMRouter)
        router.complete = AsyncMock(return_value='{"relevant": true, "summary": "Page contains info about CEO salary"}')
        evaluator = AgentEvaluator(router=router)
        result = await evaluator.evaluate("CEO salary", "text content", "http://example.com")
        assert isinstance(result, EvalResult)
        assert result.relevant is True
        assert "CEO" in result.summary

    @pytest.mark.asyncio
    async def test_evaluate_irrelevant_page(self):
        router = LLMRouter.__new__(LLMRouter)
        router.complete = AsyncMock(return_value='{"relevant": false, "summary": "Page is about cooking recipes"}')
        evaluator = AgentEvaluator(router=router)
        result = await evaluator.evaluate("CEO salary", "recipe content", "http://food.com")
        assert result.relevant is False
        assert result.summary

    @pytest.mark.asyncio
    async def test_evaluate_truncates_long_text(self):
        router = LLMRouter.__new__(LLMRouter)
        router.complete = AsyncMock(return_value='{"relevant": false, "summary": "short"}')
        evaluator = AgentEvaluator(router=router)
        long_text = "a" * 10000
        await evaluator.evaluate("test", long_text, "http://example.com")
        call_kwargs = router.complete.call_args.kwargs
        # Verify that the prompt doesn't contain more than 4000 chars of the page text
        assert long_text not in call_kwargs["prompt"]
        assert "a" * 4000 in call_kwargs["prompt"]  # truncated version is there
        assert "a" * 4001 not in call_kwargs["prompt"]

    @pytest.mark.asyncio
    async def test_evaluate_uses_simple_complexity(self):
        from app.llm.router import TaskComplexity
        router = LLMRouter.__new__(LLMRouter)
        router.complete = AsyncMock(return_value='{"relevant": true, "summary": "ok"}')
        evaluator = AgentEvaluator(router=router)
        await evaluator.evaluate("test", "content", "http://example.com")
        call_kwargs = router.complete.call_args.kwargs
        assert call_kwargs["complexity"] == TaskComplexity.SIMPLE

    @pytest.mark.asyncio
    async def test_evaluate_includes_url_in_prompt(self):
        router = LLMRouter.__new__(LLMRouter)
        router.complete = AsyncMock(return_value='{"relevant": true, "summary": "ok"}')
        evaluator = AgentEvaluator(router=router)
        await evaluator.evaluate("test", "content", "http://specific-url.com/page")
        call_kwargs = router.complete.call_args.kwargs
        assert "http://specific-url.com/page" in call_kwargs["prompt"]

    @pytest.mark.asyncio
    async def test_evaluate_handles_json_in_prose(self):
        router = LLMRouter.__new__(LLMRouter)
        router.complete = AsyncMock(return_value='Analysis result: {"relevant": true, "summary": "Found it"}')
        evaluator = AgentEvaluator(router=router)
        result = await evaluator.evaluate("test", "content", "http://example.com")
        assert result.relevant is True

    @pytest.mark.asyncio
    async def test_evaluate_handles_empty_response(self):
        router = LLMRouter.__new__(LLMRouter)
        router.complete = AsyncMock(return_value="")
        evaluator = AgentEvaluator(router=router)
        result = await evaluator.evaluate("test", "content", "http://example.com")
        assert isinstance(result, EvalResult)
        assert result.relevant is False

    @pytest.mark.asyncio
    async def test_evaluate_handles_malformed_json(self):
        router = LLMRouter.__new__(LLMRouter)
        router.complete = AsyncMock(return_value="{not valid json}")
        evaluator = AgentEvaluator(router=router)
        result = await evaluator.evaluate("test", "content", "http://example.com")
        assert isinstance(result, EvalResult)


class TestEvalResultParseMethod:
    def test_parse_valid_json(self):
        evaluator = AgentEvaluator.__new__(AgentEvaluator)
        result = evaluator._parse_eval_result('{"relevant": true, "summary": "test"}')
        assert result.relevant is True
        assert result.summary == "test"

    def test_parse_false_relevant(self):
        evaluator = AgentEvaluator.__new__(AgentEvaluator)
        result = evaluator._parse_eval_result('{"relevant": false, "summary": "not relevant"}')
        assert result.relevant is False

    def test_parse_empty_response(self):
        evaluator = AgentEvaluator.__new__(AgentEvaluator)
        result = evaluator._parse_eval_result("")
        assert result.relevant is False

    def test_parse_json_embedded_in_text(self):
        evaluator = AgentEvaluator.__new__(AgentEvaluator)
        result = evaluator._parse_eval_result('Here is my result: {"relevant": true, "summary": "yes"}')
        assert result.relevant is True
        assert result.summary == "yes"
