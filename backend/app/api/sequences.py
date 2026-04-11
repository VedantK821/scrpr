"""API endpoints for email drip sequences."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.column import Column
from app.models.row import Row
from app.models.sequence import (
    EmailEvent, EmailEventType,
    EnrollmentStatus,
    Sequence, SequenceEnrollment, SequenceStatus, SequenceStep,
)

router = APIRouter()


# ── Request / Response models ──────────────────────────────────────────────────

class CreateSequenceRequest(BaseModel):
    name: str
    table_id: str
    send_window_start: int = 9
    send_window_end: int = 18
    max_per_hour: int = 10
    max_per_day: int = 50
    timezone: str = "Asia/Kolkata"
    min_confidence: float = 0.5


class AddStepRequest(BaseModel):
    step_number: int
    delay_days: int = 0
    delay_jitter_hours: int = 4
    subject_template: str
    body_template: str


class EnrollRequest(BaseModel):
    row_ids: list[str] | None = None  # If None, enroll all rows with a valid email
    email_column_name: str = "Email"


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/sequences")
async def create_sequence(
    body: CreateSequenceRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a new drip sequence."""
    seq = Sequence(
        name=body.name,
        table_id=uuid.UUID(body.table_id),
        send_window_start=body.send_window_start,
        send_window_end=body.send_window_end,
        max_per_hour=body.max_per_hour,
        max_per_day=body.max_per_day,
        timezone=body.timezone,
        min_confidence=body.min_confidence,
    )
    db.add(seq)
    await db.commit()
    await db.refresh(seq)
    return {"id": str(seq.id), "name": seq.name, "status": seq.status}


