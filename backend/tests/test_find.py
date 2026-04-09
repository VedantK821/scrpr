import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient

from app.services.list_builder import ListBuilder


# ---------------------------------------------------------------------------
# ListBuilder._parse_list unit tests
# ---------------------------------------------------------------------------

class TestParseList:
    def setup_method(self):
        # Instantiate without calling __init__ to avoid requiring LLM/scraper
        self.builder = ListBuilder.__new__(ListBuilder)

    def test_parse_valid_json_array(self):
        response = '[{"name": "TCS", "domain": "tcs.com"}, {"name": "Infosys", "domain": "infosys.com"}]'
        result = self.builder._parse_list(response)
        assert len(result) == 2
        assert result[0]["name"] == "TCS"
        assert result[1]["domain"] == "infosys.com"

    def test_parse_json_wrapped_in_think_tags(self):
        response = (
            '<think>Let me think about this...</think>\n'
            '[{"name": "Wipro", "industry": "IT"}, {"name": "HCL", "industry": "IT"}]'
        )
        result = self.builder._parse_list(response)
        assert len(result) == 2
        assert result[0]["name"] == "Wipro"
        assert result[1]["name"] == "HCL"

    def test_parse_json_with_multiline_think_tags(self):
        response = (
            '<think>\nI need to consider many companies.\n'
            'Let me list the top ones.\n</think>\n'
            '[{"name": "TCS"}, {"name": "Infosys"}]'
        )
        result = self.builder._parse_list(response)
        assert len(result) == 2
        assert result[0]["name"] == "TCS"

    def test_parse_empty_response(self):
        result = self.builder._parse_list("")
        assert result == []

    def test_parse_none_response(self):
        result = self.builder._parse_list(None)
        assert result == []

    def test_parse_response_with_no_json(self):
        result = self.builder._parse_list("Here is a list of companies: TCS, Infosys, Wipro")
        assert result == []

    def test_parse_filters_non_dict_items(self):
        response = '[{"name": "TCS"}, "not a dict", 42, {"name": "Infosys"}]'
        result = self.builder._parse_list(response)
        assert len(result) == 2
        assert result[0]["name"] == "TCS"
        assert result[1]["name"] == "Infosys"

    def test_parse_empty_array(self):
        result = self.builder._parse_list("[]")
        assert result == []

    def test_parse_json_with_surrounding_text(self):
        response = (
            'Here are the companies:\n'
            '[{"name": "Accenture", "headquarters": "Dublin"}]\n'
            'These are some of the top companies.'
        )
        result = self.builder._parse_list(response)
        assert len(result) == 1
        assert result[0]["name"] == "Accenture"


# ---------------------------------------------------------------------------
# POST /find endpoint tests
# ---------------------------------------------------------------------------

MOCK_BUILD_RESULT = {
    "entities": [
        {"name": "TCS", "domain": "tcs.com", "industry": "IT Services", "headquarters": "Mumbai"},
        {"name": "Infosys", "domain": "infosys.com", "industry": "IT Services", "headquarters": "Bengaluru"},
        {"name": "Wipro", "domain": "wipro.com", "industry": "IT Services", "headquarters": "Bengaluru"},
    ],
    "total": 3,
    "fields": ["name", "domain", "industry", "headquarters"],
}


