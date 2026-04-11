"""Table expand API — create linked tables with N rows per source row."""
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.table import Table
from app.models.column import Column, ColumnType
from app.models.row import Row
from app.models.cell import Cell

router = APIRouter()


class ExpandRequest(BaseModel):
    name: str  # New table name (e.g., "TCS Contacts")
    source_column: str  # Column to carry over (e.g., "Company")
    count_per_row: int = 3  # How many rows per source row
    add_enrichment: bool = True  # Auto-add Key Contact + Email columns


@router.post("/tables/{table_id}/expand")
async def expand_table(
    table_id: uuid.UUID,
    body: ExpandRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a new table with N rows per row in the source table.

    Example: Source has 10 companies, count_per_row=3 → new table has 30 rows.
    Each row carries the source column value (e.g., company name).
    Optionally adds Key Contact and Email enrichment columns.
    """
    # Validate source table
    source_table = await db.get(Table, table_id)
    if not source_table:
        raise HTTPException(status_code=404, detail="Source table not found")

    # Find source column
    col_result = await db.execute(
        select(Column).where(Column.table_id == table_id, Column.name == body.source_column)
    )
    source_col = col_result.scalar_one_or_none()
    if not source_col:
        raise HTTPException(status_code=400, detail=f"Column '{body.source_column}' not found")

    # Get source rows with cells
    row_result = await db.execute(
        select(Row).where(Row.table_id == table_id).options(selectinload(Row.cells))
    )
    source_rows = row_result.scalars().all()
    if not source_rows:
        raise HTTPException(status_code=400, detail="Source table has no rows")

    # Create target table
    target_table = Table(name=body.name)
    db.add(target_table)
    await db.flush()

    # Create columns in target table
    pos = 0

    # Source column (carried over)
    target_source_col = Column(
        table_id=target_table.id,
        name=body.source_column,
        type=ColumnType.TEXT,
        position=pos,
    )
    db.add(target_source_col)
    await db.flush()
    pos += 1

    # Contact number column
    contact_num_col = Column(
        table_id=target_table.id,
        name="Contact #",
        type=ColumnType.TEXT,
        position=pos,
    )
    db.add(contact_num_col)
    await db.flush()
    pos += 1

    # Optional enrichment columns
    if body.add_enrichment:
        key_contact_col = Column(
            table_id=target_table.id,
            name="Key Contact",
            type=ColumnType.AGENT,
            position=pos,
            config={
                "prompt": (
                    f"Find contact person #{{Contact #}} (hiring manager, recruiter, or HR) at"
                    f" /{body.source_column}/. Return their full name, title, and LinkedIn URL."
                    f" If Contact # is 2 or 3, find a DIFFERENT person than Contact #1."
                )
            },
        )
        db.add(key_contact_col)
        await db.flush()
        pos += 1

        email_col = Column(
            table_id=target_table.id,
            name="Email",
            type=ColumnType.WATERFALL,
            position=pos,
            config={
                "prompt": f"Find email for /Key Contact/ at /{body.source_column}/",
                "sources": ["website_email", "email_pattern", "ai_agent"],
            },
        )
        db.add(email_col)
        await db.flush()
        pos += 1

    # Create expanded rows
    rows_created = 0
    for source_row in source_rows:
        # Get source column value
        source_cell = next(
            (c for c in source_row.cells if c.column_id == source_col.id),
            None,
        )
        source_value = source_cell.value if source_cell else ""

        if not source_value:
            continue

        for i in range(1, body.count_per_row + 1):
            row = Row(table_id=target_table.id)
            db.add(row)
            await db.flush()

            # Source column cell
            db.add(Cell(row_id=row.id, column_id=target_source_col.id, value=source_value))

            # Contact number cell
            db.add(Cell(row_id=row.id, column_id=contact_num_col.id, value=str(i)))

            rows_created += 1

    await db.commit()

    return {
        "table_id": str(target_table.id),
        "table_name": body.name,
        "rows_created": rows_created,
        "source_rows": len(source_rows),
        "columns": pos,
    }
