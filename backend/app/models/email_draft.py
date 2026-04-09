import uuid
from datetime import datetime
from enum import StrEnum
from sqlalchemy import String, Text, Float, DateTime, Enum as SAEnum, func
from sqlalchemy import Uuid, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class PersonalizationLevel(StrEnum):
    LIGHT = "light"      # Template variable substitution only
    MEDIUM = "medium"    # AI rewrites 1-2 sentences
    MAX = "max"          # AI rewrites entire email


class EmailStatus(StrEnum):
    DRAFT = "draft"
    PERSONALIZED = "personalized"
    PREVIEWED = "previewed"
    SENT = "sent"
    BOUNCED = "bounced"
    SKIPPED = "skipped"
    FAILED = "failed"


class EmailDraft(Base):
    __tablename__ = "email_drafts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    table_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tables.id", ondelete="CASCADE"))
    row_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("rows.id", ondelete="CASCADE"))
    to_email: Mapped[str] = mapped_column(String(255), nullable=False)
    subject_template: Mapped[str] = mapped_column(Text, nullable=False)
    subject_personalized: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_template: Mapped[str] = mapped_column(Text, nullable=False)
    body_personalized: Mapped[str | None] = mapped_column(Text, nullable=True)
    personalization_level: Mapped[PersonalizationLevel] = mapped_column(
        SAEnum(PersonalizationLevel, name="personalizationlevel"), default=PersonalizationLevel.LIGHT
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[EmailStatus] = mapped_column(
        SAEnum(EmailStatus, name="emailstatus"), default=EmailStatus.DRAFT
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
