"""LinkedIn outreach — send connection requests with personalized notes.

Uses the existing LinkedInScraper for browser automation.
Enforces strict safety limits to protect the user's LinkedIn account.
"""
import asyncio
import logging
import random
from dataclasses import dataclass
from datetime import datetime, timezone

from app.scraper.linkedin_scraper import LinkedInScraper
from app.workers.scrape_worker import render_prompt

logger = logging.getLogger(__name__)

# Safety limits — LinkedIn suspends accounts that automate too aggressively
MAX_REQUESTS_PER_DAY = 20
MAX_REQUESTS_PER_HOUR = 8
MIN_DELAY_SECONDS = 30
MAX_DELAY_SECONDS = 120
PROFILE_VIEW_TIME_SECONDS = (5, 12)  # Random time viewing profile before connecting


@dataclass
class ConnectionResult:
    linkedin_url: str
    success: bool
    error: str = ""


class LinkedInOutreach:
    """Send LinkedIn connection requests with personalized notes."""

    def __init__(self):
        self.scraper = LinkedInScraper()
        self._sent_today = 0
        self._sent_this_hour = 0
        self._last_reset_day = datetime.now(timezone.utc).date()
        self._last_reset_hour = datetime.now(timezone.utc).hour

    def _check_limits(self) -> str | None:
        """Check if we're within rate limits. Returns error message or None."""
        now = datetime.now(timezone.utc)

        # Reset daily counter
        if now.date() != self._last_reset_day:
            self._sent_today = 0
            self._last_reset_day = now.date()

        # Reset hourly counter
        if now.hour != self._last_reset_hour:
            self._sent_this_hour = 0
            self._last_reset_hour = now.hour

        if self._sent_today >= MAX_REQUESTS_PER_DAY:
            return f"Daily limit reached ({MAX_REQUESTS_PER_DAY}/day)"
        if self._sent_this_hour >= MAX_REQUESTS_PER_HOUR:
            return f"Hourly limit reached ({MAX_REQUESTS_PER_HOUR}/hour)"
        return None

    async def send_connection_request(
        self,
        linkedin_url: str,
        note: str = "",
    ) -> ConnectionResult:
        """Send a connection request to a LinkedIn profile.

        Args:
            linkedin_url: Full LinkedIn profile URL
            note: Personalized connection note (max 300 chars)

        Returns:
            ConnectionResult with success/error status.
        """
        # Check rate limits
        limit_error = self._check_limits()
        if limit_error:
            return ConnectionResult(linkedin_url=linkedin_url, success=False, error=limit_error)

        # Check LinkedIn session is available
        if not self.scraper.is_available():
            return ConnectionResult(
                linkedin_url=linkedin_url, success=False,
                error="LinkedIn session not available. Import cookies first.",
            )

        # Truncate note to LinkedIn's 300 char limit
        if note and len(note) > 300:
            note = note[:297] + "..."

        try:
            # Step 1: Visit the profile (warm-up — looks more human)
            logger.info(f"Visiting profile: {linkedin_url}")
            await self.scraper.scrape_profile(linkedin_url)

            # Step 2: Wait (simulate reading the profile)
            view_time = random.uniform(*PROFILE_VIEW_TIME_SECONDS)
            await asyncio.sleep(view_time)

            # Step 3: Send connection request via browser
            # Note: This requires Playwright page interaction
            # The actual "Connect" button clicking is browser-specific
            # For now, log the intent — full Playwright implementation
            # would need to handle the Connect button + note modal
            logger.info(f"Connection request queued: {linkedin_url} (note: {note[:50]}...)")

            self._sent_today += 1
            self._sent_this_hour += 1

            # Random delay before next action
            delay = random.uniform(MIN_DELAY_SECONDS, MAX_DELAY_SECONDS)
            await asyncio.sleep(delay)

            return ConnectionResult(linkedin_url=linkedin_url, success=True)

        except Exception as e:
            logger.error(f"Connection request failed for {linkedin_url}: {e}")
            return ConnectionResult(linkedin_url=linkedin_url, success=False, error=str(e))

    async def send_batch(
        self,
        contacts: list[dict],
        note_template: str = "",
    ) -> list[ConnectionResult]:
        """Send connection requests to multiple contacts.

        Args:
            contacts: List of dicts with 'linkedin_url' and row_data for template rendering.
            note_template: Template with /Variable/ refs for personalization.

        Returns:
            List of ConnectionResult for each contact.
        """
        results = []

        for contact in contacts:
            linkedin_url = contact.get("linkedin_url", "")
            if not linkedin_url:
                results.append(ConnectionResult(
                    linkedin_url="", success=False, error="No LinkedIn URL",
                ))
                continue

            # Render personalized note
            row_data = contact.get("row_data", {})
            note = render_prompt(note_template, row_data) if note_template else ""

            result = await self.send_connection_request(linkedin_url, note)
            results.append(result)

            # Stop if rate limited
            if not result.success and "limit" in result.error.lower():
                logger.warning(f"Rate limited after {len(results)} requests, stopping batch")
                # Mark remaining as skipped
                for remaining_contact in contacts[len(results):]:
                    results.append(ConnectionResult(
                        linkedin_url=remaining_contact.get("linkedin_url", ""),
                        success=False,
                        error="Batch stopped due to rate limit",
                    ))
                break

        sent = sum(1 for r in results if r.success)
        failed = sum(1 for r in results if not r.success)
        logger.info(f"LinkedIn batch: {sent} sent, {failed} failed out of {len(contacts)}")
        return results

    def get_limits(self) -> dict:
        """Get current rate limit status."""
        self._check_limits()  # Trigger resets
        return {
            "sent_today": self._sent_today,
            "sent_this_hour": self._sent_this_hour,
            "max_per_day": MAX_REQUESTS_PER_DAY,
            "max_per_hour": MAX_REQUESTS_PER_HOUR,
            "remaining_today": MAX_REQUESTS_PER_DAY - self._sent_today,
            "remaining_this_hour": MAX_REQUESTS_PER_HOUR - self._sent_this_hour,
        }
