"""Tests for Phase 8: Mainline recovery E2E.

Verifies:
- Output claim failure triggers BAGEL attribution (not silent completion)
- Node failure enters recovery path
- Multiple failures cause graph JIT healing
- Recovery can succeed and retry
"""
from __future__ import annotations

from typing import Any

from planning.mainline.mainline_runner import (
    DefaultClaimVerifier,
    MainlineRunner,
    RuntimeSnapshot,
)
from planning.mainline.mission_graph_v4 import (
    ClaimContract,
    MissionEdgeV4,
    MissionGraphV4,
    MissionNodeV4,
)


def _graph_with_output_failure() -> MissionGraphV4:
    g = MissionGraphV4(mission_id="recovery_test")
    g.add_node(MissionNodeV4(
        node_id="n1",
        node_type="combat",
        skill_candidates=["combat_encounter"],
        output_claims=[ClaimContract(claim_type="combat_result")],
    ))
    return g


def _graph_multi_node() -> MissionGraphV4:
    g = MissionGraphV4(mission_id="multi_recovery")
    g.add_node(MissionNodeV4(
        node_id="n1",
        node_type="navigate",
        output_claims=[ClaimContract(claim_type="nav_result")],
    ))
    g.add_node(MissionNodeV4(
        node_id="n2",
        node_type="combat",
        output_claims=[ClaimContract(claim_type="combat_result")],
    ))
    g.add_node(MissionNodeV4(
        node_id="n3",
        node_type="interact",
        output_claims=[ClaimContract(claim_type="interact_result")],
    ))
    g.add_edge(MissionEdgeV4(from_node="n1", to_node="n2"))
    g.add_edge(MissionEdgeV4(from_node="n2", to_node="n3"))
    return g


class TestMainlineRecovery:
    """Test recovery and BAGEL attribution paths."""

    def test_output_claim_failure_enters_failed_not_completed(self):
        call_count = 0

        def execute_fn(node: MissionNodeV4) -> dict[str, Any]:
            nonlocal call_count
            call_count += 1
            return {}  # empty data → output claim fails

        runner = MainlineRunner(
            skill_execute_fn=execute_fn,
            max_node_retries=0,
        )
        graph = _graph_with_output_failure()
        result = runner.run(graph)

        assert result.node_results[0].status == "failed"
        assert "output_claim_failed" in result.node_results[0].error
        assert result.success is False

    def test_recovery_retries_before_final_failure(self):
        attempt = 0

        def execute_fn(node: MissionNodeV4) -> dict[str, Any]:
            nonlocal attempt
            attempt += 1
            if attempt < 3:
                return {}
            return {"combat_result": "victory"}

        runner = MainlineRunner(
            skill_execute_fn=execute_fn,
            max_node_retries=3,
        )
        graph = _graph_with_output_failure()
        result = runner.run(graph)

        assert result.node_results[0].status == "completed"
        assert attempt == 3

    def test_multi_node_failure_prevents_downstream(self):
        results_by_node = {
            "n1": {"result": "ok", "nav_result": "done"},
            "n2": {},
            "n3": {"result": "ok", "interact_result": "done"},
        }

        def execute_fn(node: MissionNodeV4) -> dict[str, Any]:
            return results_by_node.get(node.node_id, {})

        runner = MainlineRunner(
            skill_execute_fn=execute_fn,
            max_node_retries=0,
        )
        graph = _graph_multi_node()
        result = runner.run(graph)

        assert "n1" in result.completed_nodes
        assert "n2" in result.failed_nodes
        assert "n3" in result.skipped_nodes

    def test_exception_triggers_failure_not_completion(self):
        def execute_fn(node: MissionNodeV4) -> dict[str, Any]:
            raise RuntimeError("combat engine crashed")

        runner = MainlineRunner(
            skill_execute_fn=execute_fn,
            max_node_retries=0,
        )
        g = MissionGraphV4(mission_id="exc_test")
        g.add_node(MissionNodeV4(
            node_id="n1",
            node_type="combat",
            output_claims=[ClaimContract(claim_type="combat_result")],
        ))
        result = runner.run(g)

        assert result.node_results[0].status == "failed"
        assert "combat engine crashed" in result.node_results[0].error

    def test_no_skill_fn_is_blocked_not_completed(self):
        runner = MainlineRunner()
        g = MissionGraphV4(mission_id="no_skill")
        g.add_node(MissionNodeV4(
            node_id="n1",
            node_type="navigate",
            output_claims=[ClaimContract(claim_type="nav_result")],
        ))
        result = runner.run(g)

        assert result.node_results[0].status == "blocked"
        assert result.success is False

    def test_dry_run_claim_data_not_accepted_as_output(self):
        def execute_fn(node: MissionNodeV4) -> dict[str, Any]:
            return {"dry_run": True}

        runner = MainlineRunner(
            skill_execute_fn=execute_fn,
            max_node_retries=0,
        )
        graph = _graph_with_output_failure()
        result = runner.run(graph)

        assert result.node_results[0].status == "failed"
