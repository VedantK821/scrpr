import json
import logging
from dataclasses import dataclass
from app.llm.router import LLMRouter, TaskComplexity

logger = logging.getLogger(__name__)

MAX_PAGE_TEXT_LENGTH = 4000


@dataclass
class EvalResult:
    relevant: bool
    summary: str


class AgentEvaluator:
    def __init__(self, router: LLMRouter | None = None):
        self.router = router or LLMRouter()

    async def evaluate(self, prompt: str, page_text: str, page_url: str) -> EvalResult:
        truncated_text = page_text[:MAX_PAGE_TEXT_LENGTH] if page_text else ""
        system_prompt = (
            "You are a relevance evaluator. Given a research prompt and a web page's text content, "
            "determine if the page contains relevant information to answer the prompt. "
            'Respond ONLY with a JSON object: {"relevant": true/false, "summary": "brief summary or reason"}'
        )
        user_prompt = (
            f"Research prompt: {prompt}\n\n"
            f"Page URL: {page_url}\n\n"
            f"Page content:\n{truncated_text}\n\n"
            "Does this page contain relevant information? "
            'Respond ONLY with JSON: {"relevant": true/false, "summary": "..."}'
        )
        response = await self.router.complete(
            prompt=user_prompt,
            complexity=TaskComplexity.SIMPLE,
            system_prompt=system_prompt,
            temperature=0.1,
            max_tokens=300,
        )
        return self._parse_eval_result(response)

    def _parse_eval_result(self, response: str) -> EvalResult:
        if not response:
            return EvalResult(relevant=False, summary="No response from LLM")
        text = response.strip()
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(text[start : end + 1])
                relevant = bool(data.get("relevant", False))
                summary = str(data.get("summary", ""))
                return EvalResult(relevant=relevant, summary=summary)
            except (json.JSONDecodeError, KeyError):
                pass
        # Fallback: check if response indicates relevance
        lower = text.lower()
        relevant = "true" in lower or "relevant" in lower
        return EvalResult(relevant=relevant, summary=text[:200])
