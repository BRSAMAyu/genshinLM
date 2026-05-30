"""Tests for ui_flow_engine and ui_flows modules."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from core.events import Interrupt
from core.state_bus import StateBus
from core.timebase import Timebase
from core.types import InputLease, Observation, SkillResult, UIStateEstimate
from interaction.ui_flow_engine import (
    UIFlow,
    UIFlowExecutor,
    UIFlowInterrupted,
    UIFlowPreconditionFailed,
    UIFlowTimeout,
    UIStep,
    click,
    click_menu_button,
    confirm,
    delay,
    open_menu,
    press,
    wait_loading,
    wait_not_loading,
    wait_state,
    STEP_PRESS_KEY,
    STEP_CLICK_AT,
    STEP_WAIT_STATE,
    STEP_DELAY,
    STEP_CONFIRM,
    STEP_SCROLL,
    STEP_OPEN_MENU,
)
from interaction.ui_flows import (
    ALL_FLOWS,
    OPEN_CHARACTER_MENU,
    CLOSE_MENU,
    TELEPORT_FLOW,
    CHARACTER_LEVEL_UP,
    WISH_TEN_PULL,
    get_flow,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeBackend:
    """Minimal fake backend that records calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []
        self._rect = MagicMock()
        self._rect.left = 0
        self._rect.top = 0
        self._rect.width = 1920
        self._rect.height = 1080
        self._rect.center = (960, 540)

    def click_at(self, x: int, y: int, reason: str = "") -> None:
        self.calls.append(("click_at", x, y, reason))

    def left_click(self, reason: str = "") -> None:
        self.calls.append(("left_click", reason))

    def right_click(self, reason: str = "") -> None:
        self.calls.append(("right_click", reason))

    def mouse_scroll(self, delta: int = -1, reason: str = "") -> None:
        self.calls.append(("mouse_scroll", delta, reason))

    def hold_click(self, duration_sec: float = 0.5, reason: str = "") -> None:
        self.calls.append(("hold_click", duration_sec, reason))

    def key_down(self, key: str, reason: str = "") -> None:
        self.calls.append(("key_down", key, reason))

    def key_up(self, key: str, reason: str = "") -> None:
        self.calls.append(("key_up", key, reason))

    def client_rect(self):
        return self._rect

    def is_target_focused(self) -> bool:
        return True


class FakeInputWorker:
    """Accepts all leases and records them."""

    def __init__(self, backend: FakeBackend) -> None:
        self.backend = backend
        self.leases: list[InputLease] = []

    def submit_lease(self, lease: InputLease) -> bool:
        self.leases.append(lease)
        # Simulate key press on backend
        for key, state in lease.key_states.items():
            if state == "DOWN":
                self.backend.key_down(key, reason=lease.reason)
            elif state == "UP":
                self.backend.key_up(key, reason=lease.reason)
        return True


def _make_executor(
    screen_state: str = "world_hud",
) -> tuple[UIFlowExecutor, StateBus, FakeInputWorker, FakeBackend]:
    bus = StateBus(observation_history_capacity=5)
    backend = FakeBackend()
    worker = FakeInputWorker(backend)
    tb = Timebase()

    # Publish an initial observation with the desired screen state
    obs = Observation(
        frame_id=1,
        t_capture=tb.now(),
        t_processed=tb.now(),
        latency_ms=1.0,
        viewport_size=(1920, 1080),
        target_track=None,
        obstacle_field=None,
        ui_state=UIStateEstimate(
            frame_id=1, timestamp=tb.now(), state=screen_state, confidence=0.9,
        ),
        visual_triggers={},
        os_focus=MagicMock(focused=True),
    )
    bus.publish_observation(obs)

    classifier = MagicMock()
    executor = UIFlowExecutor(
        state_bus=bus,
        input_worker=worker,  # type: ignore[arg-type]
        timebase=tb,
        wait_chunk_ms=20,
    )
    return executor, bus, worker, backend


# ---------------------------------------------------------------------------
# Step construction tests
# ---------------------------------------------------------------------------

