import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_table(client: AsyncClient):
    response = await client.post("/api/tables", json={"name": "My Table"})
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "My Table"
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data


@pytest.mark.asyncio
async def test_list_tables_empty(client: AsyncClient):
    response = await client.get("/api/tables")
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_list_tables(client: AsyncClient):
    await client.post("/api/tables", json={"name": "Table A"})
    await client.post("/api/tables", json={"name": "Table B"})
    response = await client.get("/api/tables")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


@pytest.mark.asyncio
async def test_get_table(client: AsyncClient):
    create_resp = await client.post("/api/tables", json={"name": "Get Test"})
    table_id = create_resp.json()["id"]

    response = await client.get(f"/api/tables/{table_id}")
    assert response.status_code == 200
    assert response.json()["name"] == "Get Test"


@pytest.mark.asyncio
async def test_get_table_not_found(client: AsyncClient):
    response = await client.get("/api/tables/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_table(client: AsyncClient):
    create_resp = await client.post("/api/tables", json={"name": "Old Name"})
    table_id = create_resp.json()["id"]

    response = await client.patch(f"/api/tables/{table_id}", json={"name": "New Name"})
    assert response.status_code == 200
    assert response.json()["name"] == "New Name"


@pytest.mark.asyncio
async def test_update_table_not_found(client: AsyncClient):
    response = await client.patch(
        "/api/tables/00000000-0000-0000-0000-000000000000",
        json={"name": "x"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_table(client: AsyncClient):
    create_resp = await client.post("/api/tables", json={"name": "To Delete"})
    table_id = create_resp.json()["id"]

    response = await client.delete(f"/api/tables/{table_id}")
    assert response.status_code == 204

    get_resp = await client.get(f"/api/tables/{table_id}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_table_not_found(client: AsyncClient):
    response = await client.delete("/api/tables/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
