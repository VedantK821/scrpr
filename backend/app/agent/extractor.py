import json
import logging
import re
from dataclasses import dataclass, field
from app.llm.router import LLMRouter, TaskComplexity

logger = logging.getLogger(__name__)

MAX_COMBINED_TEXT_LENGTH = 10000


EXTRACT_SYSTEM_PROMPT = """/no_think You are an expert data extractor for a web research agent.

Given a research task and content from multiple web pages, extract the BEST answer as structured data.

Extraction rules:
1. CROSS-REFERENCE across sources — if two pages mention the same person/data, confidence goes UP
2. Prefer data from LinkedIn profiles and official company pages over third-party sites
3. If the research task asks for a person, extract ALL available fields: full_name, title, email, linkedin_url, company, department
4. If multiple candidates match, pick the BEST match for the research task and note alternatives
5. NEVER fabricate data — if a field isn't found, omit it entirely rather than guessing
6. Clean up extracted data: proper capitalization for names, full URLs for LinkedIn, lowercase for emails
7. CRITICAL: full_name MUST be a person's actual name (first and last name, e.g., "Rajesh Kumar", "Bonnie Dilber"). It must NEVER be a job title (e.g., "Director, Talent Acquisition", "HR Manager"). If you cannot find a specific person's name, set full_name to null rather than putting the title there. The title goes in the "title" field only.

Confidence scoring:
- 0.9-1.0: Exact match found with corroborating evidence from multiple sources
- 0.7-0.8: Strong match from a single reliable source (LinkedIn profile, company page)
- 0.5-0.6: Probable match but some uncertainty (title is close but not exact, or from an older source)
- 0.3-0.4: Partial match — found the department/team but not the specific person
- 0.1-0.2: Very uncertain — found tangentially related info only
- 0.0: Nothing relevant found

Return ONLY this JSON:
{
  "data": {
    "full_name": "...",
    "title": "...",
    "email": "...",
    "linkedin_url": "...",
    "company": "...",
    ...any other relevant fields from the research task
  },
  "confidence": 0.0,
  "reasoning": "Brief explanation of why this is the best answer and what sources confirmed it"
}"""


@dataclass
class ExtractionResult:
    data: dict = field(default_factory=dict)
    confidence: float = 0.0
    raw_response: str = ""


class AgentExtractor:
    def __init__(self, router: LLMRouter | None = None):
        self.router = router or LLMRouter()

    async def extract(
        self,
        prompt: str,
        page_texts: list[str],
        context: dict,
    ) -> ExtractionResult:
        combined = self._combine_texts(page_texts)
        context_str = json.dumps(context, indent=2) if context else "No additional context."

        user_prompt = (
            f"RESEARCH TASK: {prompt}\n\n"
            f"KNOWN CONTEXT:\n{context_str}\n\n"
            f"COLLECTED WEB DATA ({len(page_texts)} sources):\n{combined}\n\n"
            f"Extract the best answer to the research task. Cross-reference sources for accuracy."
        )
        response = await self.router.complete(
            prompt=user_prompt,
            complexity=TaskComplexity.COMPLEX,
            system_prompt=EXTRACT_SYSTEM_PROMPT,
            temperature=0.1,
            max_tokens=1500,
        )
        return self._parse_extraction_result(response)

    def _combine_texts(self, page_texts: list[str]) -> str:
        if not page_texts:
            return ""
        combined_parts = []
        remaining = MAX_COMBINED_TEXT_LENGTH
        for i, text in enumerate(page_texts):
            if remaining <= 0:
                break
            chunk = text[:remaining]
            combined_parts.append(f"=== SOURCE {i + 1} ===\n{chunk}")
            remaining -= len(chunk)
        return "\n\n".join(combined_parts)

    def _parse_extraction_result(self, response: str) -> ExtractionResult:
        if not response:
            return ExtractionResult(raw_response="")
        text = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL).strip()
        text = re.sub(r'```(?:json)?\s*', '', text).strip()
        if not text:
            text = response.strip()
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                parsed = json.loads(text[start : end + 1])
                data = parsed.get("data", {})
                if not isinstance(data, dict):
                    data = {"value": data}
                confidence = float(parsed.get("confidence", 0.0))
                confidence = max(0.0, min(1.0, confidence))
                return ExtractionResult(data=data, confidence=confidence, raw_response=response)
            except (json.JSONDecodeError, ValueError, TypeError):
                pass
        return ExtractionResult(data={}, confidence=0.0, raw_response=response)
