import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.table import Table
from app.models.column import Column
from app.schemas.column import ColumnCreate, ColumnUpdate, ColumnResponse

router = APIRouter(prefix="/tables/{table_id}/columns", tags=["columns"])


async def _get_table_or_404(table_id: uuid.UUID, db: AsyncSession) -> Table:
    result = await db.execute(select(Table).where(Table.id == table_id))
    table = result.scalar_one_or_none()
    if not table:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Table not found")
    return table


@router.post("", response_model=ColumnResponse, status_code=status.HTTP_201_CREATED)
async def create_column(
    table_id: uuid.UUID,
    payload: ColumnCreate,
    db: AsyncSession = Depends(get_db),
):
    await _get_table_or_404(table_id, db)
    column = Column(
        table_id=table_id,
        name=payload.name,
        type=payload.type,
        position=payload.position,
        config=payload.config,
    )
    db.add(column)
    await db.commit()
    await db.refresh(column)
    return column


@router.get("", response_model=list[ColumnResponse])
async def list_columns(table_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    await _get_table_or_404(table_id, db)
    result = await db.execute(
        select(Column).where(Column.table_id == table_id).order_by(Column.position)
    )
    return result.scalars().all()


@router.get("/{column_id}", response_model=ColumnResponse)
async def get_column(table_id: uuid.UUID, column_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Column).where(Column.table_id == table_id, Column.id == column_id)
    )
    column = result.scalar_one_or_none()
    if not column:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Column not found")
    return column


@router.patch("/{column_id}", response_model=ColumnResponse)
async def update_column(
    table_id: uuid.UUID,
    column_id: uuid.UUID,
    payload: ColumnUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Column).where(Column.table_id == table_id, Column.id == column_id)
    )
    column = result.scalar_one_or_none()
    if not column:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Column not found")
    if payload.name is not None:
        column.name = payload.name
    if payload.type is not None:
        column.type = payload.type
    if payload.position is not None:
        column.position = payload.position
    if payload.config is not None:
        column.config = payload.config
    await db.commit()
    await db.refresh(column)
    return column


@router.delete("/{column_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_column(
    table_id: uuid.UUID,
    column_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Column).where(Column.table_id == table_id, Column.id == column_id)
    )
    column = result.scalar_one_or_none()
    if not column:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Column not found")
    await db.delete(column)
    await db.commit()
