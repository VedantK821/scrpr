import uuid
from datetime import datetime
from pydantic import BaseModel
from app.schemas.cell import CellResponse


class RowCreate(BaseModel):
    # column_id -> value mapping for initial cell values
    cells: dict[str, str] | None = None


class RowResponse(BaseModel):
    id: uuid.UUID
    table_id: uuid.UUID
    created_at: datetime
    cells: list[CellResponse] = []

    model_config = {"from_attributes": True}
