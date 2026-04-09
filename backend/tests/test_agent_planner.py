import pytest
from unittest.mock import AsyncMock
from app.agent.planner import AgentPlanner
from app.llm.router import LLMRouter


class TestAgentPlannerGenerateQueries:
    @pytest.mark.asyncio
    async def test_generate_queries_returns_list(self):
        router = LLMRouter.__new__(LLMRouter)
        router.complete = AsyncMock(return_value='["query one", "query two", "query three"]')
        planner = AgentPlanner(router=router)
        queries = await planner.generate_queries("Find info about Python", {})
        assert isinstance(queries, list)
        assert len(queries) == 3
        assert "query one" in queries

    @pytest.mark.asyncio
    async def test_generate_queries_passes_prompt(self):
        router = LLMRouter.__new__(LLMRouter)
        router.complete = AsyncMock(return_value='["search query"]')
        planner = AgentPlanner(router=router)
        await planner.generate_queries("My research prompt", {"key": "value"})
        call_kwargs = router.complete.call_args.kwargs
        assert "My research prompt" in call_kwargs["prompt"]

    @pytest.mark.asyncio
    async def test_generate_queries_with_context(self):
        router = LLMRouter.__new__(LLMRouter)
        router.complete = AsyncMock(return_value='["q1", "q2"]')
        planner = AgentPlanner(router=router)
        queries = await planner.generate_queries("Find CEO", {"company": "Acme Corp"})
        assert isinstance(queries, list)

    @pytest.mark.asyncio
    async def test_generate_queries_uses_simple_complexity(self):
        from app.llm.router import TaskComplexity
        router = LLMRouter.__new__(LLMRouter)
        router.complete = AsyncMock(return_value='["query"]')
        planner = AgentPlanner(router=router)
        await planner.generate_queries("test", {})
        call_kwargs = router.complete.call_args.kwargs
        assert call_kwargs["complexity"] == TaskComplexity.SIMPLE

    @pytest.mark.asyncio
    async def test_generate_queries_with_json_in_prose(self):
        router = LLMRouter.__new__(LLMRouter)
        router.complete = AsyncMock(return_value='Here are the queries: ["q1", "q2", "q3"]')
        planner = AgentPlanner(router=router)
        queries = await planner.generate_queries("test", {})
        assert "q1" in queries
        assert "q2" in queries

    @pytest.mark.asyncio
    async def test_generate_queries_fallback_to_newlines(self):
        router = LLMRouter.__new__(LLMRouter)
        router.complete = AsyncMock(return_value="query line one\nquery line two\nquery line three")
        planner = AgentPlanner(router=router)
        queries = await planner.generate_queries("test", {})
        assert len(queries) >= 2

    @pytest.mark.asyncio
    async def test_generate_queries_empty_response(self):
        router = LLMRouter.__new__(LLMRouter)
        router.complete = AsyncMock(return_value="")
        planner = AgentPlanner(router=router)
        queries = await planner.generate_queries("test", {})
        assert queries == []


class TestAgentPlannerRefineQueries:
    @pytest.mark.asyncio
    async def test_refine_queries_returns_list(self):
        router = LLMRouter.__new__(LLMRouter)
        router.complete = AsyncMock(return_value='["refined q1", "refined q2"]')
        planner = AgentPlanner(router=router)
        queries = await planner.refine_queries(
            "original prompt",
            {},
            ["previous query 1"],
            ["finding 1"],
        )
        assert isinstance(queries, list)
        assert "refined q1" in queries

    @pytest.mark.asyncio
    async def test_refine_queries_includes_previous_queries_in_prompt(self):
        router = LLMRouter.__new__(LLMRouter)
        router.complete = AsyncMock(return_value='["new q"]')
        planner = AgentPlanner(router=router)
        await planner.refine_queries(
            "prompt",
            {},
            ["old query 1", "old query 2"],
            [],
        )
        call_kwargs = router.complete.call_args.kwargs
        assert "old query 1" in call_kwargs["prompt"]
        assert "old query 2" in call_kwargs["prompt"]

    @pytest.mark.asyncio
    async def test_refine_queries_includes_findings_in_prompt(self):
        router = LLMRouter.__new__(LLMRouter)
        router.complete = AsyncMock(return_value='["new q"]')
        planner = AgentPlanner(router=router)
        await planner.refine_queries(
            "prompt",
            {},
            ["old query"],
            ["important finding here"],
        )
        call_kwargs = router.complete.call_args.kwargs
        assert "important finding here" in call_kwargs["prompt"]

    @pytest.mark.asyncio
    async def test_refine_queries_no_findings(self):
        router = LLMRouter.__new__(LLMRouter)
        router.complete = AsyncMock(return_value='["refined"]')
        planner = AgentPlanner(router=router)
        queries = await planner.refine_queries("prompt", {}, ["q1"], [])
        assert isinstance(queries, list)


class TestParseQueries:
    def test_parse_valid_json_array(self):
        planner = AgentPlanner.__new__(AgentPlanner)
        result = planner._parse_queries('["q1", "q2", "q3"]')
        assert result == ["q1", "q2", "q3"]

    def test_parse_json_array_in_prose(self):
        planner = AgentPlanner.__new__(AgentPlanner)
        result = planner._parse_queries('Here are queries: ["q1", "q2"]')
        assert "q1" in result
        assert "q2" in result

    def test_parse_newline_fallback(self):
        planner = AgentPlanner.__new__(AgentPlanner)
        result = planner._parse_queries("line one query\nline two query")
        assert len(result) == 2

    def test_parse_empty_string(self):
        planner = AgentPlanner.__new__(AgentPlanner)
        result = planner._parse_queries("")
        assert result == []

    def test_parse_strips_list_markers(self):
        planner = AgentPlanner.__new__(AgentPlanner)
        result = planner._parse_queries("- query one\n- query two")
        assert any("query one" in q for q in result)
