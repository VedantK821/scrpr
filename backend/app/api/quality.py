"""Data quality API — email verification breakdown and confidence stats."""
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import json

from app.database import get_db
from app.models.cell import Cell, CellStatus
from app.models.column import Column, ColumnType
from app.models.enrichment_result import EnrichmentResult
from app.models.sequence import EmailEvent, EmailEventType, SequenceEnrollment

router = APIRouter()


@router.get("/tables/{table_id}/quality")
async def get_quality(table_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Get email verification quality breakdown for a table."""
    # Find enrichment columns (waterfall/agent) that produce emails
    result = await db.execute(
        select(Column).where(
            Column.table_id == table_id,
            Column.type.in_([ColumnType.AGENT, ColumnType.WATERFALL]),
        )
    )
    enrich_cols = result.scalars().all()
    if not enrich_cols:
        return {"total_emails": 0, "verification_breakdown": {}, "confidence_distribution": {}}

    col_ids = [c.id for c in enrich_cols]

    # Get all enrichment results for these columns
    result = await db.execute(
        select(EnrichmentResult)
        .join(Cell, EnrichmentResult.cell_id == Cell.id)
        .where(Cell.column_id.in_(col_ids))
        .where(EnrichmentResult.extracted_value.isnot(None))
    )
    results = result.scalars().all()

    # Categorize by method and confidence
    verification_breakdown = {}
    confidence_buckets = {"high": 0, "medium": 0, "low": 0, "bounced": 0}
    domains = {}

    for r in results:
        method = "unknown"
        provider = ""
        if r.raw_response:
            try:
                data = json.loads(r.raw_response) if isinstance(r.raw_response, str) else r.raw_response
                if isinstance(data, dict):
                    method = data.get("method", r.source or "unknown")
                    provider = data.get("provider", "")
            except (json.JSONDecodeError, TypeError):
                method = r.source or "unknown"

        verification_breakdown[method] = verification_breakdown.get(method, 0) + 1

        conf = r.confidence or 0
        if conf >= 0.8:
            confidence_buckets["high"] += 1
        elif conf >= 0.4:
            confidence_buckets["medium"] += 1
        else:
            confidence_buckets["low"] += 1

        # Track domains
        if r.extracted_value and "@" in r.extracted_value:
            domain = r.extracted_value.split("@")[1].lower()
            if domain not in domains:
                domains[domain] = {"count": 0, "provider": provider, "verified": 0}
            domains[domain]["count"] += 1
            if conf >= 0.8:
                domains[domain]["verified"] += 1

    # Count bounces from email events
    bounce_count = 0
    try:
        bounce_result = await db.execute(
            select(func.count(EmailEvent.id)).where(
                EmailEvent.event_type == EmailEventType.BOUNCED
            )
        )
        bounce_count = bounce_result.scalar() or 0
        confidence_buckets["bounced"] = bounce_count
    except Exception:
        pass

    total = len(results)
    top_domains = sorted(domains.items(), key=lambda x: -x[1]["count"])[:10]

    return {
        "total_emails": total,
        "verification_breakdown": verification_breakdown,
        "confidence_distribution": confidence_buckets,
        "top_domains": [
            {"domain": d, "count": info["count"], "provider": info["provider"], "verified": info["verified"]}
            for d, info in top_domains
        ],
        "bounce_rate": bounce_count / total if total > 0 else 0,
    }
