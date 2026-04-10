import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter()


class ConnectionManager:
    """Manages WebSocket connections per table."""

    def __init__(self):
        self.connections: dict[str, list[WebSocket]] = {}  # table_id -> [websockets]

    async def connect(self, websocket: WebSocket, table_id: str):
        await websocket.accept()
        if table_id not in self.connections:
            self.connections[table_id] = []
        self.connections[table_id].append(websocket)
        logger.info(f"WebSocket connected for table {table_id}")

    def disconnect(self, websocket: WebSocket, table_id: str):
        if table_id in self.connections:
            self.connections[table_id] = [ws for ws in self.connections[table_id] if ws != websocket]
        logger.info(f"WebSocket disconnected for table {table_id}")

    async def broadcast_cell_update(self, table_id: str, cell_id: str, column_id: str | None, value: str | None, status: str):
        """Push a cell update to all connected clients for this table."""
        if table_id not in self.connections:
            return
        message = json.dumps({
            "type": "cell_update",
            "cell_id": cell_id,
            "column_id": column_id,
            "value": value,
            "status": status,
        })
        dead = []
        for ws in self.connections[table_id]:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws, table_id)


# Global instance
manager = ConnectionManager()


@router.websocket("/ws/{table_id}")
async def websocket_endpoint(websocket: WebSocket, table_id: str):
    await manager.connect(websocket, table_id)
    try:
        while True:
            # Keep connection alive, handle any client messages
            data = await websocket.receive_text()
            # Client can send ping/pong or other messages
    except WebSocketDisconnect:
        manager.disconnect(websocket, table_id)