@router.get("/sequences")
async def list_sequences(db: AsyncSession = Depends(get_db)):
    """List all sequences ordered newest first."""
    result = await db.execute(
        select(Sequence).order_by(Sequence.created_at.desc())
    )
    seqs = result.scalars().all()
    return [
        {
            "id": str(s.id),
            "name": s.name,
            "table_id": str(s.table_id),
            "status": s.status,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in seqs
    ]


@router.get("/sequences/{sequence_id}")
async def get_sequence(sequence_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Get a sequence with its steps and enrollment stats."""
    result = await db.execute(
        select(Sequence)
        .where(Sequence.id == sequence_id)
        .options(
            selectinload(Sequence.steps),
            selectinload(Sequence.enrollments),
        )
    )
    seq = result.scalar_one_or_none()
    if not seq:
        raise HTTPException(status_code=404, detail="Sequence not found")

    active = sum(1 for e in seq.enrollments if e.status == EnrollmentStatus.ACTIVE)
    replied = sum(1 for e in seq.enrollments if e.status == EnrollmentStatus.REPLIED)
    bounced = sum(1 for e in seq.enrollments if e.status == EnrollmentStatus.BOUNCED)
    completed = sum(1 for e in seq.enrollments if e.status == EnrollmentStatus.COMPLETED)

    return {
        "id": str(seq.id),
        "name": seq.name,
        "table_id": str(seq.table_id),
        "status": seq.status,
        "send_window_start": seq.send_window_start,
        "send_window_end": seq.send_window_end,
        "max_per_hour": seq.max_per_hour,
        "max_per_day": seq.max_per_day,
        "timezone": seq.timezone,
        "min_confidence": seq.min_confidence,
        "steps": [
            {
                "id": str(s.id),
                "step_number": s.step_number,
                "delay_days": s.delay_days,
                "delay_jitter_hours": s.delay_jitter_hours,
                "subject_template": s.subject_template,
                "body_template": s.body_template,
            }
            for s in sorted(seq.steps, key=lambda s: s.step_number)
        ],
        "stats": {
            "total": len(seq.enrollments),
            "active": active,
            "replied": replied,
            "bounced": bounced,
            "completed": completed,
        },
    }


@router.post("/sequences/{sequence_id}/steps")
async def add_step(
    sequence_id: uuid.UUID,
    body: AddStepRequest,
    db: AsyncSession = Depends(get_db),
):
    """Add a step to a sequence."""
    seq = await db.get(Sequence, sequence_id)
    if not seq:
        raise HTTPException(status_code=404, detail="Sequence not found")

    step = SequenceStep(
        sequence_id=sequence_id,
        step_number=body.step_number,
        delay_days=body.delay_days,
        delay_jitter_hours=body.delay_jitter_hours,
        subject_template=body.subject_template,
        body_template=body.body_template,
    )
    db.add(step)
    await db.commit()
    await db.refresh(step)
    return {"id": str(step.id), "step_number": step.step_number}


@router.post("/sequences/{sequence_id}/enroll")
async def enroll_rows(
    sequence_id: uuid.UUID,
    body: EnrollRequest,
    db: AsyncSession = Depends(get_db),
):
    """Enroll rows in a sequence, pulling email from the named column."""
    seq_result = await db.execute(
        select(Sequence)
        .where(Sequence.id == sequence_id)
        .options(selectinload(Sequence.steps))
    )
    sequence = seq_result.scalar_one_or_none()
    if not sequence:
        raise HTTPException(status_code=404, detail="Sequence not found")
    if not sequence.steps:
        raise HTTPException(status_code=400, detail="Sequence has no steps — add at least one step first")

    # Resolve the email column
    col_result = await db.execute(
        select(Column).where(
            Column.table_id == sequence.table_id,
            Column.name == body.email_column_name,
        )
    )
    email_col = col_result.scalar_one_or_none()
    if not email_col:
        raise HTTPException(
            status_code=400,
            detail=f"Column '{body.email_column_name}' not found in this table",
        )

    # Fetch target rows
    row_query = (
        select(Row)
        .where(Row.table_id == sequence.table_id)
        .options(selectinload(Row.cells))
    )
    if body.row_ids:
        row_query = row_query.where(Row.id.in_([uuid.UUID(rid) for rid in body.row_ids]))
    row_result = await db.execute(row_query)
    rows = row_result.scalars().all()

    # Collect already-enrolled emails to prevent duplicates
    existing_result = await db.execute(
        select(SequenceEnrollment.email).where(
            SequenceEnrollment.sequence_id == sequence_id,
            SequenceEnrollment.status.in_([EnrollmentStatus.ACTIVE, EnrollmentStatus.COMPLETED]),
        )
    )
    enrolled_emails: set[str] = {r[0] for r in existing_result.fetchall()}

    now = datetime.now(timezone.utc)
    enrolled = 0
    skipped = 0

    for row in rows:
        email_cell = next((c for c in row.cells if c.column_id == email_col.id), None)
        if not email_cell or not email_cell.value or "@" not in email_cell.value:
            skipped += 1
            continue

        email_addr = email_cell.value.strip()

        if email_addr in enrolled_emails:
            skipped += 1
            continue

        enrollment = SequenceEnrollment(
            sequence_id=sequence_id,
            row_id=row.id,
            email=email_addr,
            current_step=1,
            next_send_at=now,  # First email eligible immediately (subject to send window)
        )
        db.add(enrollment)
        enrolled_emails.add(email_addr)
        enrolled += 1

    await db.commit()
    return {"enrolled": enrolled, "skipped": skipped}


@router.post("/sequences/{sequence_id}/activate")
async def activate_sequence(sequence_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Set sequence to active — processor will start sending."""
    seq = await db.get(Sequence, sequence_id)
    if not seq:
        raise HTTPException(status_code=404, detail="Sequence not found")
    seq.status = SequenceStatus.ACTIVE
    await db.commit()
    return {"status": seq.status}


@router.post("/sequences/{sequence_id}/pause")
async def pause_sequence(sequence_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Pause a sequence — no emails will be sent until resumed."""
    seq = await db.get(Sequence, sequence_id)
    if not seq:
        raise HTTPException(status_code=404, detail="Sequence not found")
    seq.status = SequenceStatus.PAUSED
    await db.commit()
    return {"status": seq.status}


@router.post("/sequences/{sequence_id}/resume")
async def resume_sequence(sequence_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Resume a paused sequence."""
    seq = await db.get(Sequence, sequence_id)
    if not seq:
        raise HTTPException(status_code=404, detail="Sequence not found")
    seq.status = SequenceStatus.ACTIVE
    await db.commit()
    return {"status": seq.status}


@router.get("/sequences/{sequence_id}/events")
async def get_events(sequence_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Get the 100 most recent email events for a sequence."""
    result = await db.execute(
        select(EmailEvent)
        .join(SequenceEnrollment)
        .where(SequenceEnrollment.sequence_id == sequence_id)
        .order_by(EmailEvent.created_at.desc())
        .limit(100)
    )
    events = result.scalars().all()
    return [
        {
            "id": str(e.id),
            "enrollment_id": str(e.enrollment_id),
            "step_number": e.step_number,
            "event_type": e.event_type,
            "message_id": e.message_id,
            "smtp_response": e.smtp_response,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in events
    ]


@router.post("/settings/imap/test")
async def test_imap():
    """Test IMAP connection with current settings."""
    from app.services.imap_service import IMAPService
    service = IMAPService()
    return await service.test_connection()
