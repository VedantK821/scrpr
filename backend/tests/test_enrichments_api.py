import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient

from app.sources.base import SourceResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_table(client: AsyncClient, name: str = "EnrichTest") -> str:
    resp = await client.post("/api/tables", json={"name": name})
    assert resp.status_code == 201
    return resp.json()["id"]


async def _create_column(client: AsyncClient, table_id: str, col_type: str = "agent", config: dict | None = None) -> str:
    payload = {"name": "Email", "type": col_type, "position": 0}
    if config is not None:
        payload["config"] = config
    resp = await client.post(f"/api/tables/{table_id}/columns", json=payload)
    assert resp.status_code == 201
    return resp.json()["id"]


async def _create_row(client: AsyncClient, table_id: str, col_id: str, value: str = "placeholder") -> tuple[str, str]:
    """Returns (row_id, cell_id)."""
    resp = await client.post(
        f"/api/tables/{table_id}/rows",
        json={"cells": {col_id: value}},
    )
    assert resp.status_code == 201
    row_data = resp.json()
    return row_data["id"], row_data["cells"][0]["id"]


def make_success_job_result(value="found@example.com"):
    return {
        "success": True,
        "value": value,
        "source": "ai_agent",
        "confidence": 0.9,
    }


def make_failure_job_result():
    return {
        "success": False,
        "value": None,
        "source": "ai_agent",
        "confidence": 0.0,
    }


# ---------------------------------------------------------------------------
# POST /tables/{table_id}/columns/{column_id}/enrich
# ---------------------------------------------------------------------------

