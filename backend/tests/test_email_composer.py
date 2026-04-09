import pytest
from unittest.mock import AsyncMock, patch
from app.services.email_composer import EmailComposer
from app.models.email_draft import PersonalizationLevel


class TestSubstituteVariables:
    def test_replaces_matching_variable(self):
        composer = EmailComposer()
        result = composer.substitute_variables("Hello /Name/!", {"Name": "Alice"})
        assert result == "Hello Alice!"

    def test_replaces_multiple_variables(self):
        composer = EmailComposer()
        result = composer.substitute_variables(
            "Hi /Name/, you work at /Company/.",
            {"Name": "Bob", "Company": "Acme"}
        )
        assert result == "Hi Bob, you work at Acme."

    def test_case_insensitive_fallback(self):
        composer = EmailComposer()
        # Variable is /Name/ but data key is "name" (lowercase)
        result = composer.substitute_variables("Hello /Name/!", {"name": "Carol"})
        assert result == "Hello Carol!"

    def test_unknown_variable_left_unchanged(self):
        composer = EmailComposer()
        result = composer.substitute_variables("Hello /Unknown/!", {"Name": "Dave"})
        assert result == "Hello /Unknown/!"

    def test_empty_template_returns_empty(self):
        composer = EmailComposer()
        result = composer.substitute_variables("", {"Name": "Eve"})
        assert result == ""

    def test_no_variables_in_template(self):
        composer = EmailComposer()
        result = composer.substitute_variables("Hello world!", {"Name": "Frank"})
        assert result == "Hello world!"


class TestPersonalizeLight:
    @pytest.mark.asyncio
    async def test_light_substitutes_variables_no_llm(self):
        composer = EmailComposer()
        result = await composer.personalize(
            subject_template="Hi /Name/",
            body_template="Dear /Name/, we'd love to work with /Company/.",
            row_data={"Name": "Grace", "Company": "Beta Corp"},
            level=PersonalizationLevel.LIGHT,
        )
        assert result["subject"] == "Hi Grace"
        assert result["body"] == "Dear Grace, we'd love to work with Beta Corp."
        assert result["confidence"] == 1.0

    @pytest.mark.asyncio
    async def test_light_does_not_call_llm(self):
        composer = EmailComposer()
        with patch.object(composer.llm, "complete", new_callable=AsyncMock) as mock_complete:
            await composer.personalize(
                subject_template="Hello /Name/",
                body_template="Body /Name/",
                row_data={"Name": "Hank"},
                level=PersonalizationLevel.LIGHT,
            )
            mock_complete.assert_not_called()


class TestPersonalizeMax:
    @pytest.mark.asyncio
    async def test_max_calls_llm_and_returns_response(self):
        composer = EmailComposer()
        with patch.object(composer.llm, "complete", new_callable=AsyncMock) as mock_complete:
            mock_complete.return_value = "  AI personalized body  "
            result = await composer.personalize(
                subject_template="Hi /Name/",
                body_template="Dear /Name/, reach out about /Company/.",
                row_data={"Name": "Iris", "Company": "Gamma Inc"},
                level=PersonalizationLevel.MAX,
            )
        assert result["subject"] == "Hi Iris"
        assert result["body"] == "AI personalized body"
        assert result["confidence"] == 0.85
        mock_complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_max_falls_back_on_llm_error(self):
        composer = EmailComposer()
        with patch.object(composer.llm, "complete", new_callable=AsyncMock) as mock_complete:
            mock_complete.side_effect = RuntimeError("LLM unavailable")
            result = await composer.personalize(
                subject_template="Hi /Name/",
                body_template="Dear /Name/.",
                row_data={"Name": "Jack"},
                level=PersonalizationLevel.MAX,
            )
        # Falls back to variable-substituted template
        assert result["subject"] == "Hi Jack"
        assert result["body"] == "Dear Jack."
        assert result["confidence"] == 0.5

    @pytest.mark.asyncio
    async def test_medium_calls_llm_with_moderate_complexity(self):
        from app.llm.router import TaskComplexity
        composer = EmailComposer()
        with patch.object(composer.llm, "complete", new_callable=AsyncMock) as mock_complete:
            mock_complete.return_value = "Medium personalized body"
            result = await composer.personalize(
                subject_template="Hi /Name/",
                body_template="Dear /Name/.",
                row_data={"Name": "Kim"},
                level=PersonalizationLevel.MEDIUM,
            )
        call_kwargs = mock_complete.call_args.kwargs
        assert call_kwargs["complexity"] == TaskComplexity.MODERATE
        assert result["confidence"] == 0.85
