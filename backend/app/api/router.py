from fastapi import APIRouter
from app.api import tables, columns, rows, cells, agent
from app.api.ws import router as ws_router
from app.api.enrichments import router as enrichments_router
from app.api.emails import router as emails_router
from app.api.csv_routes import router as csv_router
from app.api.linkedin import router as linkedin_router
from app.api.find import router as find_router
from app.api.sequences import router as sequences_router
from app.api.quality import router as quality_router
from app.api.table_expand import router as expand_router

api_router = APIRouter()

api_router.include_router(tables.router)
api_router.include_router(columns.router)
api_router.include_router(rows.router)
api_router.include_router(cells.router)
api_router.include_router(agent.router)
api_router.include_router(enrichments_router, tags=["enrichments"])
api_router.include_router(ws_router, tags=["websocket"])
api_router.include_router(emails_router, tags=["emails"])
api_router.include_router(csv_router, tags=["csv"])
api_router.include_router(linkedin_router, tags=["linkedin"])
api_router.include_router(find_router, tags=["find"])
api_router.include_router(sequences_router, tags=["sequences"])
api_router.include_router(quality_router, tags=["quality"])
api_router.include_router(expand_router, tags=["expand"])
