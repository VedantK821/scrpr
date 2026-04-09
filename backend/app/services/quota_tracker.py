from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class QuotaLimit:
    source: str
    limit: int
    period_days: int = 30  # monthly
    used: int = 0
    reset_at: datetime = field(default_factory=lambda: datetime.now() + timedelta(days=30))


class QuotaTracker:
    """Tracks free tier usage per enrichment source."""

    DEFAULT_LIMITS = {
        "hunter": QuotaLimit(source="hunter", limit=25, period_days=30),
        "apollo": QuotaLimit(source="apollo", limit=60, period_days=30),
        "ai_agent": QuotaLimit(source="ai_agent", limit=999999, period_days=30),  # Unlimited local
        "email_pattern": QuotaLimit(source="email_pattern", limit=999999, period_days=30),
    }

    def __init__(self):
        self.quotas: dict[str, QuotaLimit] = {
            k: QuotaLimit(source=v.source, limit=v.limit, period_days=v.period_days)
            for k, v in self.DEFAULT_LIMITS.items()
        }

    def can_use(self, source: str) -> bool:
        quota = self.quotas.get(source)
        if not quota:
            return True
        if datetime.now() >= quota.reset_at:
            quota.used = 0
            quota.reset_at = datetime.now() + timedelta(days=quota.period_days)
        return quota.used < quota.limit

    def record_use(self, source: str) -> None:
        quota = self.quotas.get(source)
        if quota:
            quota.used += 1

    def get_usage(self) -> dict[str, dict]:
        return {
            name: {"used": q.used, "limit": q.limit, "remaining": q.limit - q.used}
            for name, q in self.quotas.items()
        }
