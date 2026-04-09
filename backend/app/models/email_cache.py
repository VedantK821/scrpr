import uuid
from datetime import datetime
from sqlalchemy import String, Float, DateTime, Index, func
import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class EmailCache(Base):
    __tablename__ = "email_cache"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    person_name: Mapped[str] = mapped_column(String(255), nullable=False)
    company: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    verified: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False)  # "smtp_verified", "hunter", "apollo", "linkedin", "web_scrape"
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    extra_data: Mapped[dict | None] = mapped_column(sa.JSON, nullable=True)  # title, linkedin_url, etc.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_email_cache_lookup", "person_name", "company"),
        Index("ix_email_cache_email", "email"),
        Index("ix_email_cache_domain", "domain"),
    )
