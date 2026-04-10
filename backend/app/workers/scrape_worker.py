import logging
import re
import uuid
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import async_session
from app.models.cell import Cell, CellStatus
from app.models.column import Column, ColumnType
from app.models.row import Row
from app.models.enrichment_result import EnrichmentResult
from app.models.job import Job, JobStatus
from app.sources import get_source_by_name
from app.sources.ai_agent import AIAgentSource
from app.services.enrichment_router import WaterfallEngine

logger = logging.getLogger(__name__)


def render_prompt(prompt: str, row_data: dict[str, str]) -> str:
    """Replace /ColumnName/ references in prompt with actual row values."""
    def _replace(match):
        key = match.group(1)
        return row_data.get(key, match.group(0))
    return re.sub(r'/([^/]+)/', _replace, prompt)


async def run_enrichment_job(cell_id: str, **kwargs) -> dict:
    """Process a single cell enrichment job."""
    async with async_session() as db:
        cell = await db.get(Cell, uuid.UUID(cell_id))
        if not cell:
            return {"error": "Cell not found"}

        column = await db.get(Column, cell.column_id)
        if not column or not column.config:
            return {"error": "Column not configured"}

        # Build row context from sibling cells
        result = await db.execute(
            select(Row).where(Row.id == cell.row_id).options(selectinload(Row.cells))
        )
        row = result.scalar_one_or_none()
        if not row:
            return {"error": "Row not found"}

        row_data = {}
        for other_cell in row.cells:
            if other_cell.value and other_cell.column_id != cell.column_id:
                other_col = await db.get(Column, other_cell.column_id)
                if other_col:
                    row_data[other_col.name] = other_cell.value

        # Update cell status to running
        cell.status = CellStatus.RUNNING
        await db.commit()

        try:
            raw_prompt = column.config.get("prompt", "")
            prompt = render_prompt(raw_prompt, row_data)

            if column.type == ColumnType.AGENT:
                source = AIAgentSource()
                source_result = await source.enrich(row_data, prompt)
            elif column.type == ColumnType.WATERFALL:
                source_names = column.config.get("sources", ["ai_agent", "hunter", "apollo", "email_pattern"])
                engine = WaterfallEngine.from_config(source_names)
                source_result = await engine.run(row_data, prompt)
            else:
                return {"error": f"Column type {column.type} not enrichable"}

            # Update cell with result
            if source_result.found:
                cell.value = source_result.value
                cell.status = CellStatus.FOUND
            else:
                cell.status = CellStatus.NOT_FOUND if source_result.confidence == 0 else CellStatus.REVIEW

            # Save enrichment history
            enrichment = EnrichmentResult(
                cell_id=cell.id,
                source=source_result.source_name,
                raw_response=source_result.data,
                extracted_value=source_result.value,
                confidence=source_result.confidence,
            )
            db.add(enrichment)
            await db.commit()

            return {
                "success": source_result.found,
                "value": source_result.value,
                "source": source_result.source_name,
                "confidence": source_result.confidence,
            }

        except Exception as e:
            logger.error(f"Enrichment job failed for cell {cell_id}: {e}")
            cell.status = CellStatus.ERROR
            await db.commit()
            return {"error": str(e)}


# arq worker settings (used when running: arq app.workers.scrape_worker.WorkerSettings)
class WorkerSettings:
    functions = [run_enrichment_job]
    redis_settings = None  # Will be set from config when Redis is available
