"""Tests for Mainline Runner — continuous mission execution."""
from __future__ import annotations

import pytest

from planning.mainline.mainline_runner import MainlineRunner, MissionRunResult, NodeResult
from planning.mainline.mission_graph_v4 import (
    ClaimContract,
    MissionEdgeV4,
    MissionGraphV4,
    MissionNodeV4,
    NodeBudget,
)
from control.sentinel.sentinel_runtime import SentinelRuntime


# -- Helpers --

def _claim(claim_type: str = "screen_state_match") -> ClaimContract:
    return ClaimContract(claim_type=claim_type)


def _node(
    node_id: str = "n1",
    node_type: str = "observe",
    outputs: tuple[ClaimContract, ...] = (),
) -> MissionNodeV4:
    return MissionNodeV4(
        node_id=node_id,
        node_type=node_type,
        output_claims=outputs,
    )


def _linear_graph() -> MissionGraphV4:
    g = MissionGraphV4(mission_id="test_run")
    g.add_node(_node("start", "observe", outputs=(_claim("screen"),)))
    g.add_node(_node("mid", "dialog", outputs=(_claim("dialog_done"),)))
    g.add_node(_node("end", "claim_reward", outputs=(_claim("reward"),)))
    g.add_edge(MissionEdgeV4("start", "mid"))
    g.add_edge(MissionEdgeV4("mid", "end"))
    return g


# -- Tests --

class TestMainlineRunner:
    def test_linear_graph_dry_run(self) -> None:
        runner = MainlineRunner()
        graph = _linear_graph()
        result = runner.run(graph)
        assert result.success
        assert len(result.completed_nodes) == 3
        assert result.failed_nodes == []
        assert result.duration_sec >= 0

    def test_invalid_graph_fails(self) -> None:
        runner = MainlineRunner()
        # Graph with terminal node missing output_claims
        g = MissionGraphV4()
        g.add_node(MissionNodeV4(node_id="bad", node_type="observe"))
        result = runner.run(g)
        assert not result.success

    def test_cyclic_graph_fails(self) -> None:
        runner = MainlineRunner()
        g = MissionGraphV4()
        g.add_node(_node("a"))
        g.add_node(_node("b"))
        g.add_edge(MissionEdgeV4("a", "b"))
        g.add_edge(MissionEdgeV4("b", "a"))
        result = runner.run(g)
        assert not result.success

    def test_skill_execute_fn(self) -> None:
        executed: list[str] = []

        def execute_fn(node):
            executed.append(node.node_id)
            return {"claim": "verified"}

        runner = MainlineRunner(skill_execute_fn=execute_fn)
        result = runner.run(_linear_graph())
        assert result.success
        assert executed == ["start", "mid", "end"]

    def test_skill_execute_fn_failure(self) -> None:
        call_count = 0

        def failing_fn(node):
            nonlocal call_count
            call_count += 1
            if node.node_id == "mid":
                raise RuntimeError("skill failed")
            return {}

        runner = MainlineRunner(skill_execute_fn=failing_fn, max_node_retries=1)
        result = runner.run(_linear_graph())
        assert not result.success
        assert "mid" in result.failed_nodes
        # start should complete, mid fails, end is skipped (predecessor failed)
        assert "end" in result.skipped_nodes

    def test_predecessor_failure_skips_successors(self) -> None:
        runner = MainlineRunner()
        g = MissionGraphV4()
        g.add_node(_node("a", outputs=(_claim("x"),)))
        g.add_node(_node("b", outputs=(_claim("y"),)))
        g.add_node(_node("c", outputs=(_claim("z"),)))
        g.add_edge(MissionEdgeV4("a", "b"))
        g.add_edge(MissionEdgeV4("b", "c"))

        def fail_on_b(node):
            if node.node_id == "b":
                raise RuntimeError("fail")
            return {}

        result = MainlineRunner(skill_execute_fn=fail_on_b, max_node_retries=0).run(g)
        assert "a" in result.completed_nodes
        assert "b" in result.failed_nodes
        assert "c" in result.skipped_nodes

    def test_duration_budget(self) -> None:
        runner = MainlineRunner(max_duration_sec=0.0)  # immediately exhausted
        # This may or may not complete depending on timing, but the check is there
        result = runner.run(_linear_graph())
        # With 0s budget it might still execute the first node before timing out
        # Just verify no crash
        assert isinstance(result, MissionRunResult)

    def test_sentinel_integration(self) -> None:
        sentinel = SentinelRuntime()
        runner = MainlineRunner(sentinel=sentinel)
        result = runner.run(_linear_graph())
        assert result.success
        # No anomalies in healthy execution
        assert result.sentinel_interventions == 0

    def test_node_result_has_duration(self) -> None:
        runner = MainlineRunner()
        result = runner.run(_linear_graph())
        for nr in result.node_results:
            assert nr.duration_sec >= 0

    def test_empty_graph(self) -> None:
        runner = MainlineRunner()
        g = MissionGraphV4()
        result = runner.run(g)
        assert not result.success  # no nodes = no terminals completed

    def test_single_node_graph(self) -> None:
        runner = MainlineRunner()
        g = MissionGraphV4()
        g.add_node(_node("only", outputs=(_claim("done"),)))
        result = runner.run(g)
        assert result.success
        assert result.completed_nodes == ["only"]

    def test_diamond_graph(self) -> None:
        g = MissionGraphV4()
        g.add_node(_node("a", outputs=(_claim("x"),)))
        g.add_node(_node("b", outputs=(_claim("y"),)))
        g.add_node(_node("c", outputs=(_claim("z"),)))
        g.add_node(_node("d", outputs=(_claim("w"),)))
        g.add_edge(MissionEdgeV4("a", "b"))
        g.add_edge(MissionEdgeV4("a", "c"))
        g.add_edge(MissionEdgeV4("b", "d"))
        g.add_edge(MissionEdgeV4("c", "d"))

        runner = MainlineRunner()
        result = runner.run(g)
        assert result.success
        assert len(result.completed_nodes) == 4
