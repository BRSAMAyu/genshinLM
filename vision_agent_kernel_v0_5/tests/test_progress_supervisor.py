from __future__ import annotations

from core.types import FocusState, Observation, TargetTrack
from control.progress_supervisor import ProgressSupervisor, ProgressSupervisorConfig


def _track(center_x: float, confidence: float = 1.0) -> TargetTrack:
    return TargetTrack(
        track_id="1",
        class_id="target",
        state="TRACKED",
        bbox_xyxy=None,
        smoothed_center_px=(center_x, 360.0),
        velocity_px_s=(0.0, 0.0),
        confidence=confidence,
        identity_confidence=confidence,
        missing_duration_ms=0.0,
        bearing_deg=None,
        pitch_deg=None,
        estimated_range=None,
        last_seen_frame_id=1,
    )


def _observation(timestamp: float, center_x: float | None, stale: bool = False) -> Observation:
    return Observation(
        frame_id=int(timestamp * 10),
        t_capture=timestamp,
        t_processed=timestamp,
        latency_ms=0.0,
        viewport_size=(1280, 720),
        target_track=_track(center_x) if center_x is not None else None,
        obstacle_field=None,
        ui_state=None,
        visual_triggers={},
        os_focus=FocusState(focused=True),
        stale=stale,
    )


def test_progress_frustration_trend() -> None:
    supervisor = ProgressSupervisor(
        config=ProgressSupervisorConfig(
            positive_slope_threshold=0.05,
            flat_slope_epsilon=0.02,
            low_visibility_penalty=5.0,
            flat_progress_penalty=2.0,
            stale_penalty=8.0,
        )
    )

    first = supervisor.update(_observation(0.0, 100.0))
    second = supervisor.update(_observation(1.0, 320.0))
    third = supervisor.update(_observation(2.0, 640.0))

    assert first.progress_slope_2s == 0.0
    assert second.progress_slope_2s > 0.0
    assert third.trend == "IMPROVING"
    assert second.frustration < first.frustration
    assert third.frustration <= second.frustration


def test_progress_uses_window_not_single_frame() -> None:
    supervisor = ProgressSupervisor()

    supervisor.update(_observation(0.0, 640.0))
    supervisor.update(_observation(0.5, 640.0))
    state = supervisor.update(_observation(1.0, None, stale=True))

    assert state.visibility_ratio_1s < 1.0
    assert state.frustration > 0.0
    assert state.trend == "DEGRADING"
