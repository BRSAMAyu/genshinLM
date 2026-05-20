from __future__ import annotations

import time

from core.events import Interrupt
from core.state_bus import StateBus
from core.timebase import Timebase
from core.types import FocusState, Observation
from execution.console_backend import ConsoleInputBackend
from execution.input_worker import InputWorker
from execution.visual_action_block import VisualActionBlockExecutor
from orchestration.graph import COMPLETE, INTERRUPTED, OrchestrationGraph
from orchestration.orchestrator import Orchestrator
from orchestration.skills import (
    AcquireTargetSkill,
    EnterTargetRegionSkill,
    ExecuteVisualActionBlockSkill,
    LoadTaskSkill,
    RecoverSkill,
    TrackAndApproachSkill,
    VerifySuccessSkill,
)
from orchestration.task_spec import TaskSpec


def _observation() -> Observation:
    now = time.perf_counter()
    return Observation(
        frame_id=1,
        t_capture=now,
        t_processed=now,
        latency_ms=0.0,
        viewport_size=(1280, 720),
        target_track=None,
        obstacle_field=None,
        ui_state=None,
        visual_triggers={
            "target_visible": True,
            "in_range_estimated": True,
            "action_sequence_completed": True,
        },
        os_focus=FocusState(focused=True),
    )


def _orchestrator(state_bus: StateBus, timebase: Timebase, worker: InputWorker) -> Orchestrator:
    executor = VisualActionBlockExecutor(state_bus, worker, timebase=timebase, wait_chunk_ms=50)
    return Orchestrator(
        state_bus=state_bus,
        skills={
            "load_task": LoadTaskSkill(
                state_bus,
                TaskSpec("unit", {}, {}, max_duration_sec=10.0, max_retries=1),
                timebase,
            ),
            "enter_target_region": EnterTargetRegionSkill(state_bus, timebase),
            "acquire_target": AcquireTargetSkill(state_bus, timebase),
            "track_and_approach": TrackAndApproachSkill(state_bus, timebase),
            "execute_visual_action_block": ExecuteVisualActionBlockSkill(executor),
            "verify_success": VerifySuccessSkill(state_bus, timebase),
            "recover": RecoverSkill(state_bus, timebase),
        },
        graph=OrchestrationGraph(),
        timebase=timebase,
    )


def test_orchestrator_reaches_complete_on_happy_path() -> None:
    timebase = Timebase()
    state_bus = StateBus()
    state_bus.publish_observation(_observation())
    worker = InputWorker(ConsoleInputBackend(timebase), timebase=timebase)
    orchestrator = _orchestrator(state_bus, timebase, worker)

    worker.start()
    try:
        for _ in range(8):
            orchestrator.run_once()
            if orchestrator.state == COMPLETE:
                break
    finally:
        worker.stop()

    assert orchestrator.state == COMPLETE
    transitions = orchestrator.transitions_snapshot()
    assert [transition.next_state for transition in transitions[:7]] == [
        "LOAD_TASK",
        "ENTER_TARGET_REGION",
        "ACQUIRE_TARGET",
        "TRACK_AND_APPROACH",
        "EXECUTE_VISUAL_ACTION_BLOCK",
        "VERIFY_SUCCESS",
        "COMPLETE",
    ]
    assert all(result.status == "SUCCESS" for result in orchestrator.results_snapshot())


def test_orchestrator_p0_interrupt_enters_interrupted() -> None:
    timebase = Timebase()
    state_bus = StateBus()
    worker = InputWorker(ConsoleInputBackend(timebase), timebase=timebase)
    orchestrator = _orchestrator(state_bus, timebase, worker)
    state_bus.publish_interrupt(
        Interrupt(
            priority=0,
            timestamp=timebase.now(),
            code="EMERGENCY_STOP",
            source="unit_test",
            requires_input_release=True,
        )
    )

    transition = orchestrator.run_once()

    assert transition.next_state == INTERRUPTED
    assert orchestrator.state == INTERRUPTED
