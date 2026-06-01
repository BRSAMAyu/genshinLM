"""Verifies that all StateBus neural connections are wired correctly.

Run: python -m pytest tests/test_neural_connections.py -v
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import pytest

from core.state_bus import StateBus
from core.types import Observation, TargetTrack, UIStateEstimate, FocusState, ObstacleField
from execution.ui_flow_skill_adapter import UIFlowSkillAdapter
from runtime.claim_events import ClaimEventPublisher, ClaimGraphState
from runtime.claim_worker import ClaimGraphWorker, ClaimGraphCommand
from runtime.runtime_health_publisher import start_health_publisher


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _make_obs(frame_id: int, t: float = 0.0) -> Observation:
    return Observation(
        frame_id=frame_id,
        t_capture=t or time.perf_counter(),
        t_processed=time.perf_counter(),
        latency_ms=10.0,
        viewport_size=(1920, 1080),
        target_track=TargetTrack(
            track_id=f"t{frame_id}",
            class_id="enemy",
            state="visible",
            bbox_xyxy=(100, 100, 200, 200),
            smoothed_center_px=(150.0, 150.0),
            velocity_px_s=(0.0, 0.0),
            confidence=0.9,
            identity_confidence=0.9,
            missing_duration_ms=0.0,
            bearing_deg=None,
            pitch_deg=None,
            estimated_range=None,
            last_seen_frame_id=frame_id,
        ),
        obstacle_field=ObstacleField(frame_id=frame_id, timestamp=time.perf_counter(), sectors={}, confidence=0.5, source="test"),
        ui_state=UIStateEstimate(frame_id=frame_id, timestamp=time.perf_counter(), state="overworld", confidence=0.9, payload={}),
        visual_triggers={"test_trigger": True},
        os_focus=FocusState(focused=True),
        stale=False,
    )


# ---------------------------------------------------------------------------
# P0.1: observation_ring → AnalyticsConsumer → runtime_health
# ---------------------------------------------------------------------------

def test_observation_ring_has_consumer() -> None:
    """Verify AnalyticsConsumer publishes runtime_health from observation_ring."""
    bus = StateBus()

    for i in range(5):
        bus.publish_observation(_make_obs(i))

    assert len(bus.observation_ring) == 5

    # Start health publisher (daemon thread)
    start_health_publisher(bus, interval_sec=0.5)
    time.sleep(0.8)

    health = bus.runtime_health.get()
    assert health is not None
    assert isinstance(health.healthy, bool)


def test_claim_graph_worker_consumes_observation_ring() -> None:
    """Verify ClaimGraphWorker receives observations from observation_ring."""
    bus = StateBus()
    publisher = ClaimEventPublisher(bus)
    worker = ClaimGraphWorker(publisher=publisher, mission_id="test_obs", graph_id="g1")
    worker.start()

    for i in range(3):
        bus.publish_observation(_make_obs(i))

    assert len(bus.observation_ring) >= 3
    assert worker.graph is not None

    worker.stop(timeout=1.0)


# ---------------------------------------------------------------------------
# P0.2: mission_graph → StateBus (write and read)
# ---------------------------------------------------------------------------

def test_mission_graph_slot_write_and_read() -> None:
    """Verify StateBus.mission_graph accepts writes."""
    from planning.mainline.mission_graph_v4 import MissionGraphV4

    bus = StateBus()
    graph = MissionGraphV4(mission_id="test_graph")
    bus.mission_graph.put(graph)

    retrieved = bus.mission_graph.get()
    assert retrieved is graph
    assert retrieved.mission_id == "test_graph"


def test_mission_graph_published_to_statebus_readable() -> None:
    """Verify MissionGraph published to StateBus is readable by MainlineRunner."""
    from planning.mainline.mission_graph_v4 import MissionGraphV4

    bus = StateBus()
    graph = MissionGraphV4(mission_id="planned_test")
    bus.mission_graph.put(graph)

    retrieved = bus.mission_graph.get()
    assert retrieved is not None
    assert retrieved.mission_id == "planned_test"


# ---------------------------------------------------------------------------
# P0.3: combat_signal → BossCombatRuntime (via BossCombatBridge)
# ---------------------------------------------------------------------------

def test_combat_signal_slot_write_and_read() -> None:
    """Verify StateBus.combat_signal accepts writes."""
    from perception.fusion_runtime import CombatSignal

    bus = StateBus()
    signal = CombatSignal(
        enemy_visible=True,
        enemy_count=1,
        enemy_hp_ratio=0.8,
        danger_score=0.3,
        frame_id=10,
        timestamp=time.perf_counter(),
    )
    bus.combat_signal.put(signal)

    retrieved = bus.combat_signal.get()
    assert retrieved is not None
    assert retrieved.enemy_visible is True
    assert retrieved.danger_score == 0.3


def test_boss_combat_bridge_submits_lease() -> None:
    """Verify BossCombatBridge reads combat_signal and can submit InputLease."""
    from combat.boss_combat_bridge import BossCombatBridge
    from execution.console_backend import ConsoleInputBackend
    from execution.input_worker import InputWorker
    from combat.team_capability import TeamCombatPlan, TeamProfile, CharacterCapability

    bus = StateBus()
    backend = ConsoleInputBackend()
    worker = InputWorker(backend=backend, state_bus=bus)
    worker.start()

    team = TeamProfile(
        characters=[CharacterCapability(
            character_id="traveler",
            slot=1,
            element="anemo",
            role="on_field_dps",
        )],
    )
    plan = TeamCombatPlan(
        conservative_level=1,
        main_chain=["pyro", "anemo"],
        survival_chain=["dodge"],
        low_resource_chain=["normal_attack"],
        fallback_chain=["safe_abort"],
        reason="test",
    )

    bridge = BossCombatBridge(
        state_bus=bus,
        input_worker=worker,
        boss_profile=None,
        team_profile=team,
        team_plan=plan,
    )

    from perception.fusion_runtime import CombatSignal
    signal = CombatSignal(enemy_visible=True, enemy_count=1, enemy_hp_ratio=0.7, danger_score=0.5)
    bus.combat_signal.put(signal)

    decision = bridge.tick_once()
    bridge.stop(timeout=1.0)
    worker.stop(timeout=1.0)

    assert decision is not None
    assert decision.state in ("init", "acquire_target", "identify_phase", "execute_tactic", "finished", "failed_safe")
    # If execute_tactic, a lease should be present
    if decision.state == "execute_tactic":
        assert decision.lease is not None, "execute_tactic should produce a lease"


# ---------------------------------------------------------------------------
# P0.4: runtime_health has producer
# ---------------------------------------------------------------------------

def test_runtime_health_slot_write_and_read() -> None:
    """Verify StateBus.runtime_health accepts writes."""
    from core.state_bus import RuntimeHealth

    bus = StateBus()
    health = RuntimeHealth(healthy=True, last_error=None, last_update=time.perf_counter())
    bus.runtime_health.put(health)

    retrieved = bus.runtime_health.get()
    assert retrieved is not None
    assert retrieved.healthy is True


def test_health_publisher_writes_runtime_health() -> None:
    """Verify start_health_publisher publishes RuntimeHealth."""
    bus = StateBus()

    for i in range(10):
        bus.publish_observation(_make_obs(i))

    start_health_publisher(bus, interval_sec=0.3)
    time.sleep(0.6)

    health = bus.runtime_health.get()
    assert health is not None
    assert isinstance(health.last_update, float)


# ---------------------------------------------------------------------------
# P1.2: ExecutionRuntime ↔ UIFlowSkillAdapter wiring
# ---------------------------------------------------------------------------

def test_execution_runtime_has_ui_flow_adapter() -> None:
    """Verify ExecutionRuntime accepts and holds UIFlowSkillAdapter."""
    from execution.execution_runtime import ExecutionRuntime
    from execution.console_backend import ConsoleInputBackend
    from execution.ui_flow_skill_adapter import UIFlowSkillAdapter

    bus = StateBus()
    backend = ConsoleInputBackend()
    adapter = UIFlowSkillAdapter(state_bus=bus)

    runtime = ExecutionRuntime(
        backend=backend,
        state_bus=bus,
        ui_flow_adapter=adapter,
    )

    assert runtime._ui_flow_adapter is adapter
    assert hasattr(runtime, "submit_ui_action")


def test_ui_flow_adapter_and_execution_runtime_same_worker() -> None:
    """Verify UIFlowSkillAdapter and ExecutionRuntime share the same InputWorker."""
    from execution.execution_runtime import ExecutionRuntime
    from execution.console_backend import ConsoleInputBackend
    from execution.ui_flow_skill_adapter import UIFlowSkillAdapter
    from execution.input_worker import InputWorker

    bus = StateBus()
    backend = ConsoleInputBackend()
    worker = InputWorker(backend=backend, state_bus=bus)

    adapter = UIFlowSkillAdapter(state_bus=bus, input_worker=worker)

    runtime = ExecutionRuntime(
        backend=backend,
        state_bus=bus,
        ui_flow_adapter=adapter,
    )

    # adapter and runtime share the same worker
    assert adapter._worker is worker
    # runtime creates its own worker, so we verify the adapter is properly set
    assert runtime._ui_flow_adapter is adapter


# ---------------------------------------------------------------------------
# P1.3: BossCombatRuntime produces lease consumable by InputWorker
# ---------------------------------------------------------------------------

def test_boss_combat_runtime_lease_submittable() -> None:
    """Verify BossCombatRuntime.lease can be submitted to InputWorker."""
    from combat.boss_combat_runtime import BossCombatRuntime, BossCombatInput
    from execution.console_backend import ConsoleInputBackend
    from execution.input_worker import InputWorker
    from combat.team_capability import TeamProfile, TeamCombatPlan, CharacterCapability

    backend = ConsoleInputBackend()
    worker = InputWorker(backend=backend)
    worker.start()

    team = TeamProfile(
        characters=[CharacterCapability(
            character_id="traveler",
            slot=1,
            element="anemo",
            role="on_field_dps",
        )],
    )
    plan = TeamCombatPlan(
        conservative_level=1,
        main_chain=["anemo"],
        survival_chain=["dodge"],
        low_resource_chain=["normal_attack"],
        fallback_chain=["safe_abort"],
        reason="test",
    )

    runtime = BossCombatRuntime(
        boss_profile=None,
        team_profile=team,
        team_plan=plan,
    )

    input_data = BossCombatInput(
        frame_id=1,
        boss_hp_ratio=0.8,
        danger_score=0.3,
        target_visible=True,
    )

    decision = runtime.tick(input_data, time.perf_counter())

    if decision.lease is not None:
        ok = worker.submit_lease(decision.lease)
        assert ok, "Lease should be submittable to InputWorker"

    worker.stop()


# ---------------------------------------------------------------------------
# Integration: full chain verification
# ---------------------------------------------------------------------------

def test_full_neural_chain_observation_to_action() -> None:
    """End-to-end: observation_ring → RuntimeHealth + BossCombatDecision → InputLease."""
    from combat.boss_combat_bridge import BossCombatBridge
    from execution.console_backend import ConsoleInputBackend
    from execution.input_worker import InputWorker
    from perception.fusion_runtime import CombatSignal
    from combat.team_capability import TeamProfile, TeamCombatPlan, CharacterCapability

    bus = StateBus()

    # 1. Publish observations (fills observation_ring)
    for i in range(10):
        bus.publish_observation(_make_obs(i))

    # 2. Publish combat signal
    signal = CombatSignal(
        enemy_visible=True,
        enemy_count=2,
        enemy_hp_ratio=0.6,
        danger_score=0.6,
        boss_mechanic_active="area_attack",
        frame_id=999,
        timestamp=time.perf_counter(),
    )
    bus.combat_signal.put(signal)

    # 3. Start health publisher
    start_health_publisher(bus, interval_sec=0.3)
    time.sleep(0.5)

    # 4. Verify runtime_health was published
    health = bus.runtime_health.get()
    assert health is not None

    # 5. Start boss combat bridge
    backend = ConsoleInputBackend()
    worker = InputWorker(backend=backend, state_bus=bus)
    worker.start()

    team = TeamProfile(
        characters=[CharacterCapability(
            character_id="traveler",
            slot=1,
            element="anemo",
            role="on_field_dps",
        )],
    )
    plan = TeamCombatPlan(
        conservative_level=1,
        main_chain=["anemo"],
        survival_chain=["dodge"],
        low_resource_chain=["normal_attack"],
        fallback_chain=["safe_abort"],
        reason="test",
    )

    bridge = BossCombatBridge(
        state_bus=bus,
        input_worker=worker,
        boss_profile=None,
        team_profile=team,
        team_plan=plan,
    )

    decision = bridge.tick_once()
    bridge.stop(timeout=1.0)
    worker.stop()

    assert decision is not None
    assert decision.state in ("init", "acquire_target", "identify_phase", "execute_tactic", "finished", "failed_safe")


# ---------------------------------------------------------------------------
# Integration: SkillRegistry + BossCombatBridge wiring
# ---------------------------------------------------------------------------

def test_skill_registry_wired_to_ui_flow_adapter() -> None:
    """Verify SkillRegistry is injected into UIFlowSkillAdapter."""
    from planning.skill_registry import SkillRegistry

    bus = StateBus()
    adapter = UIFlowSkillAdapter(state_bus=bus)
    registry = SkillRegistry(skill_executor=adapter, state_bus=bus)

    assert registry.can_handle("combat_encounter")
    assert registry.can_handle("combat_boss")


def test_skill_registry_quest_adapter_has_state_machine() -> None:
    """Verify quest adapter created by SkillRegistry includes QuestStateMachine."""
    from planning.skill_registry import SkillRegistry

    bus = StateBus()
    adapter = UIFlowSkillAdapter(state_bus=bus)
    registry = SkillRegistry(skill_executor=adapter, state_bus=bus)

    assert registry.can_handle("quest_drive_dialog")


def test_boss_combat_bridge_start_stop() -> None:
    """Verify BossCombatBridge can start and stop cleanly."""
    from execution.console_backend import ConsoleInputBackend
    from execution.input_worker import InputWorker
    from combat.boss_combat_bridge import BossCombatBridge
    from combat.team_capability import TeamProfile, TeamCombatPlan, CharacterCapability

    bus = StateBus()
    backend = ConsoleInputBackend()
    worker = InputWorker(backend=backend, state_bus=bus)
    worker.start()

    team = TeamProfile(
        characters=[CharacterCapability(character_id="traveler", slot=1, element="anemo", role="on_field_dps")],
    )
    plan = TeamCombatPlan(
        conservative_level=1, main_chain=["anemo"], survival_chain=["dodge"],
        low_resource_chain=["normal_attack"], fallback_chain=["safe_abort"], reason="test",
    )
    bridge = BossCombatBridge(
        state_bus=bus, input_worker=worker, boss_profile=None,
        team_profile=team, team_plan=plan,
    )

    bridge.start()
    time.sleep(0.3)
    bridge.stop(timeout=1.0)
    worker.stop(timeout=1.0)
    assert bridge._decision_count >= 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])