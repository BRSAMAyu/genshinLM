"""Tests for pose-closed-loop navigation and last-mile visual reacquire."""
from __future__ import annotations

import math

import pytest

from control.pose_navigation import (
    PoseNavConfig,
    PoseNavigationController,
    PoseNavTarget,
)
from control.visual_reacquire import (
    ReacquireConfig,
    VisualReacquireController,
)
from core.types import CameraModel, PoseEstimate, TargetTrack


def _pose(
    pos: tuple[float, float] = (0.0, 0.0),
    heading: float = 0.0,
    confidence: float = 1.0,
    uncertainty: float = 0.1,
) -> PoseEstimate:
    return PoseEstimate(
        frame_id=1,
        timestamp=0.0,
        position=pos,
        heading_deg=heading,
        confidence=confidence,
        position_uncertainty=uncertainty,
        has_absolute_fix=True,
    )


# --- pose navigation -------------------------------------------------------


def test_arrived_within_radius() -> None:
    nav = PoseNavigationController()
    d = nav.step(_pose((0.0, 0.0)), PoseNavTarget((1.0, 1.0), arrival_radius=2.0), now=0.0)
    assert d.status == "arrived"


def test_lost_when_confidence_low() -> None:
    nav = PoseNavigationController(PoseNavConfig(min_confidence=0.25))
    d = nav.step(_pose((0.0, 0.0), confidence=0.1), PoseNavTarget((100.0, 0.0)), now=0.0)
    assert d.status == "lost"


def test_steer_emits_camera_yaw_toward_bearing() -> None:
    nav = PoseNavigationController()
    # facing north (0), target due east -> bearing 90, positive yaw error
    d = nav.step(_pose((0.0, 0.0), heading=0.0), PoseNavTarget((100.0, 0.0)), now=0.0)
    assert d.status == "steer"
    assert d.heading_error_deg == pytest.approx(90.0)
    assert d.camera is not None
    assert d.camera.yaw_delta > 0.0
    # 90° off -> negligible forward
    assert d.movement is not None
    assert d.movement.move_forward == pytest.approx(0.0, abs=1e-6)


def test_steer_full_forward_when_aligned() -> None:
    nav = PoseNavigationController()
    # facing north, target due north -> aligned, no camera correction, full forward
    d = nav.step(_pose((0.0, 0.0), heading=0.0), PoseNavTarget((0.0, 100.0)), now=0.0)
    assert d.status == "steer"
    assert d.heading_error_deg == pytest.approx(0.0)
    assert d.camera is None
    assert d.movement is not None
    assert d.movement.move_forward == pytest.approx(1.0)


def test_reacquire_when_close_but_uncertain() -> None:
    nav = PoseNavigationController(PoseNavConfig(reacquire_uncertainty_ratio=0.5))
    target = PoseNavTarget((0.0, 4.0), arrival_radius=1.0, reacquire_radius=6.0)
    # distance 4, uncertainty 3 > 0.5*4 -> reacquire
    d = nav.step(_pose((0.0, 0.0), uncertainty=3.0), target, now=0.0)
    assert d.status == "reacquire"


def test_stuck_when_commanding_forward_without_progress() -> None:
    cfg = PoseNavConfig(stuck_window_sec=1.0, stuck_min_displacement=0.5)
    nav = PoseNavigationController(cfg)
    target = PoseNavTarget((0.0, 100.0))
    pose = _pose((0.0, 0.0), heading=0.0)  # aligned -> commands forward
    # feed several ticks at the same position across the window
    nav.step(pose, target, now=0.0)
    nav.step(pose, target, now=0.5)
    d = nav.step(pose, target, now=1.0)
    assert d.status == "stuck"


# --- visual reacquire ------------------------------------------------------


def _track(
    center: tuple[float, float],
    bbox: tuple[float, float, float, float],
    state: str = "visible",
) -> TargetTrack:
    return TargetTrack(
        track_id="t",
        class_id="npc",
        state=state,
        bbox_xyxy=bbox,
        smoothed_center_px=center,
        velocity_px_s=(0.0, 0.0),
        confidence=0.9,
        identity_confidence=0.9,
        missing_duration_ms=0.0,
        bearing_deg=None,
        pitch_deg=None,
        estimated_range=None,
        last_seen_frame_id=1,
    )


def test_search_when_no_target_then_not_found() -> None:
    rc = VisualReacquireController(config=ReacquireConfig(search_yaw_step_deg=200.0, search_max_sweep_deg=400.0))
    d1 = rc.step(None)
    assert d1.status == "search"
    assert d1.camera is not None and d1.camera.yaw_delta == pytest.approx(200.0)
    rc.step(None)  # swept 400
    d3 = rc.step(None)  # exceeds max
    assert d3.status == "not_found"


def test_servo_centers_offcenter_target() -> None:
    rc = VisualReacquireController(CameraModel())  # 1280x720 center=(640,360)
    d = rc.step(_track(center=(940.0, 360.0), bbox=(900.0, 320.0, 980.0, 400.0)))
    assert d.status == "servo"
    assert d.yaw_error_deg > 0.0
    assert d.camera is not None and d.camera.yaw_delta > 0.0


def test_approach_when_centered_and_far() -> None:
    rc = VisualReacquireController(CameraModel())
    d = rc.step(_track(center=(640.0, 360.0), bbox=(620.0, 340.0, 660.0, 380.0)))
    assert d.status == "approach"
    assert d.movement is not None and d.movement.move_forward == pytest.approx(1.0)


def test_arrived_when_target_large() -> None:
    rc = VisualReacquireController(CameraModel(), ReacquireConfig(arrival_area_ratio=0.12))
    # bbox 400x400 / (1280*720) ~= 0.173 >= 0.12
    d = rc.step(_track(center=(640.0, 360.0), bbox=(440.0, 160.0, 840.0, 560.0)))
    assert d.status == "arrived"


def test_lost_track_triggers_search() -> None:
    rc = VisualReacquireController()
    d = rc.step(_track(center=(640.0, 360.0), bbox=(600.0, 340.0, 680.0, 380.0), state="lost"))
    assert d.status == "search"
