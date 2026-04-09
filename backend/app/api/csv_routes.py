import csv
import io
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.table import Table
from app.models.column import Column, ColumnType
from app.models.row import Row
from app.models.cell import Cell, CellStatus

router = APIRouter()


@router.post("/tables/{table_id}/import-csv")
async def import_csv(table_id: uuid.UUID, file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    """Import a CSV file into an existing table. Creates columns if they don't exist."""
    table = await db.get(Table, table_id)
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")

    content = await file.read()
    text = content.decode("utf-8-sig")  # Handle BOM
    reader = csv.DictReader(io.StringIO(text))

    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV has no headers")

    # Get or create columns
    existing_cols = await db.execute(select(Column).where(Column.table_id == table_id))
    col_map = {c.name.lower(): c for c in existing_cols.scalars().all()}

    columns_by_header = {}
    for i, header in enumerate(reader.fieldnames):
        header = header.strip()
        if header.lower() in col_map:
            columns_by_header[header] = col_map[header.lower()]
        else:
            col = Column(table_id=table_id, name=header, type=ColumnType.TEXT, position=len(col_map) + i)
            db.add(col)
            await db.flush()
            columns_by_header[header] = col

    # Import rows
    rows_created = 0
    for csv_row in reader:
        row = Row(table_id=table_id)
        db.add(row)
        await db.flush()

        for header, value in csv_row.items():
            if header.strip() in columns_by_header and value:
                cell = Cell(
                    row_id=row.id,
                    column_id=columns_by_header[header.strip()].id,
                    value=value.strip(),
                    status=CellStatus.FOUND,
                )
                db.add(cell)
        rows_created += 1

    await db.commit()
    return {"rows_imported": rows_created, "columns": len(columns_by_header)}


@router.get("/tables/{table_id}/export-csv")
async def export_csv(table_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Export table data as CSV."""
    from fastapi.responses import StreamingResponse

    # Get columns
    col_result = await db.execute(
        select(Column).where(Column.table_id == table_id).order_by(Column.position)
    )
    columns = col_result.scalars().all()

    if not columns:
        raise HTTPException(status_code=404, detail="Table has no columns")

    # Get rows with cells
    row_result = await db.execute(
        select(Row).where(Row.table_id == table_id).options(selectinload(Row.cells)).order_by(Row.created_at)
    )
    rows = row_result.scalars().all()

    # Build CSV
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([c.name for c in columns])

    # Data rows
    for row in rows:
        cell_map = {str(cell.column_id): cell.value or "" for cell in row.cells}
        writer.writerow([cell_map.get(str(c.id), "") for c in columns])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=scrpr-export-{table_id}.csv"},
    )
