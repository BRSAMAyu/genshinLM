"""Tests for the navigation coordinator and pose pipeline wiring."""
from __future__ import annotations

import pytest

from control.navigation_coordinator import (
    NavigationCoordinator,
    RecoveryOutput,
)
from control.pose_navigation import PoseNavConfig, PoseNavigationController, PoseNavTarget
from control.visual_reacquire import ReacquireConfig, VisualReacquireController
from core.types import CameraModel, MotionCommand, MovementIntent, PoseEstimate, TargetTrack
from perception.pose_wiring import attach_pose_estimation


def _pose(pos=(0.0, 0.0), heading=0.0, confidence=1.0, uncertainty=0.1) -> PoseEstimate:
    return PoseEstimate(
        frame_id=1, timestamp=0.0, position=pos, heading_deg=heading,
        confidence=confidence, position_uncertainty=uncertainty, has_absolute_fix=True,
    )


def _track(center, bbox, state="visible") -> TargetTrack:
    return TargetTrack(
        track_id="t", class_id="npc", state=state, bbox_xyxy=bbox,
        smoothed_center_px=center, velocity_px_s=(0.0, 0.0), confidence=0.9,
        identity_confidence=0.9, missing_duration_ms=0.0, bearing_deg=None,
        pitch_deg=None, estimated_range=None, last_seen_frame_id=1,
    )


class _StubRecovery:
    def __init__(self, resolved=False):
        self.calls = []
        self._resolved = resolved

    def recover(self, reason, pose, target):
        self.calls.append(reason)
        return RecoveryOutput(
            movement=MovementIntent(move_forward=-0.5, move_right=0.0, reason="backstep"),
            resolved=self._resolved, reason=f"recover:{reason}",
        )


# --- coordinator -----------------------------------------------------------


def test_navigate_steer_passes_through() -> None:
    co = NavigationCoordinator()
    d = co.step(_pose((0.0, 0.0), heading=0.0), PoseNavTarget((0.0, 100.0)), now=0.0)
    assert co.mode == "navigate"
    assert d.mode == "navigate" and d.status == "steer"
    assert d.movement is not None and d.movement.move_forward == pytest.approx(1.0)


def test_arrived_is_sticky() -> None:
    co = NavigationCoordinator()
    d = co.step(_pose((0.0, 0.0)), PoseNavTarget((1.0, 0.0), arrival_radius=2.0), now=0.0)
    assert d.mode == "arrived"
    # subsequent calls stay arrived
    d2 = co.step(_pose((50.0, 50.0)), PoseNavTarget((1.0, 0.0)), now=1.0)
    assert d2.mode == "arrived"


def test_reacquire_handoff_runs_visual_servo() -> None:
    co = NavigationCoordinator()
    target = PoseNavTarget((0.0, 4.0), arrival_radius=1.0, reacquire_radius=6.0)
    # close + uncertain -> nav returns reacquire -> coordinator runs visual servo on the track
    off_center = _track(center=(940.0, 360.0), bbox=(900.0, 320.0, 980.0, 400.0))
    d = co.step(_pose((0.0, 0.0), uncertainty=3.0), target, now=0.0, track=off_center)
    assert co.mode == "reacquire"
    assert d.mode == "reacquire" and d.status == "servo"
    assert d.camera is not None and d.camera.yaw_delta > 0.0


def test_reacquire_arrives_when_target_large() -> None:
    co = NavigationCoordinator(reacquire=VisualReacquireController(CameraModel(), ReacquireConfig(arrival_area_ratio=0.12)))
    target = PoseNavTarget((0.0, 4.0), arrival_radius=1.0, reacquire_radius=6.0)
    big = _track(center=(640.0, 360.0), bbox=(440.0, 160.0, 840.0, 560.0))
    d = co.step(_pose((0.0, 0.0), uncertainty=3.0), target, now=0.0, track=big)
    assert d.mode == "arrived"


def test_reacquire_not_found_falls_to_recovery() -> None:
    rec = _StubRecovery()
    co = NavigationCoordinator(
        reacquire=VisualReacquireController(config=ReacquireConfig(search_yaw_step_deg=500.0, search_max_sweep_deg=400.0)),
        recovery=rec,
    )
    target = PoseNavTarget((0.0, 4.0), arrival_radius=1.0, reacquire_radius=6.0)
    # no track -> reacquire searches; first step sweeps 500 >= 400 next call → not_found
    co.step(_pose((0.0, 0.0), uncertainty=3.0), target, now=0.0, track=None)  # enters reacquire, search
    d = co.step(_pose((0.0, 0.0), uncertainty=3.0), target, now=0.1, track=None)  # not_found → recover
    assert d.mode == "recover"
    assert rec.calls and rec.calls[-1] == "reacquire_not_found"


def test_lost_invokes_recovery() -> None:
    rec = _StubRecovery()
    co = NavigationCoordinator(nav=PoseNavigationController(PoseNavConfig(min_confidence=0.25)), recovery=rec)
    d = co.step(_pose((0.0, 0.0), confidence=0.05), PoseNavTarget((100.0, 0.0)), now=0.0)
    assert d.mode == "recover"
    assert d.movement is not None and d.movement.move_forward == pytest.approx(-0.5)
    assert rec.calls == ["lost"]


def test_recover_resolved_returns_to_navigate() -> None:
    rec = _StubRecovery(resolved=True)
    co = NavigationCoordinator(nav=PoseNavigationController(PoseNavConfig(min_confidence=0.25)), recovery=rec)
    co.step(_pose((0.0, 0.0), confidence=0.05), PoseNavTarget((100.0, 0.0)), now=0.0)  # recover, resolved
    assert co.mode == "navigate"


def test_recovery_unwired_surfaces_condition() -> None:
    co = NavigationCoordinator(nav=PoseNavigationController(PoseNavConfig(min_confidence=0.25)))
    d = co.step(_pose((0.0, 0.0), confidence=0.05), PoseNavTarget((100.0, 0.0)), now=0.0)
    assert d.mode == "recover"
    assert "no strategy wired" in d.reason


# --- pose wiring -----------------------------------------------------------


class _FakePipeline:
    def __init__(self):
        self.processors = []

    def add_post_processor(self, p):
        self.processors.append(p)


class _StubProvider:
    def read(self, frame, frame_id, timestamp):
        from core.types import LocalizationReading
        return LocalizationReading(timestamp=timestamp, frame_id=frame_id)


def test_attach_pose_estimation_registers_processor() -> None:
    pipeline = _FakePipeline()
    cmd = MotionCommand(timestamp=0.0)
    proc = attach_pose_estimation(pipeline, _StubProvider(), command_source=lambda: cmd)
    assert len(pipeline.processors) == 1
    assert pipeline.processors[0] is proc
    # processor is usable: returns a current pose snapshot
    assert proc.current_pose() is not None
