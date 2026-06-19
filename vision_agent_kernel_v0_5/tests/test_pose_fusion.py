"""Tests for the sensor-agnostic pose fusion substrate."""
from __future__ import annotations

import math

import pytest

from core.state_bus import StateBus
from core.types import LocalizationReading, MotionCommand, PoseEstimate
from perception.pose_fusion import (
    PoseFusion,
    PoseFusionConfig,
    bearing_to,
    blend_heading,
    shortest_arc_deg,
    wrap360,
)


# --- angle helpers ---------------------------------------------------------


def test_wrap360_normalizes() -> None:
    assert wrap360(370.0) == pytest.approx(10.0)
    assert wrap360(-10.0) == pytest.approx(350.0)
    assert wrap360(0.0) == pytest.approx(0.0)


def test_shortest_arc_is_signed_and_bounded() -> None:
    assert shortest_arc_deg(350.0, 10.0) == pytest.approx(20.0)
    assert shortest_arc_deg(10.0, 350.0) == pytest.approx(-20.0)
    # +/-180 resolves to +180, never -180
    assert shortest_arc_deg(0.0, 180.0) == pytest.approx(180.0)
    assert shortest_arc_deg(0.0, -180.0) == pytest.approx(180.0)


def test_bearing_to_matches_heading_convention() -> None:
    # 0=+Y north, 90=+X east, 180=-Y south
    assert bearing_to((0.0, 0.0), (0.0, 1.0)) == pytest.approx(0.0)
    assert bearing_to((0.0, 0.0), (1.0, 0.0)) == pytest.approx(90.0)
    assert bearing_to((0.0, 0.0), (0.0, -1.0)) == pytest.approx(180.0)


def test_blend_heading_takes_shortest_arc() -> None:
    # blending 0 -> 90 by 0.85 lands at 76.5, not the long way around
    assert blend_heading(0.0, 90.0, 0.85) == pytest.approx(76.5)
    # wrap-around: 350 -> 10 nudges forward past 360
    assert blend_heading(350.0, 10.0, 0.5) == pytest.approx(0.0)


# --- dead-reckoning (predict) ----------------------------------------------


def test_first_update_establishes_baseline_without_moving() -> None:
    f = PoseFusion(initial_position=(0.0, 0.0), initial_heading_deg=0.0)
    pose = f.predict(
        MotionCommand(timestamp=0.0, forward=1.0, speed_world_units_per_sec=5.0, is_moving=True),
        now=0.0,
    )
    # dt is 0 on the first call -> no displacement
    assert pose.position == pytest.approx((0.0, 0.0))


def test_dead_reckon_moves_along_heading() -> None:
    f = PoseFusion(initial_heading_deg=0.0)
    f.predict(MotionCommand(timestamp=0.0), now=0.0)  # baseline
    north = f.predict(
        MotionCommand(timestamp=1.0, forward=1.0, speed_world_units_per_sec=2.0, is_moving=True),
        now=1.0,
    )
    assert north.position == pytest.approx((0.0, 2.0))
    assert "deadreckon" in north.source


def test_dead_reckon_respects_heading_east() -> None:
    f = PoseFusion(initial_heading_deg=90.0)
    f.predict(MotionCommand(timestamp=0.0), now=0.0)
    east = f.predict(
        MotionCommand(timestamp=1.0, forward=1.0, speed_world_units_per_sec=3.0, is_moving=True),
        now=1.0,
    )
    assert east.position == pytest.approx((3.0, 0.0), abs=1e-6)


def test_yaw_rate_integrates_and_grows_heading_uncertainty() -> None:
    f = PoseFusion(initial_heading_deg=0.0)
    f.reset((0.0, 0.0), 0.0, timestamp=0.0)  # heading uncertainty -> 0
    pose = f.predict(
        MotionCommand(timestamp=1.0, yaw_rate_deg_per_sec=30.0),
        now=1.0,
    )
    assert pose.heading_deg == pytest.approx(30.0)
    assert pose.heading_uncertainty_deg > 0.0  # dead-reckoned heading is less certain


# --- correction (compass / flow / absolute) --------------------------------


def test_compass_pulls_heading_and_shrinks_uncertainty() -> None:
    f = PoseFusion(initial_heading_deg=0.0)
    f.predict(MotionCommand(timestamp=0.0), now=0.0)
    before = f.current().heading_uncertainty_deg
    pose = f.correct(
        LocalizationReading(timestamp=1.0, frame_id=1, heading_deg=90.0, heading_confidence=1.0),
        now=1.0,
    )
    assert pose.heading_deg == pytest.approx(76.5)  # 0 + 0.85 * 90
    assert pose.heading_uncertainty_deg < before
    assert "compass" in pose.source