class TestStepConstruction:
    def test_press_key(self) -> None:
        step = press("escape", reason="close")
        assert step.type == STEP_PRESS_KEY
        assert step.key == "escape"

    def test_click(self) -> None:
        step = click(0.5, 0.8, reason="test")
        assert step.type == STEP_CLICK_AT
        assert step.nx == 0.5
        assert step.ny == 0.8

    def test_wait_state(self) -> None:
        step = wait_state("dialog", timeout_ms=3000)
        assert step.target_state == "dialog"
        assert step.timeout_ms == 3000

    def test_confirm(self) -> None:
        step = confirm(reason="ok")
        assert step.type == STEP_CONFIRM

    def test_delay(self) -> None:
        step = delay(500)
        assert step.type == STEP_DELAY
        assert step.timeout_ms == 500

    def test_click_menu_button_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown menu button"):
            click_menu_button("nonexistent")


# ---------------------------------------------------------------------------
# Executor tests
# ---------------------------------------------------------------------------

class TestUIFlowExecutor:
    def test_press_key_step(self) -> None:
        executor, _, worker, backend = _make_executor()
        flow = UIFlow(name="test_press", steps=(press("escape", reason="test"),))
        result = executor.execute(flow)
        assert result.status == "SUCCESS"
        assert any("escape" in str(c) for c in backend.calls)

    def test_click_at_step(self) -> None:
        executor, _, worker, backend = _make_executor()
        flow = UIFlow(name="test_click", steps=(click(0.5, 0.5, reason="center"),))
        result = executor.execute(flow)
        assert result.status == "SUCCESS"
        assert ("click_at", 960, 540, "center") in backend.calls

    def test_delay_step(self) -> None:
        executor, _, _, _ = _make_executor()
        flow = UIFlow(name="test_delay", steps=(delay(50),))
        start = time.perf_counter()
        result = executor.execute(flow)
        elapsed = time.perf_counter() - start
        assert result.status == "SUCCESS"
        assert elapsed >= 0.03  # at least some delay happened

    def test_confirm_step(self) -> None:
        executor, _, _, backend = _make_executor()
        flow = UIFlow(name="test_confirm", steps=(confirm(reason="ok"),))
        result = executor.execute(flow)
        assert result.status == "SUCCESS"
        # Confirm should click at ~0.65, 0.85
        click_calls = [c for c in backend.calls if c[0] == "click_at"]
        assert len(click_calls) == 1
        assert click_calls[0][1] == int(0.65 * 1920)
        assert click_calls[0][2] == int(0.85 * 1080)

    def test_scroll_step(self) -> None:
        executor, _, _, backend = _make_executor()
        flow = UIFlow(name="test_scroll", steps=(UIStep(type=STEP_SCROLL, delta=3),))
        result = executor.execute(flow)
        assert result.status == "SUCCESS"
        scroll_calls = [c for c in backend.calls if c[0] == "mouse_scroll"]
        assert len(scroll_calls) == 3

    def test_multi_step_flow(self) -> None:
        executor, _, _, backend = _make_executor()
        flow = UIFlow(
            name="test_multi",
            steps=(
                press("escape", reason="open"),
                delay(50),
                click(0.5, 0.5, reason="click"),
            ),
        )
        result = executor.execute(flow)
        assert result.status == "SUCCESS"
        assert len(backend.calls) >= 3

    def test_precondition_failed(self) -> None:
        executor, _, _, _ = _make_executor(screen_state="world_hud")
        flow = UIFlow(
            name="test_precondition",
            steps=(press("f"),),
            precondition_state="dialog",
        )
        result = executor.execute(flow)
        assert result.status == "PRECONDITION_FAILED"

    def test_precondition_passes(self) -> None:
        executor, _, _, _ = _make_executor(screen_state="dialog")
        flow = UIFlow(
            name="test_precondition_ok",
            steps=(press("f"),),
            precondition_state="dialog",
        )
        result = executor.execute(flow)
        assert result.status == "SUCCESS"

    def test_wait_state_success(self) -> None:
        executor, bus, _, _ = _make_executor(screen_state="world_hud")
        # Schedule a state change after a short delay
        def _change_state() -> None:
            time.sleep(0.1)
            obs = Observation(
                frame_id=2,
                t_capture=time.perf_counter(),
                t_processed=time.perf_counter(),
                latency_ms=1.0,
                viewport_size=(1920, 1080),
                target_track=None,
                obstacle_field=None,
                ui_state=UIStateEstimate(
                    frame_id=2, timestamp=time.perf_counter(), state="dialog", confidence=0.9,
                ),
                visual_triggers={},
                os_focus=MagicMock(focused=True),
            )
            bus.publish_observation(obs)

        t = threading.Thread(target=_change_state, daemon=True)
        t.start()

        flow = UIFlow(name="test_wait", steps=(wait_state("dialog", timeout_ms=2000),))
        result = executor.execute(flow)
        assert result.status == "SUCCESS"

    def test_wait_state_timeout(self) -> None:
        executor, _, _, _ = _make_executor(screen_state="world_hud")
        flow = UIFlow(
            name="test_wait_timeout",
            steps=(wait_state("dialog", timeout_ms=100),),
        )
        result = executor.execute(flow)
        assert result.status == "TIMEOUT"

    def test_interrupt_cancels(self) -> None:
        executor, bus, _, _ = _make_executor()
        # Inject a P0 interrupt
        bus.publish_interrupt(Interrupt(
            priority=0, timestamp=time.perf_counter(),
            code="EMERGENCY_STOP", source="test",
        ))
        flow = UIFlow(name="test_interrupt", steps=(delay(500),))
        result = executor.execute(flow)
        assert result.status == "CANCELLED"
        assert result.failure_code == "EMERGENCY_STOP"

    def test_escape_on_failure(self) -> None:
        executor, _, _, backend = _make_executor()
        flow = UIFlow(
            name="test_escape_cleanup",
            steps=(UIStep(type="invalid_type"),),
            escape_on_failure=True,
        )
        result = executor.execute(flow)
        assert result.status == "FAILED"
        # Should have pressed escape for cleanup
        key_calls = [c for c in backend.calls if c[0] in ("key_down", "key_up") and "escape" in str(c)]
        assert len(key_calls) >= 1

    def test_open_menu_step(self) -> None:
        executor, _, _, backend = _make_executor()
        flow = UIFlow(name="test_open_menu", steps=(open_menu(),))
        result = executor.execute(flow)
        assert result.status == "SUCCESS"
        assert any("escape" in str(c) for c in backend.calls)


