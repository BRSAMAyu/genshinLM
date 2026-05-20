from __future__ import annotations

import time
import numpy as np
from dataclasses import dataclass

from core.state_bus import StateBus
from core.timebase import Timebase
from core.types import Observation, TargetTrack, CameraIntent, MovementIntent, CameraModel
from perception.capture_base import FramePacket
from perception.pipeline import PerceptionPipeline, PerceptionPipelineConfig, FramePostProcessor
from control.controller_loop import ControllerLoop
from control.camera_servo import CameraServo, CameraServoConfig
from orchestration.orchestrator import Orchestrator
from orchestration.skills import (
    AcquireTargetSkill,
    TrackAndApproachSkill,
    ExecuteVisualActionBlockSkill,
    VerifySuccessSkill,
    RecoverSkill,
)
from execution.console_backend import ConsoleInputBackend
from execution.input_worker import InputWorker
from execution.visual_action_block import VisualActionBlockExecutor


class DummyPostProcessor:
    def process(self, frame: np.ndarray, observation: Observation, state_bus: StateBus) -> None:
        red_mask = frame[:, :, 0] > 200
        if np.any(red_mask):
            y_indices, x_indices = np.where(red_mask)
            cy, cx = float(np.mean(y_indices)), float(np.mean(x_indices))
            object.__setattr__(observation, "target_track", TargetTrack(
                track_id="demo_target",
                class_id="monster",
                state="TRACKED",
                bbox_xyxy=(cx - 40, cy - 40, cx + 40, cy + 40),
                smoothed_center_px=(cx, cy),
                velocity_px_s=(0.0, 0.0),
                confidence=0.95,
                identity_confidence=0.95,
                missing_duration_ms=0.0,
                bearing_deg=0.0,
                pitch_deg=0.0,
                estimated_range=5.0,
                last_seen_frame_id=observation.frame_id,
            ))


class DemoCapturer:
    def __init__(self, timebase: Timebase) -> None:
        self._timebase = timebase
        self._frame_id = 0

    def start(self) -> None:
        pass

    def get_latest_frame(self) -> FramePacket:
        self._frame_id += 1
        # Create a frame with a red box (red channel high)
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


def _wait_for(predicate, timeout: float = 2.0) -> None:
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition was not met before timeout")


def test_heart_bypass_e2e() -> None:
    """Pipeline → Observation(non-None target_track) → ControllerLoop(intent) → Orchestrator(COMPLETE)"""
    timebase = Timebase()
    state_bus = StateBus()
    
    # Register dynamic slots if needed
    camera_intent_slot = state_bus.register_slot("camera_intent")
    movement_intent_slot = state_bus.register_slot("movement_intent")

    # 1. Setup Capturer and Pipeline with Post Processor
    capturer = DemoCapturer(timebase)
    post_processor = DummyPostProcessor()
    pipeline = PerceptionPipeline(
        capturer=capturer,
        state_bus=state_bus,
        timebase=timebase,
        config=PerceptionPipelineConfig(
            max_fps=60.0,
            static_visual_triggers={
                "target_visible": True,
                "in_range_estimated": True,
                "action_sequence_completed": True,
            },
        ),
        post_processors=[post_processor],
    )

    # 2. Setup Controller Loop with Camera Servo
    camera_servo = CameraServo(CameraServoConfig(dead_zone_deg=0.0, kp_yaw=0.5, kp_pitch=0.5, smoothing_alpha=1.0))
    controller = ControllerLoop(
        state_bus=state_bus,
        camera_servo=camera_servo,
        tick_seconds=1.0 / 30.0,
    )
    # Mock a camera model so camera_servo compute_error gets executed
    controller._camera_model = CameraModel(horizontal_fov_deg=90.0, viewport_width=1280, viewport_height=720)

    # 3. Setup Orchestrator & Skills
    backend = ConsoleInputBackend(timebase)
    input_worker = InputWorker(backend=backend, timebase=timebase, tick_seconds=0.01)
    action_executor = VisualActionBlockExecutor(
        state_bus=state_bus,
        input_worker=input_worker,
        timebase=timebase,
        wait_chunk_ms=20,
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

    # 4. Start all components
    input_worker.start()
    pipeline.start()
    controller.start()
    orchestrator.start()

    try:
        # Wait until target_track is not None in latest observation
        _wait_for(lambda: (
            state_bus.latest_observation.get() is not None and 
            state_bus.latest_observation.get().target_track is not None
        ))
        
        # Verify that camera_intent has been generated
        _wait_for(lambda: camera_intent_slot.get() is not None)
        
        # Verify Orchestrator steps through states
        # The Orchestrator cycles: INIT -> LOAD_TASK -> ACQUIRE_TARGET -> TRACK_AND_APPROACH -> EXECUTE -> VERIFY -> COMPLETE
        _wait_for(lambda: orchestrator.state == "COMPLETE", timeout=3.0)

    finally:
        orchestrator.stop()
        controller.stop()
        pipeline.stop()
        input_worker.stop()

    # Final Assertions
    latest_obs = state_bus.latest_observation.get()
    assert latest_obs is not None
    assert latest_obs.target_track is not None
    assert latest_obs.target_track.track_id == "demo_target"
    
    intent = camera_intent_slot.get()
    assert intent is not None
    assert isinstance(intent, CameraIntent)
    assert intent.confidence == 0.95
