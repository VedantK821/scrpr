import asyncio
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db, async_session
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

    # Kick off background processing and return immediately
    cell_ids = [str(c.id) for c in cells_to_enrich]
    asyncio.create_task(_run_enrichments_background(cell_ids, str(table_id)))

    return {"triggered": len(cells_to_enrich), "status": "running"}


@router.post("/tables/{table_id}/enrich-all")
async def enrich_all(table_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Run all enrichment columns sequentially: AGENT first, then WATERFALL."""
    result = await db.execute(
        select(Column).where(
            Column.table_id == table_id,
            Column.type.in_([ColumnType.AGENT, ColumnType.WATERFALL]),
        ).order_by(Column.position)
    )
    columns = result.scalars().all()

    if not columns:
        raise HTTPException(status_code=400, detail="No enrichment columns found")

    for col in columns:
        if not col.config or "prompt" not in col.config:
            raise HTTPException(status_code=400, detail=f"Column '{col.name}' has no prompt configured")

    row_result = await db.execute(
        select(Row).where(Row.table_id == table_id).options(selectinload(Row.cells))
    )
    rows = row_result.scalars().all()

    if not rows:
        raise HTTPException(status_code=404, detail="No rows found")

    agent_cols = [c for c in columns if c.type == ColumnType.AGENT]
    waterfall_cols = [c for c in columns if c.type == ColumnType.WATERFALL]

    agent_cell_ids = []
    waterfall_cell_ids = []

    for col in columns:
        target = agent_cell_ids if col in agent_cols else waterfall_cell_ids
        for row in rows:
            cell = next((c for c in row.cells if c.column_id == col.id), None)
            if not cell:
                cell = Cell(row_id=row.id, column_id=col.id, status=CellStatus.PENDING)
                db.add(cell)
                await db.flush()
            else:
                cell.status = CellStatus.PENDING
            target.append(str(cell.id))

    await db.commit()

    total = len(agent_cell_ids) + len(waterfall_cell_ids)
    asyncio.create_task(_run_all_sequential(agent_cell_ids, waterfall_cell_ids, str(table_id)))

    return {
        "triggered": total,
        "status": "running",
        "agent_cells": len(agent_cell_ids),
        "waterfall_cells": len(waterfall_cell_ids),
    }


async def _run_all_sequential(
    agent_cell_ids: list[str],
    waterfall_cell_ids: list[str],
    table_id: str,
) -> None:
    """Run AGENT cells first, wait, then WATERFALL cells."""
    if agent_cell_ids:
        await _broadcast_log(table_id, f"Phase 1/2: Enriching {len(agent_cell_ids)} agent cells...")
        await _run_enrichments_background(agent_cell_ids, table_id)
        await _broadcast_log(table_id, "Phase 1 complete — contact data ready.")

    if waterfall_cell_ids:
        await _broadcast_log(table_id, f"Phase 2/2: Enriching {len(waterfall_cell_ids)} waterfall cells...")
        await _run_enrichments_background(waterfall_cell_ids, table_id)

    await _broadcast_log(table_id, "All enrichments complete!")


async def _run_enrichments_background(cell_ids: list[str], table_id: str) -> None:
    """Process enrichments concurrently (3 at a time), with per-cell activity logging."""
    import time

    semaphore = asyncio.Semaphore(3)  # 3 concurrent cells

    async def _process_one(cell_id: str, index: int) -> None:
        async with semaphore:
            start = time.time()
            # Look up column_id for this cell
            _col_id = None
            async with async_session() as _db:
                _cell = await _db.get(Cell, uuid.UUID(cell_id))
                if _cell:
                    _col_id = str(_cell.column_id)

            # Broadcast that we're starting this cell
            await manager.broadcast_cell_update(
                table_id, cell_id, _col_id, None, "running",
            )
            await _broadcast_log(table_id, f"[{index+1}/{len(cell_ids)}] Starting enrichment for cell {cell_id[:8]}...")

            try:
                result = await asyncio.wait_for(
                    run_enrichment_job(cell_id),
                    timeout=120.0,
                )
                elapsed = time.time() - start
                if result.get("error"):
                    await _broadcast_log(table_id, f"[{index+1}/{len(cell_ids)}] Error after {elapsed:.0f}s: {result['error'][:100]}")
                else:
                    value = result.get("value", "")
                    source = result.get("source", "unknown")
                    await _broadcast_log(table_id, f"[{index+1}/{len(cell_ids)}] Found via {source} ({elapsed:.0f}s): {str(value)[:60]}")

            except asyncio.TimeoutError:
                await _broadcast_log(table_id, f"[{index+1}/{len(cell_ids)}] Timed out after 120s")
                async with async_session() as db:
                    cell = await db.get(Cell, uuid.UUID(cell_id))
                    if cell:
                        cell.status = CellStatus.ERROR
                        await db.commit()
            except Exception as e:
                await _broadcast_log(table_id, f"[{index+1}/{len(cell_ids)}] Exception: {str(e)[:100]}")
                async with async_session() as db:
                    cell = await db.get(Cell, uuid.UUID(cell_id))
                    if cell:
                        cell.status = CellStatus.ERROR
                        await db.commit()

            # Broadcast final cell state
            async with async_session() as db:
                cell = await db.get(Cell, uuid.UUID(cell_id))
                if cell:
                    await manager.broadcast_cell_update(
                        table_id, cell_id, str(cell.column_id), cell.value, cell.status,
                    )

    await _broadcast_log(table_id, f"Starting enrichment: {len(cell_ids)} cells, 3 concurrent workers")
    await asyncio.gather(*[_process_one(cid, i) for i, cid in enumerate(cell_ids)])
    await _broadcast_log(table_id, f"Enrichment complete: all {len(cell_ids)} cells processed")


async def _broadcast_log(table_id: str, message: str) -> None:
    """Send a log message to all WebSocket clients for this table."""
    import json as _json
    log_msg = _json.dumps({"type": "enrichment_log", "message": message})
    if table_id in manager.connections:
        dead = []
        for ws in manager.connections[table_id]:
            try:
                await ws.send_text(log_msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            manager.disconnect(ws, table_id)


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


@router.post("/tables/{table_id}/auto-enrich-columns")
async def auto_create_enrichment_columns(table_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Auto-create Key Contact + Email enrichment columns for an existing table."""
    table = await db.get(Table, table_id)
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")

    # Get existing columns
    result = await db.execute(select(Column).where(Column.table_id == table_id).order_by(Column.position))
    existing = result.scalars().all()
    existing_names = {c.name.lower() for c in existing}
    next_pos = len(existing)

    # Find the company/name column to reference in prompts
    company_col = next(
        (c for c in existing if c.name.lower() in ("company", "name", "company name", "organisation")),
        existing[0] if existing else None,
    )
    if not company_col:
        raise HTTPException(status_code=400, detail="Table has no columns to reference")

    created = []

    # Add Key Contact column if not exists
    if not any(n in existing_names for n in ("key contact", "contact", "hiring contact", "recruiter")):
        col = Column(
            table_id=table_id,
            name="Key Contact",
            type=ColumnType.AGENT,
            position=next_pos,
            config={
                "prompt": f"Find the most relevant contact person at /{company_col.name}/. Return their full name, title, and LinkedIn URL."
            },
        )
        db.add(col)
        await db.flush()
        created.append("Key Contact")
        next_pos += 1

    # Add Email column if not exists
    if not any(n in existing_names for n in ("email", "email address", "work email")):
        contact_ref = "Key Contact" if "key contact" not in existing_names else "Recruiter"
        col = Column(
            table_id=table_id,
            name="Email",
            type=ColumnType.WATERFALL,
            position=next_pos,
            config={
                "prompt": f"Find email for /{contact_ref}/ at /{company_col.name}/",
                "sources": ["email_pattern", "ai_agent"],
            },
        )
        db.add(col)
        await db.flush()
        created.append("Email")

    await db.commit()
    return {"created": created, "message": f"Added {len(created)} enrichment column(s)" if created else "Enrichment columns already exist"}


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


@router.post("/email-correct")
async def correct_email(body: dict, db: AsyncSession = Depends(get_db)):
    """User corrects an email — stores ground truth and learns the pattern.

    This is the feedback loop: one correction teaches Scrpr the company's
    email format, improving accuracy for all future lookups at that company.
    """
    email = body.get("email", "")
    person_name = body.get("person_name", "")
    company = body.get("company", "")
    cell_id = body.get("cell_id", "")

    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Invalid email")

    # Store in cache as user-verified ground truth
    cache = EmailCacheService()
    await cache.store(
        person_name=person_name,
        company=company,
        email=email,
        source="user_correction",
        confidence=1.0,
        verified=True,
    )

    # Update the cell if provided
    if cell_id:
        cell = await db.get(Cell, uuid.UUID(cell_id))
        if cell:
            cell.value = email
            cell.status = CellStatus.FOUND
            await db.commit()

    # Learn: analyze what pattern this email uses
    domain = email.split("@")[1]
    local = email.split("@")[0]
    pattern = "unknown"
    if "." in local:
        parts = local.split(".")
        if len(parts) == 2:
            pattern = "first.last" if len(parts[0]) > 1 else "f.last"
    elif "_" in local:
        pattern = "first_last"
    else:
        pattern = "firstlast"

    return {
        "stored": True,
        "email": email,
        "domain": domain,
        "detected_pattern": pattern,
        "message": f"Correction stored. Pattern '{pattern}' learned for {domain}.",
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
