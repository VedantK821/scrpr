import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import update
from app.api.router import api_router
from app.config import settings
from app.database import engine, Base, async_session
from app.models import *  # noqa: F401,F403 — register models with Base
from app.models.cell import Cell, CellStatus

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Reset any cells stuck in "running" from a previous crash
    async with async_session() as db:
        result = await db.execute(
            update(Cell)
            .where(Cell.status == CellStatus.RUNNING)
            .values(status=CellStatus.PENDING)
        )
        if result.rowcount > 0:
            await db.commit()
            logger.info(f"Reset {result.rowcount} stuck 'running' cells to 'pending'")

    yield


app = FastAPI(title="Scrpr", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok"}
