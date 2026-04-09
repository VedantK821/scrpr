import uuid
from datetime import datetime
from enum import StrEnum
from sqlalchemy import String, Integer, Text, ForeignKey, DateTime, Enum as SAEnum, func
from sqlalchemy import Uuid, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD = "dead"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    table_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tables.id", ondelete="CASCADE"))
    column_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("columns.id", ondelete="CASCADE"))
    row_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("rows.id", ondelete="CASCADE"))
    status: Mapped[JobStatus] = mapped_column(SAEnum(JobStatus, name="jobstatus"), nullable=False, default=JobStatus.QUEUED)
    retries: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
