import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.table import Table
from app.models.column import Column, ColumnType
from app.models.row import Row
from app.models.cell import Cell, CellStatus
from app.services.list_builder import ListBuilder

router = APIRouter()


class FindRequest(BaseModel):
    criteria: str  # "Top 100 MNCs in India that hire from campus"
    target_count: int = 25
    entity_type: str = "companies"  # "companies" or "people"
    table_name: str | None = None  # Optional — auto-generates if not provided


class FindResponse(BaseModel):
    table_id: str
    table_name: str
    entities_found: int
    fields: list[str]


@router.post("/find", response_model=FindResponse)
async def find_and_create_table(body: FindRequest, db: AsyncSession = Depends(get_db)):
    """AI-powered list building. Describe what you want, get a populated table."""

    builder = ListBuilder()

    # Build the list
    result = await builder.build_list(
        criteria=body.criteria,
        target_count=body.target_count,
        entity_type=body.entity_type,
    )

    entities = result["entities"]
    if not entities:
        raise HTTPException(status_code=404, detail="Could not find any matching entities. Try different criteria.")

    fields = result["fields"]

    # Create table
    table_name = body.table_name or f"{body.entity_type.title()}: {body.criteria[:50]}"
    table = Table(name=table_name)
    db.add(table)
    await db.flush()

    # Create columns from the entity fields
    columns = {}
    for i, field_name in enumerate(fields):
        col = Column(
            table_id=table.id,
            name=field_name.replace("_", " ").title(),
            type=ColumnType.TEXT,
            position=i,
        )
        db.add(col)
        await db.flush()
        columns[field_name] = col

    # Create rows from entities
    for entity in entities:
        row = Row(table_id=table.id)
        db.add(row)
        await db.flush()

        for field_name, col in columns.items():
            value = entity.get(field_name)
            if value:
                cell = Cell(
                    row_id=row.id,
                    column_id=col.id,
                    value=str(value),
                    status=CellStatus.FOUND,
                )
                db.add(cell)

    await db.commit()

    return FindResponse(
        table_id=str(table.id),
        table_name=table_name,
        entities_found=len(entities),
        fields=fields,
    )
