import pytest
from httpx import AsyncClient


async def _create_table(client: AsyncClient, name: str = "Test Table") -> str:
    resp = await client.post("/api/tables", json={"name": name})
    return resp.json()["id"]


async def _create_column(client: AsyncClient, table_id: str, name: str = "Company", col_type: str = "text") -> str:
    resp = await client.post(
        f"/api/tables/{table_id}/columns",
        json={"name": name, "type": col_type, "position": 0},
    )
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_create_row_empty(client: AsyncClient):
    table_id = await _create_table(client)
    response = await client.post(f"/api/tables/{table_id}/rows", json={})
    assert response.status_code == 201
    data = response.json()
    assert data["table_id"] == table_id
    assert data["cells"] == []


@pytest.mark.asyncio
async def test_create_row_with_cells(client: AsyncClient):
    table_id = await _create_table(client)
    col_id = await _create_column(client, table_id, "Company Name")

    response = await client.post(
        f"/api/tables/{table_id}/rows",
        json={"cells": {col_id: "Acme Corp"}},
    )
    assert response.status_code == 201
    data = response.json()
    assert len(data["cells"]) == 1
    assert data["cells"][0]["value"] == "Acme Corp"
    assert data["cells"][0]["column_id"] == col_id


@pytest.mark.asyncio
async def test_create_row_invalid_column(client: AsyncClient):
    table_id = await _create_table(client)
    response = await client.post(
        f"/api/tables/{table_id}/rows",
        json={"cells": {"00000000-0000-0000-0000-000000000000": "value"}},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_rows(client: AsyncClient):
    table_id = await _create_table(client)
    await client.post(f"/api/tables/{table_id}/rows", json={})
    await client.post(f"/api/tables/{table_id}/rows", json={})

    response = await client.get(f"/api/tables/{table_id}/rows")
    assert response.status_code == 200
    assert len(response.json()) == 2


@pytest.mark.asyncio
async def test_list_rows_empty(client: AsyncClient):
    table_id = await _create_table(client)
    response = await client.get(f"/api/tables/{table_id}/rows")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_get_row(client: AsyncClient):
    table_id = await _create_table(client)
    create_resp = await client.post(f"/api/tables/{table_id}/rows", json={})
    row_id = create_resp.json()["id"]

    response = await client.get(f"/api/tables/{table_id}/rows/{row_id}")
    assert response.status_code == 200
    assert response.json()["id"] == row_id


@pytest.mark.asyncio
async def test_delete_row(client: AsyncClient):
    table_id = await _create_table(client)
    create_resp = await client.post(f"/api/tables/{table_id}/rows", json={})
    row_id = create_resp.json()["id"]

    response = await client.delete(f"/api/tables/{table_id}/rows/{row_id}")
    assert response.status_code == 204

    get_resp = await client.get(f"/api/tables/{table_id}/rows/{row_id}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_create_row_table_not_found(client: AsyncClient):
    response = await client.post("/api/tables/00000000-0000-0000-0000-000000000000/rows", json={})
    assert response.status_code == 404
