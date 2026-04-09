import uuid
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.cell import Cell, CellStatus
from app.models.column import Column
from app.models.row import Row
from app.models.enrichment_result import EnrichmentResult
from app.agent.loop import AgentLoop, AgentResult

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentRunRequest(BaseModel):
    prompt: str
    context: dict = {}


class AgentRunResponse(BaseModel):
    success: bool
    data: dict = {}
    confidence: float = 0.0
    loops_used: int = 0
    pages_visited: int = 0
    error: str | None = None


@router.post("/run", response_model=AgentRunResponse)
async def run_agent(payload: AgentRunRequest) -> AgentRunResponse:
    """Run the AI research agent with a prompt and optional context."""
    agent = AgentLoop()
    result: AgentResult = await agent.run(payload.prompt, payload.context)
    return AgentRunResponse(
        success=result.success,
        data=result.data,
        confidence=result.confidence,
        loops_used=result.loops_used,
        pages_visited=result.pages_visited,
        error=result.error,
    )


@router.post("/enrich/{cell_id}", response_model=AgentRunResponse)
async def enrich_cell(
    cell_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> AgentRunResponse:
    """Run the AI research agent to enrich a specific cell."""
    # Load cell with relationships
    result = await db.execute(
        select(Cell)
        .options(
            selectinload(Cell.column),
            selectinload(Cell.row).selectinload(Row.cells).selectinload(Cell.column),
        )
        .where(Cell.id == cell_id)
    )
    cell = result.scalar_one_or_none()
    if not cell:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cell not found")

    column = cell.column
    if not column:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cell has no column")

    # Get prompt from column config
    config = column.config or {}
    prompt = config.get("prompt", "")
    if not prompt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Column has no prompt configured",
        )

    # Build context from other cells in the same row
    context: dict = {}
    if cell.row and cell.row.cells:
        for sibling_cell in cell.row.cells:
            if sibling_cell.id == cell_id:
                continue
            if sibling_cell.column and sibling_cell.value:
                context[sibling_cell.column.name] = sibling_cell.value

    # Mark cell as running
    cell.status = CellStatus.RUNNING
    await db.commit()

    # Run the agent
    try:
        agent = AgentLoop()
        agent_result: AgentResult = await agent.run(prompt, context)
    except Exception as e:
        logger.exception(f"Agent failed for cell {cell_id}: {e}")
        cell.status = CellStatus.ERROR
        cell.value = str(e)
        await db.commit()
        return AgentRunResponse(success=False, error=str(e))

    # Save enrichment result
    extracted_value = None
    if agent_result.data:
        # Use the first value from data dict, or serialize the whole dict
        values = list(agent_result.data.values())
        if values:
            extracted_value = str(values[0]) if len(values) == 1 else str(agent_result.data)

    enrichment = EnrichmentResult(
        cell_id=cell_id,
        source="agent",
        raw_response={"data": agent_result.data, "loops": agent_result.loops_used, "pages": agent_result.pages_visited},
        extracted_value=extracted_value,
        confidence=agent_result.confidence,
    )
    db.add(enrichment)

    # Update cell status and value
    if agent_result.success and extracted_value:
        cell.status = CellStatus.FOUND
        cell.value = extracted_value
    elif agent_result.success:
        cell.status = CellStatus.FOUND
    else:
        cell.status = CellStatus.NOT_FOUND

    await db.commit()

    return AgentRunResponse(
        success=agent_result.success,
        data=agent_result.data,
        confidence=agent_result.confidence,
        loops_used=agent_result.loops_used,
        pages_visited=agent_result.pages_visited,
        error=agent_result.error,
    )
