from app.agent.loop import AgentLoop
from app.sources.base import EnrichmentSource, SourceResult


def format_agent_data(data: dict) -> str:
    """Format extracted agent data as a human-readable string."""
    if not data:
        return ""
    # Contact data: "Name — Title — LinkedIn"
    if data.get("full_name"):
        parts = [str(data["full_name"])]
        if data.get("title"):
            parts.append(str(data["title"]))
        if data.get("linkedin_url"):
            parts.append(str(data["linkedin_url"]))
        return " — ".join(parts)
    # Known single-value fields
    for key in ("summary", "description", "answer", "result", "value"):
        if data.get(key):
            return str(data[key])
    # Fallback: join all non-empty values
    values = [str(v) for v in data.values() if v]
    return " | ".join(values) if values else ""


TITLE_WORDS = {
    "director", "manager", "head", "vp", "chief", "officer", "lead",
    "senior", "coordinator", "specialist", "recruiter", "president",
    "associate", "analyst", "executive", "supervisor", "administrator",
    "partner", "consultant", "advisor", "strategist",
}


def validate_contact_name(data: dict) -> dict:
    """Check if full_name is actually a job title. Add name_confidence score."""
    name = data.get("full_name", "")
    if not name:
        data["name_confidence"] = 0.0
        return data

    # Commas in a name are a strong signal it's a title ("Director, Talent Acquisition")
    has_comma = "," in name
    words = set(name.lower().replace(",", " ").replace("-", " ").split())
    title_overlap = words & TITLE_WORDS

    # Comma + any title word = almost certainly a title, not a name
    if has_comma and title_overlap:
        data["name_confidence"] = 0.1
        data["_warning"] = f"full_name looks like a title: '{name}'"
    # If more than half the words are title words, it's a title
    elif len(title_overlap) > len(words) / 2:
        data["name_confidence"] = 0.1
        data["_warning"] = f"full_name looks like a title: '{name}'"
    # Some title words present but could be ambiguous
    elif title_overlap and len(words) > 2:
        data["name_confidence"] = 0.4
    else:
        data["name_confidence"] = 0.9
    return data


class AIAgentSource(EnrichmentSource):
    name = "ai_agent"
    rate_limit_per_minute = 10

    async def enrich(self, row_data: dict[str, str], prompt: str) -> SourceResult:
        # Fast path: direct LLM knowledge + text confirmation
        # Skips entire web scraping pipeline — 2s vs 60s
        result = await self._fast_knowledge_lookup(row_data, prompt)
        if result:
            return result

        # Fast path didn't find anyone — return not_found rather than
        # burning 2+ minutes on slow web scraping that holds up the queue
        return SourceResult(
            found=False,
            value=None,
            data={},
            confidence=0.0,
            source_name=self.name,
            error="Not found in LLM knowledge",
        )

    async def _fast_knowledge_lookup(self, row_data: dict, prompt: str) -> SourceResult | None:
        """Ask LLM directly, confirm with a text search. No scraping needed."""
        import re
        import json
        import httpx
        from bs4 import BeautifulSoup
        from app.llm.router import LLMRouter, TaskComplexity

        company = row_data.get("Name") or row_data.get("name") or row_data.get("company") or ""
        if not company:
            return None

        router = LLMRouter()

        # Step 1: Ask Gemini — role-aware prompt
        llm_prompt = f"""/no_think You are finding the best person to contact for a job opportunity at {company}.

Rules:
- For STARTUPS (< 100 employees): Return the CEO, CTO, or founder — they decide hiring directly.
- For LARGE companies: Return the Head of Recruiting, VP of Talent, or a senior technical recruiter.
- Always return a SPECIFIC real person, not a generic title.

Research task context: {prompt}

Return ONLY this JSON, nothing else:
{{"name": "their full real name", "title": "their exact title", "linkedin_url": "their linkedin URL if you know it, otherwise null"}}

If you genuinely don't know a specific person, return {{"name": null}}"""

        try:
            result = await router.complete(
                prompt=llm_prompt,
                complexity=TaskComplexity.SIMPLE,
                temperature=0.1,
                max_tokens=300,
            )
        except Exception:
            return None

        # Parse response
        text = re.sub(r'<think>.*?</think>', '', result or '', flags=re.DOTALL)
        text = re.sub(r'```(?:json)?\s*', '', text).strip()
        start, end = text.find('{'), text.rfind('}')
        if start < 0 or end <= start:
            return None

        try:
            data = json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            return None

        name = data.get("name")
        if not name or name.lower() in ("n/a", "null", "none", "unknown", ""):
            return None

        title = data.get("title", "")
        linkedin = data.get("linkedin_url")

        # Step 2: Confirm with Bing text search
        confirmed = False
        try:
            async with httpx.AsyncClient(timeout=8.0, headers={"User-Agent": "Mozilla/5.0"}) as c:
                resp = await c.get(
                    "https://www.bing.com/search",
                    params={"q": f'"{name}" "{company}"'},
                )
                soup = BeautifulSoup(resp.text, "html.parser")
                results = soup.select("#b_results .b_algo")
                confirmed = len(results) >= 1
        except Exception:
            pass

        if not confirmed:
            return None

        # Build result
        contact_data = {"full_name": name, "title": title, "name_confidence": 0.9}
        if linkedin:
            contact_data["linkedin_url"] = linkedin

        validated = validate_contact_name(contact_data)
        formatted = format_agent_data(validated)

        if not formatted:
            return None

        return SourceResult(
            found=True,
            value=formatted,
            data=validated,
            confidence=0.85,
            source_name=self.name,
        )
