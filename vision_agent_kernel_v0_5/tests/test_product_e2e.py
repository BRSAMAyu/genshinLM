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


def test_product_checklist_and_dry_run_e2e(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    checklist = client.get("/product/checklist").json()
    result = client.post(
        "/product/run_e2e",
        json={"mode": "dry-run", "seconds": 3, "use_mock_llm": True, "chaos": "none"},
    ).json()
    latest = client.get("/product/latest_report").json()

    assert checklist["ok"] is True
    assert result["ok"] is True
    assert result["selected_profile"] == "default_1920x1080"
    assert result["selected_skill"] == "demo_product_skill"
    assert result["release_all_called"] is True
    assert Path(result["report_path"]).exists()
    assert latest["report_markdown"] is not None


def test_product_safe_window_requires_authorized_window_and_confirmation(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    result = client.post(
        "/product/run_e2e",
        json={"mode": "safe-window", "seconds": 1, "use_mock_llm": True, "chaos": "none"},
    ).json()

    assert result["ok"] is False
    assert result["release_all_called"] is True
    assert "requires selecting an authorized test window" in result["error"]
