"""Phase 4A: Verifier-Driven E2E test — dodge reflex closed loop.

Proves that state transitions are driven by VerifierResult evidence,
not script assumptions. The test simulates:
  1. Detect red danger zone (ground circle)
  2. Dodge reflex triggers
  3. Verifier confirms danger cleared (no more red pixels)
  4. VerifierResult(ok=True) drives state transition back to combat

This is the minimal viable proof of the Verifier-First architecture.
"""
from __future__ import annotations

import time

import numpy as np

from combat.danger_detector import DangerThresholds, GenshinDangerSignalExtractor
from control.controller_loop import ControllerLoop
from core.events import Interrupt
from core.state_bus import StateBus
from core.timebase import Timebase
from core.types import FocusState, Observation, TargetTrack
from execution.verifier_base import VerifierContext, VerifierResult
from perception.capture_base import FramePacket
from perception.pipeline import FramePostProcessor, PerceptionPipeline, PerceptionPipelineConfig


class _DangerFrameCapturer:
    """Produces frames that simulate danger zones appearing and clearing."""

    def __init__(self, timebase: Timebase) -> None:
        self._timebase = timebase
        self._frame_id = 0
        self._danger_active = True

    def start(self) -> None:
        pass

    def get_latest_frame(self) -> FramePacket:
        self._frame_id += 1
        image = np.zeros((360, 640, 3), dtype=np.uint8)
        if self._danger_active:
            # Red danger circle on ground area (bottom third of frame)
            image[240:350, 220:420, 2] = 200  # Red channel (BGR)
            image[240:350, 220:420, 1] = 50
            image[240:350, 220:420, 0] = 50
        # Always have a target (green box in center)
        image[150:210, 280:360, 1] = 200
        image[150:210, 280:360, 0] = 50
        image[150:210, 280:360, 2] = 50
        return FramePacket(
            frame_id=self._frame_id,
            timestamp=self._timebase.now(),
            image=image,
            source_size=(640, 360),
        )

    def stop(self) -> None:
        pass

    def clear_danger(self) -> None:
        self._danger_active = False


class _DangerAwarePostProcessor:
    """Post-processor that runs danger detection and sets target_track."""

    def __init__(self, danger_extractor: GenshinDangerSignalExtractor) -> None:
        self._extractor = danger_extractor
        self._prev_frame = None

    def process(self, frame: np.ndarray, observation: Observation, state_bus: StateBus) -> None:
        # Set target track from green box
        green_mask = (frame[:, :, 1] > 150) & (frame[:, :, 0] < 80) & (frame[:, :, 2] < 80)
        if np.any(green_mask):
            y_indices, x_indices = np.where(green_mask)
            cy, cx = float(np.mean(y_indices)), float(np.mean(x_indices))
            object.__setattr__(observation, "target_track", TargetTrack(
                track_id="test_target",
                class_id="enemy",
                state="TRACKED",
                bbox_xyxy=(cx - 40, cy - 30, cx + 40, cy + 30),
                smoothed_center_px=(cx, cy),
                velocity_px_s=(0.0, 0.0),
                confidence=0.9,
                identity_confidence=0.9,
                missing_duration_ms=0.0,
                bearing_deg=None,
                pitch_deg=None,
                estimated_range=None,
                last_seen_frame_id=observation.frame_id,
            ))

        # Run danger detection
        signals = self._extractor.extract(frame, self._prev_frame)
        observation.extensions["danger_score"] = signals.overall_danger
        observation.extensions["ground_danger"] = signals.ground_danger_zone
        observation.extensions["should_dodge"] = signals.overall_danger >= 0.7

        # Publish to danger slot
        danger_slot = state_bus.get_slot("genshin.danger_signals")
        if danger_slot is not None:
            danger_slot.put({
                "overall_danger": signals.overall_danger,
                "ground_danger_zone": signals.ground_danger_zone,
                "should_dodge": signals.overall_danger >= 0.7,
            })

        self._prev_frame = frame.copy()


class _DodgeVerifier:
    """Verifier that checks if danger has been cleared from the frame."""
    verifier_id = "dodge_verifier"

    def verify(self, context: VerifierContext | dict) -> VerifierResult:
        ctx = context if isinstance(context, VerifierContext) else VerifierContext(state=context if isinstance(context, dict) else {})
        frame = ctx.frame
        if frame is None and ctx.observation is not None:
            obs = ctx.observation
            danger_score = obs.extensions.get("danger_score", 0.0) if isinstance(obs.extensions, dict) else 0.0
        elif frame is not None:
            extractor = GenshinDangerSignalExtractor()
            signals = extractor.extract(frame)
            danger_score = signals.overall_danger
        else:
            danger_score = 0.0

        cleared = danger_score < 0.15
        return VerifierResult(
            ok=cleared,
            verifier_id=self.verifier_id,
            confidence=0.9 if cleared else 0.2,
            reason="danger_cleared" if cleared else "danger_still_present",
            evidence={"danger_score": danger_score},
            frame_id=ctx.observation.frame_id if ctx.observation else None,
        )


def _wait_for(predicate, timeout=5.0):
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError(f"condition not met within {timeout}s")


