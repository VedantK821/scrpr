import uuid
from datetime import datetime
from pydantic import BaseModel
from app.models.job import JobStatus


class JobResponse(BaseModel):
    id: uuid.UUID
    table_id: uuid.UUID
    column_id: uuid.UUID
    row_id: uuid.UUID
    status: JobStatus
    retries: int
    error: str | None
    result: dict | None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}
