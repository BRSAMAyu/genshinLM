"""Tests for Phase 8: MainlineRunner claim gating.

Verifies:
- input_claims are verified before node execution
- output_claims are verified after node execution
- Unmet input claims block node execution
- Unmet output claims cause node failure
- dry_run without skill_execute_fn produces "blocked" not "completed"
"""
from __future__ import annotations

import pytest

from planning.mainline.mainline_runner import (
    DefaultClaimVerifier,
    MainlineRunner,
    NodeResult,
    RuntimeSnapshot,
)
from planning.mainline.mission_graph_v4 import (
    ClaimContract,
    MissionEdgeV4,
    MissionGraphV4,
    MissionNodeV4,
)


def _edge(src: str, dst: str) -> MissionEdgeV4:
    return MissionEdgeV4(from_node=src, to_node=dst)


def _simple_graph() -> MissionGraphV4:
    """Create a minimal valid graph: 2 nodes, terminal has output_claims."""
    g = MissionGraphV4(mission_id="test_claim_gate")
    g.add_node(MissionNodeV4(
        node_id="n1",
        node_type="navigate",
        skill_candidates=["quest_follow"],
        output_claims=[ClaimContract(claim_type="nav_result")],
    ))
    g.add_node(MissionNodeV4(
        node_id="n2",
        node_type="interact",
        skill_candidates=["interact_npc"],
        output_claims=[ClaimContract(claim_type="interact_result")],
    ))
    g.add_edge(_edge("n1", "n2"))
    return g


def _graph_with_input_claims(expected_state: str) -> MissionGraphV4:
    """Create a graph where n1 requires a specific screen_state."""
    g = MissionGraphV4(mission_id="test_input_claim")
    g.add_node(MissionNodeV4(
        node_id="n1",
        node_type="dialog",
        skill_candidates=["dialog_advance"],
        input_claims=[ClaimContract(claim_type=expected_state)],
        output_claims=[ClaimContract(claim_type="dialog_result")],
    ))
    return g


def _graph_with_output_claims() -> MissionGraphV4:
    """Create a graph where n1 requires output claim verification."""
    g = MissionGraphV4(mission_id="test_output_claim")
    g.add_node(MissionNodeV4(
        node_id="n1",
        node_type="combat",
        skill_candidates=["combat_encounter"],
        output_claims=[ClaimContract(claim_type="combat_result")],
    ))
    return g


class TestClaimGate:
    """Test MainlineRunner claim gating."""

    def test_input_claim_satisfied_executes(self):
        runner = MainlineRunner(
            skill_execute_fn=lambda node: {"action": "done", "dialog_result": "ok"},
        )
        runner._snapshot_provider = type("P", (), {
            "snapshot": lambda self: RuntimeSnapshot(screen_state="dialog"),
        })()
        graph = _graph_with_input_claims("dialog")
        result = runner.run(graph)
        assert result.completed_nodes == ["n1"]
        assert result.node_results[0].status == "completed"

    def test_legacy_claim_check_fn_is_invoked(self):
        calls: list[str] = []

        def claim_check(claim):
            calls.append(claim.claim_type)
            return True

        runner = MainlineRunner(
            claim_check_fn=claim_check,
            skill_execute_fn=lambda node: {"dialog_result": "ok"},
        )
        runner._snapshot_provider = type("P", (), {
            "snapshot": lambda self: RuntimeSnapshot(screen_state="dialog"),
        })()
        graph = _graph_with_input_claims("dialog")
        result = runner.run(graph)

        assert result.completed_nodes == ["n1"]
        # claim_check_fn is now invoked for both input and output claims
        assert "dialog" in calls  # input claim checked
        assert "dialog_result" in calls  # output claim also checked

    def test_legacy_claim_check_fn_can_block_execution(self):
        executed: list[str] = []

        runner = MainlineRunner(
            claim_check_fn=lambda claim: (False, "external verifier rejected"),
            skill_execute_fn=lambda node: executed.append(node.node_id) or {"dialog_result": "ok"},
        )
        runner._snapshot_provider = type("P", (), {
            "snapshot": lambda self: RuntimeSnapshot(screen_state="dialog"),
        })()
        graph = _graph_with_input_claims("dialog")
        result = runner.run(graph)

        assert result.node_results[0].status == "blocked"
        assert "external verifier rejected" in result.node_results[0].error
        assert executed == []

    def test_input_claim_not_satisfied_blocks(self):
        runner = MainlineRunner(
            skill_execute_fn=lambda node: {"action": "done"},
        )
        runner._snapshot_provider = type("P", (), {
            "snapshot": lambda self: RuntimeSnapshot(screen_state="overworld"),
        })()
        graph = _graph_with_input_claims("dialog")
        result = runner.run(graph)
        assert result.node_results[0].status == "blocked"
        assert "input_claim_failed" in result.node_results[0].error

    def test_output_claim_satisfied_passes(self):
        runner = MainlineRunner(
            skill_execute_fn=lambda node: {"combat_result": "victory"},
        )
        graph = _graph_with_output_claims()
        result = runner.run(graph)
        assert result.completed_nodes == ["n1"]

    def test_output_claim_not_satisfied_fails(self):
        runner = MainlineRunner(
            skill_execute_fn=lambda node: {},
            max_node_retries=0,
        )
        graph = _graph_with_output_claims()
        result = runner.run(graph)
        assert result.node_results[0].status == "failed"
        assert "output_claim_failed" in result.node_results[0].error

    def test_dry_run_without_skill_fn_is_blocked(self):
        runner = MainlineRunner()
        graph = _simple_graph()
        result = runner.run(graph)
        assert result.node_results[0].status == "blocked"
        assert result.node_results[0].claim_data.get("dry_run") is True

    def test_no_input_claims_always_passes(self):
        runner = MainlineRunner(
            skill_execute_fn=lambda node: {"result": "ok", "nav_result": "ok", "interact_result": "ok"},
        )
        graph = _simple_graph()
        result = runner.run(graph)
        assert result.completed_nodes == ["n1", "n2"]

    def test_claim_verifier_default_allows_any_state(self):
        verifier = DefaultClaimVerifier()
        node = MissionNodeV4(node_id="x", node_type="navigate")
        ok, reason = verifier.verify_input_claims(node, RuntimeSnapshot())
        assert ok is True

    def test_claim_verifier_blocks_wrong_state(self):
        verifier = DefaultClaimVerifier()
        node = MissionNodeV4(
            node_id="x",
            node_type="dialog",
            input_claims=[ClaimContract(claim_type="dialog")],
        )
        ok, reason = verifier.verify_input_claims(node, RuntimeSnapshot(screen_state="combat"))
        assert ok is False
        assert "dialog" in reason
