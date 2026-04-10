import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.api.ws import ConnectionManager


# ---------------------------------------------------------------------------
# ConnectionManager unit tests
# ---------------------------------------------------------------------------

class TestConnectionManager:
    @pytest.mark.asyncio
    async def test_connect_adds_websocket_to_table(self):
        manager = ConnectionManager()
        mock_ws = MagicMock()
        mock_ws.accept = AsyncMock()

        await manager.connect(mock_ws, "table-123")

        assert "table-123" in manager.connections
        assert mock_ws in manager.connections["table-123"]
        mock_ws.accept.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_multiple_clients_to_same_table(self):
        manager = ConnectionManager()
        ws1 = MagicMock()
        ws1.accept = AsyncMock()
        ws2 = MagicMock()
        ws2.accept = AsyncMock()

        await manager.connect(ws1, "table-abc")
        await manager.connect(ws2, "table-abc")

        assert len(manager.connections["table-abc"]) == 2

    def test_disconnect_removes_websocket(self):
        manager = ConnectionManager()
        mock_ws = MagicMock()
        manager.connections["table-xyz"] = [mock_ws]

        manager.disconnect(mock_ws, "table-xyz")

        assert mock_ws not in manager.connections["table-xyz"]

    def test_disconnect_nonexistent_table_does_not_raise(self):
        manager = ConnectionManager()
        mock_ws = MagicMock()
        # Should not raise even if table_id is not in connections
        manager.disconnect(mock_ws, "nonexistent-table")

    def test_disconnect_only_removes_target_websocket(self):
        manager = ConnectionManager()
        ws1 = MagicMock()
        ws2 = MagicMock()
        manager.connections["table-multi"] = [ws1, ws2]

        manager.disconnect(ws1, "table-multi")

        assert ws1 not in manager.connections["table-multi"]
        assert ws2 in manager.connections["table-multi"]

    @pytest.mark.asyncio
    async def test_broadcast_sends_message_to_all_connected_clients(self):
        manager = ConnectionManager()
        ws1 = MagicMock()
        ws1.send_text = AsyncMock()
        ws2 = MagicMock()
        ws2.send_text = AsyncMock()
        manager.connections["table-broadcast"] = [ws1, ws2]

        await manager.broadcast_cell_update(
            "table-broadcast", "cell-001", "col-001", "test@example.com", "found"
        )

        ws1.send_text.assert_called_once()
        ws2.send_text.assert_called_once()

        # Verify message content
        sent_message = json.loads(ws1.send_text.call_args[0][0])
        assert sent_message["type"] == "cell_update"
        assert sent_message["cell_id"] == "cell-001"
        assert sent_message["column_id"] == "col-001"
        assert sent_message["value"] == "test@example.com"
        assert sent_message["status"] == "found"

    @pytest.mark.asyncio
    async def test_broadcast_no_connected_clients_does_not_raise(self):
        manager = ConnectionManager()
        # No connections for this table
        await manager.broadcast_cell_update("empty-table", "cell-001", None, None, "pending")

    @pytest.mark.asyncio
    async def test_broadcast_removes_dead_connections(self):
        manager = ConnectionManager()
        ws_alive = MagicMock()
        ws_alive.send_text = AsyncMock()
        ws_dead = MagicMock()
        ws_dead.send_text = AsyncMock(side_effect=Exception("Connection closed"))

        manager.connections["table-dead"] = [ws_dead, ws_alive]

        await manager.broadcast_cell_update("table-dead", "cell-002", "col-002", "val", "found")

        # Dead connection should be removed
        assert ws_dead not in manager.connections["table-dead"]
        # Alive connection should remain
        assert ws_alive in manager.connections["table-dead"]

    @pytest.mark.asyncio
    async def test_broadcast_message_format_with_none_value(self):
        manager = ConnectionManager()
        ws = MagicMock()
        ws.send_text = AsyncMock()
        manager.connections["table-null"] = [ws]

        await manager.broadcast_cell_update("table-null", "cell-003", None, None, "not_found")

        sent_message = json.loads(ws.send_text.call_args[0][0])
        assert sent_message["value"] is None
        assert sent_message["status"] == "not_found"

    @pytest.mark.asyncio
    async def test_connect_initializes_empty_list_for_new_table(self):
        manager = ConnectionManager()
        ws = MagicMock()
        ws.accept = AsyncMock()

        assert "new-table" not in manager.connections
        await manager.connect(ws, "new-table")
        assert "new-table" in manager.connections
        assert len(manager.connections["new-table"]) == 1

    @pytest.mark.asyncio
    async def test_broadcast_sends_json_string(self):
        manager = ConnectionManager()
        ws = MagicMock()
        ws.send_text = AsyncMock()
        manager.connections["table-json"] = [ws]

        await manager.broadcast_cell_update("table-json", "cell-004", "col-004", "value", "running")

        call_arg = ws.send_text.call_args[0][0]
        assert isinstance(call_arg, str)
        # Must be valid JSON
        parsed = json.loads(call_arg)
        assert isinstance(parsed, dict)
