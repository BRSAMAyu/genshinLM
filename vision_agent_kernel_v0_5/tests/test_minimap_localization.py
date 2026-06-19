"""Tests for Genshin minimap localization provider + pose estimation processor."""
from __future__ import annotations

import math

import numpy as np
import pytest

from capsules.genshin.minimap_localization import GenshinMinimapLocalizationProvider
from core.state_bus import StateBus
from core.types import FocusState, LocalizationReading, MotionCommand, Observation
from perception.minimap_flow_tracker import FlowVector
from perception.pose_estimation_processor import PoseEstimationProcessor
from perception.pose_fusion import PoseFusion


class _StubTracker:
    """Deterministic stand-in for MinimapFlowTracker."""

    def __init__(self, flow: FlowVector | None) -> None:
        self._flow = flow
        self.walking: bool | None = None

    def update(self, frame: np.ndarray) -> FlowVector | None:
        return self._flow

    def set_walking(self, walking: bool) -> None:
        self.walking = walking


def _frame() -> np.ndarray:
    return np.zeros((720, 1280, 3), dtype=np.uint8)


def _observation(frame_id: int = 1, t: float = 1.0) -> Observation:
    return Observation(
        frame_id=frame_id,
        t_capture=t,
        t_processed=t,
        latency_ms=0.0,
        viewport_size=(1280, 720),
        target_track=None,
        obstacle_field=None,
        ui_state=None,
        visual_triggers={},
        os_focus=FocusState(focused=True),
    )


# --- provider --------------------------------------------------------------


def test_provider_no_flow_yields_empty_reading() -> None:
    provider = GenshinMinimapLocalizationProvider(tracker=_StubTracker(None))
    reading = provider.read(_frame(), frame_id=1, timestamp=1.0)
    assert reading.flow_dx is None
    assert reading.heading_deg is None
    assert reading.minimap_visible
    assert reading.source == "genshin_minimap"


def test_provider_converts_flow_to_world_frame_with_default_inversions() -> None:
    flow = FlowVector(dx=10.0, dy=6.0, magnitude=math.hypot(10.0, 6.0), angle_rad=0.0,
                      confidence=0.9, timestamp=0.0)
    provider = GenshinMinimapLocalizationProvider(tracker=_StubTracker(flow))
    reading = provider.read(_frame(), frame_id=2, timestamp=1.0)
    # defaults invert both axes, scale 1.0
    assert reading.flow_dx == pytest.approx(-10.0)
    assert reading.flow_dy == pytest.approx(-6.0)
    assert reading.flow_confidence == pytest.approx(0.9)
    # heading = bearing of world motion (atan2(dx, dy)), low trust
    assert reading.heading_deg == pytest.approx(wrap_expected := math.degrees(math.atan2(-10.0, -6.0)) % 360.0)
    assert reading.heading_confidence == pytest.approx(0.3 * 0.9)


def test_provider_respects_scale_and_no_inversion() -> None:
    flow = FlowVector(dx=4.0, dy=0.0, magnitude=4.0, angle_rad=0.0, confidence=1.0, timestamp=0.0)
    provider = GenshinMinimapLocalizationProvider(
        tracker=_StubTracker(flow), flow_world_scale=0.5, invert_x=False, invert_y=False,
    )
    reading = provider.read(_frame(), frame_id=3, timestamp=1.0)
    assert reading.flow_dx == pytest.approx(2.0)
    assert reading.flow_dy == pytest.approx(0.0)


def test_provider_suppresses_heading_below_min_flow() -> None:
    flow = FlowVector(dx=1.0, dy=0.0, magnitude=1.0, angle_rad=0.0, confidence=1.0, timestamp=0.0)
    provider = GenshinMinimapLocalizationProvider(
        tracker=_StubTracker(flow), heading_flow_min_px=3.0,
    )
    reading = provider.read(_frame(), frame_id=4, timestamp=1.0)
    assert reading.heading_deg is None  # too small to infer heading


def test_provider_set_walking_forwards_to_tracker() -> None:
    tracker = _StubTracker(None)
    provider = GenshinMinimapLocalizationProvider(tracker=tracker)
    provider.set_walking(True)
    assert tracker.walking is True


def test_provider_runs_against_real_flow_tracker_without_crashing() -> None:
    # Two distinct frames so the real tracker has a prev frame to correlate.
    rng = np.random.default_rng(0)
    provider = GenshinMinimapLocalizationProvider()
    f1 = rng.integers(0, 255, size=(720, 1280, 3), dtype=np.uint8)
    f2 = rng.integers(0, 255, size=(720, 1280, 3), dtype=np.uint8)
    assert provider.read(f1, 1, 0.0).source == "genshin_minimap"  # primes prev frame
    reading = provider.read(f2, 2, 0.1)
    assert isinstance(reading, LocalizationReading)


# --- processor -------------------------------------------------------------


class _StubProvider:
    def __init__(self, reading: LocalizationReading) -> None:
        self._reading = reading

    def read(self, frame: np.ndarray, frame_id: int, timestamp: float) -> LocalizationReading:
        return self._reading


def test_processor_publishes_pose_to_state_bus_and_observation() -> None:
    reading = LocalizationReading(
        timestamp=1.0, frame_id=1, flow_dx=0.0, flow_dy=5.0, flow_confidence=1.0,
    )
    proc = PoseEstimationProcessor(_StubProvider(reading), fusion=_seeded_fusion())
    bus = StateBus()
    obs = _observation(frame_id=1, t=1.0)
    proc.process(_frame(), obs, bus)

    assert "pose" in obs.extensions
    snap = bus.latest_pose_snapshot()
    assert snap.value is not None
    # seeded at origin, flow (0,5) moves north to y=5
    assert snap.value.position == pytest.approx((0.0, 5.0))


def test_processor_uses_command_source_for_dead_reckoning() -> None:
    empty = LocalizationReading(timestamp=1.0, frame_id=1)
    cmd = MotionCommand(
        timestamp=1.0, forward=1.0, speed_world_units_per_sec=2.0, is_moving=True,
    )
    proc = PoseEstimationProcessor(
        _StubProvider(empty), fusion=_seeded_fusion(), command_source=lambda: cmd,
    )
    bus = StateBus()
    proc.process(_frame(), _observation(frame_id=1, t=1.0), bus)
    pose = bus.latest_pose_snapshot().value
    assert pose is not None
    # heading 0 (north), 2 u/s for 1s -> y=2
    assert pose.position == pytest.approx((0.0, 2.0))


def test_processor_reset_pose_snaps_belief() -> None:
    proc = PoseEstimationProcessor(_StubProvider(LocalizationReading(timestamp=0.0, frame_id=0)))
    pose = proc.reset_pose((10.0, -5.0), 90.0, timestamp=0.0)
    assert pose.position == pytest.approx((10.0, -5.0))
    assert pose.heading_deg == pytest.approx(90.0)
    assert pose.has_absolute_fix


def test_processor_survives_provider_exception() -> None:
    class _Boom:
        def read(self, frame: np.ndarray, frame_id: int, timestamp: float) -> LocalizationReading:
            raise RuntimeError("sensor fault")

    proc = PoseEstimationProcessor(_Boom())
    bus = StateBus()
    # must not raise; pose still published (confidence decays, no measurement)
    proc.process(_frame(), _observation(), bus)
    assert bus.latest_pose_snapshot().value is not None


def _seeded_fusion() -> PoseFusion:
    f = PoseFusion()
    f.reset((0.0, 0.0), 0.0, timestamp=0.0, confidence=1.0)
    return f
