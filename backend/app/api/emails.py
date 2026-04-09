import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.email_draft import EmailDraft, EmailStatus, PersonalizationLevel
from app.models.table import Table
from app.models.row import Row
from app.models.column import Column
from app.models.cell import Cell
from app.services.email_composer import EmailComposer
from app.services.email_sender import EmailSender

router = APIRouter()


class ComposeRequest(BaseModel):
    table_id: str
    subject_template: str
    body_template: str
    personalization_level: str = "light"  # light, medium, max
    ai_instructions: str | None = None
    row_ids: list[str] | None = None  # If None, compose for all rows


class EmailDraftResponse(BaseModel):
    id: str
    row_id: str
    to_email: str
    subject: str
    body: str
    personalization_level: str
    confidence: float | None
    status: str

    model_config = {"from_attributes": True}


class SendRequest(BaseModel):
    draft_ids: list[str]
    delay_seconds: float = 30.0


@router.post("/emails/compose", response_model=list[EmailDraftResponse])
async def compose_emails(body: ComposeRequest, db: AsyncSession = Depends(get_db)):
    """Generate personalized email drafts for rows in a table."""
    table_id = uuid.UUID(body.table_id)
    level = PersonalizationLevel(body.personalization_level)

    # Get rows with cells
    query = select(Row).where(Row.table_id == table_id).options(selectinload(Row.cells))
    if body.row_ids:
        row_uuids = [uuid.UUID(rid) for rid in body.row_ids]
        query = query.where(Row.id.in_(row_uuids))
    result = await db.execute(query)
    rows = result.scalars().all()

    if not rows:
        raise HTTPException(status_code=404, detail="No rows found")

    # Get column names for variable substitution
    col_result = await db.execute(select(Column).where(Column.table_id == table_id))
    columns = {str(c.id): c.name for c in col_result.scalars().all()}

    composer = EmailComposer()
    drafts = []

    for row in rows:
        # Build row_data dict (column_name -> value)
        row_data = {}
        to_email = ""
        for cell in row.cells:
            col_name = columns.get(str(cell.column_id), "")
            if cell.value:
                row_data[col_name] = cell.value
                # Auto-detect email column
                if "@" in (cell.value or "") and "." in (cell.value or ""):
                    to_email = cell.value

        if not to_email:
            continue  # Skip rows without an email

        # Personalize
        personalized = await composer.personalize(
            body.subject_template, body.body_template, row_data, level
        )

        draft = EmailDraft(
            table_id=table_id,
            row_id=row.id,
            to_email=to_email,
            subject_template=body.subject_template,
            subject_personalized=personalized["subject"],
            body_template=body.body_template,
            body_personalized=personalized["body"],
            personalization_level=level,
            confidence=personalized.get("confidence"),
            status=EmailStatus.PERSONALIZED,
        )
        db.add(draft)
        drafts.append(draft)

    await db.commit()

    return [
        EmailDraftResponse(
            id=str(d.id), row_id=str(d.row_id), to_email=d.to_email,
            subject=d.subject_personalized or d.subject_template,
            body=d.body_personalized or d.body_template,
            personalization_level=d.personalization_level,
            confidence=d.confidence, status=d.status,
        )
        for d in drafts
    ]


@router.get("/emails/drafts/{table_id}", response_model=list[EmailDraftResponse])
async def list_drafts(table_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """List all email drafts for a table."""
    result = await db.execute(
        select(EmailDraft).where(EmailDraft.table_id == table_id).order_by(EmailDraft.created_at)
    )
    drafts = result.scalars().all()
    return [
        EmailDraftResponse(
            id=str(d.id), row_id=str(d.row_id), to_email=d.to_email,
            subject=d.subject_personalized or d.subject_template,
            body=d.body_personalized or d.body_template,
            personalization_level=d.personalization_level,
            confidence=d.confidence, status=d.status,
        )
        for d in drafts
    ]


@router.patch("/emails/drafts/{draft_id}")
async def update_draft(draft_id: uuid.UUID, body: dict, db: AsyncSession = Depends(get_db)):
    """Update a draft (edit subject/body, skip, etc.)."""
    draft = await db.get(EmailDraft, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    if "subject" in body:
        draft.subject_personalized = body["subject"]
    if "body" in body:
        draft.body_personalized = body["body"]
    if "status" in body:
        draft.status = EmailStatus(body["status"])
    await db.commit()
    return {"ok": True}


@router.post("/emails/send")
async def send_emails(body: SendRequest, db: AsyncSession = Depends(get_db)):
    """Send selected email drafts via SMTP."""
    sender = EmailSender(delay_seconds=body.delay_seconds)
    results = []

    for draft_id_str in body.draft_ids:
        draft = await db.get(EmailDraft, uuid.UUID(draft_id_str))
        if not draft or draft.status == EmailStatus.SKIPPED:
            continue

        send_result = await sender.send(
            to=draft.to_email,
            subject=draft.subject_personalized or draft.subject_template,
            body=draft.body_personalized or draft.body_template,
        )

        if send_result.success:
            draft.status = EmailStatus.SENT
            draft.sent_at = datetime.now()
        else:
            draft.status = EmailStatus.FAILED if "bounced" not in send_result.error.lower() else EmailStatus.BOUNCED
            draft.error = send_result.error

        await db.commit()
        results.append({"draft_id": draft_id_str, "success": send_result.success, "error": send_result.error})

    return {"sent": len([r for r in results if r["success"]]), "failed": len([r for r in results if not r["success"]]), "results": results}


@router.post("/emails/test-send")
async def test_send(body: dict, db: AsyncSession = Depends(get_db)):
    """Send a test email to yourself."""
    sender = EmailSender()
    result = await sender.send(
        to=body.get("to", ""),
        subject=body.get("subject", "Scrpr Test Email"),
        body=body.get("body", "This is a test email from Scrpr."),
    )
    return {"success": result.success, "error": result.error}
