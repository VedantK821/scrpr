import uuid
from datetime import datetime
from enum import StrEnum
from sqlalchemy import Text, ForeignKey, DateTime, Enum as SAEnum, func
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class CellStatus(StrEnum):
    EMPTY = "empty"
    PENDING = "pending"
    RUNNING = "running"
    FOUND = "found"
    NOT_FOUND = "not_found"
    ERROR = "error"
    REVIEW = "review"


class Cell(Base):
    __tablename__ = "cells"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    row_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("rows.id", ondelete="CASCADE"))
    column_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("columns.id", ondelete="CASCADE"))
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[CellStatus] = mapped_column(SAEnum(CellStatus, name="cellstatus"), nullable=False, default=CellStatus.EMPTY)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    row: Mapped["Row"] = relationship(back_populates="cells")
    column: Mapped["Column"] = relationship(back_populates="cells")
    enrichment_results: Mapped[list["EnrichmentResult"]] = relationship(back_populates="cell", cascade="all, delete-orphan")
