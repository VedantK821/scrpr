import uuid
from datetime import datetime
from sqlalchemy import String, Text, Float, ForeignKey, DateTime, func
from sqlalchemy import Uuid, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class EnrichmentResult(Base):
    __tablename__ = "enrichment_results"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cell_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("cells.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    raw_response: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    extracted_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    cell: Mapped["Cell"] = relationship(back_populates="enrichment_results")
