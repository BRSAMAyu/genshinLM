"""Phase 2 integration test: Genshin App registers via App Registry without touching core/."""
from __future__ import annotations

import time

import numpy as np

from app_service.apps.genshin_app import GenshinApp
from app_service.app_registry import AppRegistry, AppContext
from control.controller_loop import ControllerLoop
from core.state_bus import StateBus
from core.timebase import Timebase
from execution.console_backend import ConsoleInputBackend
from execution.input_worker import InputWorker
from execution.visual_action_block import VisualActionBlockExecutor
from orchestration.orchestrator import Orchestrator
from orchestration.skills import (
    AcquireTargetSkill,
    ExecuteVisualActionBlockSkill,
    RecoverSkill,
    TrackAndApproachSkill,
    VerifySuccessSkill,
)
from perception.capture_base import FramePacket
from perception.pipeline import PerceptionPipeline, PerceptionPipelineConfig


class _TestCapturer:
    def __init__(self, timebase: Timebase) -> None:
        self._timebase = timebase
        self._frame_id = 0

    def start(self) -> None:
        pass

    def get_latest_frame(self) -> FramePacket:
        self._frame_id += 1
        return FramePacket(
            frame_id=self._frame_id,
            timestamp=self._timebase.now(),
            image=np.zeros((360, 640, 3), dtype=np.uint8),
            source_size=(640, 360),
        )

    def stop(self) -> None:
        pass


def _wait_for(predicate, timeout=3.0):
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError(f"condition not met within {timeout}s")


def test_genshin_app_registers_dynamic_slots() -> None:
    state_bus = StateBus()
    assert "genshin.screen_state" not in state_bus.registered_slot_names()
    assert "genshin.danger_signals" not in state_bus.registered_slot_names()

    app = GenshinApp()
    timebase = Timebase()
    capturer = _TestCapturer(timebase)
    pipeline = PerceptionPipeline(
        capturer=capturer, state_bus=state_bus, timebase=timebase,
        config=PerceptionPipelineConfig(max_fps=10.0),
    )
    controller = ControllerLoop(state_bus=state_bus)
    backend = ConsoleInputBackend(timebase)
    worker = InputWorker(backend=backend, timebase=timebase, tick_seconds=0.01)
    executor = VisualActionBlockExecutor(
        state_bus=state_bus, input_worker=worker, timebase=timebase, wait_chunk_ms=50,
    )
    orchestrator = Orchestrator(
        state_bus=state_bus,
        skills={
            "acquire_target": AcquireTargetSkill(state_bus, timebase),
            "track_and_approach": TrackAndApproachSkill(state_bus, timebase),
            "execute_visual_action_block": ExecuteVisualActionBlockSkill(executor),
            "verify_success": VerifySuccessSkill(state_bus, timebase),
            "recover": RecoverSkill(state_bus, timebase),
        },
        timebase=timebase,
    )

    context = AppContext(
        state_bus=state_bus,
        pipeline=pipeline,
        controller_loop=controller,
        orchestrator=orchestrator,
    )
    app.install(context)

    assert "genshin.screen_state" in state_bus.registered_slot_names()
    assert "genshin.danger_signals" in state_bus.registered_slot_names()
    assert "genshin.cooldown_state" in state_bus.registered_slot_names()
    worker.stop()


def test_genshin_app_registers_skills_in_orchestrator() -> None:
    state_bus = StateBus()
    timebase = Timebase()
    capturer = _TestCapturer(timebase)
    pipeline = PerceptionPipeline(
        capturer=capturer, state_bus=state_bus, timebase=timebase,
        config=PerceptionPipelineConfig(max_fps=10.0),
    )
    controller = ControllerLoop(state_bus=state_bus)
    orchestrator = Orchestrator(
        state_bus=state_bus, skills={}, timebase=timebase,
    )

    app = GenshinApp()
    context = AppContext(
        state_bus=state_bus,
        pipeline=pipeline,
        controller_loop=controller,
        orchestrator=orchestrator,
    )
    app.install(context)

    assert "genshin_combat" in orchestrator._skills
    assert "genshin_dodge" in orchestrator._skills


def test_genshin_app_via_registry() -> None:
    state_bus = StateBus()
    timebase = Timebase()
    capturer = _TestCapturer(timebase)
    pipeline = PerceptionPipeline(
        capturer=capturer, state_bus=state_bus, timebase=timebase,
        config=PerceptionPipelineConfig(max_fps=10.0),
    )
    controller = ControllerLoop(state_bus=state_bus)
    orchestrator = Orchestrator(state_bus=state_bus, skills={}, timebase=timebase)

    registry = AppRegistry()
    app = GenshinApp()
    context = AppContext(
        state_bus=state_bus,
        pipeline=pipeline,
        controller_loop=controller,
        orchestrator=orchestrator,
    )
    registry.register_app(app, context)
    assert "genshin" in registry.list_apps()

    registry.activate("genshin")
    assert "genshin" in registry.list_active()

    registry.deactivate("genshin")
    assert "genshin" not in registry.list_active()

    registry.unregister_app("genshin")
    assert "genshin" not in registry.list_apps()


def test_genshin_perception_bridge_publishes_to_slots() -> None:
    state_bus = StateBus()
    timebase = Timebase()
    pipeline = PerceptionPipeline(
        capturer=_TestCapturer(timebase),
        state_bus=state_bus,
        timebase=timebase,
        config=PerceptionPipelineConfig(max_fps=30.0),
    )
    controller = ControllerLoop(state_bus=state_bus)
    orchestrator = Orchestrator(state_bus=state_bus, skills={}, timebase=timebase)

    app = GenshinApp()
    context = AppContext(
        state_bus=state_bus,
        pipeline=pipeline,
        controller_loop=controller,
        orchestrator=orchestrator,
    )
    app.install(context)

    pipeline.start()
    try:
        _wait_for(lambda: state_bus.latest_observation.version >= 2)
        obs = state_bus.latest_observation.get()
        assert obs is not None
        screen_slot = state_bus.get_slot("genshin.screen_state")
        assert screen_slot is not None
    finally:
        pipeline.stop()
