import json
import logging
import re
from dataclasses import dataclass
from app.llm.router import LLMRouter, TaskComplexity

logger = logging.getLogger(__name__)

MAX_PAGE_TEXT_LENGTH = 5000


EVAL_SYSTEM_PROMPT = """/no_think You are an expert relevance evaluator for a web research agent.

Given a research task and scraped web page content, determine if this page contains information that helps answer the research task.

Evaluation criteria — mark as RELEVANT if ANY of these are true:
1. Page contains a direct answer (name, email, title, etc.)
2. Page contains a PARTIAL answer that narrows the search (e.g., department info, team structure)
3. Page contains leads to the answer (e.g., links to team pages, references to specific people)
4. Page is a LinkedIn profile of someone at the target company with a relevant role

Mark as NOT RELEVANT only if:
- Page is completely unrelated to the research task
- Page is a login wall, error page, or cookie notice
- Page is about the company but contains zero information about the specific thing being researched

Be GENEROUS with relevance. Partial information is still valuable — the extractor can work with fragments.

Return ONLY this JSON:
{"relevant": true/false, "summary": "What specific information was found (or why it's not relevant). Be specific — mention names, titles, data points found."}"""


@dataclass
class EvalResult:
    relevant: bool
    summary: str


class AgentEvaluator:
    def __init__(self, router: LLMRouter | None = None):
        self.router = router or LLMRouter()

    async def evaluate(self, prompt: str, page_text: str, page_url: str) -> EvalResult:
        truncated_text = page_text[:MAX_PAGE_TEXT_LENGTH] if page_text else ""

        # Quick heuristic pre-filter — skip obviously useless pages
        if len(truncated_text) < 50:
            return EvalResult(relevant=False, summary="Page too short to contain useful info")

        lower = truncated_text.lower()
        if any(phrase in lower for phrase in ["please enable javascript", "access denied", "403 forbidden", "page not found", "404"]):
            return EvalResult(relevant=False, summary="Error/blocked page")

        user_prompt = (
            f"RESEARCH TASK: {prompt}\n\n"
            f"PAGE URL: {page_url}\n\n"
            f"PAGE CONTENT (first {len(truncated_text)} chars):\n{truncated_text}\n\n"
            f"Does this page contain information relevant to the research task? Be generous — partial info counts."
        )
        response = await self.router.complete(
            prompt=user_prompt,
            complexity=TaskComplexity.SIMPLE,
            system_prompt=EVAL_SYSTEM_PROMPT,
            temperature=0.1,
            max_tokens=300,
        )
        return self._parse_eval_result(response)

    def _parse_eval_result(self, response: str) -> EvalResult:
        if not response:
            return EvalResult(relevant=False, summary="No response from LLM")
        text = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL).strip()
        text = re.sub(r'```(?:json)?\s*', '', text).strip()
        if not text:
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
        lower = text.lower()
        relevant = "true" in lower or "relevant" in lower
        return EvalResult(relevant=relevant, summary=text[:200])
