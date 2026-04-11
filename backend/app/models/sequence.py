import uuid
from datetime import datetime
from enum import StrEnum
from sqlalchemy import Text, ForeignKey, DateTime, Integer, Float, String, JSON
from sqlalchemy import Enum as SAEnum, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class SequenceStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"


class EnrollmentStatus(StrEnum):
    ACTIVE = "active"
    REPLIED = "replied"
    BOUNCED = "bounced"
    UNSUBSCRIBED = "unsubscribed"
    COMPLETED = "completed"
    PAUSED = "paused"
    ERROR = "error"


class EmailEventType(StrEnum):
    SENT = "sent"
    BOUNCED = "bounced"
    REPLIED = "replied"
    ERROR = "error"


class Sequence(Base):
    __tablename__ = "sequences"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    table_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tables.id", ondelete="CASCADE"))

    status: Mapped[SequenceStatus] = mapped_column(
        SAEnum(SequenceStatus, name="sequencestatus"), nullable=False, default=SequenceStatus.DRAFT
    )

    # Send window (business hours)
    send_window_start: Mapped[int] = mapped_column(Integer, nullable=False, default=9)  # 9 AM
    send_window_end: Mapped[int] = mapped_column(Integer, nullable=False, default=18)  # 6 PM

    # Rate limits
    max_per_hour: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    max_per_day: Mapped[int] = mapped_column(Integer, nullable=False, default=50)

    # Timezone for send window
    timezone: Mapped[str] = mapped_column(String(50), nullable=False, default="Asia/Kolkata")

    # Minimum email confidence to auto-enroll
    min_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    table: Mapped["Table"] = relationship()
    steps: Mapped[list["SequenceStep"]] = relationship(
        back_populates="sequence", cascade="all, delete-orphan", order_by="SequenceStep.step_number"
    )
    enrollments: Mapped[list["SequenceEnrollment"]] = relationship(
        back_populates="sequence", cascade="all, delete-orphan"
    )


class SequenceStep(Base):
    __tablename__ = "sequence_steps"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sequence_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("sequences.id", ondelete="CASCADE"))

    step_number: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-indexed
    delay_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # Days after previous step
    delay_jitter_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=4)  # ± randomization

    subject_template: Mapped[str] = mapped_column(Text, nullable=False)
    body_template: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    sequence: Mapped["Sequence"] = relationship(back_populates="steps")


class SequenceEnrollment(Base):
    __tablename__ = "sequence_enrollments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sequence_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("sequences.id", ondelete="CASCADE"))
    row_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("rows.id", ondelete="CASCADE"))

    email: Mapped[str] = mapped_column(String(320), nullable=False)  # RFC 5321 max email length
    current_step: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    status: Mapped[EnrollmentStatus] = mapped_column(
        SAEnum(EnrollmentStatus, name="enrollmentstatus"), nullable=False, default=EnrollmentStatus.ACTIVE
    )

    enrolled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_send_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    bounce_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reply_detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    sequence: Mapped["Sequence"] = relationship(back_populates="enrollments")
    row: Mapped["Row"] = relationship()
    events: Mapped[list["EmailEvent"]] = relationship(
        back_populates="enrollment", cascade="all, delete-orphan", order_by="EmailEvent.created_at"
    )


class EmailEvent(Base):
    __tablename__ = "email_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enrollment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sequence_enrollments.id", ondelete="CASCADE")
    )

    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[EmailEventType] = mapped_column(
        SAEnum(EmailEventType, name="emaileventtype"), nullable=False
    )

    message_id: Mapped[str | None] = mapped_column(String(500), nullable=True)  # SMTP Message-ID for reply matching
    smtp_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    enrollment: Mapped["SequenceEnrollment"] = relationship(back_populates="events")
