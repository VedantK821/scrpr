import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.table import Table
from app.models.column import Column
from app.models.row import Row
from app.models.cell import Cell, CellStatus
from app.schemas.row import RowCreate, RowResponse

router = APIRouter(prefix="/tables/{table_id}/rows", tags=["rows"])


async def _get_table_or_404(table_id: uuid.UUID, db: AsyncSession) -> Table:
    result = await db.execute(select(Table).where(Table.id == table_id))
    table = result.scalar_one_or_none()
    if not table:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Table not found")
    return table


@router.post("", response_model=RowResponse, status_code=status.HTTP_201_CREATED)
async def create_row(
    table_id: uuid.UUID,
    payload: RowCreate,
    db: AsyncSession = Depends(get_db),
):
    await _get_table_or_404(table_id, db)

    row = Row(table_id=table_id)
    db.add(row)
    await db.flush()  # get row.id before creating cells

    # Create cells for provided column values
    if payload.cells:
        for col_id_str, value in payload.cells.items():
            try:
                col_id = uuid.UUID(col_id_str)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid column ID: {col_id_str}",
                )
            col_result = await db.execute(
                select(Column).where(Column.id == col_id, Column.table_id == table_id)
            )
            column = col_result.scalar_one_or_none()
            if not column:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Column {col_id_str} not found in table",
                )
            cell = Cell(
                row_id=row.id,
                column_id=col_id,
                value=value,
                status=CellStatus.FOUND if value else CellStatus.EMPTY,
            )
            db.add(cell)

    await db.commit()

    # Reload with cells
    result = await db.execute(
        select(Row).options(selectinload(Row.cells)).where(Row.id == row.id)
    )
    return result.scalar_one()


@router.get("", response_model=list[RowResponse])
async def list_rows(table_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    await _get_table_or_404(table_id, db)
    result = await db.execute(
        select(Row)
        .options(selectinload(Row.cells))
        .where(Row.table_id == table_id)
        .order_by(Row.created_at)
    )
    return result.scalars().all()


@router.get("/{row_id}", response_model=RowResponse)
async def get_row(table_id: uuid.UUID, row_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Row)
        .options(selectinload(Row.cells))
        .where(Row.table_id == table_id, Row.id == row_id)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Row not found")
    return row


@router.delete("/{row_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_row(table_id: uuid.UUID, row_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Row).where(Row.table_id == table_id, Row.id == row_id)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Row not found")
    await db.delete(row)
    await db.commit()
