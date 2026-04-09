import json
import logging
from dataclasses import dataclass, field
from app.llm.router import LLMRouter, TaskComplexity

logger = logging.getLogger(__name__)

MAX_COMBINED_TEXT_LENGTH = 8000


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
        # Combine page texts with truncation to stay within limit
        combined = self._combine_texts(page_texts)
        context_str = json.dumps(context, indent=2) if context else "No additional context provided."
        system_prompt = (
            "/no_think You are a data extractor. Given a research prompt and web page content, "
            "extract the relevant information and return it as structured JSON. "
            "Provide a confidence score from 0.0 (not found) to 1.0 (highly confident). "
            'Respond ONLY with JSON: {"data": {...}, "confidence": 0.0}'
        )
        user_prompt = (
            f"Research prompt: {prompt}\n\n"
            f"Context:\n{context_str}\n\n"
            f"Web page content:\n{combined}\n\n"
            "Extract the relevant information. "
            'Respond ONLY with JSON: {"data": {"key": "value", ...}, "confidence": 0.0-1.0}'
        )
        response = await self.router.complete(
            prompt=user_prompt,
            complexity=TaskComplexity.COMPLEX,
            system_prompt=system_prompt,
            temperature=0.1,
            max_tokens=1000,
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
            combined_parts.append(f"--- Source {i + 1} ---\n{chunk}")
            remaining -= len(chunk)
        return "\n\n".join(combined_parts)

    def _parse_extraction_result(self, response: str) -> ExtractionResult:
        if not response:
            return ExtractionResult(raw_response="")
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
