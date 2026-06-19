"""Tests for DecisionMemory → MainlineRunner integration."""
from __future__ import annotations

import pytest

from learning.decision_memory import DecisionMemory, DecisionQuery
from planning.mainline.mainline_runner import MainlineRunner
from planning.mainline.mission_graph_v4 import (
    ClaimContract,
    MissionEdgeV4,
    MissionGraphV4,
    MissionNodeV4,
)


def _graph_with_nodes() -> MissionGraphV4:
    graph = MissionGraphV4(mission_id="test_dm")
    graph.add_node(MissionNodeV4(
        node_id="combat_1",
        node_type="combat",
        metadata={"skill_intent": "defeat_enemy", "capsule_id": "genshin"},
    ))
    graph.add_node(MissionNodeV4(
        node_id="dialog_1",
        node_type="dialog",
        metadata={"skill_intent": "talk_to_npc", "capsule_id": "genshin"},
    ))
    return graph


def _valid_graph() -> MissionGraphV4:
    """Graph with edges and claims for run() validation."""
    graph = MissionGraphV4(mission_id="test_dm_valid")
    graph.add_node(MissionNodeV4(
        node_id="combat_1",
        node_type="combat",
        metadata={"skill_intent": "defeat_enemy", "capsule_id": "genshin"},
    ))
    graph.add_node(MissionNodeV4(
        node_id="dialog_1",
        node_type="dialog",
        output_claims=(ClaimContract("quest_objective_changed"),),
        metadata={"skill_intent": "talk_to_npc", "capsule_id": "genshin"},
    ))
    graph.add_edge(MissionEdgeV4(from_node="combat_1", to_node="dialog_1"))
    return graph


class TestDecisionMemoryPlannerWiring:
    def test_runner_accepts_decision_memory(self) -> None:
        dm = DecisionMemory(db_path=":memory:")
        runner = MainlineRunner(decision_memory=dm)
        assert runner._decision_memory is dm

    def test_inject_learned_strategy_returns_none_when_empty(self) -> None:
        dm = DecisionMemory(db_path=":memory:")
        runner = MainlineRunner(decision_memory=dm)
        graph = _graph_with_nodes()
        node = graph.get_node("combat_1")
        assert node is not None
        result = runner._inject_learned_strategy(node)
        assert result is None

    def test_inject_learned_strategy_returns_steps_when_found(self) -> None:
        dm = DecisionMemory(db_path=":memory:")
        dm.record(
            goal="defeat_enemy",
            capsule_id="genshin",
            screen_state="world_hud",
            plan=[{"action": "attack", "target": "enemy"}],
            success=True,
            duration_sec=5.0,
            confidence=0.85,
        )
        runner = MainlineRunner(decision_memory=dm)
        graph = _graph_with_nodes()
        node = graph.get_node("combat_1")
        assert node is not None
        result = runner._inject_learned_strategy(node)
        assert result is not None
        assert "learned_steps" in result
        assert result["learned_steps"][0]["action"] == "attack"

    def test_inject_ignores_low_confidence(self) -> None:
        dm = DecisionMemory(db_path=":memory:")
        dm.record(
            goal="defeat_enemy",
            capsule_id="genshin",
            screen_state="world_hud",
            plan=[{"action": "attack"}],
            success=True,
            duration_sec=5.0,
            confidence=0.3,
        )
        runner = MainlineRunner(decision_memory=dm)
        graph = _graph_with_nodes()
        node = graph.get_node("combat_1")
        assert node is not None
        result = runner._inject_learned_strategy(node)
        assert result is None

    def test_record_on_single_node_execution(self) -> None:
        dm = DecisionMemory(db_path=":memory:")
        call_log: list[str] = []

        def skill_fn(node: object) -> dict:
            call_log.append("executed")
            return {"success": True}

        runner = MainlineRunner(
            decision_memory=dm,
            skill_execute_fn=skill_fn,
        )
        graph = _graph_with_nodes()
        node = graph.get_node("combat_1")
        assert node is not None
        result = runner._execute_node(node, set())
        assert result.status == "completed"
        # _record_to_decision_memory is called in run(), not _execute_node
        # So we test _record_to_decision_memory directly
        runner._record_to_decision_memory(node, result, success=True)
        records = dm.query(DecisionQuery(goal="defeat_enemy"))
        assert len(records) >= 1
        assert records[0].success is True

    def test_full_run_records_all_nodes(self) -> None:
        dm = DecisionMemory(db_path=":memory:")

        def skill_fn(node: object) -> dict:
            return {"success": True}

        runner = MainlineRunner(
            decision_memory=dm,
            skill_execute_fn=skill_fn,
        )
        graph = _valid_graph()
        result = runner.run(graph)
        combat_records = dm.query(DecisionQuery(goal="defeat_enemy"))
        dialog_records = dm.query(DecisionQuery(goal="talk_to_npc"))
        assert len(combat_records) >= 1
        assert len(dialog_records) >= 1

    def test_no_decision_memory_still_works(self) -> None:
        runner = MainlineRunner(decision_memory=None)

        def skill_fn(node: object) -> dict:
            return {"success": True}

        runner._skill_execute = skill_fn
        graph = _valid_graph()
        result = runner.run(graph)
        assert result is not None
