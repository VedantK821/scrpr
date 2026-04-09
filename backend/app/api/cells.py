import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.cell import Cell
from app.schemas.cell import CellUpdate, CellResponse

router = APIRouter(prefix="/cells", tags=["cells"])


@router.get("/{cell_id}", response_model=CellResponse)
async def get_cell(cell_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Cell).where(Cell.id == cell_id))
    cell = result.scalar_one_or_none()
    if not cell:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cell not found")
    return cell


@router.patch("/{cell_id}", response_model=CellResponse)
async def update_cell(
    cell_id: uuid.UUID,
    payload: CellUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Cell).where(Cell.id == cell_id))
    cell = result.scalar_one_or_none()
    if not cell:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cell not found")
    if payload.value is not None:
        cell.value = payload.value
    if payload.status is not None:
        cell.status = payload.status
    await db.commit()
    await db.refresh(cell)
    return cell
