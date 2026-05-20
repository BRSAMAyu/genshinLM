"""Phase 0 heart bypass E2E verification tests.

Validates that the main pipeline is truly connected:
  PerceptionPipeline -> Observation(non-None fields) -> ControllerLoop -> Orchestrator
"""
from __future__ import annotations

import time

import numpy as np

from control.camera_servo import CameraServo, CameraServoConfig
from control.controller_loop import ControllerLoop
from core.state_bus import StateBus
from core.timebase import Timebase
from core.types import CameraIntent, CameraModel, FocusState, Observation, TargetTrack
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


class _DemoCapturer:
    def __init__(self, timebase: Timebase) -> None:
        self._timebase = timebase
        self._frame_id = 0

    def start(self) -> None:
        pass

    def get_latest_frame(self) -> FramePacket:
        self._frame_id += 1
        image = np.zeros((360, 640, 3), dtype=np.uint8)
        x = 40 + (self._frame_id * 8) % 560
        image[140:220, x : x + 80, 0] = 255
        return FramePacket(
            frame_id=self._frame_id,
            timestamp=self._timebase.now(),
            image=image,
            source_size=(640, 360),
        )

    def stop(self) -> None:
        pass


class _RedBoxDetector:
    def process(self, frame: np.ndarray, observation: Observation, state_bus: StateBus) -> None:
        red_mask = frame[:, :, 0] > 200
        if np.any(red_mask):
            y_indices, x_indices = np.where(red_mask)
            cy, cx = float(np.mean(y_indices)), float(np.mean(x_indices))
            object.__setattr__(observation, "target_track", TargetTrack(
                track_id="demo_target",
                class_id="red_box",
                state="TRACKED",
                bbox_xyxy=(cx - 40, cy - 40, cx + 40, cy + 40),
                smoothed_center_px=(cx, cy),
                velocity_px_s=(0.0, 0.0),
                confidence=0.95,
                identity_confidence=0.9,
                missing_duration_ms=0.0,
                bearing_deg=None,
                pitch_deg=None,
                estimated_range=None,
                last_seen_frame_id=observation.frame_id,
            ))


def _wait_for(predicate: object, timeout: float = 3.0) -> None:
    assert callable(predicate)
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError(f"condition not met within {timeout}s")


def test_dynamic_slot_registration() -> None:
    state_bus = StateBus()
    slot = state_bus.register_slot("test.custom")
    assert state_bus.get_slot("test.custom") is slot
    assert state_bus.get_slot("nonexistent") is None
    assert "test.custom" in state_bus.registered_slot_names()
    slot.put("hello")
    assert slot.get() == "hello"
    slot2 = state_bus.register_slot("test.custom")
    assert slot2 is slot


def test_post_processor_sets_target_track() -> None:
    timebase = Timebase()
    state_bus = StateBus()
    capturer = _DemoCapturer(timebase)
    pipeline = PerceptionPipeline(
        capturer=capturer,
        state_bus=state_bus,
        timebase=timebase,
        config=PerceptionPipelineConfig(max_fps=30.0),
        post_processors=[_RedBoxDetector()],
    )
    pipeline.start()
    try:
        _wait_for(lambda: (
            state_bus.latest_observation.get() is not None
            and state_bus.latest_observation.get().target_track is not None
        ))
        obs = state_bus.latest_observation.get()
        assert obs is not None
        assert obs.target_track is not None
        assert obs.target_track.track_id == "demo_target"
    finally:
        pipeline.stop()


def test_post_processor_modifies_extensions() -> None:
    timebase = Timebase()
    state_bus = StateBus()

    class _ExtProc:
        def process(self, frame: np.ndarray, observation: Observation, sb: StateBus) -> None:
            observation.extensions["source"] = "test"
            sb.register_slot("test.ext").put(observation.frame_id)

    pipeline = PerceptionPipeline(
        capturer=_DemoCapturer(timebase),
        state_bus=state_bus,
        timebase=timebase,
        config=PerceptionPipelineConfig(max_fps=30.0),
        post_processors=[_ExtProc()],
    )
    pipeline.start()
    try:
        _wait_for(lambda: state_bus.latest_observation.version >= 1)
        obs = state_bus.latest_observation.get()
        assert obs is not None
        assert obs.extensions.get("source") == "test"
    finally:
        pipeline.stop()


def test_controller_loop_with_camera_servo_produces_intent() -> None:
    timebase = Timebase()
    state_bus = StateBus()
    camera_slot = state_bus.register_slot("camera_intent")

    servo = CameraServo(CameraServoConfig(dead_zone_deg=0.0, kp_yaw=0.5, kp_pitch=0.5, smoothing_alpha=1.0))
    controller = ControllerLoop(state_bus=state_bus, camera_servo=servo, tick_seconds=1.0 / 30.0)
    controller._camera_model = CameraModel(viewport_width=640, viewport_height=360, horizontal_fov_deg=90.0)

    obs = Observation(
        frame_id=1,
        t_capture=timebase.now(),
        t_processed=timebase.now(),
        latency_ms=5.0,
        viewport_size=(640, 360),
        target_track=TargetTrack(
            track_id="t", class_id="t", state="TRACKED",
            bbox_xyxy=(200.0, 100.0, 300.0, 200.0),
            smoothed_center_px=(250.0, 150.0),
            velocity_px_s=(0.0, 0.0), confidence=0.9, identity_confidence=0.9,
            missing_duration_ms=0.0, bearing_deg=None, pitch_deg=None,
            estimated_range=None, last_seen_frame_id=1,
        ),
        obstacle_field=None, ui_state=None,
        visual_triggers={"target_visible": True},
        os_focus=FocusState(focused=True), stale=False,
    )
    state_bus.publish_observation(obs)
    controller.start()
    try:
        _wait_for(lambda: camera_slot.get() is not None, timeout=2.0)
        assert isinstance(camera_slot.get(), CameraIntent)
    finally:
        controller.stop()


def test_full_e2e_pipeline_orchestrator_transitions() -> None:
    timebase = Timebase()
    state_bus = StateBus()

    pipeline = PerceptionPipeline(
        capturer=_DemoCapturer(timebase),
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
        post_processors=[_RedBoxDetector()],
    )
    controller = ControllerLoop(state_bus=state_bus, tick_seconds=1.0 / 30.0)

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

    worker.start()
    pipeline.start()
    controller.start()
    orchestrator.start()
    try:
        _wait_for(lambda: (
            state_bus.latest_observation.get() is not None
            and state_bus.latest_observation.get().target_track is not None
        ))
        assert state_bus.latest_observation.version > 0
        _wait_for(lambda: orchestrator.state in (
            "COMPLETE", "FAILED", "VERIFY_SUCCESS",
            "EXECUTE_VISUAL_ACTION_BLOCK", "TRACK_AND_APPROACH",
        ), timeout=5.0)
    finally:
        orchestrator.stop()
        controller.stop()
        pipeline.stop()
        worker.stop()
