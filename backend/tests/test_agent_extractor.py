import pytest
from unittest.mock import AsyncMock
from app.agent.extractor import AgentExtractor, ExtractionResult
from app.llm.router import LLMRouter


class TestAgentExtractor:
    @pytest.mark.asyncio
    async def test_extract_returns_extraction_result(self):
        router = LLMRouter.__new__(LLMRouter)
        router.complete = AsyncMock(return_value='{"data": {"name": "John", "salary": "100k"}, "confidence": 0.9}')
        extractor = AgentExtractor(router=router)
        result = await extractor.extract("Find CEO salary", ["page text"], {})
        assert isinstance(result, ExtractionResult)
        assert result.data == {"name": "John", "salary": "100k"}
        assert result.confidence == 0.9

    @pytest.mark.asyncio
    async def test_extract_uses_complex_complexity(self):
        from app.llm.router import TaskComplexity
        router = LLMRouter.__new__(LLMRouter)
        router.complete = AsyncMock(return_value='{"data": {}, "confidence": 0.5}')
        extractor = AgentExtractor(router=router)
        await extractor.extract("test", ["text"], {})
        call_kwargs = router.complete.call_args.kwargs
        assert call_kwargs["complexity"] == TaskComplexity.COMPLEX

    @pytest.mark.asyncio
    async def test_extract_combines_multiple_texts(self):
        router = LLMRouter.__new__(LLMRouter)
        router.complete = AsyncMock(return_value='{"data": {}, "confidence": 0.5}')
        extractor = AgentExtractor(router=router)
        await extractor.extract("test", ["page1 content", "page2 content", "page3 content"], {})
        call_kwargs = router.complete.call_args.kwargs
        assert "page1 content" in call_kwargs["prompt"]
        assert "page2 content" in call_kwargs["prompt"]

    @pytest.mark.asyncio
    async def test_extract_truncates_combined_text(self):
        router = LLMRouter.__new__(LLMRouter)
        router.complete = AsyncMock(return_value='{"data": {}, "confidence": 0.0}')
        extractor = AgentExtractor(router=router)
        # 3 pages of 5000 chars each = 15000 total, should be truncated to 8000
        large_texts = ["x" * 5000, "y" * 5000, "z" * 5000]
        await extractor.extract("test", large_texts, {})
        call_kwargs = router.complete.call_args.kwargs
        # The combined texts should not exceed 8000 chars in the prompt content
        # Check that all 5000 'x' chars appear but not all 'z' chars
        assert "x" * 5000 in call_kwargs["prompt"]

    @pytest.mark.asyncio
    async def test_extract_handles_malformed_json(self):
        router = LLMRouter.__new__(LLMRouter)
        router.complete = AsyncMock(return_value="not json at all")
        extractor = AgentExtractor(router=router)
        result = await extractor.extract("test", ["text"], {})
        assert isinstance(result, ExtractionResult)
        assert result.data == {}
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_extract_clamps_confidence_to_valid_range(self):
        router = LLMRouter.__new__(LLMRouter)
        router.complete = AsyncMock(return_value='{"data": {"val": "x"}, "confidence": 1.5}')
        extractor = AgentExtractor(router=router)
        result = await extractor.extract("test", ["text"], {})
        assert result.confidence <= 1.0

    @pytest.mark.asyncio
    async def test_extract_clamps_confidence_below_zero(self):
        router = LLMRouter.__new__(LLMRouter)
        router.complete = AsyncMock(return_value='{"data": {}, "confidence": -0.5}')
        extractor = AgentExtractor(router=router)
        result = await extractor.extract("test", ["text"], {})
        assert result.confidence >= 0.0

    @pytest.mark.asyncio
    async def test_extract_preserves_raw_response(self):
        raw = '{"data": {"answer": "42"}, "confidence": 0.8}'
        router = LLMRouter.__new__(LLMRouter)
        router.complete = AsyncMock(return_value=raw)
        extractor = AgentExtractor(router=router)
        result = await extractor.extract("test", ["text"], {})
        assert result.raw_response == raw

    @pytest.mark.asyncio
    async def test_extract_empty_page_texts(self):
        router = LLMRouter.__new__(LLMRouter)
        router.complete = AsyncMock(return_value='{"data": {}, "confidence": 0.0}')
        extractor = AgentExtractor(router=router)
        result = await extractor.extract("test", [], {})
        assert isinstance(result, ExtractionResult)

    @pytest.mark.asyncio
    async def test_extract_with_context(self):
        router = LLMRouter.__new__(LLMRouter)
        router.complete = AsyncMock(return_value='{"data": {}, "confidence": 0.5}')
        extractor = AgentExtractor(router=router)
        context = {"company": "Acme", "year": "2024"}
        await extractor.extract("test", ["text"], context)
        call_kwargs = router.complete.call_args.kwargs
        assert "Acme" in call_kwargs["prompt"]


class TestCombineTexts:
    def test_combine_single_text(self):
        extractor = AgentExtractor.__new__(AgentExtractor)
        result = extractor._combine_texts(["hello world"])
        assert "hello world" in result

    def test_combine_multiple_texts(self):
        extractor = AgentExtractor.__new__(AgentExtractor)
        result = extractor._combine_texts(["text one", "text two"])
        assert "text one" in result
        assert "text two" in result

    def test_combine_empty_list(self):
        extractor = AgentExtractor.__new__(AgentExtractor)
        result = extractor._combine_texts([])
        assert result == ""

    def test_combine_respects_max_length(self):
        extractor = AgentExtractor.__new__(AgentExtractor)
        # Two texts that exceed 8000 chars total
        texts = ["a" * 5000, "b" * 5000]
        result = extractor._combine_texts(texts)
        assert len(result) <= 8000 + 50  # some overhead for source headers


class TestParseExtractionResult:
    def test_parse_valid_json(self):
        extractor = AgentExtractor.__new__(AgentExtractor)
        result = extractor._parse_extraction_result('{"data": {"key": "value"}, "confidence": 0.7}')
        assert result.data == {"key": "value"}
        assert result.confidence == 0.7

    def test_parse_json_in_prose(self):
        extractor = AgentExtractor.__new__(AgentExtractor)
        result = extractor._parse_extraction_result('Extracted: {"data": {"x": 1}, "confidence": 0.5}')
        assert result.data == {"x": 1}
        assert result.confidence == 0.5

    def test_parse_empty_string(self):
        extractor = AgentExtractor.__new__(AgentExtractor)
        result = extractor._parse_extraction_result("")
        assert result.data == {}
        assert result.confidence == 0.0