class TestFindEndpoint:
    @pytest.mark.asyncio
    async def test_find_creates_table(self, client: AsyncClient):
        """POST /find creates a table and returns table_id."""
        with patch("app.api.find.ListBuilder") as MockBuilder:
            mock_instance = MagicMock()
            mock_instance.build_list = AsyncMock(return_value=MOCK_BUILD_RESULT)
            MockBuilder.return_value = mock_instance

            response = await client.post(
                "/api/find",
                json={
                    "criteria": "Top MNCs in India",
                    "target_count": 3,
                    "entity_type": "companies",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert "table_id" in data
        assert data["entities_found"] == 3
        assert data["fields"] == ["name", "domain", "industry", "headquarters"]

    @pytest.mark.asyncio
    async def test_find_creates_columns_from_fields(self, client: AsyncClient):
        """POST /find creates columns matching entity fields."""
        with patch("app.api.find.ListBuilder") as MockBuilder:
            mock_instance = MagicMock()
            mock_instance.build_list = AsyncMock(return_value=MOCK_BUILD_RESULT)
            MockBuilder.return_value = mock_instance

            response = await client.post(
                "/api/find",
                json={
                    "criteria": "Top MNCs in India",
                    "target_count": 3,
                    "entity_type": "companies",
                },
            )

        assert response.status_code == 200
        data = response.json()
        table_id = data["table_id"]

        # Verify columns were created
        cols_resp = await client.get(f"/api/tables/{table_id}/columns")
        assert cols_resp.status_code == 200
        columns = cols_resp.json()
        col_names = [c["name"] for c in columns]
        assert "Name" in col_names
        assert "Domain" in col_names
        assert "Industry" in col_names
        assert "Headquarters" in col_names

    @pytest.mark.asyncio
    async def test_find_creates_rows_for_each_entity(self, client: AsyncClient):
        """POST /find creates one row per entity."""
        with patch("app.api.find.ListBuilder") as MockBuilder:
            mock_instance = MagicMock()
            mock_instance.build_list = AsyncMock(return_value=MOCK_BUILD_RESULT)
            MockBuilder.return_value = mock_instance

            response = await client.post(
                "/api/find",
                json={
                    "criteria": "Top MNCs in India",
                    "target_count": 3,
                    "entity_type": "companies",
                },
            )

        assert response.status_code == 200
        table_id = response.json()["table_id"]

        rows_resp = await client.get(f"/api/tables/{table_id}/rows")
        assert rows_resp.status_code == 200
        rows = rows_resp.json()
        assert len(rows) == 3

    @pytest.mark.asyncio
    async def test_find_populates_cells_with_found_status(self, client: AsyncClient):
        """POST /find creates cells with FOUND status."""
        with patch("app.api.find.ListBuilder") as MockBuilder:
            mock_instance = MagicMock()
            mock_instance.build_list = AsyncMock(return_value=MOCK_BUILD_RESULT)
            MockBuilder.return_value = mock_instance

            response = await client.post(
                "/api/find",
                json={
                    "criteria": "Top MNCs in India",
                    "target_count": 3,
                    "entity_type": "companies",
                },
            )

        assert response.status_code == 200
        table_id = response.json()["table_id"]

        rows_resp = await client.get(f"/api/tables/{table_id}/rows")
        rows = rows_resp.json()

        # First row should have cells with values
        first_row = rows[0]
        assert len(first_row["cells"]) > 0
        for cell in first_row["cells"]:
            assert cell["status"] == "found"
            assert cell["value"] is not None

    @pytest.mark.asyncio
    async def test_find_uses_custom_table_name(self, client: AsyncClient):
        """POST /find uses provided table_name."""
        with patch("app.api.find.ListBuilder") as MockBuilder:
            mock_instance = MagicMock()
            mock_instance.build_list = AsyncMock(return_value=MOCK_BUILD_RESULT)
            MockBuilder.return_value = mock_instance

            response = await client.post(
                "/api/find",
                json={
                    "criteria": "Top MNCs in India",
                    "target_count": 3,
                    "entity_type": "companies",
                    "table_name": "My Custom Table",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["table_name"] == "My Custom Table"

    @pytest.mark.asyncio
    async def test_find_auto_generates_table_name(self, client: AsyncClient):
        """POST /find auto-generates table_name from entity_type and criteria."""
        with patch("app.api.find.ListBuilder") as MockBuilder:
            mock_instance = MagicMock()
            mock_instance.build_list = AsyncMock(return_value=MOCK_BUILD_RESULT)
            MockBuilder.return_value = mock_instance

            response = await client.post(
                "/api/find",
                json={
                    "criteria": "Top MNCs in India",
                    "target_count": 3,
                    "entity_type": "companies",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert "Companies" in data["table_name"]
        assert "Top MNCs in India" in data["table_name"]

    @pytest.mark.asyncio
    async def test_find_returns_404_when_no_entities(self, client: AsyncClient):
        """POST /find returns 404 when ListBuilder finds nothing."""
        empty_result = {"entities": [], "total": 0, "fields": []}

        with patch("app.api.find.ListBuilder") as MockBuilder:
            mock_instance = MagicMock()
            mock_instance.build_list = AsyncMock(return_value=empty_result)
            MockBuilder.return_value = mock_instance

            response = await client.post(
                "/api/find",
                json={
                    "criteria": "xyzzy nonexistent things",
                    "target_count": 5,
                    "entity_type": "companies",
                },
            )

        assert response.status_code == 404
        assert "matching entities" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_find_default_values(self, client: AsyncClient):
        """POST /find works with only required 'criteria' field."""
        with patch("app.api.find.ListBuilder") as MockBuilder:
            mock_instance = MagicMock()
            mock_instance.build_list = AsyncMock(return_value=MOCK_BUILD_RESULT)
            MockBuilder.return_value = mock_instance

            response = await client.post(
                "/api/find",
                json={"criteria": "Top IT companies"},
            )

        assert response.status_code == 200
        # Verify build_list was called with defaults
        call_kwargs = mock_instance.build_list.call_args.kwargs
        assert call_kwargs["target_count"] == 25
        assert call_kwargs["entity_type"] == "companies"
