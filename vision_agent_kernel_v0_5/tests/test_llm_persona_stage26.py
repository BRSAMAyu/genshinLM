from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app_service.agent_controller import AgentController
from app_service.api import create_api_router
from app_service.ws import create_ws_router
from llm.http_provider import _extract_json_object
from llm.request_guard import LLMRequestGuard, LLMUsageBudget
from llm.sandbox_validator import SandboxValidator
from app_service.skill_manager import SkillStore


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


def test_minimax_without_key_falls_back_to_mock(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    client = make_client(tmp_path)
    plan = client.post("/planner/task", json={"goal": "analyze sandbox state", "provider": "minimax"}).json()
    assert plan["provider"] == "mock"
    assert plan["provider_error"]
    assert plan["validation"]["ok"] is True


def test_forbidden_tool_is_rejected(tmp_path: Path) -> None:
    store = SkillStore(tmp_path)
    validator = SandboxValidator(tmp_path, store)
    result = validator.validate_task_spec(
        {
            "task_id": "bad",
            "requires_user_confirmation": True,
            "input_mode": "dry-run",
            "max_retries": 1,
            "max_duration_sec": 10,
            "tools": ["direct_click"],
            "skill_chain": [],
            "graph": {"nodes": ["COMPLETE"], "edges": []},
        }
    )
    assert result["ok"] is False
    assert any("unsafe" in error for error in result["errors"])


def test_request_guard_limits_calls() -> None:
    guard = LLMRequestGuard(LLMUsageBudget(max_calls_per_minute=2, max_calls_per_task=1, max_estimated_tokens_per_task=100))
    guard.check(estimated_tokens=50)
    try:
        guard.check(estimated_tokens=1)
    except RuntimeError as exc:
        assert "max calls per task" in str(exc)
    else:
        raise AssertionError("guard should block second task call")


def test_persona_event_includes_emotion(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    response = client.post("/persona/event", json={"event_code": "DODGE_REFLEX", "persona_id": "calm_operator", "payload": {}}).json()
    assert response["emotion"] == "warning"
    assert response["message"]


def test_failure_explanation_shape(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    response = client.post(
        "/planner/explain_failure",
        json={"provider": "mock", "summary": {"failure_code": "TARGET_LOST"}},
    ).json()
    assert "user_friendly_summary" in response
    assert "possible_skill_patch" in response


def test_json_extraction_from_fenced_response() -> None:
    data = _extract_json_object('```json\n{"task_id":"x","tools":["list_skills"]}\n```')
    assert data["task_id"] == "x"
