import uuid
from pydantic import BaseModel
from app.models.column import ColumnType


class ColumnCreate(BaseModel):
    name: str
    type: ColumnType = ColumnType.TEXT
    position: int = 0
    config: dict | None = None


class ColumnUpdate(BaseModel):
    name: str | None = None
    type: ColumnType | None = None
    position: int | None = None
    config: dict | None = None


class ColumnResponse(BaseModel):
    id: uuid.UUID
    table_id: uuid.UUID
    name: str
    type: ColumnType
    position: int
    config: dict | None

    model_config = {"from_attributes": True}
