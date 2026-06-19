from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app_service.agent_controller import AgentController
from app_service.api import create_api_router
from app_service.ws import create_ws_router


def make_client(tmp_path: Path) -> TestClient:
    profiles = tmp_path / "configs" / "profiles"
    profiles.mkdir(parents=True)
    (profiles / "default_1920x1080.json").write_text(
        '{"profile_id":"default_1920x1080","window_title":"unit","source_resolution":[1920,1080],"normalized_resolution":[1280,720],"rois":{}}',
        encoding="utf-8",
    )
    app = FastAPI()
    controller = AgentController(root=tmp_path)
    app.include_router(create_api_router(controller))
    app.include_router(create_ws_router(controller))
    return TestClient(app)


def test_goal_execute_endpoint_and_learning_review_flow(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    response = client.post(
        "/goals/execute",
        json={
            "goal_text": "做这个新的支线任务",
            "profile": "default_1920x1080",
            "live_mode": False,
            "mode": "safe-window",
            "exploration_profile": "aggressive_deep_probe",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["compiled_strategy"] == "unknown_autonomous_exploration"
    assert len(data["learning_review_queue"]) >= 1

    queue = client.get("/goals/learning_review")
    assert queue.status_code == 200
    items = queue.json()["items"]
    assert len(items) >= 1
    patch_id = items[0]["patch_id"]

    adjusted = client.post(
        f"/goals/learning_review/{patch_id}/adjust",
        json={"adjustments": {"strategy": "favor_interact"}},
    )
    assert adjusted.status_code == 200
    assert adjusted.json()["status"] == "adjusted"

    rolled_back = client.post(f"/goals/learning_review/{patch_id}/rollback")
    assert rolled_back.status_code == 200
    assert rolled_back.json()["status"] == "rolled_back"
