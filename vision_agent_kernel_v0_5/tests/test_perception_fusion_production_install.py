"""Tests for Phase 8: PerceptionFusionRuntime production install.

Verifies:
- Fusion runtime populates all 4 StateBus slots after N frames
- No double-publish of observation (pipeline is single publisher)
- Fusion runtime works as FramePostProcessor
"""
from __future__ import annotations

import time

import numpy as np

from core.state_bus import StateBus
from core.types import FocusState, Observation, UIStateEstimate
from perception.fusion_runtime import (
    CombatSignal,
    FrameQuality,
    NavigationSignal,
    PerceptionFusionRuntime,
)
from planning.screen_state_claim import ScreenStateClaim


def _make_observation(frame_id: int = 1) -> Observation:
    return Observation(
        frame_id=frame_id,
        t_capture=1.0,
        t_processed=1.01,
        latency_ms=10.0,
        viewport_size=(1920, 1080),
        target_track=None,
        obstacle_field=None,
        ui_state=UIStateEstimate(frame_id=frame_id, timestamp=1.0, state="menu", confidence=0.9),
        visual_triggers={},
        os_focus=FocusState(focused=True),
        extensions={},
    )


class TestPerceptionFusionProduction:
    """Test PerceptionFusionRuntime fills StateBus slots."""

    def test_screen_claim_populated_after_process(self):
        bus = StateBus()
        fusion = PerceptionFusionRuntime(state_bus=bus)
        fusion.set_screen_classifier(lambda frame: "menu")
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        obs = _make_observation()

        fusion.process(frame, obs, bus)

        claim = bus.screen_claim.get()
        assert claim is not None
        assert claim.screen_state == "menu"

    def test_affordances_populated_after_process(self):
        bus = StateBus()
        fusion = PerceptionFusionRuntime(state_bus=bus)
        fusion.set_screen_classifier(lambda frame: "dialog")
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)

        fusion.process(frame, _make_observation(), bus)

        affordances = bus.affordances.get()
        assert affordances is not None
        assert len(affordances) > 0

    def test_frame_quality_populated_after_process(self):
        bus = StateBus()
        fusion = PerceptionFusionRuntime(state_bus=bus)
        fusion.set_screen_classifier(lambda frame: "overworld")
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)

        fusion.process(frame, _make_observation(), bus)

        quality = bus.frame_quality.get()
        assert quality is not None
        assert quality.frame_id == 1

    def test_combat_signal_populated_when_detector_set(self):
        bus = StateBus()
        fusion = PerceptionFusionRuntime(state_bus=bus)
        fusion.set_screen_classifier(lambda frame: "combat")
        fusion.set_combat_detector(lambda frame: CombatSignal(enemy_visible=True, enemy_count=1))
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)

        fusion.process(frame, _make_observation(), bus)

        signal = bus.combat_signal.get()
        assert signal is not None
        assert signal.enemy_visible is True

    def test_navigation_signal_populated_when_detector_set(self):
        bus = StateBus()
        fusion = PerceptionFusionRuntime(state_bus=bus)
        fusion.set_screen_classifier(lambda frame: "overworld")
        fusion.set_navigation_detector(lambda frame: NavigationSignal(on_screen=True, marker_direction_deg=90.0))
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)

        fusion.process(frame, _make_observation(), bus)

        signal = bus.navigation_signal.get()
        assert signal is not None
        assert signal.on_screen is True

    def test_no_double_publish_of_observation(self):
        """Fusion process() should NOT publish observation — pipeline does that."""
        bus = StateBus()
        fusion = PerceptionFusionRuntime(state_bus=bus)
        fusion.set_screen_classifier(lambda frame: "menu")
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)

        obs = _make_observation()
        # Publish observation ourselves (simulating pipeline)
        bus.publish_observation(obs)
        v_before = bus.latest_observation.version

        # Process through fusion
        fusion.process(frame, obs, bus)
        v_after = bus.latest_observation.version

        # Observation version should NOT have changed (no double-publish)
        assert v_after == v_before

    def test_all_4_slots_non_empty_after_process(self):
        bus = StateBus()
        fusion = PerceptionFusionRuntime(state_bus=bus)
        fusion.set_screen_classifier(lambda frame: "overworld")
        fusion.set_combat_detector(lambda frame: CombatSignal(enemy_visible=False))
        fusion.set_navigation_detector(lambda frame: NavigationSignal(on_screen=False))
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)

        fusion.process(frame, _make_observation(), bus)

        assert bus.screen_claim.get() is not None
        assert bus.affordances.get() is not None
        assert bus.frame_quality.get() is not None
        assert bus.combat_signal.get() is not None
        assert bus.navigation_signal.get() is not None