class TestTriggerEnrichment:
    @pytest.mark.asyncio
    async def test_trigger_enrichment_success(self, client: AsyncClient):
        """POST enrich on an agent column returns triggered count and running status immediately."""
        table_id = await _create_table(client, "TriggerSuccess")
        col_id = await _create_column(
            client, table_id, "agent",
            config={"prompt": "Find email for {{name}}"},
        )
        row_id, cell_id = await _create_row(client, table_id, col_id)

        with patch("app.api.enrichments.run_enrichment_job", new_callable=AsyncMock) as mock_job:
            mock_job.return_value = make_success_job_result()
            response = await client.post(
                f"/api/tables/{table_id}/columns/{col_id}/enrich"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["triggered"] == 1
        assert data["status"] == "running"
        assert "results" not in data

    @pytest.mark.asyncio
    async def test_trigger_enrichment_specific_rows(self, client: AsyncClient):
        """POST enrich with row_ids only enriches those rows."""
        table_id = await _create_table(client, "TriggerSpecificRows")
        col_id = await _create_column(
            client, table_id, "agent",
            config={"prompt": "Find email"},
        )
        row_id1, _ = await _create_row(client, table_id, col_id, "placeholder1")
        row_id2, _ = await _create_row(client, table_id, col_id, "placeholder2")

        with patch("app.api.enrichments.run_enrichment_job", new_callable=AsyncMock) as mock_job:
            mock_job.return_value = make_success_job_result()
            response = await client.post(
                f"/api/tables/{table_id}/columns/{col_id}/enrich",
                json={"row_ids": [row_id1]},
            )

        assert response.status_code == 200
        data = response.json()
        # Only row_id1 should be triggered
        assert data["triggered"] == 1

    @pytest.mark.asyncio
    async def test_trigger_enrichment_column_not_found_returns_404(self, client: AsyncClient):
        """POST enrich on non-existent column returns 404."""
        table_id = await _create_table(client, "TriggerMissingCol")
        fake_col_id = "00000000-0000-0000-0000-000000000000"

        response = await client.post(
            f"/api/tables/{table_id}/columns/{fake_col_id}/enrich"
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_trigger_enrichment_non_enrichable_column_returns_400(self, client: AsyncClient):
        """POST enrich on a text column returns 400 bad request."""
        table_id = await _create_table(client, "TriggerNonEnrichable")
        col_id = await _create_column(client, table_id, "text")

        response = await client.post(
            f"/api/tables/{table_id}/columns/{col_id}/enrich"
        )
        assert response.status_code == 400
        assert "not enrichable" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_trigger_enrichment_missing_prompt_returns_400(self, client: AsyncClient):
        """POST enrich on agent column with no prompt config returns 400."""
        table_id = await _create_table(client, "TriggerNoPrompt")
        col_id = await _create_column(client, table_id, "agent")  # no config

        response = await client.post(
            f"/api/tables/{table_id}/columns/{col_id}/enrich"
        )
        assert response.status_code == 400
        assert "prompt" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_trigger_enrichment_no_rows_returns_404(self, client: AsyncClient):
        """POST enrich on column with no rows returns 404."""
        table_id = await _create_table(client, "TriggerNoRows")
        col_id = await _create_column(
            client, table_id, "agent",
            config={"prompt": "Find email"},
        )
        # No rows created
        response = await client.post(
            f"/api/tables/{table_id}/columns/{col_id}/enrich"
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_trigger_enrichment_waterfall_column(self, client: AsyncClient):
        """POST enrich on a waterfall column triggers correctly."""
        table_id = await _create_table(client, "TriggerWaterfall")
        col_id = await _create_column(
            client, table_id, "waterfall",
            config={"prompt": "Find email", "sources": ["email_pattern", "hunter"]},
        )
        await _create_row(client, table_id, col_id)

        with patch("app.api.enrichments.run_enrichment_job", new_callable=AsyncMock) as mock_job:
            mock_job.return_value = make_success_job_result()
            response = await client.post(
                f"/api/tables/{table_id}/columns/{col_id}/enrich"
            )

        assert response.status_code == 200
        assert response.json()["triggered"] == 1

    @pytest.mark.asyncio
    async def test_trigger_enrichment_column_wrong_table_returns_404(self, client: AsyncClient):
        """POST enrich with column from different table returns 404."""
        table_id1 = await _create_table(client, "Table1")
        table_id2 = await _create_table(client, "Table2")
        col_id = await _create_column(
            client, table_id1, "agent",
            config={"prompt": "Find email"},
        )

        # Try to trigger enrichment on table2 using table1's column
        response = await client.post(
            f"/api/tables/{table_id2}/columns/{col_id}/enrich"
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /tables/{table_id}/columns/{column_id}/enrich/status
# ---------------------------------------------------------------------------

class TestEnrichmentStatus:
    @pytest.mark.asyncio
    async def test_status_returns_correct_counts(self, client: AsyncClient):
        """GET status returns accurate cell status counts."""
        table_id = await _create_table(client, "StatusTest")
        col_id = await _create_column(
            client, table_id, "agent",
            config={"prompt": "Find email"},
        )

        # Create multiple rows/cells
        row1_id, cell1_id = await _create_row(client, table_id, col_id, "p1")
        row2_id, cell2_id = await _create_row(client, table_id, col_id, "p2")
        row3_id, cell3_id = await _create_row(client, table_id, col_id, "p3")

        # Set different statuses directly via the cell PATCH endpoint
        await client.patch(f"/api/cells/{cell1_id}", json={"status": "found", "value": "a@a.com"})
        await client.patch(f"/api/cells/{cell2_id}", json={"status": "not_found"})
        await client.patch(f"/api/cells/{cell3_id}", json={"status": "error"})

        response = await client.get(
            f"/api/tables/{table_id}/columns/{col_id}/enrich/status"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert data["found"] == 1
        assert data["not_found"] == 1
        assert data["errors"] == 1
        assert data["completed"] == 3
        assert data["running"] == 0

    @pytest.mark.asyncio
    async def test_status_empty_column_returns_zeros(self, client: AsyncClient):
        """GET status on column with no cells returns all zeros."""
        table_id = await _create_table(client, "StatusEmpty")
        col_id = await _create_column(
            client, table_id, "agent",
            config={"prompt": "Find email"},
        )

        response = await client.get(
            f"/api/tables/{table_id}/columns/{col_id}/enrich/status"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["completed"] == 0
        assert data["found"] == 0
        assert data["not_found"] == 0
        assert data["errors"] == 0
        assert data["running"] == 0

    @pytest.mark.asyncio
    async def test_status_counts_running_and_pending(self, client: AsyncClient):
        """GET status counts running and pending cells in the 'running' field."""
        table_id = await _create_table(client, "StatusRunning")
        col_id = await _create_column(
            client, table_id, "agent",
            config={"prompt": "Find email"},
        )
        row1_id, cell1_id = await _create_row(client, table_id, col_id)
        row2_id, cell2_id = await _create_row(client, table_id, col_id)

        await client.patch(f"/api/cells/{cell1_id}", json={"status": "running"})
        await client.patch(f"/api/cells/{cell2_id}", json={"status": "pending"})

        response = await client.get(
            f"/api/tables/{table_id}/columns/{col_id}/enrich/status"
        )
        data = response.json()
        assert data["running"] == 2
        assert data["completed"] == 0


# ---------------------------------------------------------------------------
# GET /quota
# ---------------------------------------------------------------------------

class TestGetQuota:
    @pytest.mark.asyncio
    async def test_get_quota_returns_usage_dict(self, client: AsyncClient):
        """GET /quota returns a dict with all known sources."""
        response = await client.get("/api/quota")
        assert response.status_code == 200
        data = response.json()
        assert "hunter" in data
        assert "apollo" in data
        assert "ai_agent" in data
        assert "email_pattern" in data

    @pytest.mark.asyncio
    async def test_get_quota_has_correct_fields(self, client: AsyncClient):
        """Each source entry has used, limit, and remaining fields."""
        response = await client.get("/api/quota")
        assert response.status_code == 200
        data = response.json()
        for source_name, source_data in data.items():
            assert "used" in source_data, f"Missing 'used' for {source_name}"
            assert "limit" in source_data, f"Missing 'limit' for {source_name}"
            assert "remaining" in source_data, f"Missing 'remaining' for {source_name}"

    @pytest.mark.asyncio
    async def test_get_quota_initial_usage_is_zero(self, client: AsyncClient):
        """Fresh quota tracker starts all sources at zero usage."""
        response = await client.get("/api/quota")
        data = response.json()
        # hunter and apollo have finite limits and should start at 0
        assert data["hunter"]["used"] == 0
        assert data["apollo"]["used"] == 0
