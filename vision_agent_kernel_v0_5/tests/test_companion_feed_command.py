from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app_service.agent_controller import AgentController
from app_service.api import create_api_router
from app_service.goal_executor import GoalExecutionResult
from app_service.ws import create_ws_router
from core.events import Interrupt


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


# ── (a) synthetic kernel event → companion_message in the AgentState payload ──


def test_synthetic_interrupt_surfaces_as_companion_message(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path)

    # State starts with no companion utterance.
    assert controller.state().companion_message is None

    # Push a synthetic kernel interrupt onto the StateBus (no live game needed).
    interrupt = Interrupt(
        priority=50,
        timestamp=controller._timebase.now(),
        code="TARGET_LOST",
        source="unit_test",
    )
    accepted = controller._state_bus.publish_interrupt(interrupt)
    assert accepted is True

    # The bridge ran it through DialogueGenerator; the AgentState now carries it.
    view = controller.state()
    assert view.companion_message is not None
    assert view.companion_message["event_code"] == "TARGET_LOST"
    assert view.companion_message["source"] == "unit_test"
    assert isinstance(view.companion_message["message"], str)
    assert view.companion_message["message"]  # non-empty utterance


def test_companion_message_appears_in_state_endpoint_payload(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path)
    client = _make_client(controller)

    controller._state_bus.publish_interrupt(
        Interrupt(
            priority=0,
            timestamp=controller._timebase.now(),
            code="EMERGENCY_STOP",
            source="kernel",
        )
    )
    payload = client.get("/state").json()
    assert payload["companion_message"] is not None
    assert payload["companion_message"]["event_code"] == "EMERGENCY_STOP"


def test_companion_feed_buffer_is_bounded(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path)
    feed = controller._companion_feed
    for _ in range(200):
        feed.ingest_event("TARGET_LOST", source="loop")
    # The deque is capped; never grows unbounded regardless of event volume.
    assert len(feed.history()) <= feed._max_history
    assert feed.latest() is not None


def test_unknown_event_codes_are_ignored(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path)
    feed = controller._companion_feed
    assert feed.ingest_event("NOT_A_REAL_CODE") is None
    assert feed.latest() is None


# ── (b) /command returns immediately without blocking; dispatch on a worker ──


def test_command_returns_immediately_with_job_id(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path)

    started = threading.Event()
    release = threading.Event()

    def _blocking_execute(**kwargs: object) -> GoalExecutionResult:
        # Simulate a slow loop construction; the endpoint must NOT wait for this.
        started.set()
        release.wait(timeout=5.0)
        return _stub_result(str(kwargs["goal_text"]))

    controller._goal_executor.execute_goal = MagicMock(side_effect=_blocking_execute)  # type: ignore[method-assign]
    client = _make_client(controller)

    t0 = time.perf_counter()
    response = client.post("/command", json={"text": "做每日委托", "live_mode": False})
    elapsed = time.perf_counter() - t0

    assert response.status_code == 200
    data = response.json()
    # Returned immediately while execute_goal is still blocked in the worker.
    assert elapsed < 1.0
    assert data["accepted"] is True
    assert data["status"] == "QUEUED"
    assert data["job_id"]
    assert data["dispatched"] is True
    assert data["execution"] is None  # not yet finished
    assert data["goal_type"] == "daily"
    assert data["intent"]["goal_type"] == "daily"
    # The companion reply carries persona tone (non-empty).
    assert isinstance(data["reply"], str) and data["reply"]

    # The worker did start in the background.
    assert started.wait(timeout=2.0)

    # Let the worker finish and observe the job reaching a terminal state.
    release.set()
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
    assert status["dispatched"] is True
    assert status["execution"]["mission_id"] == "mission_stub"
    assert controller._goal_executor.execute_goal.called

    # Dry-run default preserved on the worker call.
    call_kwargs = controller._goal_executor.execute_goal.call_args.kwargs
    assert call_kwargs["live_mode"] is False
    assert call_kwargs["mode"] == "dry-run"


def test_command_status_unknown_job_is_404(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path)
    client = _make_client(controller)
    response = client.get("/command/status/does-not-exist")
    assert response.status_code == 404


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
    assert data["job_id"] is None
    assert not mock_execute.called
