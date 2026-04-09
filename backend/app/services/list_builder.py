import json
import logging
from app.llm.router import LLMRouter, TaskComplexity
from app.scraper.engine import ScrapingEngine
from app.scraper.stealth import get_random_delay
import asyncio

logger = logging.getLogger(__name__)

LIST_BUILDER_SYSTEM_PROMPT = """/no_think You are an expert business researcher building a comprehensive list of entities.

Your job: produce a THOROUGH, ACCURATE list matching the given criteria. Think like a management consultant doing market research.

Quality standards:
1. ACCURACY: Only include entities you're confident actually exist and match the criteria. No hallucinated companies.
2. COMPLETENESS: Include the full range — market leaders, mid-tier players, and notable smaller ones.
3. RICHNESS: For each entity, include ALL fields you know: name, domain/website, industry, headquarters, size estimate, and anything else relevant to the criteria.
4. DIVERSITY: Cover different sub-categories (e.g., for "IT companies" include pure IT, consulting, product companies, fintech, etc.)
5. RELEVANCE: Every entry must genuinely match the search criteria. Don't pad with tangentially related entities.

For companies: include name, domain, industry, headquarters, approximate_size
For people: include full_name, title, company, linkedin_url (if known), department

Return ONLY a JSON array of objects. No explanation, no commentary."""

EXPAND_SYSTEM_PROMPT = """/no_think You are expanding a research list with new data found on the web.

Rules:
1. Add ONLY entities that genuinely match the original criteria
2. Do NOT duplicate entries already in the list (check by name, case-insensitive)
3. Fill in missing fields on existing entries if the web data has them (e.g., add a domain that was missing)
4. Maintain the same field structure as existing entries
5. Web data may be noisy — extract only verified entities, not every company name mentioned in passing

Return the COMPLETE merged list (existing + new) as a JSON array. No explanation."""


class ListBuilder:
    """Builds lists of companies/people from natural language descriptions."""

    def __init__(self):
        self.llm = LLMRouter()
        self.engine = ScrapingEngine()

    async def build_list(
        self,
        criteria: str,
        target_count: int = 25,
        entity_type: str = "companies",
    ) -> dict:
        """Build a list of entities matching the criteria.

        Returns: {"entities": [...], "total": int, "sources_used": [...]}
        """
        logger.info(f"Building list: '{criteria}' (target: {target_count} {entity_type})")

        # Step 1: Get initial list from LLM knowledge
        entities = await self._generate_initial_list(criteria, target_count, entity_type)
        logger.info(f"Initial list from LLM: {len(entities)} entities")

        # Step 2: Search the web for more
        if len(entities) < target_count:
            search_queries = await self._generate_search_queries(criteria, entity_type)
            web_results = await self._search_and_scrape(search_queries)
            if web_results:
                entities = await self._expand_list(criteria, entities, web_results, target_count, entity_type)
                logger.info(f"After web expansion: {len(entities)} entities")

        # Step 3: Deduplicate by name
        seen = set()
        deduped = []
        for entity in entities:
            name = (entity.get("name") or entity.get("company") or "").lower().strip()
            if name and name not in seen:
                seen.add(name)
                deduped.append(entity)

        return {
            "entities": deduped[:target_count],
            "total": len(deduped),
            "fields": list(deduped[0].keys()) if deduped else [],
        }

    async def _generate_initial_list(self, criteria: str, target_count: int, entity_type: str) -> list[dict]:
        prompt = (
            f"Search criteria: {criteria}\n"
            f"Entity type: {entity_type}\n"
            f"Target count: {target_count}\n\n"
            f"Generate a list of {target_count} {entity_type} matching this criteria. "
            f"Include as many relevant fields as possible (name, domain, industry, location, etc.)."
        )

        response = await self.llm.complete(
            prompt,
            system_prompt=LIST_BUILDER_SYSTEM_PROMPT,
            complexity=TaskComplexity.COMPLEX,
            temperature=0.3,
            max_tokens=4000,
        )

        return self._parse_list(response)

    async def _generate_search_queries(self, criteria: str, entity_type: str) -> list[str]:
        prompt = (
            f"I need to find a list of {entity_type} matching: {criteria}\n\n"
            f"Generate 3 Google search queries that would return pages listing these {entity_type}. "
            f"Return ONLY a JSON array of query strings."
        )

        response = await self.llm.complete(
            prompt,
            system_prompt="/no_think Return only a JSON array of search query strings.",
            complexity=TaskComplexity.SIMPLE,
            temperature=0.2,
            max_tokens=300,
        )

        try:
            import re
            text = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL).strip()
            start = text.find("[")
            end = text.rfind("]")
            if start != -1 and end != -1:
                return json.loads(text[start:end + 1])
        except Exception:
            pass
        return [criteria]

    async def _search_and_scrape(self, queries: list[str]) -> str:
        """Search and scrape top results, return combined text."""
        from app.scraper.stealth import get_random_user_agent
        import httpx
        from bs4 import BeautifulSoup

        all_text = []

        for query in queries[:3]:
            try:
                headers = {"User-Agent": get_random_user_agent()}
                data = {"q": query}
                async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=15.0) as client:
                    resp = await client.post("https://html.duckduckgo.com/html/", data=data)

                soup = BeautifulSoup(resp.text, "html.parser")
                urls = []
                for result_div in soup.select("div.result, div.web-result"):
                    link = result_div.select_one("a.result__a, h2 a")
                    if link:
                        href = link.get("href", "")
                        if href.startswith("http"):
                            urls.append(href)
                        elif "uddg=" in href:
                            from urllib.parse import parse_qs, urlparse
                            parsed = parse_qs(urlparse(href).query)
                            url = parsed.get("uddg", [None])[0]
                            if url:
                                urls.append(url)

                # Scrape top 2 URLs per query
                for url in urls[:2]:
                    try:
                        result = await self.engine.scrape(url)
                        if result.success and result.text:
                            all_text.append(result.text[:3000])
                    except Exception:
                        pass
                    await asyncio.sleep(get_random_delay(1.0, 2.0))

            except Exception as e:
                logger.warning(f"Search failed for '{query}': {e}")

            await asyncio.sleep(get_random_delay(1.0, 2.0))

        return "\n\n---\n\n".join(all_text)

    async def _expand_list(self, criteria: str, existing: list[dict], web_text: str, target_count: int, entity_type: str) -> list[dict]:
        existing_json = json.dumps(existing, indent=2)
        # Truncate web text to stay within token limits
        web_text = web_text[:6000]

        prompt = (
            f"Search criteria: {criteria}\n"
            f"Entity type: {entity_type}\n"
            f"Target count: {target_count}\n\n"
            f"Existing list ({len(existing)} items):\n{existing_json}\n\n"
            f"Web search results:\n{web_text}\n\n"
            f"Expand the list with any NEW {entity_type} found in the web results. "
            f"Return the complete list as a JSON array."
        )

        response = await self.llm.complete(
            prompt,
            system_prompt=EXPAND_SYSTEM_PROMPT,
            complexity=TaskComplexity.COMPLEX,
            temperature=0.2,
            max_tokens=4000,
        )

        expanded = self._parse_list(response)
        return expanded if expanded else existing

    def _parse_list(self, response: str) -> list[dict]:
        if not response:
            return []
        import re
        text = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL).strip()

        # Find JSON array
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(text[start:end + 1])
                if isinstance(data, list):
                    return [item for item in data if isinstance(item, dict)]
            except json.JSONDecodeError:
                pass
        return []
