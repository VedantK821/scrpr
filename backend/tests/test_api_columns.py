import pytest
from httpx import AsyncClient


async def _create_table(client: AsyncClient, name: str = "Test Table") -> str:
    resp = await client.post("/api/tables", json={"name": name})
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_create_column_text(client: AsyncClient):
    table_id = await _create_table(client)
    response = await client.post(
        f"/api/tables/{table_id}/columns",
        json={"name": "Name", "type": "text", "position": 0},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Name"
    assert data["type"] == "text"
    assert data["table_id"] == table_id


@pytest.mark.asyncio
async def test_create_column_agent_with_config(client: AsyncClient):
    table_id = await _create_table(client)
    config = {"prompt": "Find the CEO of {{company}}", "model": "gpt-4o"}
    response = await client.post(
        f"/api/tables/{table_id}/columns",
        json={"name": "CEO", "type": "agent", "position": 1, "config": config},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["type"] == "agent"
    assert data["config"]["prompt"] == "Find the CEO of {{company}}"


@pytest.mark.asyncio
async def test_list_columns(client: AsyncClient):
    table_id = await _create_table(client)
    await client.post(f"/api/tables/{table_id}/columns", json={"name": "Col A", "type": "text", "position": 0})
    await client.post(f"/api/tables/{table_id}/columns", json={"name": "Col B", "type": "url", "position": 1})

    response = await client.get(f"/api/tables/{table_id}/columns")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["name"] == "Col A"
    assert data[1]["name"] == "Col B"


@pytest.mark.asyncio
async def test_list_columns_empty(client: AsyncClient):
    table_id = await _create_table(client)
    response = await client.get(f"/api/tables/{table_id}/columns")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_get_column(client: AsyncClient):
    table_id = await _create_table(client)
    create_resp = await client.post(
        f"/api/tables/{table_id}/columns",
        json={"name": "My Col", "type": "email"},
    )
    col_id = create_resp.json()["id"]

    response = await client.get(f"/api/tables/{table_id}/columns/{col_id}")
    assert response.status_code == 200
    assert response.json()["name"] == "My Col"


@pytest.mark.asyncio
async def test_update_column(client: AsyncClient):
    table_id = await _create_table(client)
    create_resp = await client.post(
        f"/api/tables/{table_id}/columns",
        json={"name": "Old", "type": "text"},
    )
    col_id = create_resp.json()["id"]

    response = await client.patch(
        f"/api/tables/{table_id}/columns/{col_id}",
        json={"name": "New", "type": "url"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "New"
    assert data["type"] == "url"


@pytest.mark.asyncio
async def test_delete_column(client: AsyncClient):
    table_id = await _create_table(client)
    create_resp = await client.post(
        f"/api/tables/{table_id}/columns",
        json={"name": "To Delete", "type": "text"},
    )
    col_id = create_resp.json()["id"]

    response = await client.delete(f"/api/tables/{table_id}/columns/{col_id}")
    assert response.status_code == 204

    get_resp = await client.get(f"/api/tables/{table_id}/columns/{col_id}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_create_column_table_not_found(client: AsyncClient):
    response = await client.post(
        "/api/tables/00000000-0000-0000-0000-000000000000/columns",
        json={"name": "Col", "type": "text"},
    )
    assert response.status_code == 404
