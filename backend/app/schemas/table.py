import uuid
from datetime import datetime
from pydantic import BaseModel


class TableCreate(BaseModel):
    name: str


class TableUpdate(BaseModel):
    name: str | None = None


class TableResponse(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TableListResponse(BaseModel):
    items: list[TableResponse]
    total: int
