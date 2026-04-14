import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import update
from app.api.router import api_router
from app.config import settings
from app.database import engine, Base, async_session
from app.models import *  # noqa: F401,F403 — register models with Base
from app.models.cell import Cell, CellStatus

# ── Logging setup ────────────────────────────────────────────────────
LOG_DIR = os.path.expanduser("~/.scrpr/logs")
os.makedirs(LOG_DIR, exist_ok=True)

_fmt = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s", datefmt="%H:%M:%S")

# Root logger — file + console
_root = logging.getLogger()
_root.setLevel(logging.INFO)
_fh = logging.FileHandler(os.path.join(LOG_DIR, "scrpr.log"), encoding="utf-8")
_fh.setFormatter(_fmt)
_root.addHandler(_fh)

# Enrichment-specific log — everything the pipeline does
_elog = logging.getLogger("enrichment")
_elog.setLevel(logging.DEBUG)
_efh = logging.FileHandler(os.path.join(LOG_DIR, "enrichment.log"), encoding="utf-8")
_efh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s", datefmt="%H:%M:%S"))
_elog.addHandler(_efh)

# Quiet noisy libs
for _lib in ("httpx", "httpcore", "urllib3", "watchfiles", "asyncio"):
    logging.getLogger(_lib).setLevel(logging.WARNING)

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
