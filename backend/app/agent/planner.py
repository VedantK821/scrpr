import json
import logging
import re
from app.llm.router import LLMRouter, TaskComplexity

logger = logging.getLogger(__name__)


GENERATE_SYSTEM_PROMPT = """/no_think You are an expert research strategist generating search queries for a web research agent.

Your job is to produce 5 highly targeted search queries that will surface the EXACT information requested. Think like a professional investigator — not a casual Googler.

Strategy:
1. Use simple keyword queries (DuckDuckGo search — NO site: or intitle: operators, they don't work)
2. Include the company name + role/title being searched
3. Try LinkedIn-style queries: "person name company linkedin"
4. Try news queries: "company appointed new head of recruitment"
5. Keep queries short and natural — like what a human would type

Each query should take a DIFFERENT angle — don't just rephrase the same thing. Cover:
- Direct name/title searches
- Company team/leadership pages
- LinkedIn profile searches
- News/appointment announcements
- Industry-specific directories

Return ONLY a JSON array of 5 query strings. No explanation."""


REFINE_SYSTEM_PROMPT = """/no_think You are an expert research strategist refining search queries after initial attempts failed to find the answer.

The previous queries didn't work. You need to try COMPLETELY DIFFERENT approaches:
- If you searched for a specific title, try related titles (e.g., "campus hiring" → "university relations" → "talent acquisition" → "early careers" → "graduate recruitment")
- If you searched the company site, try LinkedIn or press releases
- If you searched in English, try local language terms
- Try searching for the DEPARTMENT rather than the person (e.g., "TCS campus hiring team")
- Try competitor companies' similar roles for comparison
- Try searching for events/conferences where this person might have spoken

Return ONLY a JSON array of 5 query strings. No explanation."""


class AgentPlanner:
    def __init__(self, router: LLMRouter | None = None):
        self.router = router or LLMRouter()

    async def generate_queries(self, prompt: str, context: dict) -> list[str]:
        context_str = json.dumps(context, indent=2) if context else "No additional context."
        user_prompt = (
            f"RESEARCH TASK: {prompt}\n\n"
            f"KNOWN CONTEXT:\n{context_str}\n\n"
            f"Generate 5 targeted search queries using different strategies (LinkedIn, company site, news, job boards, direct search)."
        )
        response = await self.router.complete(
            prompt=user_prompt,
            complexity=TaskComplexity.SIMPLE,
            system_prompt=GENERATE_SYSTEM_PROMPT,
            temperature=0.3,
            max_tokens=600,
        )
        return self._parse_queries(response)

    async def refine_queries(
        self,
        original_prompt: str,
        context: dict,
        previous_queries: list[str],
        findings_so_far: list[str],
    ) -> list[str]:
        context_str = json.dumps(context, indent=2) if context else "No additional context."
        prev_str = "\n".join(f"  - {q}" for q in previous_queries)
        findings_str = "\n".join(f"  - {f}" for f in findings_so_far) if findings_so_far else "  Nothing relevant found yet."

        user_prompt = (
            f"RESEARCH TASK: {original_prompt}\n\n"
            f"KNOWN CONTEXT:\n{context_str}\n\n"
            f"QUERIES ALREADY TRIED (do NOT repeat):\n{prev_str}\n\n"
            f"WHAT WE FOUND SO FAR:\n{findings_str}\n\n"
            f"Generate 5 completely different search queries using new angles and strategies."
        )
        response = await self.router.complete(
            prompt=user_prompt,
            complexity=TaskComplexity.SIMPLE,
            system_prompt=REFINE_SYSTEM_PROMPT,
            temperature=0.4,
            max_tokens=600,
        )
        return self._parse_queries(response)

    def _parse_queries(self, response: str) -> list[str]:
        if not response:
            return []
        text = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL).strip()
        if not text:
            text = response.strip()
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1 and end > start:
            try:
                queries = json.loads(text[start : end + 1])
                if isinstance(queries, list):
                    return [str(q).strip() for q in queries if q and str(q).strip()]
            except json.JSONDecodeError:
                pass
        lines = [
            line.strip().lstrip("-•*123456789. ").strip()
            for line in text.splitlines()
            if line.strip()
        ]
        return [line for line in lines if line and len(line) > 3]
