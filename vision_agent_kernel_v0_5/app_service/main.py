from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app_service.agent_controller import AgentController
from app_service.api import create_api_router
from app_service.ws import create_ws_router


controller = AgentController()

app = FastAPI(
    title="Vision Agent Local Service",
    version="0.5.0-stage19",
    description="Local dry-run-first service shell for the vision agent kernel.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173", "tauri://localhost"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(create_api_router(controller))
app.include_router(create_ws_router(controller))