def test_flow_is_used_as_measured_displacement() -> None:
    f = PoseFusion()
    f.reset((0.0, 0.0), 0.0, timestamp=0.0)
    pose = f.correct(
        LocalizationReading(
            timestamp=1.0, frame_id=1, flow_dx=3.0, flow_dy=4.0, flow_confidence=0.9,
        ),
        now=1.0,
    )
    assert pose.position == pytest.approx((3.0, 4.0))
    assert "flow" in pose.source
    # measured flow is low-noise: dist 5 * flow_noise 0.04 = 0.2
    assert pose.position_uncertainty == pytest.approx(0.2)


def test_flow_beats_dead_reckoning_when_both_present() -> None:
    f = PoseFusion(initial_heading_deg=0.0)
    f.reset((0.0, 0.0), 0.0, timestamp=0.0)
    pose = f.update(
        reading=LocalizationReading(
            timestamp=1.0, frame_id=1, flow_dx=1.0, flow_dy=0.0, flow_confidence=0.8,
        ),
        command=MotionCommand(
            timestamp=1.0, forward=1.0, speed_world_units_per_sec=99.0, is_moving=True,
        ),
        now=1.0,
    )
    # flow (1,0) wins over the large dead-reckoned forward step
    assert pose.position == pytest.approx((1.0, 0.0))


def test_absolute_fix_pulls_position_and_collapses_uncertainty() -> None:
    f = PoseFusion(initial_heading_deg=0.0)
    f.reset((0.0, 0.0), 0.0, timestamp=0.0)
    drifted = f.predict(
        MotionCommand(timestamp=1.0, forward=1.0, speed_world_units_per_sec=10.0, is_moving=True),
        now=1.0,
    )
    assert drifted.position_uncertainty > 0.0
    fixed = f.correct(
        LocalizationReading(
            timestamp=2.0, frame_id=2, absolute_position=(0.0, 10.0), absolute_confidence=1.0,
        ),
        now=2.0,
    )
    assert fixed.has_absolute_fix
    assert fixed.position_uncertainty < drifted.position_uncertainty
    # gain 0.8 toward the true (0,10) from the dead-reckoned (0,10)-ish estimate
    assert fixed.position[1] == pytest.approx(10.0, abs=2.0)
    assert "absolute" in fixed.source


# --- uncertainty / confidence dynamics -------------------------------------


def test_confidence_decays_without_measurements() -> None:
    cfg = PoseFusionConfig(confidence_decay_per_sec=0.25)
    f = PoseFusion(cfg)
    f.reset((0.0, 0.0), 0.0, timestamp=0.0, confidence=1.0)
    pose = f.update(reading=None, command=None, now=1.0)
    assert pose.confidence == pytest.approx(0.75)


def test_dead_reckon_grows_position_uncertainty_more_than_flow() -> None:
    f_dr = PoseFusion()
    f_dr.reset((0.0, 0.0), 0.0, timestamp=0.0)
    dr = f_dr.predict(
        MotionCommand(timestamp=1.0, forward=1.0, speed_world_units_per_sec=5.0, is_moving=True),
        now=1.0,
    )
    f_flow = PoseFusion()
    f_flow.reset((0.0, 0.0), 0.0, timestamp=0.0)
    flow = f_flow.correct(
        LocalizationReading(timestamp=1.0, frame_id=1, flow_dx=0.0, flow_dy=5.0, flow_confidence=1.0),
        now=1.0,
    )
    # same 5-unit displacement, but dead-reckoning is noisier
    assert dr.position == pytest.approx(flow.position)
    assert dr.position_uncertainty > flow.position_uncertainty


def test_reset_snaps_pose() -> None:
    f = PoseFusion()
    f.reset((12.5, -3.0), 270.0, timestamp=5.0, confidence=1.0)
    pose = f.current()
    assert pose.position == pytest.approx((12.5, -3.0))
    assert pose.heading_deg == pytest.approx(270.0)
    assert pose.position_uncertainty == pytest.approx(0.0)
    assert pose.has_absolute_fix
    assert pose.confidence == pytest.approx(1.0)


def test_max_dt_clamps_huge_gaps() -> None:
    cfg = PoseFusionConfig(max_dt_sec=1.0)
    f = PoseFusion(cfg, initial_heading_deg=0.0)
    f.predict(MotionCommand(timestamp=0.0), now=0.0)
    # a 1000s gap must not teleport us a kilometre via dead-reckoning
    pose = f.predict(
        MotionCommand(timestamp=1000.0, forward=1.0, speed_world_units_per_sec=10.0, is_moving=True),
        now=1000.0,
    )
    assert pose.position[1] == pytest.approx(10.0)  # clamped to max_dt * speed


# --- StateBus integration --------------------------------------------------


def test_state_bus_pose_slot_roundtrip() -> None:
    bus = StateBus()
    assert bus.latest_pose_snapshot().value is None
    pose = PoseEstimate(frame_id=7, timestamp=1.0, position=(1.0, 2.0), heading_deg=30.0)
    version = bus.publish_pose(pose)
    snap = bus.latest_pose_snapshot()
    assert snap.value is not None
    assert snap.value.position == (1.0, 2.0)
    assert snap.value.heading_deg == 30.0
    assert snap.version == version
