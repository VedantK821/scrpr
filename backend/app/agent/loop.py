import asyncio
import logging
from dataclasses import dataclass, field

import httpx
from bs4 import BeautifulSoup

from app.agent.evaluator import AgentEvaluator
from app.agent.extractor import AgentExtractor
from app.agent.planner import AgentPlanner
from app.scraper.engine import ScrapingEngine
from app.scraper.linkedin_scraper import LinkedInScraper

logger = logging.getLogger(__name__)

DEFAULT_MAX_LOOPS = 5
DEFAULT_TIMEOUT = 180
CONFIDENCE_THRESHOLD = 0.3
DUCKDUCKGO_SEARCH_URL = "https://html.duckduckgo.com/html/"


@dataclass
class AgentResult:
    success: bool
    data: dict = field(default_factory=dict)
    confidence: float = 0.0
    loops_used: int = 0
    pages_visited: int = 0
    error: str | None = None


class AgentLoop:
    def __init__(
        self,
        max_loops: int = DEFAULT_MAX_LOOPS,
        timeout: int = DEFAULT_TIMEOUT,
        planner: AgentPlanner | None = None,
        evaluator: AgentEvaluator | None = None,
        extractor: AgentExtractor | None = None,
        engine: ScrapingEngine | None = None,
    ):
        self.max_loops = max_loops
        self.timeout = timeout
        self.planner = planner or AgentPlanner()
        self.evaluator = evaluator or AgentEvaluator()
        self.extractor = extractor or AgentExtractor()
        self.engine = engine or ScrapingEngine()

    async def run(self, prompt: str, context: dict) -> AgentResult:
        try:
            return await asyncio.wait_for(
                self._run_inner(prompt, context),
                timeout=self.timeout,
            )
        except asyncio.TimeoutError:
            return AgentResult(
                success=False,
                error=f"Agent timed out after {self.timeout}s",
            )
        except Exception as e:
            logger.exception(f"Agent loop failed: {e}")
            return AgentResult(success=False, error=str(e))

    async def _run_inner(self, prompt: str, context: dict) -> AgentResult:
        all_relevant_texts: list[str] = []
        all_relevant_summaries: list[str] = []
        previous_queries: list[str] = []
        pages_visited = 0

        for loop_num in range(self.max_loops):
            logger.info(f"Agent loop {loop_num + 1}/{self.max_loops}")

            # Plan: generate or refine queries
            if loop_num == 0:
                queries = await self.planner.generate_queries(prompt, context)
            else:
                queries = await self.planner.refine_queries(
                    prompt, context, previous_queries, all_relevant_summaries
                )

            if not queries:
                logger.warning("No queries generated, stopping.")
                break

            previous_queries.extend(queries)

            # Search: run the first query (or all, taking top results)
            loop_relevant_texts: list[str] = []
            for query in queries[:2]:  # limit to 2 queries per loop to stay within timeout
                search_results = await self._google_search(query, num_results=5)
                urls = [r["url"] for r in search_results if r.get("url")]

                # Scrape top URLs
                for url in urls[:3]:
                    pages_visited += 1
                    try:
                        scrape_result = await self.engine.scrape(url)
                        if scrape_result.success and scrape_result.text:
                            # Evaluate relevance
                            eval_result = await self.evaluator.evaluate(
                                prompt, scrape_result.text, url
                            )
                            if eval_result.relevant:
                                loop_relevant_texts.append(scrape_result.text)
                                all_relevant_texts.append(scrape_result.text)
                                all_relevant_summaries.append(eval_result.summary)
                                logger.info(f"Relevant page found: {url}")
                    except Exception as e:
                        logger.warning(f"Failed to scrape {url}: {e}")

            # Also search LinkedIn directly if the session is available
            linkedin = LinkedInScraper()
            if linkedin.is_available():
                li_query = f"{context.get('company', '')} {prompt}"
                try:
                    li_results = await linkedin.search_people(li_query[:100], max_results=3)
                    if li_results:
                        for person in li_results:
                            text = f"LinkedIn Profile: {person['name']} - {person['title']} - {person['linkedin_url']}"
                            all_relevant_texts.append(text)
                            loop_relevant_texts.append(text)
                            all_relevant_summaries.append(
                                f"Found {person['name']} ({person['title']}) on LinkedIn"
                            )
                except Exception as e:
                    logger.warning(f"LinkedIn search failed in agent loop: {e}")

            # Extract if we have relevant pages
            if loop_relevant_texts:
                extraction = await self.extractor.extract(
                    prompt, loop_relevant_texts, context
                )
                if extraction.confidence >= CONFIDENCE_THRESHOLD:
                    return AgentResult(
                        success=True,
                        data=extraction.data,
                        confidence=extraction.confidence,
                        loops_used=loop_num + 1,
                        pages_visited=pages_visited,
                    )

        # Final attempt: extract from all relevant texts collected
        if all_relevant_texts:
            extraction = await self.extractor.extract(prompt, all_relevant_texts, context)
            return AgentResult(
                success=extraction.confidence >= CONFIDENCE_THRESHOLD,
                data=extraction.data,
                confidence=extraction.confidence,
                loops_used=self.max_loops,
                pages_visited=pages_visited,
            )

        return AgentResult(
            success=False,
            data={},
            confidence=0.0,
            loops_used=self.max_loops,
            pages_visited=pages_visited,
            error="No relevant information found after exhausting all loops",
        )

    async def _google_search(
        self, query: str, num_results: int = 5
    ) -> list[dict]:
        """Search using DuckDuckGo HTML (more scraping-friendly than Google)."""
        from app.scraper.stealth import get_random_user_agent
        headers = {"User-Agent": get_random_user_agent()}
        data = {"q": query}
        results = []
        try:
            async with httpx.AsyncClient(
                headers=headers, follow_redirects=True, timeout=15.0
            ) as client:
                response = await client.post(DUCKDUCKGO_SEARCH_URL, data=data)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "html.parser")

                for result_div in soup.select("div.result, div.web-result"):
                    link = result_div.select_one("a.result__a, a.result__url, h2 a")
                    snippet_el = result_div.select_one("a.result__snippet, .result__snippet")
                    url = None
                    if link:
                        href = link.get("href", "")
                        if href.startswith("http"):
                            url = href
                        elif "uddg=" in href:
                            import urllib.parse
                            parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                            url = parsed.get("uddg", [None])[0]

                    snippet = snippet_el.get_text(strip=True) if snippet_el else ""

                    if url:
                        results.append({"url": url, "snippet": snippet})
                        if len(results) >= num_results:
                            break
        except Exception as e:
            logger.warning(f"Google search failed for query '{query}': {e}")

        return results
