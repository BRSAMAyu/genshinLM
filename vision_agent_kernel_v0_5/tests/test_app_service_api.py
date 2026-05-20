from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app_service.agent_controller import AgentController
from app_service.api import create_api_router
from app_service.ws import create_ws_router


def make_client(root: Path) -> TestClient:
    app = FastAPI()
    controller = AgentController(root=root)
    app.include_router(create_api_router(controller))
    app.include_router(create_ws_router(controller))
    return TestClient(app)


def test_app_service_health_and_state_endpoints(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    health = client.get("/health")
    state = client.get("/state")

    assert health.status_code == 200
    assert health.json()["status"] == "OK"
    assert state.status_code == 200
    assert state.json()["input_backend"] == "console"


def test_app_service_websocket_state_frame(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    with client.websocket_connect("/ws/state") as websocket:
        data = websocket.receive_json()

    assert data["mode"] in {"STOPPED", "RUNNING", "PAUSED", "EMERGENCY_STOPPED"}
    assert data["input_backend"] == "console"


def test_app_service_start_pause_emergency_endpoints(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    started = client.post("/agent/start")
    paused = client.post("/agent/pause")
    stopped = client.post("/agent/emergency_stop")

    assert started.status_code == 200
    assert started.json()["state"]["input_backend"] == "console"
    assert paused.status_code == 200
    assert paused.json()["state"]["mode"] == "PAUSED"
    assert stopped.status_code == 200
    assert stopped.json()["state"]["mode"] == "EMERGENCY_STOPPED"
    assert stopped.json()["state"]["runtime_health"]["release_all_called"] is True


def test_app_service_calibration_and_model_endpoints(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    profile = {
        "profile": {
            "profile_id": "api_unit_profile",
            "window_title": "unit",
            "source_resolution": [1920, 1080],
            "normalized_resolution": [1280, 720],
            "rois": {
                "main_view": {"mode": "relative", "x": 0.1, "y": 0.1, "w": 0.8, "h": 0.7},
                "minimap": {
                    "mode": "anchor",
                    "anchor": "top-right",
                    "offset_x_px": -320,
                    "offset_y_px": 16,
                    "width_px": 280,
                    "height_px": 280,
                },
            },
        },
        "activate": True,
    }

    saved = client.post("/calibration/profile", json=profile)
    tested = client.post("/calibration/test", json={"profile_id": "api_unit_profile"})
    model_status = client.get("/models/status")

    assert saved.status_code == 200
    assert saved.json()["profile_id"] == "api_unit_profile"
    assert tested.status_code == 200
    assert tested.json()["ok"] is True
    assert model_status.status_code == 200
    assert "ultralytics_available" in model_status.json()
