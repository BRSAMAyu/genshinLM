"""Tests for MainlineRunner node type branching (C1 fix)."""
from __future__ import annotations

import pytest

from planning.mainline.mainline_runner import MainlineRunner
from planning.mainline.mission_graph_v4 import (
    ClaimContract,
    MissionGraphV4,
    MissionNodeV4,
    NodeBudget,
)


def _node(nid: str, ntype: str) -> MissionNodeV4:
    return MissionNodeV4(
        node_id=nid,
        node_type=ntype,
        skill_candidates=("generic_skill",),
        output_claims=(
            ClaimContract(claim_type="task_done", target=nid, claim_role="terminal"),
        ),
        budgets=NodeBudget(max_retries=0, max_duration_sec=5.0),
    )


class TestNodeTypeRouting:

    def test_register_and_resolve_handler(self) -> None:
        runner = MainlineRunner()
        handler = lambda node: {"type": "dialog"}
        runner.register_type_handler("dialog", handler)
        node = _node("n1", "dialog")
        assert runner._resolve_type_handler(node) is handler

    def test_longest_prefix_match(self) -> None:
        runner = MainlineRunner()
        generic = lambda node: {"type": "combat"}
        boss = lambda node: {"type": "boss"}
        runner.register_type_handler("combat", generic)
        runner.register_type_handler("combat_boss", boss)
        # combat_boss_raid should match combat_boss, not combat
        node = _node("n1", "combat_boss_raid")
        assert runner._resolve_type_handler(node) is boss

    def test_no_handler_returns_none(self) -> None:
        runner = MainlineRunner()
        node = _node("n1", "explore_waypoint")
        assert runner._resolve_type_handler(node) is None

    def test_no_handlers_registered(self) -> None:
        runner = MainlineRunner()
        node = _node("n1", "dialog")
        assert runner._resolve_type_handler(node) is None

    def test_type_handler_called_in_execution(self) -> None:
        """Type handler is used instead of skill_execute when registered."""
        results: list[str] = []
        skill_execute = lambda node: results.append("skill") or {"via": "skill"}
        type_handler = lambda node: results.append("type") or {"via": "type"}

        runner = MainlineRunner(skill_execute_fn=skill_execute)
        runner.register_type_handler("dialog", type_handler)

        graph = MissionGraphV4(mission_id="test")
        node = _node("n1", "dialog_advance")
        graph.add_node(node)

        result = runner.run(graph)
        # The type handler should have been used
        assert "type" in results
        assert "skill" not in results

    def test_fallback_to_skill_execute(self) -> None:
        """Nodes without type handler fall back to skill_execute."""
        results: list[str] = []
        skill_execute = lambda node: results.append("skill") or {"via": "skill"}

        runner = MainlineRunner(skill_execute_fn=skill_execute)
        runner.register_type_handler("dialog", lambda node: {"via": "type"})

        graph = MissionGraphV4(mission_id="test")
        node = _node("n1", "explore_waypoint")
        graph.add_node(node)

        result = runner.run(graph)
        assert "skill" in results

    def test_multiple_type_handlers(self) -> None:
        runner = MainlineRunner()
        dialog_h = lambda node: {"t": "dialog"}
        combat_h = lambda node: {"t": "combat"}
        explore_h = lambda node: {"t": "explore"}
        runner.register_type_handler("dialog", dialog_h)
        runner.register_type_handler("combat", combat_h)
        runner.register_type_handler("exploration", explore_h)

        assert runner._resolve_type_handler(_node("n1", "dialog_advance")) is dialog_h
        assert runner._resolve_type_handler(_node("n2", "combat_boss")) is combat_h
        assert runner._resolve_type_handler(_node("n3", "exploration_chest")) is explore_h
        assert runner._resolve_type_handler(_node("n4", "navigate_walk")) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
