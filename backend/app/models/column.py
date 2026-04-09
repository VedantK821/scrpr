import uuid
from enum import StrEnum
from sqlalchemy import String, Integer, ForeignKey, Enum as SAEnum
from sqlalchemy import Uuid, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class ColumnType(StrEnum):
    TEXT = "text"
    URL = "url"
    CHECKBOX = "checkbox"
    SELECT = "select"
    MULTI_SELECT = "multi_select"
    NUMBER = "number"
    DATE = "date"
    CURRENCY = "currency"
    EMAIL = "email"
    AGENT = "agent"
    WATERFALL = "waterfall"
    FORMULA = "formula"
    HTTP_API = "http_api"


class Column(Base):
    __tablename__ = "columns"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    table_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tables.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[ColumnType] = mapped_column(SAEnum(ColumnType, name="columntype"), nullable=False, default=ColumnType.TEXT)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    table: Mapped["Table"] = relationship(back_populates="columns")
    cells: Mapped[list["Cell"]] = relationship(back_populates="column", cascade="all, delete-orphan")
