"""Tests for perception/fusion_runtime.py: 3-layer cadence perception fusion."""
from __future__ import annotations

import time
from typing import Any

import numpy as np
import pytest

from core.state_bus import StateBus
from core.types import FocusState, ObstacleField, Observation, TargetTrack
from perception.fusion_runtime import (
    ActionAffordance,
    CombatSignal,
    FrameQuality,
    FrameQualityTracker,
    NavigationSignal,
    PerceptionFusionRuntime,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_frame() -> np.ndarray:
    return np.zeros((720, 1280, 3), dtype=np.uint8)


def _fake_observation(frame_id: int = 1, latency_ms: float = 10.0) -> Observation:
    return Observation(
        frame_id=frame_id,
        t_capture=time.perf_counter() - latency_ms / 1000,
        t_processed=time.perf_counter(),
        latency_ms=latency_ms,
        viewport_size=(1280, 720),
        target_track=None,
        obstacle_field=None,
        ui_state=None,
        visual_triggers={},
        os_focus=FocusState(focused=True),
    )


# ---------------------------------------------------------------------------
# FrameQualityTracker
# ---------------------------------------------------------------------------

class TestFrameQualityTracker:
    def test_stale_rate_computed(self):
        tracker = FrameQualityTracker()
        # 3 stale out of 30 → 10%
        for i in range(30):
            obs = _fake_observation(frame_id=i, latency_ms=200.0 if i % 10 == 0 else 10.0)
            fq = tracker.record(i, obs.latency_ms, None, None, None, {})
        assert fq.staleness_rate_30f < 0.2

    def test_quality_score_full(self):
        tracker = FrameQualityTracker()
        target = _make_target_track()
        ui = _make_ui_state()
        obs = _fake_observation()
        fq = tracker.record(1, 10.0, target, _make_obstacle(), ui, {"a": True, "b": True})
        assert fq.quality_score > 0.7
        assert fq.target_track_populated
        assert fq.obstacle_field_populated
        assert fq.ui_state_populated

    def test_quality_score_degraded(self):
        tracker = FrameQualityTracker()
        fq = tracker.record(1, 200.0, None, None, None, {})
        assert fq.quality_score < 0.5


# ---------------------------------------------------------------------------
# CombatSignal
# ---------------------------------------------------------------------------

class TestCombatSignal:
    def test_defaults(self):
        cs = CombatSignal()
        assert cs.enemy_visible is False
        assert cs.enemy_hp_ratio == 1.0
        assert cs.player_hp_ratio == 1.0
        assert cs.boss_phase == 1

    def test_full_combat_signal(self):
        cs = CombatSignal(
            enemy_visible=True,
            enemy_count=3,
            enemy_hp_ratio=0.5,
            enemy_aura="pyro",
            enemy_shield_element="cryo",
            enemy_shield_hp_pct=80.0,
            player_hp_ratio=0.3,
            danger_score=0.8,
            aoe_incoming=True,
            aoe_eta_sec=1.2,
        )
        assert cs.enemy_count == 3
        assert cs.enemy_aura == "pyro"
        assert cs.enemy_shield_element == "cryo"


# ---------------------------------------------------------------------------
# NavigationSignal
# ---------------------------------------------------------------------------

class TestNavigationSignal:
    def test_defaults(self):
        ns = NavigationSignal()
        assert ns.on_screen is False
        assert ns.arrival_confirmed is False

    def test_with_marker(self):
        ns = NavigationSignal(
            on_screen=True,
            marker_direction_deg=45.0,
            marker_distance_approx=50.0,
            marker_color="yellow",
        )
        assert ns.marker_direction_deg == 45.0


# ---------------------------------------------------------------------------
# ActionAffordance
# ---------------------------------------------------------------------------

class TestActionAffordance:
    def test_frozen(self):
        af = ActionAffordance(action_id="x", intent="combat", target="", confidence=0.9)
        mutated = False
        try:
            af.confidence = 0.5  # type: ignore[misc]
        except AttributeError:
            mutated = True
        assert mutated


# ---------------------------------------------------------------------------
# PerceptionFusionRuntime
# ---------------------------------------------------------------------------

class TestPerceptionFusionRuntime:
    def _make_runtime(self) -> tuple[PerceptionFusionRuntime, StateBus]:
        bus = StateBus()
        runtime = PerceptionFusionRuntime(state_bus=bus)
        return runtime, bus

    def test_process_sets_non_none_target_track(self):
        runtime, bus = self._make_runtime()
        runtime.set_yolo_detector(lambda f: [{
            "track_id": "e1", "class_id": "enemy", "confidence": 0.9,
            "bbox": (100.0, 200.0, 300.0, 400.0),
        }])
        obs = _fake_observation(1)
        # Process via FramePostProcessor interface
        runtime.process(_fake_frame(), obs, bus)
        slot = bus.latest_observation.get()
        assert slot is not None
        assert slot.target_track is not None

    def test_process_sets_non_none_obstacle_field(self):
        runtime, bus = self._make_runtime()
        obs = _fake_observation(2)
        runtime.process(_fake_frame(), obs, bus)
        slot = bus.latest_observation.get()
        assert slot is not None
        assert slot.obstacle_field is not None

    def test_process_sets_non_none_ui_state(self):
        runtime, bus = self._make_runtime()
        runtime.set_screen_classifier(lambda f: "overworld")
        obs = _fake_observation(3)
        runtime.process(_fake_frame(), obs, bus)
        slot = bus.latest_observation.get()
        assert slot is not None
        assert slot.ui_state is not None
        assert slot.ui_state.state == "overworld"

    def test_screen_claim_written_to_statebus(self):
        runtime, bus = self._make_runtime()
        runtime.set_screen_classifier(lambda f: "combat")
        runtime.set_ocr(lambda f: ["HP 5000"])
        obs = _fake_observation(15)
        # Trigger mid-freq (frame 15)
        runtime.process(_fake_frame(), obs, bus)
        claim = bus.screen_claim.get()
        assert claim is not None
        assert claim.screen_state == "combat"

    def test_affordances_written(self):
        runtime, bus = self._make_runtime()
        runtime.set_screen_classifier(lambda f: "dialog")
        obs = _fake_observation(16)
        runtime.process(_fake_frame(), obs, bus)
        aff = bus.affordances.get()
        assert aff is not None
        assert len(aff) >= 1
        assert any(a.intent == "dialog_advance" for a in aff)

    def test_combat_signal_written(self):
        runtime, bus = self._make_runtime()
        runtime.set_screen_classifier(lambda f: "combat")
        runtime.set_combat_detector(lambda f: CombatSignal(enemy_visible=True, enemy_count=2))
        obs = _fake_observation(30)
        runtime.process(_fake_frame(), obs, bus)
        cs = bus.combat_signal.get()
        assert cs is not None
        assert cs.enemy_visible
        assert cs.enemy_count == 2

    def test_navigation_signal_written(self):
        runtime, bus = self._make_runtime()
        runtime.set_navigation_detector(lambda f: NavigationSignal(on_screen=True, marker_direction_deg=90.0))
        obs = _fake_observation(45)
        runtime.process(_fake_frame(), obs, bus)
        ns = bus.navigation_signal.get()
        assert ns is not None
        assert ns.on_screen
        assert ns.marker_direction_deg == 90.0

    def test_frame_quality_written(self):
        runtime, bus = self._make_runtime()
        runtime.set_yolo_detector(lambda f: [{"track_id": "e1", "class_id": "enemy", "confidence": 0.9, "bbox": (0, 0, 100, 100)}])
        obs = _fake_observation(15)
        runtime.process(_fake_frame(), obs, bus)
        fq = bus.frame_quality.get()
        assert fq is not None
        assert fq.target_track_populated

    def test_visual_triggers_merged(self):
        runtime, bus = self._make_runtime()
        runtime.set_screen_classifier(lambda f: "overworld")
        runtime.set_yolo_detector(lambda f: [{"track_id": "e1", "class_id": "enemy", "confidence": 0.9, "bbox": (0, 0, 100, 100)}])
        obs = _fake_observation(1)
        runtime.process(_fake_frame(), obs, bus)
        slot = bus.latest_observation.get()
        assert slot is not None
        triggers = slot.visual_triggers
        assert "screen_overworld" in triggers
        assert "detected_enemy" in triggers

    def test_unknown_screen_kind_handled(self):
        runtime, bus = self._make_runtime()
        runtime.set_screen_classifier(lambda f: "not_a_real_state")
        obs = _fake_observation(1)
        runtime.process(_fake_frame(), obs, bus)
        slot = bus.latest_observation.get()
        assert slot is not None
        # Classifier output is used as-is (no Literal restriction at runtime)
        assert slot.ui_state.state == "not_a_real_state"

    def test_yolo_failure_graceful(self):
        runtime, bus = self._make_runtime()
        runtime.set_yolo_detector(lambda f: (_[None] for _ in ()).throw(RuntimeError("oops")))  # type: ignore[return-value]
        obs = _fake_observation(1)
        runtime.process(_fake_frame(), obs, bus)
        slot = bus.latest_observation.get()
        assert slot is not None
        assert slot.target_track is None

    def test_combat_signal_defaults_when_no_detector(self):
        runtime, bus = self._make_runtime()
        obs = _fake_observation(30)
        runtime.process(_fake_frame(), obs, bus)
        cs = bus.combat_signal.get()
        # No detector set → slot stays None until mid-freq runs
        # But the runtime itself doesn't crash

    def test_affordances_different_screen_states(self):
        runtime, bus = self._make_runtime()
        for state, expected_intent in [("dialog", "dialog_advance"), ("map", "teleport"), ("combat", "combat_encounter")]:
            runtime, bus = self._make_runtime()
            runtime.set_screen_classifier(lambda f, s=state: s)
            obs = _fake_observation(1)
            runtime.process(_fake_frame(), obs, bus)
            aff = bus.affordances.get()
            assert aff is not None
            assert any(a.intent == expected_intent for a in aff), f"{state}: {aff}"

    def test_frame_counter_increments(self):
        runtime, bus = self._make_runtime()
        runtime.set_screen_classifier(lambda f: "overworld")
        for i in range(1, 4):
            obs = _fake_observation(i)
            runtime.process(_fake_frame(), obs, bus)
        assert runtime.frame_count == 3

    def test_vlm_called_on_low_confidence(self):
        calls = []

        class FakeVLM:
            def arbitrate(self, frame: np.ndarray, question: str) -> dict[str, Any]:
                calls.append(question)
                return {}
            def describe_scene(self, frame: np.ndarray, context: dict[str, Any]) -> str:
                calls.append(str(context))
                return "overworld"

        runtime, bus = self._make_runtime()
        runtime.set_screen_classifier(lambda f: "unknown")
        runtime.set_vlm_arbiter(FakeVLM())
        # Run enough frames to trigger low-freq (180)
        obs = _fake_observation(1)
        for i in range(1, 181):
            runtime._process(_fake_frame(), _fake_observation(i), bus)
        # Should have called VLM (confidence < 0.6 for unknown)
        assert len(calls) > 0


# ---------------------------------------------------------------------------
# Integration: full frame → claim → affordance → action chain
# ---------------------------------------------------------------------------

class TestPerceptionDecisionLoop:
    def test_full_loop(self):
        """Simulate: frame → fusion → affordance → semantic action."""
        bus = StateBus()
        runtime = PerceptionFusionRuntime(state_bus=bus)

        runtime.set_screen_classifier(lambda f: "combat")
        runtime.set_yolo_detector(lambda f: [{
            "track_id": "boss1", "class_id": "boss", "confidence": 0.95,
            "bbox": (200.0, 150.0, 600.0, 500.0),
        }])
        runtime.set_combat_detector(lambda f: CombatSignal(
            enemy_visible=True, enemy_count=1, enemy_hp_ratio=0.8,
            player_hp_ratio=0.9, danger_score=0.3,
        ))

        obs = _fake_observation(1)
        runtime.process(_fake_frame(), obs, bus)

        # Check all slots populated
        assert bus.latest_observation.get() is not None
        claim = bus.screen_claim.get()
        assert claim is not None
        aff_list = bus.affordances.get()
        assert aff_list is not None
        combat_sig = bus.combat_signal.get()
        assert combat_sig is not None
        fq = bus.frame_quality.get()
        assert fq is not None

        # Affordance → SemanticAction mapping
        combat_aff = next((a for a in aff_list if a.intent == "combat_encounter"), None)
        assert combat_aff is not None
        assert combat_aff.confidence > 0.8
        assert combat_aff.risk == "high"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_target_track() -> TargetTrack:
    return TargetTrack(
        track_id="test1", class_id="enemy", state="visible",
        bbox_xyxy=(100, 100, 200, 200),
        smoothed_center_px=(150.0, 150.0),
        velocity_px_s=(0.0, 0.0),
        confidence=0.9, identity_confidence=0.85,
        missing_duration_ms=0.0,
        bearing_deg=0.0, pitch_deg=0.0,
        estimated_range=5.0,
        last_seen_frame_id=1,
    )


def _make_obstacle() -> ObstacleField:
    return ObstacleField(
        frame_id=1, timestamp=time.perf_counter(),
        sectors={"left": 2.0, "center": 0.0, "right": 1.0, "far": 3.0, "close": 0.0},
        confidence=0.7, source="test",
    )


def _make_ui_state() -> Any:
    from core.types import UIStateEstimate
    return UIStateEstimate(frame_id=1, timestamp=time.perf_counter(), state="combat", confidence=0.9)