from fastapi import APIRouter
from app.api import tables, columns, rows, cells

api_router = APIRouter()

api_router.include_router(tables.router)
api_router.include_router(columns.router)
api_router.include_router(rows.router)
api_router.include_router(cells.router)
