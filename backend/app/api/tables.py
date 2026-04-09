import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.table import Table
from app.schemas.table import TableCreate, TableUpdate, TableResponse, TableListResponse

router = APIRouter(prefix="/tables", tags=["tables"])


@router.post("", response_model=TableResponse, status_code=status.HTTP_201_CREATED)
async def create_table(payload: TableCreate, db: AsyncSession = Depends(get_db)):
    table = Table(name=payload.name)
    db.add(table)
    await db.commit()
    await db.refresh(table)
    return table


@router.get("", response_model=TableListResponse)
async def list_tables(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Table).order_by(Table.created_at.desc()))
    tables = result.scalars().all()
    return TableListResponse(items=list(tables), total=len(tables))


@router.get("/{table_id}", response_model=TableResponse)
async def get_table(table_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Table).where(Table.id == table_id))
    table = result.scalar_one_or_none()
    if not table:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Table not found")
    return table


@router.patch("/{table_id}", response_model=TableResponse)
async def update_table(table_id: uuid.UUID, payload: TableUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Table).where(Table.id == table_id))
    table = result.scalar_one_or_none()
    if not table:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Table not found")
    if payload.name is not None:
        table.name = payload.name
    await db.commit()
    await db.refresh(table)
    return table


@router.delete("/{table_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_table(table_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Table).where(Table.id == table_id))
    table = result.scalar_one_or_none()
    if not table:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Table not found")
    await db.delete(table)
    await db.commit()
