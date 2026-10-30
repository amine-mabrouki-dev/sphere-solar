import json
import os
from typing import Dict, Set

import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

SECRET_KEY = os.getenv("JWT_SECRET", "change-me-in-production")
ALGORITHM  = "HS256"

router = APIRouter(tags=["websocket"])


class ConnectionManager:
    def __init__(self):
        # inverter_id → set of open WebSocket connections
        self._by_inverter: Dict[int, Set[WebSocket]] = {}
        # ws → set of subscribed inverter_ids (for clean teardown)
        self._subs: Dict[WebSocket, Set[int]] = {}

    def subscribe(self, ws: WebSocket, inverter_id: int) -> None:
        self._by_inverter.setdefault(inverter_id, set()).add(ws)
        self._subs.setdefault(ws, set()).add(inverter_id)

    def disconnect(self, ws: WebSocket) -> None:
        for inv_id in self._subs.pop(ws, set()):
            self._by_inverter.get(inv_id, set()).discard(ws)

    async def broadcast(self, inverter_id: int, data: dict) -> None:
        dead: Set[WebSocket] = set()
        for ws in list(self._by_inverter.get(inverter_id, set())):
            try:
                await ws.send_text(json.dumps(data))
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


async def broadcaster(inverter_id: int, data: dict) -> None:
    """Registered with mqtt_worker on startup; routes live readings to WS clients."""
    await manager.broadcast(inverter_id, data)


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, token: str = Query(...)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        int(payload["sub"])  # validates sub is a user id
    except jwt.PyJWTError:
        await ws.close(code=4001)
        return

    await ws.accept()
    try:
        while True:
            # Client sends {"subscribe": [1, 2, 3]} to declare which inverters it wants
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
                for inv_id in msg.get("subscribe", []):
                    manager.subscribe(ws, int(inv_id))
            except Exception:
                pass
    except WebSocketDisconnect:
        manager.disconnect(ws)
