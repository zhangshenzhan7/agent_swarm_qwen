"""WebSocket 路由"""

import json
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from state import state

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    state.websockets.append(websocket)

    try:
        await websocket.send_text(json.dumps({
            "type": "init",
            "data": {
                "agents": state.get_all_agents(),
                "tasks": list(state.tasks.values()),
            },
            "timestamp": datetime.now().isoformat()
        }, ensure_ascii=False, default=str))

        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        if websocket in state.websockets:
            state.websockets.remove(websocket)
