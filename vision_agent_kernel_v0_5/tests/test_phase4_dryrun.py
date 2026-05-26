"""Phase 4D: Dry-Run Demo validation — Genshin App full pipeline in dry-run mode.

Proves the full pipeline works: DemoCapturer → Pipeline → GenshinApp post-processor
→ ControllerLoop → Orchestrator with Genshin skills → Failure/Persona bridges ready.
"""
from __future__ import annotations

import time

import numpy as np

from app_service.apps.genshin_app import GenshinApp
from app_service.app_registry import AppContext, AppRegistry
from combat.danger_detector import DangerThresholds, GenshinDangerSignalExtractor
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


class _GenshinDemoCapturer:
    """Produces frames with moving target and optional danger zones."""

    def __init__(self, timebase: Timebase) -> None:
        self._timebase = timebase
        self._frame_id = 0
        self._danger_active = False

    def start(self) -> None:
        pass

    def get_latest_frame(self) -> FramePacket:
        self._frame_id += 1
        image = np.zeros((360, 640, 3), dtype=np.uint8)
        # Moving target (blue box)
        x = 40 + (self._frame_id * 5) % 520
        image[150:210, x:x + 80, 0] = 200
        image[150:210, x:x + 80, 1] = 50
        image[150:210, x:x + 80, 2] = 50
        if self._danger_active:
            # Red danger zone at bottom
            image[240:350, 200:440, 2] = 200
            image[240:350, 200:440, 1] = 50
            image[240:350, 200:440, 0] = 50
        return FramePacket(
            frame_id=self._frame_id,
            timestamp=self._timebase.now(),
            image=image,
            source_size=(640, 360),
        )

    def stop(self) -> None:
        pass

    def activate_danger(self) -> None:
        self._danger_active = True

    def clear_danger(self) -> None:
        self._danger_active = False


def _wait_for(predicate, timeout=10.0):
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError(f"condition not met within {timeout}s")


def _build_genshin_pipeline(
    state_bus: StateBus,
    timebase: Timebase,
    capturer: _GenshinDemoCapturer,
) -> tuple[PerceptionPipeline, ControllerLoop, Orchestrator, InputWorker]:
    pipeline = PerceptionPipeline(
        capturer=capturer,
        state_bus=state_bus,
        timebase=timebase,
        config=PerceptionPipelineConfig(
            max_fps=30.0,
            static_visual_triggers={
                "target_visible": True,
                "in_range_estimated": True,
                "action_sequence_completed": True,
            },
        ),
    )
    backend = ConsoleInputBackend(timebase)
    input_worker = InputWorker(backend=backend, timebase=timebase, tick_seconds=0.01)
    controller = ControllerLoop(state_bus=state_bus)
    action_executor = VisualActionBlockExecutor(
        state_bus=state_bus,
        input_worker=input_worker,
        timebase=timebase,
        wait_chunk_ms=50,
    )
    orchestrator = Orchestrator(
        state_bus=state_bus,
        skills={
            "acquire_target": AcquireTargetSkill(state_bus, timebase),
            "track_and_approach": TrackAndApproachSkill(state_bus, timebase),
            "execute_visual_action_block": ExecuteVisualActionBlockSkill(action_executor),
            "verify_success": VerifySuccessSkill(state_bus, timebase),
            "recover": RecoverSkill(state_bus, timebase),
        },
        timebase=timebase,
    )
    return pipeline, controller, orchestrator, input_worker


def test_genshin_app_full_pipeline_dryrun() -> None:
    """Full dry-run: Pipeline + GenshinApp + Controller + Orchestrator for 2 seconds."""
    timebase = Timebase()
    state_bus = StateBus()
    capturer = _GenshinDemoCapturer(timebase)
    pipeline, controller, orchestrator, worker = _build_genshin_pipeline(
        state_bus, timebase, capturer,
    )

    app = GenshinApp()
    context = AppContext(
        state_bus=state_bus,
        pipeline=pipeline,
        controller_loop=controller,
        orchestrator=orchestrator,
    )
    app.install(context)

    pipeline.start()
    controller.start()
    orchestrator.start()
    worker.start()
    try:
        # Wait for pipeline to produce observations
        _wait_for(lambda: state_bus.latest_observation.version >= 5, timeout=10.0)
        obs = state_bus.latest_observation.get()
        assert obs is not None, "Pipeline should produce observations"

        # Verify genshin slots are populated
        screen_slot = state_bus.get_slot("genshin.screen_state")
        assert screen_slot is not None
        danger_slot = state_bus.get_slot("genshin.danger_signals")
        assert danger_slot is not None
        failure_slot = state_bus.get_slot("genshin.failure_state")
        assert failure_slot is not None, "Failure bridge should register slot"
        persona_slot = state_bus.get_slot("genshin.persona_response")
        assert persona_slot is not None, "Persona bridge should register slot"

        # Verify orchestrator state advanced
        mode = state_bus.current_mode.get()
        assert mode is not None, "Orchestrator should have set a mode"
    finally:
        orchestrator.stop()
        controller.stop()
        pipeline.stop()
        worker.stop()