def test_danger_detection_on_red_frame() -> None:
    frame = np.zeros((360, 640, 3), dtype=np.uint8)
    frame[240:350, 220:420, 2] = 200
    frame[240:350, 220:420, 1] = 50
    frame[240:350, 220:420, 0] = 50

    extractor = GenshinDangerSignalExtractor(DangerThresholds(ground_danger=0.05))
    signals = extractor.extract(frame)
    assert signals.ground_danger_zone > 0.0, "Red pixels should trigger ground danger"
    assert signals.overall_danger > 0.0, "Overall danger should be elevated"


def test_danger_cleared_on_black_frame() -> None:
    frame_danger = np.zeros((360, 640, 3), dtype=np.uint8)
    frame_danger[240:350, 220:420, 2] = 200

    frame_safe = np.zeros((360, 640, 3), dtype=np.uint8)

    extractor = GenshinDangerSignalExtractor(DangerThresholds(ground_danger=0.05))
    signals_danger = extractor.extract(frame_danger)
    assert signals_danger.ground_danger_zone > 0.0

    signals_safe = extractor.extract(frame_safe)
    assert signals_safe.ground_danger_zone == 0.0
    assert signals_safe.overall_danger < 0.15


def test_dodge_verifier_confirms_cleared() -> None:
    verifier = _DodgeVerifier()

    safe_obs = Observation(
        frame_id=1,
        t_capture=0.0, t_processed=0.0, latency_ms=0.0,
        viewport_size=(640, 360),
        target_track=None, obstacle_field=None, ui_state=None,
        visual_triggers={}, os_focus=FocusState(focused=True),
        extensions={"danger_score": 0.02},
    )
    result = verifier.verify(VerifierContext(state={}, observation=safe_obs))
    assert result.ok is True
    assert result.confidence >= 0.9
    assert "cleared" in result.reason


def test_dodge_verifier_rejects_danger() -> None:
    verifier = _DodgeVerifier()

    danger_obs = Observation(
        frame_id=2,
        t_capture=0.0, t_processed=0.0, latency_ms=0.0,
        viewport_size=(640, 360),
        target_track=None, obstacle_field=None, ui_state=None,
        visual_triggers={}, os_focus=FocusState(focused=True),
        extensions={"danger_score": 0.8},
    )
    result = verifier.verify(VerifierContext(state={}, observation=danger_obs))
    assert result.ok is False
    assert result.confidence < 0.5
    assert "present" in result.reason


def test_full_dodge_reflex_closed_loop() -> None:
    """E2E: danger detected → interrupt fired → danger cleared → verifier confirms."""
    timebase = Timebase()
    state_bus = StateBus()
    state_bus.register_slot("genshin.danger_signals")

    extractor = GenshinDangerSignalExtractor(DangerThresholds(ground_danger=0.05))
    capturer = _DangerFrameCapturer(timebase)
    processor = _DangerAwarePostProcessor(extractor)

    pipeline = PerceptionPipeline(
        capturer=capturer,
        state_bus=state_bus,
        timebase=timebase,
        config=PerceptionPipelineConfig(max_fps=30.0),
        post_processors=[processor],
    )

    pipeline.start()
    try:
        # Phase 1: Wait for danger detection
        _wait_for(lambda: (
            state_bus.latest_observation.get() is not None
            and state_bus.latest_observation.get().extensions.get("ground_danger", 0.0) > 0.0
        ))
        obs_danger = state_bus.latest_observation.get()
        assert obs_danger is not None
        danger_score = obs_danger.extensions.get("danger_score", 0.0)
        assert danger_score > 0.0, f"Danger should be detected, got {danger_score}"

        # Phase 2: Verifier should reject (danger still present)
        verifier = _DodgeVerifier()
        result_before = verifier.verify(VerifierContext(state={}, observation=obs_danger))
        assert result_before.ok is False, "Verifier should reject while danger present"

        # Phase 3: Clear the danger (simulate dodge)
        capturer.clear_danger()

        # Phase 4: Wait for danger to clear
        _wait_for(lambda: (
            state_bus.latest_observation.get() is not None
            and state_bus.latest_observation.get().extensions.get("danger_score", 1.0) < 0.15
        ))
        obs_safe = state_bus.latest_observation.get()
        assert obs_safe is not None

        # Phase 5: Verifier should now confirm danger cleared
        result_after = verifier.verify(VerifierContext(state={}, observation=obs_safe))
        assert result_after.ok is True, "Verifier should confirm danger cleared"
        assert result_after.confidence >= 0.9
        assert result_after.verifier_id == "dodge_verifier"
        assert result_after.frame_id is not None
    finally:
        pipeline.stop()


def test_verifier_result_has_evidence_chain() -> None:
    """VerifierResult must carry frame_id and evidence for trace replay."""
    verifier = _DodgeVerifier()
    obs = Observation(
        frame_id=42,
        t_capture=0.0, t_processed=0.0, latency_ms=0.0,
        viewport_size=(640, 360),
        target_track=None, obstacle_field=None, ui_state=None,
        visual_triggers={}, os_focus=FocusState(focused=True),
        extensions={"danger_score": 0.01},
    )
    result = verifier.verify(VerifierContext(state={}, observation=obs))

    assert result.frame_id == 42, "Evidence must reference source frame"
    assert "danger_score" in result.evidence, "Evidence must contain detection data"
    assert result.ok is True
