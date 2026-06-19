"""Live pose-wiring proof: synthetic frames → provider → fusion → StateBus.

Exercises the self-contained live path (no perception pipeline / post-processor)
that ``perception.live_pose_wiring.wire_genshin_pose`` builds for the AgentLoop.
"""
from __future__ import annotations

import numpy as np
import pytest

from core.state_bus import StateBus
from core.types import LocalizationReading, MotionCommand, MovementIntent, PoseEstimate
from perception.live_pose_wiring import load_minimap_roi, wire_genshin_pose


def _frame(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.integers(0, 255, (1080, 1920, 3), dtype=np.uint8)


def test_profile_roi_is_loaded_not_hardcoded() -> None:
    # genshin_1920x1080.json: minimap 20,20 200x200 against 1920x1080.
    roi = load_minimap_roi("genshin_1920x1080")
    assert roi[0] == pytest.approx(20 / 1920)
    assert roi[1] == pytest.approx(20 / 1080)
    assert roi[2] == pytest.approx(200 / 1920)
    assert roi[3] == pytest.approx(200 / 1080)


def test_unknown_profile_falls_back() -> None:
    roi = load_minimap_roi("does_not_exist")
    assert roi == (0.0, 0.0, 0.10, 0.17)


def test_synthetic_flow_publishes_pose_to_state_bus() -> None:
    """A real minimap shift produces a flow reading → PoseEstimate on the bus."""
    bus = StateBus()
    t = [0.0]
    wiring = wire_genshin_pose(bus, profile="genshin_1920x1080", clock=lambda: t[0])

    assert bus.latest_pose.get() is None

    base = _frame(7)
    # Frame 1: baseline — provider has no previous frame, so flow is None.
    pose1 = wiring.tick(base, frame_id=1)
    assert isinstance(pose1, PoseEstimate)
    assert bus.latest_pose.get() is pose1
    pos_unc_after_baseline = pose1.position_uncertainty

    # Frame 2: shift the minimap content → measured flow shrinks uncertainty
    # relative to a pure dead-reckoning step of the same distance.
    t[0] = 0.05
    shifted = np.roll(base, 6, axis=1)
    pose2 = wiring.tick(shifted, frame_id=2)
    assert bus.latest_pose.get() is pose2
    # A measured flow fix gives the pose real confidence and an absolute belief
    # that moved off the origin.
    assert pose2.confidence > 0.0
    assert pose2.position != (0.0, 0.0)
    # Flow is low-noise: uncertainty must not blow up the way dead-reckoning would.
    assert pose2.position_uncertainty <= pos_unc_after_baseline
    assert "flow" in pose2.source


def test_feed_motion_advances_dead_reckoned_position() -> None:
    """Feeding a MotionCommand moves the predicted position with no measurement."""
    bus = StateBus()
    t = [0.0]
    # Provider that never measures — isolate dead-reckoning.

    class _NullProvider:
        def read(self, frame: np.ndarray, frame_id: int, timestamp: float) -> LocalizationReading:
            return LocalizationReading(timestamp=timestamp, frame_id=frame_id, source="null")

    wiring = wire_genshin_pose(
        bus, provider=_NullProvider(), clock=lambda: t[0],
    )
    frame = _frame(1)

    # Baseline tick establishes the clock; heading 0 = +Y north.
    wiring.tick(frame, frame_id=1)
    start = wiring.current_pose().position

    # Executor commands "walk forward" at 5 u/s for ~0.2s.
    wiring.feed_motion(
        MotionCommand(
            timestamp=0.0,
            forward=1.0,
            speed_world_units_per_sec=5.0,
            is_moving=True,
        )
    )
    t[0] = 0.2
    pose = wiring.tick(frame, frame_id=2)

    # Moved forward (north / +Y) by ~ 5 * 0.2 = 1.0 units, uncertainty grew.
    assert pose.position[1] > start[1] + 0.5
    assert pose.position_uncertainty > 0.0
    assert "deadreckon" in pose.source


def test_movement_intent_adapter_drives_dead_reckoning() -> None:
    """feed_movement_intent adapts the kernel-native MovementIntent."""
    bus = StateBus()
    t = [0.0]

    class _NullProvider:
        def read(self, frame: np.ndarray, frame_id: int, timestamp: float) -> LocalizationReading:
            return LocalizationReading(timestamp=timestamp, frame_id=frame_id, source="null")

    wiring = wire_genshin_pose(
        bus,
        provider=_NullProvider(),
        walk_speed_world_units_per_sec=4.0,
        clock=lambda: t[0],
    )
    frame = _frame(2)
    wiring.tick(frame, frame_id=1)
    start = wiring.current_pose().position

    wiring.feed_movement_intent(MovementIntent(move_forward=1.0, move_right=0.0), now=0.0)
    t[0] = 0.25
    pose = wiring.tick(frame, frame_id=2)
    assert pose.position[1] > start[1] + 0.5


def test_reset_pose_snaps_belief() -> None:
    bus = StateBus()
    wiring = wire_genshin_pose(bus, profile="genshin_1920x1080")
    pose = wiring.reset_pose((10.0, 20.0), 90.0, timestamp=0.0, confidence=1.0)
    assert pose.position == (10.0, 20.0)
    assert pose.heading_deg == pytest.approx(90.0)
    assert pose.has_absolute_fix is True
    assert pose.position_uncertainty == 0.0
