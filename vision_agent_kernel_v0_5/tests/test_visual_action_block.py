from __future__ import annotations

import threading
import time

from core.events import Interrupt
from core.state_bus import StateBus
from core.timebase import Timebase
from core.types import FocusState, Observation
from execution.console_backend import ConsoleInputBackend
from execution.input_worker import InputWorker
from execution.visual_action_block import (
    VisualActionBlock,
    VisualActionBlockExecutor,
    VisualActionStep,
)


def _observation(trigger: str | None = None) -> Observation:
    triggers = {trigger: True} if trigger is not None else {}
    return Observation(
        frame_id=1,
        t_capture=time.perf_counter(),
        t_processed=time.perf_counter(),
        latency_ms=0.0,
        viewport_size=(1280, 720),
        target_track=None,
        obstacle_field=None,
        ui_state=None,
        visual_triggers=triggers,
        os_focus=FocusState(focused=True),
    )


def test_visual_action_block_success_with_visual_trigger() -> None:
    timebase = Timebase()
    state_bus = StateBus()
    state_bus.publish_observation(_observation("target_visible_and_centered"))
    backend = ConsoleInputBackend(timebase)
    worker = InputWorker(backend=backend, timebase=timebase, tick_seconds=0.005)
    executor = VisualActionBlockExecutor(
        state_bus=state_bus,
        input_worker=worker,
        timebase=timebase,
        wait_chunk_ms=50,
    )
    block = VisualActionBlock(
        name="demo",
        precondition=["target_visible_and_centered"],
        steps=[
            VisualActionStep(type="press_key", key="Q", lease_ms=50),
            VisualActionStep(type="wait_visual_trigger", trigger="action_started", timeout_ms=500),
        ],
    )

    def publish_trigger() -> None:
        time.sleep(0.08)
        state_bus.publish_observation(_observation("action_started"))

    worker.start()
    thread = threading.Thread(target=publish_trigger)
    thread.start()
    try:
        result = executor.execute(block)
    finally:
        thread.join(timeout=1.0)
        worker.stop()

    assert result.status == "SUCCESS"
    assert result.failure_code is None
    assert any(event.action == "key_down" for event in backend.events_snapshot())


def test_visual_action_block_interrupts_chunked_wait() -> None:
    timebase = Timebase()
    state_bus = StateBus()
    backend = ConsoleInputBackend(timebase)
    worker = InputWorker(backend=backend, timebase=timebase, tick_seconds=0.005)
    executor = VisualActionBlockExecutor(
        state_bus=state_bus,
        input_worker=worker,
        timebase=timebase,
        wait_chunk_ms=50,
    )
    block = VisualActionBlock(
        name="interruptible",
        steps=[VisualActionStep(type="wait_visual_trigger", trigger="never", timeout_ms=1000)],
    )
    interrupt = Interrupt(
        priority=0,
        timestamp=timebase.now(),
        code="EMERGENCY_STOP",
        source="unit_test",
        requires_input_release=True,
    )

    def publish_interrupt() -> None:
        time.sleep(0.06)
        state_bus.publish_interrupt(interrupt)

    worker.start()
    thread = threading.Thread(target=publish_interrupt)
    thread.start()
    try:
        started = timebase.now()
        result = executor.execute(block)
        elapsed = timebase.now() - started
    finally:
        thread.join(timeout=1.0)
        worker.stop()

    assert result.status == "CANCELLED"
    assert result.failure_code == "EMERGENCY_STOP"
    assert elapsed < 0.5


def test_visual_action_block_emits_action_intent_and_telemetry() -> None:
    timebase = Timebase()
    state_bus = StateBus()
    state_bus.publish_observation(_observation("target_visible_and_centered"))
    backend = ConsoleInputBackend(timebase)
    worker = InputWorker(backend=backend, timebase=timebase, tick_seconds=0.005)
    telemetry: list[str] = []
    executor = VisualActionBlockExecutor(
        state_bus=state_bus,
        input_worker=worker,
        timebase=timebase,
        wait_chunk_ms=50,
        telemetry_sink=lambda event_type, event: telemetry.append(event_type),
    )
    block = VisualActionBlock(
        name="emit_demo",
        precondition=["target_visible_and_centered"],
        steps=[VisualActionStep(type="emit_action_intent", intent="ACTION_TRIGGERED")],
    )

    worker.start()
    try:
        result = executor.execute(block)
    finally:
        worker.stop()

    assert result.status == "SUCCESS"
    assert result.payload["emitted_intents"] == ["ACTION_TRIGGERED"]
    assert any(
        event.action == "action_intent" and event.payload["intent"] == "ACTION_TRIGGERED"
        for event in backend.events_snapshot()
    )
    assert "action_block_step_start" in telemetry
    assert "action_block_step_success" in telemetry
    assert "skill_result" in telemetry
