from __future__ import annotations

import asyncio
from dataclasses import asdict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app_service.agent_controller import AgentController


def create_ws_router(controller: AgentController) -> APIRouter:
    router = APIRouter()

    @router.websocket("/ws/state")
    async def state_socket(websocket: WebSocket) -> None:
        await websocket.accept()
        try:
            while True:
                await websocket.send_json(asdict(controller.state()))
                await asyncio.sleep(0.2)
        except WebSocketDisconnect:
            return

    return router
