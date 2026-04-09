import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.cell import Cell, CellStatus
from app.models.column import Column, ColumnType
from app.models.row import Row
from app.models.table import Table
from app.workers.scrape_worker import run_enrichment_job
from app.api.ws import manager
from app.services.quota_tracker import QuotaTracker
from app.scraper.email_verifier import EmailVerifier
from app.services.email_cache import EmailCacheService

router = APIRouter()
quota_tracker = QuotaTracker()


class EnrichmentRequest(BaseModel):
    row_ids: list[str] | None = None  # If None, run on all rows


class EnrichmentStatusResponse(BaseModel):
    total: int
    completed: int
    found: int
    not_found: int
    errors: int
    running: int


@router.post("/tables/{table_id}/columns/{column_id}/enrich")
async def trigger_enrichment(
    table_id: uuid.UUID,
    column_id: uuid.UUID,
    body: EnrichmentRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Trigger enrichment for a column on specified rows (or all rows)."""
    column = await db.get(Column, column_id)
    if not column or column.table_id != table_id:
        raise HTTPException(status_code=404, detail="Column not found")

    if column.type not in (ColumnType.AGENT, ColumnType.WATERFALL):
        raise HTTPException(status_code=400, detail="Column type is not enrichable")

    if not column.config or "prompt" not in column.config:
        raise HTTPException(status_code=400, detail="Column has no enrichment prompt configured")

    # Get rows
    query = select(Row).where(Row.table_id == table_id).options(selectinload(Row.cells))
    if body and body.row_ids:
        row_uuids = [uuid.UUID(rid) for rid in body.row_ids]
        query = query.where(Row.id.in_(row_uuids))
    result = await db.execute(query)
    rows = result.scalars().all()

    if not rows:
        raise HTTPException(status_code=404, detail="No rows found")

    # Find or create cells for this column in each row
    cells_to_enrich = []
    for row in rows:
        cell = next((c for c in row.cells if c.column_id == column_id), None)
        if not cell:
            cell = Cell(row_id=row.id, column_id=column_id, status=CellStatus.PENDING)
            db.add(cell)
            await db.flush()
        else:
            cell.status = CellStatus.PENDING
        cells_to_enrich.append(cell)
    await db.commit()

    # Run enrichments (synchronously for now — arq workers handle async when Redis is available)
    results = []
    for cell in cells_to_enrich:
        result = await run_enrichment_job(str(cell.id))
        # Broadcast update via WebSocket
        await db.refresh(cell)
        await manager.broadcast_cell_update(
            str(table_id), str(cell.id), cell.value, cell.status,
        )
        results.append(result)

    return {
        "triggered": len(cells_to_enrich),
        "results": results,
    }


@router.get("/tables/{table_id}/columns/{column_id}/enrich/status", response_model=EnrichmentStatusResponse)
async def enrichment_status(
    table_id: uuid.UUID,
    column_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get enrichment status for a column."""
    result = await db.execute(
        select(Cell).where(Cell.column_id == column_id)
    )
    cells = result.scalars().all()

    return EnrichmentStatusResponse(
        total=len(cells),
        completed=sum(1 for c in cells if c.status in (CellStatus.FOUND, CellStatus.NOT_FOUND, CellStatus.ERROR)),
        found=sum(1 for c in cells if c.status == CellStatus.FOUND),
        not_found=sum(1 for c in cells if c.status == CellStatus.NOT_FOUND),
        errors=sum(1 for c in cells if c.status == CellStatus.ERROR),
        running=sum(1 for c in cells if c.status in (CellStatus.RUNNING, CellStatus.PENDING)),
    )


@router.get("/quota")
async def get_quota():
    """Get current quota usage for all sources."""
    return quota_tracker.get_usage()


@router.post("/verify-email")
async def verify_email(body: dict):
    """Verify if an email address exists via SMTP."""
    email = body.get("email", "")
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Invalid email")
    verifier = EmailVerifier()
    result = await verifier.verify(email)
    return {
        "email": result.email,
        "status": result.status,
        "mx_host": result.mx_host,
        "error": result.error,
    }


@router.get("/email-cache/stats")
async def email_cache_stats():
    """Get statistics about the local email cache."""
    cache = EmailCacheService()
    return await cache.get_stats()


@router.get("/email-cache/search")
async def search_email_cache(q: str):
    """Search the email cache by email address or domain."""
    cache = EmailCacheService()
    results = []
    if "@" in q:
        entry = await cache.lookup_by_email(q)
        if entry:
            results.append(entry)
    else:
        domain_results = await cache.lookup_by_domain(q)
        results.extend(domain_results)
    return {
        "results": [
            {
                "email": r.email,
                "person": r.person_name,
                "company": r.company,
                "verified": r.verified,
                "confidence": r.confidence,
                "source": r.source,
            }
            for r in results
        ]
    }