# ---------------------------------------------------------------------------
# UIFlow library tests
# ---------------------------------------------------------------------------

class TestUIFlowsLibrary:
    def test_all_flows_have_names(self) -> None:
        for name, flow in ALL_FLOWS.items():
            assert flow.name == name
            assert len(flow.steps) > 0

    def test_get_flow_existing(self) -> None:
        flow = get_flow("open_character_menu")
        assert flow is OPEN_CHARACTER_MENU

    def test_get_flow_missing_raises(self) -> None:
        with pytest.raises(KeyError, match="unknown flow"):
            get_flow("nonexistent_flow")

    def test_teleport_flow_has_load_wait(self) -> None:
        types = [s.type for s in TELEPORT_FLOW.steps]
        assert STEP_WAIT_STATE in types or "wait_loading" in types

    def test_wish_flow_structure(self) -> None:
        types = [s.type for s in WISH_TEN_PULL.steps]
        assert STEP_CLICK_AT in types
        assert STEP_DELAY in types

    def test_character_level_up_flow(self) -> None:
        types = [s.type for s in CHARACTER_LEVEL_UP.steps]
        assert STEP_CLICK_AT in types

    def test_close_menu_flow(self) -> None:
        assert CLOSE_MENU.steps[0].key == "escape"

    def test_flow_count_minimum(self) -> None:
        assert len(ALL_FLOWS) >= 20, f"expected at least 20 flows, got {len(ALL_FLOWS)}"
