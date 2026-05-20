from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app_service.agent_controller import AgentController
from app_service.api import create_api_router
from app_service.ws import create_ws_router
from combat.danger_detector import DangerDetector
from combat.dodge_policy import DodgePolicy
from llm.tool_schema import tool_allowed


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


def valid_skill_payload() -> dict:
    return {
        "skill_id": "unit_combo",
        "name": "Unit Combo",
        "type": "combat",
        "version": 1,
        "metadata": {"author": "test"},
        "environment_profile": "default_1920x1080",
        "preconditions": ["require_focus"],
        "steps": [
            {
                "step_id": "wait_started",
                "type": "wait_visual_trigger",
                "timeout_ms": 1000,
                "interruptible": True,
                "params": {"trigger": "action_started", "chunk_ms": 100},
            },
            {
                "step_id": "fallback",
                "type": "fallback_basic_loop",
                "interruptible": True,
                "params": {},
            },
        ],
        "visual_triggers": {"action_started": {"type": "target_color_green"}},
        "success_criteria": ["visual_action_completed"],
        "failure_policy": {"max_retries": 1, "fallback": "pause_and_reacquire"},
        "cleanup": [{"type": "release_all"}],
        "safety": {"dry_run_default": True, "interruptible": True, "require_focus": True, "max_duration_ms": 3000},
    }


def test_skill_record_validate_dry_run_and_versions(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    assert client.post("/skills/record/start").json()["ok"] is True
    draft = client.post("/skills/record/stop").json()["draft"]
    assert draft["segments"]

    created = client.post("/skills", json=valid_skill_payload())
    assert created.status_code == 200
    updated_payload = {**valid_skill_payload(), "metadata": {"author": "test", "updated": True}}
    updated = client.put("/skills/unit_combo", json=updated_payload)
    assert updated.status_code == 200
    assert updated.json()["version"] == 2

    validation = client.post("/skills/unit_combo/validate").json()
    dry_run = client.post("/skills/unit_combo/dry_run").json()
    versions = client.get("/skills/unit_combo/versions").json()

    assert validation["ok"] is True
    assert dry_run["ok"] is True
    assert "unit_combo.v1.json" in versions["versions"]


def test_invalid_skill_cannot_save(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    payload = valid_skill_payload()
    payload["skill_id"] = "bad_skill"
    payload["safety"] = {"dry_run_default": False, "interruptible": False, "require_focus": False}
    response = client.post("/skills", json=payload)
    assert response.status_code == 422


def test_persona_planner_and_combat_api(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    client.post("/skills", json=valid_skill_payload())
    persona = client.post("/persona/event", json={"event_code": "TARGET_LOST", "persona_id": "default_companion", "payload": {}}).json()
    plan = client.post("/planner/task", json={"goal": "complete sandbox task", "provider": "mock"}).json()
    playbook = client.post("/combat/playbook", json={"goal": "safe combat demo"}).json()
    danger = client.post(
        "/combat/danger",
        json={"signals": {"generic_warning_area": 1.0, "projectile_approaching": 1.0, "scripted_testbed_danger": 1.0}, "context_priority": 0.1},
    ).json()

    assert "重新搜索" in persona["message"]
    assert plan["ok"] is True
    assert playbook["ok"] is True
    assert danger["level"] == "HIGH"
    assert danger["interrupt"]["code"] == "DODGE_REFLEX"


def test_tool_schema_and_dodge_cooldown() -> None:
    assert tool_allowed("create_task_spec")
    assert not tool_allowed("direct_click")
    danger = DangerDetector().evaluate({"projectile_approaching": 1.0, "scripted_testbed_danger": 1.0}, context_priority=0.3)
    policy = DodgePolicy(min_interval_ms=1000)
    first = policy.choose_dodge(danger)
    second = policy.choose_dodge(danger)
    assert first["ok"] is True
    assert second["ok"] is False
    assert second["reason"] == "cooldown"
