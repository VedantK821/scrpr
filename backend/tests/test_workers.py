import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.sources.base import SourceResult
from tests.conftest import TestSession


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_source_result(found=True, value="test@example.com", confidence=0.9, source_name="ai_agent"):
    return SourceResult(
        found=found,
        value=value,
        data={"email": value} if value else {},
        confidence=confidence,
        source_name=source_name,
    )


@pytest.fixture
def patch_worker_session():
    """Patch async_session in the worker module to use the test SQLite DB."""
    with patch("app.workers.scrape_worker.async_session", TestSession):
        yield


# ---------------------------------------------------------------------------
# run_enrichment_job tests
# ---------------------------------------------------------------------------

class TestRunEnrichmentJob:
    @pytest.mark.asyncio
    async def test_job_cell_not_found_returns_error(self, patch_worker_session):
        """When the cell doesn't exist, return an error dict."""
        from app.workers.scrape_worker import run_enrichment_job

        fake_cell_id = str(uuid.uuid4())
        result = await run_enrichment_job(fake_cell_id)
        assert result == {"error": "Cell not found"}

    @pytest.mark.asyncio
    async def test_job_column_not_configured_returns_error(self, client, patch_worker_session):
        """If column has no config, return column not configured error."""
        from app.workers.scrape_worker import run_enrichment_job

        table_resp = await client.post("/api/tables", json={"name": "WorkerTestTable"})
        table_id = table_resp.json()["id"]

        col_resp = await client.post(
            f"/api/tables/{table_id}/columns",
            json={"name": "Email", "type": "agent", "position": 0},
        )
        col_id = col_resp.json()["id"]

        row_resp = await client.post(
            f"/api/tables/{table_id}/rows",
            json={"cells": {col_id: "placeholder"}},
        )
        cell_id = row_resp.json()["cells"][0]["id"]

        result = await run_enrichment_job(cell_id)
        assert "error" in result
        assert "not configured" in result["error"]

    @pytest.mark.asyncio
    async def test_job_updates_cell_to_found_on_success(self, client, patch_worker_session):
        """run_enrichment_job with mocked AIAgentSource sets cell status to FOUND."""
        from app.workers.scrape_worker import run_enrichment_job

        table_resp = await client.post("/api/tables", json={"name": "WorkerSuccessTable"})
        table_id = table_resp.json()["id"]

        col_resp = await client.post(
            f"/api/tables/{table_id}/columns",
            json={
                "name": "Email",
                "type": "agent",
                "position": 0,
                "config": {"prompt": "Find the email for {{name}}"},
            },
        )
        col_id = col_resp.json()["id"]

        row_resp = await client.post(
            f"/api/tables/{table_id}/rows",
            json={"cells": {col_id: "placeholder"}},
        )
        cell_id = row_resp.json()["cells"][0]["id"]

        mock_result = make_source_result(found=True, value="found@example.com", confidence=0.95)

        with patch("app.workers.scrape_worker.AIAgentSource") as MockSource:
            mock_instance = MagicMock()
            mock_instance.enrich = AsyncMock(return_value=mock_result)
            MockSource.return_value = mock_instance

            result = await run_enrichment_job(cell_id)

        assert result["success"] is True
        assert result["value"] == "found@example.com"
        assert result["source"] == "ai_agent"
        assert result["confidence"] == pytest.approx(0.95)

        # Verify cell was updated in DB
        cell_resp = await client.get(f"/api/cells/{cell_id}")
        assert cell_resp.json()["status"] == "found"
        assert cell_resp.json()["value"] == "found@example.com"

    @pytest.mark.asyncio
    async def test_job_updates_cell_to_not_found_on_failure(self, client, patch_worker_session):
        """run_enrichment_job with no-result source sets cell status to NOT_FOUND."""
        from app.workers.scrape_worker import run_enrichment_job

        table_resp = await client.post("/api/tables", json={"name": "WorkerFailTable"})
        table_id = table_resp.json()["id"]

        col_resp = await client.post(
            f"/api/tables/{table_id}/columns",
            json={
                "name": "Email",
                "type": "agent",
                "position": 0,
                "config": {"prompt": "Find the email"},
            },
        )
        col_id = col_resp.json()["id"]

        row_resp = await client.post(
            f"/api/tables/{table_id}/rows",
            json={"cells": {col_id: "placeholder"}},
        )
        cell_id = row_resp.json()["cells"][0]["id"]

        mock_result = make_source_result(found=False, value=None, confidence=0.0, source_name="ai_agent")

        with patch("app.workers.scrape_worker.AIAgentSource") as MockSource:
            mock_instance = MagicMock()
            mock_instance.enrich = AsyncMock(return_value=mock_result)
            MockSource.return_value = mock_instance

            result = await run_enrichment_job(cell_id)

        assert result["success"] is False

        cell_resp = await client.get(f"/api/cells/{cell_id}")
        assert cell_resp.json()["status"] == "not_found"

    @pytest.mark.asyncio
    async def test_job_uses_waterfall_engine_for_waterfall_column(self, client, patch_worker_session):
        """run_enrichment_job uses WaterfallEngine when column type is waterfall."""
        from app.workers.scrape_worker import run_enrichment_job

        table_resp = await client.post("/api/tables", json={"name": "WaterfallWorkerTable"})
        table_id = table_resp.json()["id"]

        col_resp = await client.post(
            f"/api/tables/{table_id}/columns",
            json={
                "name": "Email",
                "type": "waterfall",
                "position": 0,
                "config": {
                    "prompt": "Find contact email",
                    "sources": ["email_pattern", "hunter"],
                },
            },
        )
        col_id = col_resp.json()["id"]

        row_resp = await client.post(
            f"/api/tables/{table_id}/rows",
            json={"cells": {col_id: "placeholder"}},
        )
        cell_id = row_resp.json()["cells"][0]["id"]

        mock_result = make_source_result(found=True, value="waterfall@example.com", source_name="email_pattern")

        with patch("app.workers.scrape_worker.WaterfallEngine") as MockEngine:
            mock_engine_instance = MagicMock()
            mock_engine_instance.run = AsyncMock(return_value=mock_result)
            MockEngine.from_config = MagicMock(return_value=mock_engine_instance)

            result = await run_enrichment_job(cell_id)

        assert result["success"] is True
        assert result["value"] == "waterfall@example.com"
        assert result["source"] == "email_pattern"

    @pytest.mark.asyncio
    async def test_job_updates_cell_to_error_on_exception(self, client, patch_worker_session):
        """When the source raises, cell status is set to ERROR."""
        from app.workers.scrape_worker import run_enrichment_job

        table_resp = await client.post("/api/tables", json={"name": "WorkerErrorTable"})
        table_id = table_resp.json()["id"]

        col_resp = await client.post(
            f"/api/tables/{table_id}/columns",
            json={
                "name": "Email",
                "type": "agent",
                "position": 0,
                "config": {"prompt": "Find the email"},
            },
        )
        col_id = col_resp.json()["id"]

        row_resp = await client.post(
            f"/api/tables/{table_id}/rows",
            json={"cells": {col_id: "placeholder"}},
        )
        cell_id = row_resp.json()["cells"][0]["id"]

        with patch("app.workers.scrape_worker.AIAgentSource") as MockSource:
            mock_instance = MagicMock()
            mock_instance.enrich = AsyncMock(side_effect=RuntimeError("Source exploded"))
            MockSource.return_value = mock_instance

            result = await run_enrichment_job(cell_id)

        assert "error" in result
        assert "Source exploded" in result["error"]

        cell_resp = await client.get(f"/api/cells/{cell_id}")
        assert cell_resp.json()["status"] == "error"

    @pytest.mark.asyncio
    async def test_job_builds_row_context_from_sibling_cells(self, client, patch_worker_session):
        """run_enrichment_job passes sibling cell values as row_data to the source."""
        from app.workers.scrape_worker import run_enrichment_job

        table_resp = await client.post("/api/tables", json={"name": "ContextTestTable"})
        table_id = table_resp.json()["id"]

        # Create a context column (text)
        name_col_resp = await client.post(
            f"/api/tables/{table_id}/columns",
            json={"name": "name", "type": "text", "position": 0},
        )
        name_col_id = name_col_resp.json()["id"]

        # Create an enrichment column (agent)
        email_col_resp = await client.post(
            f"/api/tables/{table_id}/columns",
            json={
                "name": "Email",
                "type": "agent",
                "position": 1,
                "config": {"prompt": "Find email"},
            },
        )
        email_col_id = email_col_resp.json()["id"]

        # Create a row with a value in the context column
        row_resp = await client.post(
            f"/api/tables/{table_id}/rows",
            json={"cells": {name_col_id: "Alice Smith", email_col_id: "placeholder"}},
        )
        cells = row_resp.json()["cells"]
        email_cell_id = next(c["id"] for c in cells if c["column_id"] == email_col_id)

        captured_row_data = {}

        async def capture_enrich(row_data, prompt):
            captured_row_data.update(row_data)
            return make_source_result(found=True, value="alice@test.com")

        with patch("app.workers.scrape_worker.AIAgentSource") as MockSource:
            mock_instance = MagicMock()
            mock_instance.enrich = capture_enrich
            MockSource.return_value = mock_instance

            await run_enrichment_job(email_cell_id)

        assert "name" in captured_row_data
        assert captured_row_data["name"] == "Alice Smith"
