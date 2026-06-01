"""Tests for SpinalReflexAgentImpl + MemoryStore protocol conformance."""
from __future__ import annotations

import tempfile
from pathlib import Path

from agent_kernel.memory import FileMemoryStore
from agent_kernel.protocols import MemoryStore as MemoryStoreProtocol
from agent_kernel.protocols import SpinalReflexAgent as SpinalReflexProtocol
from agent_kernel.spinal_reflex_agent import SpinalReflexAgentImpl
from agent_kernel.types import CombatCommand, Experience, ThreatSignal


class TestSpinalReflexAgentImpl:

    def test_protocol_conformance(self) -> None:
        agent = SpinalReflexAgentImpl()
        assert isinstance(agent, SpinalReflexProtocol)

    def test_evaluate_threats_none_frame(self) -> None:
        agent = SpinalReflexAgentImpl()
        assert agent.evaluate_threats(None) == []

    def test_evaluate_threats_dict_with_danger(self) -> None:
        agent = SpinalReflexAgentImpl()
        frame = {"danger_score": 0.9, "threat_type": "projectile", "direction": 45.0}
        threats = agent.evaluate_threats(frame)
        assert len(threats) == 1
        assert threats[0].threat_type == "projectile"
        assert threats[0].severity == 0.9

    def test_evaluate_threats_dict_low_hp(self) -> None:
        agent = SpinalReflexAgentImpl()
        frame = {"danger_score": 0.1, "hp_ratios": [0.2, 0.9, 1.0, 1.0]}
        threats = agent.evaluate_threats(frame)
        assert any(t.threat_type == "low_hp" for t in threats)

    def test_evaluate_threats_dict_no_danger(self) -> None:
        agent = SpinalReflexAgentImpl()
        frame = {"danger_score": 0.3}
        assert agent.evaluate_threats(frame) == []

    def test_tick_combat_reflex_critical_threat(self) -> None:
        agent = SpinalReflexAgentImpl()
        threats = [ThreatSignal(threat_type="projectile", severity=0.9)]
        cmd = agent.tick_combat_reflex(threats, 0)
        assert cmd is not None
        assert cmd.reflex_action == "dodge"

    def test_tick_combat_reflex_low_hp(self) -> None:
        agent = SpinalReflexAgentImpl()
        threats = [ThreatSignal(threat_type="low_hp", severity=0.8)]
        cmd = agent.tick_combat_reflex(threats, 0)
        assert cmd is not None
        assert cmd.reflex_action == "heal_emergency"

    def test_tick_combat_reflex_combo(self) -> None:
        agent = SpinalReflexAgentImpl(combo_length=5)
        cmd = agent.tick_combat_reflex([], 0)
        assert cmd is not None
        assert cmd.reflex_action == "combo_normal_attack"

    def test_tick_combat_reflex_combo_exhaustion(self) -> None:
        agent = SpinalReflexAgentImpl(combo_length=3)
        cmd = agent.tick_combat_reflex([], 3)
        assert cmd is not None
        assert cmd.reflex_action == "cast_skill_e"

    def test_combo_step_tracking(self) -> None:
        agent = SpinalReflexAgentImpl(combo_length=5)
        assert agent.combo_step == 0
        agent.tick_combat_reflex([], 0)
        assert agent.combo_step == 1

    def test_set_character(self) -> None:
        agent = SpinalReflexAgentImpl()
        agent.set_character(3)
        cmd = agent.tick_combat_reflex([], 2)
        assert cmd is not None
        assert cmd.target_character_index == 3


class TestFileMemoryStoreProtocolConformance:

    def test_protocol_conformance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = FileMemoryStore(path=Path(tmp) / "test.jsonl")
            assert isinstance(store, MemoryStoreProtocol)

    def test_record_and_recall(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = FileMemoryStore(path=Path(tmp) / "test.jsonl")
            exp = Experience(
                goal_description="Level up Zhongli",
                scene_description="Character menu",
                action_taken="Click level up",
                outcome="success",
            )
            store.record(exp)
            results = store.recall("Zhongli level")
            assert len(results) == 1
            assert results[0].goal_description == "Level up Zhongli"

    def test_recall_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = FileMemoryStore(path=Path(tmp) / "test.jsonl")
            assert store.recall("nothing") == []

    def test_recall_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = FileMemoryStore(path=Path(tmp) / "test.jsonl")
            store.record(Experience(
                goal_description="combat boss",
                scene_description="arena",
                action_taken="dodge",
                outcome="failed",
                failure_reason="Too slow",
            ))
            store.record(Experience(
                goal_description="combat boss",
                scene_description="arena",
                action_taken="attack",
                outcome="success",
            ))
            failures = store.recall_failures("combat")
            assert len(failures) == 1
            assert failures[0].outcome == "failed"
