from __future__ import annotations

import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app_service.agent_controller import AgentController
from app_service.api import create_api_router
from app_service.skill_manager import SkillDefinition, SkillReplayRuntime, SkillStep, SkillValidator
from app_service.ws import create_ws_router
from execution.console_backend import ConsoleInputBackend
from execution.input_worker import InputWorker


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


def test_recording_to_skill_draft(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    assert client.post("/skills/record/start", json={"backend": "mock"}).json()["ok"] is True
    client.post(
        "/skills/record/event",
        json={
            "event_type": "mouse_move",
            "payload": {"dx": 12, "dy": -2},
            "target_state": "TRACKED",
            "focus_state": "FOCUSED",
            "visual_triggers": {"target_visible": True},
        },
    )
    client.post("/skills/record/marker", json={"marker": "manual_checkpoint"})
    draft = client.post("/skills/record/stop").json()["draft"]
    assert draft["raw_events"]
    assert draft["segments"]
    assert any(segment["reason"] in {"visual_state_change", "user_marker", "recording_end"} for segment in draft["segments"])
    assert "target_visible" in draft["suggested_preconditions"]


def test_no_permanent_key_down(tmp_path: Path) -> None:
    (tmp_path / "configs" / "profiles").mkdir(parents=True)
    (tmp_path / "configs" / "profiles" / "default_1920x1080.json").write_text("{}", encoding="utf-8")
    skill = SkillDefinition(
        skill_id="bad",
        name="Bad",
        type="ui",
        version=1,
        metadata={},
        environment_profile="default_1920x1080",
        preconditions=[],
        steps=[SkillStep(step_id="down", type="key_down", interruptible=True, params={"key": "E"})],
        visual_triggers={},
        success_criteria=[],
        failure_policy={"max_retries": 1},
        cleanup=[],
        safety={"dry_run_default": True, "interruptible": True, "require_focus": True, "max_duration_ms": 1000},
    )
    errors = SkillValidator(tmp_path).validate(skill)
    assert any("permanent key_down" in error for error in errors)


def test_replay_uses_input_lease() -> None:
    backend = ConsoleInputBackend()
    worker = InputWorker(backend=backend, tick_seconds=0.005)
    worker.start()
    try:
        skill = _replay_skill()
        result = SkillReplayRuntime(worker).replay(skill, mode="safe-window", confirm=True, focus_ok=True)
        time.sleep(0.05)
        assert result.status == "SUCCESS"
        assert result.payload["leases_submitted"] >= 2
        assert any(event.action in {"key_down", "mouse_move"} for event in backend.events_snapshot())
    finally:
        worker.stop()


def test_safe_replay_requires_focus() -> None:
    worker = InputWorker(backend=ConsoleInputBackend(), tick_seconds=0.005)
    result = SkillReplayRuntime(worker).replay(_replay_skill(), mode="safe-window", confirm=True, focus_ok=False)
    assert result.status == "FAILED"
    assert "focus" in str(result.failure_code)


def test_skill_versioning(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    client.post("/skills/record/start", json={"backend": "mock"})
    client.post("/skills/record/stop")
    first = client.post("/skills/record/save", json={"skill_id": "recorded_unit", "name": "Recorded Unit"}).json()
    client.post("/skills/record/start", json={"backend": "mock"})
    client.post("/skills/record/stop")
    second = client.post("/skills/record/save", json={"skill_id": "recorded_unit", "name": "Recorded Unit"}).json()
    versions = client.get("/skills/recorded_unit/versions").json()
    assert first["version"] == 1
    assert second["version"] == 2
    assert versions["versions"]


def _replay_skill() -> SkillDefinition:
    return SkillDefinition(
        skill_id="replay",
        name="Replay",
        type="ui",
        version=1,
        metadata={},
        environment_profile="default_1920x1080",
        preconditions=[],
        steps=[
            SkillStep(step_id="tap", type="key_tap", interruptible=True, params={"key": "E", "lease_ms": 40}),
            SkillStep(step_id="move", type="mouse_move", interruptible=True, params={"dx": 3, "dy": -1, "lease_ms": 40}),
            SkillStep(step_id="wait", type="wait", interruptible=True, params={"duration_ms": 5, "chunk_ms": 5}),
        ],
        visual_triggers={},
        success_criteria=[],
        failure_policy={"max_retries": 1},
        cleanup=[],
        safety={"dry_run_default": True, "interruptible": True, "require_focus": True, "max_duration_ms": 1000},
    )
