import io
import pytest
from httpx import AsyncClient


async def _create_table(client: AsyncClient, name: str = "CSV Test Table") -> str:
    resp = await client.post("/api/tables", json={"name": name})
    assert resp.status_code == 201
    return resp.json()["id"]


async def _create_column(client: AsyncClient, table_id: str, name: str, col_type: str = "text") -> str:
    resp = await client.post(
        f"/api/tables/{table_id}/columns",
        json={"name": name, "type": col_type, "position": 0},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _csv_file(content: str, filename: str = "test.csv") -> tuple:
    """Return (files dict, content) suitable for httpx multipart upload."""
    return ("file", (filename, io.BytesIO(content.encode("utf-8")), "text/csv"))


@pytest.mark.asyncio
async def test_import_csv_creates_columns_and_rows(client: AsyncClient):
    table_id = await _create_table(client)

    csv_content = "Name,Email,Company\nAlice,alice@example.com,Acme\nBob,bob@example.com,Globex\n"
    response = await client.post(
        f"/api/tables/{table_id}/import-csv",
        files=[_csv_file(csv_content)],
    )
    assert response.status_code == 200
    data = response.json()
    assert data["rows_imported"] == 2
    assert data["columns"] == 3

    # Verify columns were created
    cols_resp = await client.get(f"/api/tables/{table_id}/columns")
    assert cols_resp.status_code == 200
    col_names = {c["name"] for c in cols_resp.json()}
    assert col_names == {"Name", "Email", "Company"}

    # Verify rows were created
    rows_resp = await client.get(f"/api/tables/{table_id}/rows")
    assert rows_resp.status_code == 200
    rows = rows_resp.json()
    assert len(rows) == 2

    # Verify cell values
    all_values = {cell["value"] for row in rows for cell in row["cells"]}
    assert "Alice" in all_values
    assert "alice@example.com" in all_values
    assert "Acme" in all_values


@pytest.mark.asyncio
async def test_import_csv_reuses_existing_columns(client: AsyncClient):
    table_id = await _create_table(client)

    # Pre-create a column
    await _create_column(client, table_id, "Name")

    csv_content = "Name,Email\nCharlie,charlie@example.com\n"
    response = await client.post(
        f"/api/tables/{table_id}/import-csv",
        files=[_csv_file(csv_content)],
    )
    assert response.status_code == 200
    data = response.json()
    assert data["rows_imported"] == 1
    assert data["columns"] == 2

    # Only 2 columns total (existing Name + new Email)
    cols_resp = await client.get(f"/api/tables/{table_id}/columns")
    col_names = [c["name"] for c in cols_resp.json()]
    # Name should appear only once
    assert col_names.count("Name") == 1
    assert len(col_names) == 2


@pytest.mark.asyncio
async def test_import_csv_case_insensitive_column_matching(client: AsyncClient):
    table_id = await _create_table(client)

    # Pre-create column with mixed case
    await _create_column(client, table_id, "Company")

    # CSV uses lowercase header
    csv_content = "company,website\nAcme,acme.com\n"
    response = await client.post(
        f"/api/tables/{table_id}/import-csv",
        files=[_csv_file(csv_content)],
    )
    assert response.status_code == 200
    data = response.json()
    # Should reuse existing 'Company' column, create 'website'
    assert data["columns"] == 2

    cols_resp = await client.get(f"/api/tables/{table_id}/columns")
    col_names = [c["name"] for c in cols_resp.json()]
    assert len(col_names) == 2


@pytest.mark.asyncio
async def test_import_csv_table_not_found(client: AsyncClient):
    csv_content = "Name\nAlice\n"
    response = await client.post(
        "/api/tables/00000000-0000-0000-0000-000000000000/import-csv",
        files=[_csv_file(csv_content)],
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_import_empty_csv_returns_400(client: AsyncClient):
    table_id = await _create_table(client)
    # File with no content at all — no headers
    response = await client.post(
        f"/api/tables/{table_id}/import-csv",
        files=[_csv_file("")],
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_export_csv_returns_valid_csv(client: AsyncClient):
    table_id = await _create_table(client)

    # Create columns
    name_col_id = await _create_column(client, table_id, "Name")
    email_col_id = await _create_column(client, table_id, "Email")

    # Create a row with cell values
    await client.post(
        f"/api/tables/{table_id}/rows",
        json={"cells": {name_col_id: "Diana", email_col_id: "diana@example.com"}},
    )

    response = await client.get(f"/api/tables/{table_id}/export-csv")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert f"scrpr-export-{table_id}.csv" in response.headers["content-disposition"]

    content = response.text
    lines = [line for line in content.strip().splitlines() if line]
    assert len(lines) == 2  # header + 1 data row
    assert "Name" in lines[0]
    assert "Email" in lines[0]
    assert "Diana" in lines[1]
    assert "diana@example.com" in lines[1]


@pytest.mark.asyncio
async def test_export_csv_empty_table_no_columns(client: AsyncClient):
    table_id = await _create_table(client)
    response = await client.get(f"/api/tables/{table_id}/export-csv")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_export_csv_no_rows(client: AsyncClient):
    table_id = await _create_table(client)
    await _create_column(client, table_id, "Name")

    response = await client.get(f"/api/tables/{table_id}/export-csv")
    assert response.status_code == 200
    content = response.text
    lines = [line for line in content.strip().splitlines() if line]
    # Only header row, no data rows
    assert len(lines) == 1
    assert "Name" in lines[0]


@pytest.mark.asyncio
async def test_import_csv_handles_bom(client: AsyncClient):
    table_id = await _create_table(client)

    # Simulate a Windows-exported CSV with UTF-8 BOM: encode plain text with utf-8-sig
    # which prepends the BOM bytes (EF BB BF) automatically
    csv_content = "Title,Count\nTest,42\n"
    bom_bytes = csv_content.encode("utf-8-sig")  # adds BOM prefix

    response = await client.post(
        f"/api/tables/{table_id}/import-csv",
        files=[("file", ("bom.csv", io.BytesIO(bom_bytes), "text/csv"))],
    )
    assert response.status_code == 200
    data = response.json()
    assert data["rows_imported"] == 1
    assert data["columns"] == 2

    cols_resp = await client.get(f"/api/tables/{table_id}/columns")
    col_names = [c["name"] for c in cols_resp.json()]
    # BOM should be stripped — first column should be "Title", not "\ufeffTitle"
    assert "Title" in col_names
