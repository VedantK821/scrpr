import uuid
from datetime import datetime
from pydantic import BaseModel
from app.models.cell import CellStatus


class CellUpdate(BaseModel):
    value: str | None = None
    status: CellStatus | None = None


class CellResponse(BaseModel):
    id: uuid.UUID
    row_id: uuid.UUID
    column_id: uuid.UUID
    value: str | None
    status: CellStatus
    updated_at: datetime

    model_config = {"from_attributes": True}


class CellBulkUpdate(BaseModel):
    cells: list[CellUpdate]
