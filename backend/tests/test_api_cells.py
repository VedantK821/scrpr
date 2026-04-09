import pytest
from httpx import AsyncClient


async def _setup_table_col_row(client: AsyncClient):
    """Helper: create table, column, row with a cell, return (table_id, col_id, row_id, cell_id)."""
    table_resp = await client.post("/api/tables", json={"name": "CellTestTable"})
    table_id = table_resp.json()["id"]

    col_resp = await client.post(
        f"/api/tables/{table_id}/columns",
        json={"name": "Company", "type": "text", "position": 0},
    )
    col_id = col_resp.json()["id"]

    row_resp = await client.post(
        f"/api/tables/{table_id}/rows",
        json={"cells": {col_id: "Initial Value"}},
    )
    row_data = row_resp.json()
    row_id = row_data["id"]
    cell_id = row_data["cells"][0]["id"]

    return table_id, col_id, row_id, cell_id


@pytest.mark.asyncio
async def test_get_cell(client: AsyncClient):
    _, _, _, cell_id = await _setup_table_col_row(client)
    response = await client.get(f"/api/cells/{cell_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["value"] == "Initial Value"
    assert data["status"] == "found"


@pytest.mark.asyncio
async def test_update_cell_value(client: AsyncClient):
    _, _, _, cell_id = await _setup_table_col_row(client)
    response = await client.patch(f"/api/cells/{cell_id}", json={"value": "Updated Value"})
    assert response.status_code == 200
    data = response.json()
    assert data["value"] == "Updated Value"


@pytest.mark.asyncio
async def test_update_cell_status(client: AsyncClient):
    _, _, _, cell_id = await _setup_table_col_row(client)
    response = await client.patch(f"/api/cells/{cell_id}", json={"status": "pending"})
    assert response.status_code == 200
    assert response.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_update_cell_value_and_status(client: AsyncClient):
    _, _, _, cell_id = await _setup_table_col_row(client)
    response = await client.patch(
        f"/api/cells/{cell_id}",
        json={"value": "New Data", "status": "found"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["value"] == "New Data"
    assert data["status"] == "found"


@pytest.mark.asyncio
async def test_update_cell_not_found(client: AsyncClient):
    response = await client.patch(
        "/api/cells/00000000-0000-0000-0000-000000000000",
        json={"value": "x"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_cell_not_found(client: AsyncClient):
    response = await client.get("/api/cells/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cell_deleted_with_row(client: AsyncClient):
    table_id, _, row_id, cell_id = await _setup_table_col_row(client)

    # Delete the row
    await client.delete(f"/api/tables/{table_id}/rows/{row_id}")

    # Cell should be gone (cascade)
    response = await client.get(f"/api/cells/{cell_id}")
    assert response.status_code == 404