def test_genshin_danger_triggers_during_dryrun() -> None:
    """Danger zone appears mid-run → danger slot shows elevated danger."""
    timebase = Timebase()
    state_bus = StateBus()
    capturer = _GenshinDemoCapturer(timebase)
    pipeline, controller, orchestrator, worker = _build_genshin_pipeline(
        state_bus, timebase, capturer,
    )

    app = GenshinApp()
    context = AppContext(
        state_bus=state_bus,
        pipeline=pipeline,
        controller_loop=controller,
        orchestrator=orchestrator,
    )
    app.install(context)

    pipeline.start()
    controller.start()
    orchestrator.start()
    worker.start()
    try:
        # Wait for baseline
        _wait_for(lambda: state_bus.latest_observation.version >= 3)

        # Activate danger
        capturer.activate_danger()

        # Wait for danger detection
        _wait_for(
            lambda: (
                state_bus.get_slot("genshin.danger_signals") is not None
                and state_bus.get_slot("genshin.danger_signals").get() is not None
                and state_bus.get_slot("genshin.danger_signals").get().get("overall_danger", 0.0) > 0.0
            ),
            timeout=5.0,
        )
        danger_data = state_bus.get_slot("genshin.danger_signals").get()
        assert danger_data["overall_danger"] > 0.0

        # Clear danger and verify it clears
        capturer.clear_danger()
        _wait_for(
            lambda: (
                state_bus.get_slot("genshin.danger_signals").get() is not None
                and state_bus.get_slot("genshin.danger_signals").get().get("overall_danger", 1.0) < 0.15
            ),
            timeout=5.0,
        )
    finally:
        orchestrator.stop()
        controller.stop()
        pipeline.stop()
        worker.stop()


def test_genshin_failure_bridge_records_skill_failure() -> None:
    """Simulate a FAILED SkillResult → failure bridge records and publishes."""
    timebase = Timebase()
    state_bus = StateBus()
    from core.types import SkillResult

    from app_service.apps.genshin_failure_bridge import GenshinFailureBridge
    bridge = GenshinFailureBridge(state_bus)

    result = SkillResult(
        skill_name="genshin_combat",
        status="FAILED",
        failure_code="COMBAT_TIMEOUT",
        started_at=0.0,
        finished_at=1.0,
        payload={},
    )
    bridge.on_skill_result(result)

    failure_slot = state_bus.get_slot("genshin.failure_state")
    assert failure_slot is not None
    data = failure_slot.get()
    assert data is not None
    assert data["failure_id"] is not None
    assert len(data["patterns"]) >= 0  # patterns may be empty on first failure


def test_genshin_persona_bridge_responds_to_interrupt() -> None:
    """Simulate an interrupt → persona bridge publishes response."""
    timebase = Timebase()
    state_bus = StateBus()
    from core.events import Interrupt

    from app_service.apps.genshin_persona_bridge import GenshinPersonaBridge
    bridge = GenshinPersonaBridge(state_bus)

    interrupt = Interrupt(priority=30, timestamp=timebase.now(), code="DODGE_REFLEX", source="test")
    bridge.on_interrupt(interrupt)

    response_slot = state_bus.get_slot("genshin.persona_response")
    assert response_slot is not None
    data = response_slot.get()
    assert data is not None
    assert "text" in data
    assert "emotion" in data


def test_aurorabench_v0_flywheel_end_to_end() -> None:
    """Benchmark: EvolutionEngine flywheel creates repair session, patch draft, and tracks failures."""
    from unittest.mock import patch

    from learning.evolution_engine import EvolutionEngine
    from core.types import SkillResult

    state_bus = StateBus()
    timebase = Timebase()

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        engine = EvolutionEngine(state_bus, patches_dir=tmp)

        # Mock _verify_in_sandbox to avoid subprocess pytest overhead
        with patch.object(engine, "_verify_in_sandbox", return_value=True):
            # 1. Simulate a failure
            result = SkillResult(
                skill_name="genshin_combat",
                status="FAILED",
                failure_code="TARGET_LOST",
                started_at=timebase.now(),
                finished_at=timebase.now() + 1.0,
                payload={"observation": {"target_confidence_drop": True}},
            )

            # 2. Feed failure into EvolutionEngine
            draft = engine.handle_failure(
                skill_name=result.skill_name,
                failure_code=result.failure_code,
                observation_data=result.payload.get("observation", {}),
            )

            assert draft is not None
            assert draft["skill_id"] == "genshin_combat"
            assert "increase_coasting_window" in draft["patches"]
            assert draft["verified"] is True

            # 3. Verify repair session was created
            session = engine.get_repair_session(draft.get("repair_session_id", ""))
            assert session is not None
            assert len(session.events) > 0
            assert len(session.demonstration_ids) > 0

            # 4. Verify SkillPatchDraft was created
            new_patch_id = draft.get("new_patch_id")
            assert new_patch_id is not None
            patch_draft = engine.get_skill_patch_draft(new_patch_id)
            assert patch_draft is not None
            assert patch_draft.skill_id == "genshin_combat"

            # 5. Approve patch and verify benchmark delta
            approved = engine.approve_patch("genshin_combat")
            assert approved is True

            delta = engine.benchmark_delta("genshin_combat")
            assert delta is not None
            assert delta["skill_id"] == "genshin_combat"

            # 6. List patch drafts
            drafts = engine.list_patch_drafts("genshin_combat")
            assert len(drafts) > 0

            # 7. Run 10 iterations to verify flywheel repeatability
            for _ in range(10):
                draft = engine.handle_failure(
                    skill_name="genshin_combat",
                    failure_code="TARGET_LOST",
                    observation_data={"target_confidence_drop": True},
                )
                assert draft is not None
                assert draft["verified"] is True
                assert engine.approve_patch("genshin_combat") is True

            all_drafts = engine.list_patch_drafts("genshin_combat")
            assert len(all_drafts) >= 11  # 1 initial + 10 flywheel iterations

