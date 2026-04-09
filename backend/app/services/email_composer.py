import re
import logging
from app.llm.router import LLMRouter, TaskComplexity
from app.models.email_draft import PersonalizationLevel

logger = logging.getLogger(__name__)

PERSONALIZE_SYSTEM_PROMPT = """You are an email personalization expert. Given a template email and data about the recipient, rewrite the email to feel personally crafted for them.

Rules:
- Keep the core message and intent intact
- Reference specific details about the person/company from the provided data
- Sound human, warm, and professional — not salesy or generic
- Keep it concise (under 150 words for the body)
- Do not add fake facts — only use data that was provided
- Return ONLY the personalized email body, nothing else (no subject line, no "Here's the email", just the body text)"""

MEDIUM_SYSTEM_PROMPT = """You are an email personalization expert. Given a template email and data about the recipient, enhance 1-2 sentences to reference specific details about the person/company.

Rules:
- Keep most of the email unchanged
- Only modify 1-2 sentences to add personalization
- Use specific data provided about the recipient
- Return ONLY the modified email body, nothing else"""


class EmailComposer:
    def __init__(self):
        self.llm = LLMRouter()

    def substitute_variables(self, template: str, row_data: dict[str, str]) -> str:
        """Replace /ColumnName/ variables with actual values."""
        def replace_var(match):
            var_name = match.group(1)
            # Try exact match, then case-insensitive
            value = row_data.get(var_name) or row_data.get(var_name.lower()) or row_data.get(var_name.upper())
            return value if value else match.group(0)

        return re.sub(r'/([^/]+)/', replace_var, template)

    async def personalize(
        self,
        subject_template: str,
        body_template: str,
        row_data: dict[str, str],
        level: PersonalizationLevel,
    ) -> dict:
        """Personalize an email for a specific recipient."""
        # Always substitute variables in subject
        subject = self.substitute_variables(subject_template, row_data)

        if level == PersonalizationLevel.LIGHT:
            body = self.substitute_variables(body_template, row_data)
            return {"subject": subject, "body": body, "confidence": 1.0}

        # For medium/max, use AI
        body_with_vars = self.substitute_variables(body_template, row_data)
        data_summary = "\n".join(f"- {k}: {v}" for k, v in row_data.items() if v)

        system = MEDIUM_SYSTEM_PROMPT if level == PersonalizationLevel.MEDIUM else PERSONALIZE_SYSTEM_PROMPT

        prompt = (
            f"Template email:\n{body_with_vars}\n\n"
            f"Recipient data:\n{data_summary}\n\n"
            f"Personalize this email:"
        )

        try:
            body = await self.llm.complete(
                prompt,
                system_prompt=system,
                complexity=TaskComplexity.MODERATE if level == PersonalizationLevel.MEDIUM else TaskComplexity.COMPLEX,
                temperature=0.4,
                max_tokens=500,
            )
            return {"subject": subject, "body": body.strip(), "confidence": 0.85}
        except Exception as e:
            logger.error(f"AI personalization failed: {e}")
            return {"subject": subject, "body": body_with_vars, "confidence": 0.5}
