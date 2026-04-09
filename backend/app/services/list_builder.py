import json
import logging
import re
import asyncio
from app.llm.router import LLMRouter, TaskComplexity
from app.scraper.engine import ScrapingEngine
from app.scraper.stealth import get_random_user_agent, get_random_delay
import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

EXTRACT_LIST_PROMPT = """/no_think You are extracting a structured list of entities from web page content.

Given search criteria and raw web page text, extract ALL matching entities as a JSON array.

Rules:
1. ONLY extract entities actually mentioned in the web content — do NOT make up entries
2. Each entity must have at minimum a "name" field
3. Add any other fields you can find: domain, industry, headquarters, description, etc.
4. If a company's website/domain is mentioned, include it
5. Extract as many as you can find — err on the side of inclusion
6. Clean up names (proper capitalization, full company names)

Return ONLY a JSON array of objects. No explanation."""

QUERY_GEN_PROMPT = """/no_think Generate 5 diverse search queries to find a comprehensive list matching this criteria.

Use different angles:
- Direct list queries ("top X companies in Y")
- Industry reports ("2024 report companies hiring campus India")
- Rankings and awards ("best employers India 2024")
- News articles ("companies hiring from IITs 2024")
- Forum/discussion queries ("reddit best companies campus placement India")

Return ONLY a JSON array of 5 query strings."""


class ListBuilder:
    """Builds lists by searching the web first, then using LLM to extract structured data."""

    def __init__(self):
        self.llm = LLMRouter()
        self.engine = ScrapingEngine()

    async def build_list(
        self,
        criteria: str,
        target_count: int = 25,
        entity_type: str = "companies",
    ) -> dict:
        logger.info(f"Building list: '{criteria}' (target: {target_count} {entity_type})")

        # Step 1: Generate diverse search queries
        logger.info("Step 1: Generating search queries...")
        queries = await self._generate_search_queries(criteria, entity_type)
        logger.info(f"Generated {len(queries)} queries")

        # Step 2: Search and scrape web pages
        logger.info("Step 2: Searching and scraping web...")
        all_entities = []
        for i, query in enumerate(queries):
            logger.info(f"  Query {i+1}/{len(queries)}: {query[:60]}...")
            page_texts = await self._search_and_scrape_one(query)
            if page_texts:
                # Step 3: Extract entities from each page
                for text in page_texts:
                    entities = await self._extract_entities(criteria, text, entity_type)
                    if entities:
                        all_entities.extend(entities)
                        logger.info(f"    Extracted {len(entities)} entities (total: {len(all_entities)})")

            if len(all_entities) >= target_count * 2:  # Get more than needed for dedup
                break

        # Step 4: Deduplicate by name
        logger.info(f"Step 3: Deduplicating {len(all_entities)} raw entities...")
        seen = set()
        deduped = []
        for entity in all_entities:
            name = (entity.get("name") or entity.get("company") or "").lower().strip()
            # Normalize common variations
            name = re.sub(r'\s*(ltd\.?|limited|inc\.?|pvt\.?|private|corp\.?)\s*', '', name).strip()
            if name and len(name) > 1 and name not in seen:
                seen.add(name)
                deduped.append(entity)

        logger.info(f"Final: {len(deduped)} unique entities")

        return {
            "entities": deduped[:target_count],
            "total": len(deduped),
            "fields": list(deduped[0].keys()) if deduped else [],
        }

    async def _generate_search_queries(self, criteria: str, entity_type: str) -> list[str]:
        prompt = f"Find a list of {entity_type} matching: {criteria[:300]}"

        response = await self.llm.complete(
            prompt,
            system_prompt=QUERY_GEN_PROMPT,
            complexity=TaskComplexity.SIMPLE,
            temperature=0.3,
            max_tokens=500,
        )

        try:
            text = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL).strip()
            start = text.find("[")
            end = text.rfind("]")
            if start != -1 and end != -1:
                queries = json.loads(text[start:end+1])
                if isinstance(queries, list):
                    return [str(q) for q in queries if q][:5]
        except Exception:
            pass
        # Fallback: use criteria directly as a search query
        return [criteria[:100], f"list of {criteria[:80]}", f"top {criteria[:80]} 2024"]

    async def _search_and_scrape_one(self, query: str) -> list[str]:
        """Search DuckDuckGo for one query, scrape top 3 results, return page texts."""
        texts = []
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

            # Scrape top 3 URLs
            for url in urls[:3]:
                try:
                    result = await self.engine.scrape(url)
                    if result.success and result.text and len(result.text) > 200:
                        texts.append(result.text[:4000])
                except Exception:
                    pass
                await asyncio.sleep(get_random_delay(0.5, 1.5))

        except Exception as e:
            logger.warning(f"Search failed for '{query[:50]}': {e}")

        return texts

    async def _extract_entities(self, criteria: str, page_text: str, entity_type: str) -> list[dict]:
        """Use LLM to extract structured entities from a web page."""
        prompt = (
            f"Search criteria: {criteria[:300]}\n"
            f"Entity type: {entity_type}\n\n"
            f"Web page content:\n{page_text[:4000]}\n\n"
            f"Extract all {entity_type} mentioned that match the criteria."
        )

        try:
            response = await self.llm.complete(
                prompt,
                system_prompt=EXTRACT_LIST_PROMPT,
                complexity=TaskComplexity.MODERATE,
                temperature=0.1,
                max_tokens=3000,
            )

            return self._parse_list(response)
        except Exception as e:
            logger.warning(f"Entity extraction failed: {e}")
            return []

    def _parse_list(self, response: str) -> list[dict]:
        if not response:
            return []
        text = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL).strip()
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(text[start:end+1])
                if isinstance(data, list):
                    return [item for item in data if isinstance(item, dict)]
            except json.JSONDecodeError:
                pass
        return []
