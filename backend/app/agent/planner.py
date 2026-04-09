import json
import logging
from app.llm.router import LLMRouter, TaskComplexity

logger = logging.getLogger(__name__)


class AgentPlanner:
    def __init__(self, router: LLMRouter | None = None):
        self.router = router or LLMRouter()

    async def generate_queries(self, prompt: str, context: dict) -> list[str]:
        context_str = json.dumps(context, indent=2) if context else "No additional context provided."
        system_prompt = (
            "/no_think You are a search query generator. Given a research prompt and context, "
            "generate 3-5 targeted Google search queries that will help find the needed information. "
            "Respond ONLY with a JSON array of strings. Example: [\"query one\", \"query two\"]"
        )
        user_prompt = (
            f"Research prompt: {prompt}\n\n"
            f"Context:\n{context_str}\n\n"
            "Generate 3-5 Google search queries to find this information. "
            "Return ONLY a JSON array of query strings."
        )
        response = await self.router.complete(
            prompt=user_prompt,
            complexity=TaskComplexity.SIMPLE,
            system_prompt=system_prompt,
            temperature=0.2,
            max_tokens=500,
        )
        return self._parse_queries(response)

    async def refine_queries(
        self,
        original_prompt: str,
        context: dict,
        previous_queries: list[str],
        findings_so_far: list[str],
    ) -> list[str]:
        context_str = json.dumps(context, indent=2) if context else "No additional context provided."
        prev_queries_str = "\n".join(f"- {q}" for q in previous_queries)
        findings_str = "\n".join(f"- {f}" for f in findings_so_far) if findings_so_far else "No relevant findings yet."
        system_prompt = (
            "/no_think You are a search query refiner. Given a research prompt, previous search queries, "
            "and what was found so far, generate 3-5 new, different search queries to find better results. "
            "Avoid repeating previous queries. Respond ONLY with a JSON array of strings."
        )
        user_prompt = (
            f"Research prompt: {original_prompt}\n\n"
            f"Context:\n{context_str}\n\n"
            f"Previous queries tried:\n{prev_queries_str}\n\n"
            f"Findings so far:\n{findings_str}\n\n"
            "Generate 3-5 new, different search queries. "
            "Return ONLY a JSON array of query strings."
        )
        response = await self.router.complete(
            prompt=user_prompt,
            complexity=TaskComplexity.SIMPLE,
            system_prompt=system_prompt,
            temperature=0.3,
            max_tokens=500,
        )
        return self._parse_queries(response)

    def _parse_queries(self, response: str) -> list[str]:
        if not response:
            return []
        # Strip thinking tags (qwen3 and similar models)
        import re
        text = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL).strip()
        if not text:
            text = response.strip()
        # Look for a JSON array
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1 and end > start:
            try:
                queries = json.loads(text[start : end + 1])
                if isinstance(queries, list):
                    return [str(q).strip() for q in queries if q and str(q).strip()]
            except json.JSONDecodeError:
                pass
        # Fallback: split by newlines and clean up
        lines = [
            line.strip().lstrip("-•*123456789. ").strip()
            for line in text.splitlines()
            if line.strip()
        ]
        return [line for line in lines if line and len(line) > 3]
