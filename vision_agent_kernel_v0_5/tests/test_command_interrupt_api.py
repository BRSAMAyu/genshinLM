from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app_service.agent_controller import AgentController
from app_service.api import create_api_router
from app_service.goal_executor import GoalExecutionResult
from app_service.ws import create_ws_router


def _make_controller(tmp_path: Path) -> AgentController:
    profiles = tmp_path / "configs" / "profiles"
    profiles.mkdir(parents=True)
    (profiles / "default_1920x1080.json").write_text(
        '{"profile_id":"default_1920x1080","window_title":"unit",'
        '"source_resolution":[1920,1080],"normalized_resolution":[1280,720],"rois":{}}',
        encoding="utf-8",
    )
    return AgentController(root=tmp_path)


def _make_client(controller: AgentController) -> TestClient:
    app = FastAPI()
    app.include_router(create_api_router(controller))
    app.include_router(create_ws_router(controller))
    return TestClient(app)


def _stub_result(goal_text: str) -> GoalExecutionResult:
    return GoalExecutionResult(
        ok=True,
        goal_text=goal_text,
        profile="default_1920x1080",
        live_mode=False,
        mode="dry-run",
        exploration_profile="aggressive_deep_probe",
        compiled_strategy="stub_strategy",
        goal_phase="completed",
        mission_id="mission_stub",
        completed_nodes=["n0"],
        failed_nodes=[],
        learning_review_queue=[],
        node_traces=[],
        error=None,
    )


def test_command_parses_intent_and_invokes_execute_goal(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path)
    # Mock the live loop so no real game is required.
    mock_execute = MagicMock(side_effect=lambda **kwargs: _stub_result(kwargs["goal_text"]))
    controller._goal_executor.execute_goal = mock_execute  # type: ignore[method-assign]
    client = _make_client(controller)

    response = client.post("/command", json={"text": "做每日委托", "live_mode": False})
    assert response.status_code == 200
    data = response.json()

    # UniversalEntryAgent parsed the NL text into a structured intent.
    assert data["accepted"] is True
    assert data["goal_type"] == "daily"
    assert data["intent"]["goal_type"] == "daily"
    assert data["intent"]["raw_text"] == "做每日委托"
    assert data["intent"]["confidence"] > 0.0

    # The command is dispatched to a background worker: immediate response is
    # QUEUED with a job id and no execution payload yet.
    assert data["dispatched"] is True
    assert data["status"] == "QUEUED"
    assert data["job_id"]
    assert data["execution"] is None

    # The worker eventually invokes execute_goal in dry-run (never live).
    job_id = data["job_id"]
    deadline = time.perf_counter() + 5.0
    status = None
    while time.perf_counter() < deadline:
        status = client.get(f"/command/status/{job_id}").json()
        if status["status"] in {"SUCCEEDED", "FAILED"}:
            break
        time.sleep(0.02)
    assert status is not None
    assert status["status"] == "SUCCEEDED"
    assert mock_execute.called
    call_kwargs = mock_execute.call_args.kwargs
    assert call_kwargs["goal_text"] == "做每日委托"
    assert call_kwargs["live_mode"] is False
    assert call_kwargs["mode"] == "dry-run"
    assert status["dispatched"] is True
    assert status["execution"]["mission_id"] == "mission_stub"


def test_command_empty_text_is_rejected_without_dispatch(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path)
    mock_execute = MagicMock(side_effect=lambda **kwargs: _stub_result(kwargs["goal_text"]))
    controller._goal_executor.execute_goal = mock_execute  # type: ignore[method-assign]
    client = _make_client(controller)

    response = client.post("/command", json={"text": "   "})
    assert response.status_code == 200
    data = response.json()
    assert data["accepted"] is False
    assert data["dispatched"] is False
    assert not mock_execute.called


def test_interrupt_stop_enqueues_p0_emergency(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path)
    client = _make_client(controller)

    response = client.post("/interrupt", json={"kind": "stop", "text": "halt now"})
    assert response.status_code == 200
    data = response.json()
    assert data["accepted"] is True
    assert data["priority"] == 0
    assert data["code"] == "EMERGENCY_STOP"

    # P0 emergency-stop interrupt landed on the StateBus event queue.
    interrupt = controller._state_bus.next_interrupt(timeout=0.0)
    assert interrupt is not None
    assert interrupt.priority == 0
    assert interrupt.code == "EMERGENCY_STOP"
    assert interrupt.requires_input_release is True
    # Safety: emergency stop drives the controller into a terminal stopped state.
    assert controller.state().mode == "EMERGENCY_STOPPED"


def test_interrupt_override_enqueues_p2_human_override(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path)
    client = _make_client(controller)

    response = client.post("/interrupt", json={"kind": "override", "text": "do X instead"})
    assert response.status_code == 200
    data = response.json()
    assert data["accepted"] is True
    assert data["priority"] == 20
    assert data["code"] == "HUMAN_OVERRIDE"

    interrupt = controller._state_bus.next_interrupt(timeout=0.0)
    assert interrupt is not None
    assert interrupt.priority == 20  # P2_HUMAN_OVERRIDE
    assert interrupt.code == "HUMAN_OVERRIDE"
    assert interrupt.payload["reason"] == "do X instead"
    # Override does not force input release (loop reacts, no hard halt).
    assert interrupt.requires_input_release is False
