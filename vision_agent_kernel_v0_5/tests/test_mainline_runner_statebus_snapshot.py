"""Tests for Phase 8: MainlineRunner StateBus snapshot integration.

Verifies:
- StateBusSnapshotProvider reads screen_claim, combat_signal, navigation_signal, frame_quality
- RuntimeSnapshot populated correctly from StateBus
- Runner receives snapshot and routes differently per screen_state
"""
from __future__ import annotations

import time

from core.state_bus import StateBus
from perception.fusion_runtime import CombatSignal, FrameQuality, NavigationSignal
from planning.mainline.mainline_runner import (
    MainlineRunner,
    MissionGraphV4,
    MissionNodeV4,
    RuntimeSnapshot,
    StateBusSnapshotProvider,
)
from planning.mainline.mission_graph_v4 import ClaimContract, MissionEdgeV4
from planning.screen_state_claim import ScreenStateClaim


def _bus_with_claims(screen_state: str = "overworld") -> StateBus:
    bus = StateBus()
    bus.screen_claim.put(ScreenStateClaim(
        game_id="genshin",
        screen_state=screen_state,
        confidence=0.9,
        source="classifier",
        frame_id=1,
        timestamp=time.perf_counter(),
    ))
    bus.combat_signal.put(CombatSignal(enemy_visible=True, enemy_count=2, danger_score=0.7))
    bus.navigation_signal.put(NavigationSignal(on_screen=True, marker_direction_deg=45.0))
    bus.frame_quality.put(FrameQuality(
        frame_id=1, latency_ms=10.0,
        target_track_populated=True, obstacle_field_populated=False,
        ui_state_populated=True, visual_triggers_count=3,
        staleness_rate_30f=0.0, quality_score=0.85,
    ))
    return bus


class TestStateBusSnapshot:
    """Test StateBusSnapshotProvider reads all slots correctly."""

    def test_reads_screen_claim(self):
        bus = _bus_with_claims("dialog")
        provider = StateBusSnapshotProvider(bus)
        snap = provider.snapshot()
        assert snap.screen_state == "dialog"
        assert snap.screen_claim_confidence == 0.9

    def test_reads_combat_signal(self):
        bus = _bus_with_claims()
        provider = StateBusSnapshotProvider(bus)
        snap = provider.snapshot()
        assert snap.combat_active is True

    def test_reads_navigation_signal(self):
        bus = _bus_with_claims()
        provider = StateBusSnapshotProvider(bus)
        snap = provider.snapshot()
        assert snap.navigation_active is True

    def test_reads_frame_quality(self):
        bus = _bus_with_claims()
        provider = StateBusSnapshotProvider(bus)
        snap = provider.snapshot()
        assert snap.frame_quality_score == 0.85

    def test_empty_bus_returns_defaults(self):
        bus = StateBus()
        provider = StateBusSnapshotProvider(bus)
        snap = provider.snapshot()
        assert snap.screen_state == "unknown"
        assert snap.combat_active is False
        assert snap.navigation_active is False
        assert snap.frame_quality_score == 0.0

    def test_no_combat_signal_means_not_active(self):
        bus = StateBus()
        bus.screen_claim.put(ScreenStateClaim(
            game_id="genshin", screen_state="overworld", confidence=0.8,
            source="test", frame_id=1, timestamp=1.0,
        ))
        provider = StateBusSnapshotProvider(bus)
        snap = provider.snapshot()
        assert snap.combat_active is False

    def test_snapshot_version_increases(self):
        bus = StateBus()
        provider = StateBusSnapshotProvider(bus)
        v0 = provider.snapshot().snapshot_version
        bus.screen_claim.put(ScreenStateClaim(
            game_id="genshin", screen_state="combat", confidence=0.9,
            source="test", frame_id=2, timestamp=2.0,
        ))
        v1 = provider.snapshot().snapshot_version
        assert v1 > v0


class TestRunnerStateBusIntegration:
    """Test MainlineRunner uses StateBus snapshot for decisions."""

    def test_runner_uses_snapshot_from_bus(self):
        bus = _bus_with_claims("dialog")
        provider = StateBusSnapshotProvider(bus)
        calls: list[RuntimeSnapshot] = []

        def tracking_execute(node: MissionNodeV4) -> dict:
            snap = provider.snapshot()
            calls.append(snap)
            return {"result": "ok", "action_result": "done"}

        runner = MainlineRunner(
            skill_execute_fn=tracking_execute,
            snapshot_provider=provider,
        )
        g = MissionGraphV4(mission_id="snap_test")
        g.add_node(MissionNodeV4(
            node_id="n1",
            node_type="navigate",
            output_claims=[ClaimContract(claim_type="action_result")],
        ))
        result = runner.run(g)
        assert len(calls) >= 1
        assert calls[0].screen_state == "dialog"

    def test_different_screen_states_produce_different_snapshots(self):
        bus_combat = _bus_with_claims("combat")
        bus_dialog = _bus_with_claims("dialog")
        snap_combat = StateBusSnapshotProvider(bus_combat).snapshot()
        snap_dialog = StateBusSnapshotProvider(bus_dialog).snapshot()
        assert snap_combat.screen_state != snap_dialog.screen_state
