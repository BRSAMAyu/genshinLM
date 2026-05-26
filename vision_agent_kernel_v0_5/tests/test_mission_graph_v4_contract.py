"""Tests for MissionGraph v4 — claim-gated nodes and validator."""
from __future__ import annotations

import json

import pytest

from planning.mainline.mission_graph_v4 import (
    BeliefTemplate,
    ClaimContract,
    FallbackDecl,
    MissionEdgeV4,
    MissionGraphV4,
    MissionNodeV4,
    NodeBudget,
)
from planning.mainline.mission_graph_validator_v4 import (
    MissionGraphValidatorV4,
    ValidationIssue,
)


# -- Helpers --

def _claim(claim_type: str = "screen_state_match", target: str = "",
           role: str = "local", recipe: str = "") -> ClaimContract:
    return ClaimContract(claim_type, target, "verified", role, recipe)


def _node(
    node_id: str = "n1",
    node_type: str = "dialog",
    risk: str = "medium",
    outputs: tuple[ClaimContract, ...] = (),
    inputs: tuple[ClaimContract, ...] = (),
    fallbacks: tuple[FallbackDecl, ...] = (),
    beliefs: tuple[BeliefTemplate, ...] = (),
    budgets: NodeBudget | None = None,
) -> MissionNodeV4:
    return MissionNodeV4(
        node_id=node_id,
        node_type=node_type,
        risk_level=risk,
        input_claims=inputs,
        output_claims=outputs,
        fallbacks=fallbacks,
        belief_templates=beliefs,
        budgets=budgets or NodeBudget(),
    )


def _linear_graph() -> MissionGraphV4:
    """Build a minimal valid 3-node linear graph."""
    g = MissionGraphV4(mission_id="test_mission")
    g.add_node(_node("start", "observe", "low", outputs=(_claim("screen_state_match", "world"),)))
    g.add_node(_node("talk", "dialog", "medium",
                      outputs=(_claim("quest_objective_changed", "active_quest.objective_text"),),
                      inputs=(_claim("screen_state_match", "dialogue"),),
                      fallbacks=(FallbackDecl("UI_LOST_RECOVERY"),),
                      beliefs=(BeliefTemplate("quest objective", "objective_type_hypothesis"),)))
    g.add_node(_node("end", "claim_reward", "low",
                      outputs=(_claim("quest_completed", "active_quest.status", role="terminal"),),
                      inputs=(_claim("quest_objective_changed", "active_quest.objective_text"),)))
    g.add_edge(MissionEdgeV4("start", "talk"))
    g.add_edge(MissionEdgeV4("talk", "end"))
    return g


# -- MissionNodeV4 tests --

class TestMissionNodeV4:
    def test_to_dict_roundtrip(self) -> None:
        node = _node("n1", "combat", "high",
                      outputs=(_claim("target_killed", "enemy_1"),),
                      beliefs=(BeliefTemplate("enemy", "enemy_state_hypothesis",
                                              "enemy is vulnerable", "damage taken > 0"),))
        d = node.to_dict()
        assert d["node_id"] == "n1"
        assert d["node_type"] == "combat"
        assert len(d["output_claims"]) == 1
        assert d["output_claims"][0]["claim_type"] == "target_killed"
        assert len(d["belief_templates"]) == 1
        assert d["belief_templates"][0]["causal_role"] == "enemy_state_hypothesis"

    def test_is_terminal_with_outputs(self) -> None:
        node = _node(outputs=(_claim("x"),))
        assert node.is_terminal()

    def test_is_not_terminal_without_outputs(self) -> None:
        node = _node()
        assert not node.is_terminal()


# -- MissionGraphV4 tests --

class TestMissionGraphV4:
    def test_add_nodes_and_edges(self) -> None:
        g = _linear_graph()
        assert g.node_count == 3
        assert g.edge_count == 2

    def test_root_nodes(self) -> None:
        g = _linear_graph()
        assert g.root_nodes() == ["start"]

    def test_terminal_nodes(self) -> None:
        g = _linear_graph()
        assert g.terminal_nodes() == ["end"]

    def test_successors_predecessors(self) -> None:
        g = _linear_graph()
        assert g.successors("start") == {"talk"}
        assert g.predecessors("end") == {"talk"}
        assert g.successors("end") == set()
        assert g.predecessors("start") == set()

    def test_no_cycle_in_linear(self) -> None:
        g = _linear_graph()
        assert not g.has_cycle()

    def test_detects_cycle(self) -> None:
        g = MissionGraphV4()
        g.add_node(_node("a", outputs=(_claim("x"),)))
        g.add_node(_node("b", outputs=(_claim("y"),)))
        g.add_node(_node("c", outputs=(_claim("z"),)))
        g.add_edge(MissionEdgeV4("a", "b"))
        g.add_edge(MissionEdgeV4("b", "c"))
        g.add_edge(MissionEdgeV4("c", "a"))
        assert g.has_cycle()

    def test_topological_order(self) -> None:
        g = _linear_graph()
        order = g.topological_order()
        assert order is not None
        assert order.index("start") < order.index("talk") < order.index("end")

    def test_topological_order_cycle_returns_none(self) -> None:
        g = MissionGraphV4()
        g.add_node(_node("a"))
        g.add_node(_node("b"))
        g.add_edge(MissionEdgeV4("a", "b"))
        g.add_edge(MissionEdgeV4("b", "a"))
        assert g.topological_order() is None

    def test_to_dict_deterministic(self) -> None:
        g = _linear_graph()
        d1 = g.to_dict()
        d2 = g.to_dict()
        assert d1 == d2

    def test_roundtrip_serialization(self) -> None:
        g = _linear_graph()
        data = g.to_dict()
        g2 = MissionGraphV4.from_dict(data)
        assert g2.mission_id == g.mission_id
        assert g2.node_count == g.node_count
        assert g2.edge_count == g.edge_count
        assert g2.to_dict() == data

    def test_to_json_valid(self) -> None:
        g = _linear_graph()
        j = g.to_json()
        parsed = json.loads(j)
        assert parsed["mission_id"] == "test_mission"
        assert len(parsed["nodes"]) == 3

    def test_node_ids_preserve_insertion_order(self) -> None:
        g = MissionGraphV4()
        g.add_node(_node("c_node"))
        g.add_node(_node("a_node"))
        g.add_node(_node("b_node"))
        assert g.node_ids == ["c_node", "a_node", "b_node"]

    def test_get_node(self) -> None:
        g = _linear_graph()
        node = g.get_node("talk")
        assert node is not None
        assert node.node_type == "dialog"
        assert g.get_node("nonexistent") is None


# -- Validator tests --

class TestMissionGraphValidatorV4:
    def setup_method(self) -> None:
        self.validator = MissionGraphValidatorV4()

    def test_valid_graph_passes(self) -> None:
        g = _linear_graph()
        issues = self.validator.validate(g)
        errors = [i for i in issues if i.severity == "error"]
        assert errors == []

    def test_is_valid_true_for_good_graph(self) -> None:
        assert self.validator.is_valid(_linear_graph())

    def test_terminal_without_output_claim_fails(self) -> None:
        g = MissionGraphV4()
        g.add_node(_node("orphan", "observe", "low"))  # no outputs, no edges = terminal
        issues = self.validator.validate(g)
        errors = [i for i in issues if i.severity == "error"]
        assert any(i.rule == "terminal_output_claim" for i in errors)

    def test_high_risk_without_fallback_fails(self) -> None:
        g = MissionGraphV4()
        g.add_node(_node("risky", "combat", "high",
                          outputs=(_claim("target_killed", "enemy"),),
                          fallbacks=()))  # no fallbacks
        issues = self.validator.validate(g)
        errors = [i for i in issues if i.severity == "error"]
        assert any(i.rule == "high_risk_fallback" for i in errors)

    def test_critical_risk_without_fallback_fails(self) -> None:
        g = MissionGraphV4()
        g.add_node(_node("danger", "boss_fight", "critical",
                          outputs=(_claim("boss_defeated", "boss"),),
                          fallbacks=()))
        issues = self.validator.validate(g)
        assert any(i.rule == "high_risk_fallback" and i.severity == "error" for i in issues)

    def test_medium_risk_no_fallback_ok(self) -> None:
        g = MissionGraphV4()
        g.add_node(_node("safe", "dialog", "medium",
                          outputs=(_claim("dialogue_advanced", "dialog"),)))
        issues = self.validator.validate(g)
        assert not any(i.rule == "high_risk_fallback" for i in issues)

    def test_high_risk_with_fallback_ok(self) -> None:
        g = MissionGraphV4()
        g.add_node(_node("risky", "combat", "high",
                          outputs=(_claim("target_killed", "enemy"),),
                          fallbacks=(FallbackDecl("COMBAT_DEFEAT_RECOVERY"),)))
        issues = self.validator.validate(g)
        assert not any(i.rule == "high_risk_fallback" and i.severity == "error" for i in issues)

    def test_cycle_detected(self) -> None:
        g = MissionGraphV4()
        g.add_node(_node("a", outputs=(_claim("x"),)))
        g.add_node(_node("b", outputs=(_claim("y"),)))
        g.add_edge(MissionEdgeV4("a", "b"))
        g.add_edge(MissionEdgeV4("b", "a"))
        issues = self.validator.validate(g)
        assert any(i.rule == "acyclic" and i.severity == "error" for i in issues)

    def test_belief_template_missing_target_warning(self) -> None:
        g = MissionGraphV4()
        g.add_node(_node("n1", "dialog", "low",
                          outputs=(_claim("x"),),
                          beliefs=(BeliefTemplate("", "objective_type_hypothesis"),)))
        issues = self.validator.validate(g)
        assert any(i.rule == "belief_template_target" for i in issues)

    def test_belief_template_missing_role_warning(self) -> None:
        g = MissionGraphV4()
        g.add_node(_node("n1", "dialog", "low",
                          outputs=(_claim("x"),),
                          beliefs=(BeliefTemplate("quest", ""),)))
        issues = self.validator.validate(g)
        assert any(i.rule == "belief_template_role" for i in issues)

    def test_roundtrip_serialization_warning(self) -> None:
        """Graph with nodes that roundtrip correctly should have no serialization issues."""
        g = _linear_graph()
        issues = self.validator.validate(g)
        assert not any(i.rule == "serialization" and i.severity == "error" for i in issues)

    def test_non_terminal_without_output_claims_ok(self) -> None:
        """Non-terminal node (has successors) doesn't need output claims."""
        g = MissionGraphV4()
        g.add_node(_node("start", "observe", "low"))  # no outputs
        g.add_node(_node("end", "dialog", "low",
                          outputs=(_claim("quest_done", "quest"),)))
        g.add_edge(MissionEdgeV4("start", "end"))
        issues = self.validator.validate(g)
        assert not any(i.rule == "terminal_output_claim" for i in issues)

    def test_diamond_graph_valid(self) -> None:
        """Diamond-shaped DAG: A -> B, A -> C, B -> D, C -> D."""
        g = MissionGraphV4()
        g.add_node(_node("a", "observe", "low", outputs=(_claim("screen", "world"),)))
        g.add_node(_node("b", "dialog", "medium",
                          outputs=(_claim("dialog_done", "dialog"),),
                          fallbacks=(FallbackDecl("UI_LOST_RECOVERY"),)))
        g.add_node(_node("c", "navigate", "medium",
                          outputs=(_claim("arrived", "location"),)))
        g.add_node(_node("d", "claim_reward", "low",
                          outputs=(_claim("reward_claimed", "reward", role="terminal"),)))
        g.add_edge(MissionEdgeV4("a", "b"))
        g.add_edge(MissionEdgeV4("a", "c"))
        g.add_edge(MissionEdgeV4("b", "d"))
        g.add_edge(MissionEdgeV4("c", "d"))

        assert not g.has_cycle()
        assert self.validator.is_valid(g)
        order = g.topological_order()
        assert order is not None
        assert order[0] == "a"
        assert order[-1] == "d"

    def test_node_budget_defaults(self) -> None:
        budget = NodeBudget()
        assert budget.max_retries == 2
        assert budget.max_uncertain == 1
        assert budget.max_duration_sec == 120.0

    def test_custom_budget(self) -> None:
        node = _node("n1", budgets=NodeBudget(max_retries=5, max_duration_sec=300.0))
        assert node.budgets.max_retries == 5
        assert node.budgets.max_duration_sec == 300.0


# -- Audit fix tests (C1, C2, H3, H6, M4) --

class TestAuditFixes:
    def test_metadata_roundtrip_preserved(self) -> None:
        """C1: metadata must survive serialization round-trip."""
        node = _node("n1", "dialog", "medium",
                      outputs=(_claim("x"),),
                      budgets=NodeBudget())
        node_with_meta = MissionNodeV4(
            node_id="n1", node_type="dialog",
            output_claims=(_claim("x"),),
            metadata={"claim_id": "c_123", "executor_tag": "v2"},
        )
        d = node_with_meta.to_dict()
        assert d["metadata"]["claim_id"] == "c_123"
        assert d["metadata"]["executor_tag"] == "v2"

        g = MissionGraphV4()
        g.add_node(node_with_meta)
        data = g.to_dict()
        g2 = MissionGraphV4.from_dict(data)
        restored = g2.get_node("n1")
        assert restored is not None
        assert restored.metadata["claim_id"] == "c_123"

    def test_duplicate_node_id_replaced(self) -> None:
        """C2: adding same node_id twice replaces, doesn't duplicate."""
        g = MissionGraphV4()
        g.add_node(_node("a", "observe", "low", outputs=(_claim("x"),)))
        g.add_node(_node("a", "dialog", "medium", outputs=(_claim("y"),)))
        assert g.node_count == 1
        assert g.node_ids == ["a"]
        assert g.get_node("a").node_type == "dialog"

    def test_edge_condition_serialized(self) -> None:
        """H3: edge condition must survive round-trip."""
        g = MissionGraphV4()
        g.add_node(_node("a", outputs=(_claim("x"),)))
        g.add_node(_node("b", outputs=(_claim("y"),)))
        g.add_edge(MissionEdgeV4("a", "b", condition="failure"))
        data = g.to_dict()
        assert data["edges"][0]["condition"] == "failure"

        g2 = MissionGraphV4.from_dict(data)
        data2 = g2.to_dict()
        assert data2["edges"][0]["condition"] == "failure"

    def test_invalid_risk_level_caught(self) -> None:
        """H6: invalid risk_level is a validation error."""
        g = MissionGraphV4()
        node = MissionNodeV4(
            node_id="bad", node_type="combat",
            risk_level="extreme",  # type: ignore  # intentionally invalid
            output_claims=(_claim("x"),),
        )
        g.add_node(node)
        validator = MissionGraphValidatorV4()
        issues = validator.validate(g)
        assert any(i.rule == "invalid_risk_level" and i.severity == "error" for i in issues)

    def test_invalid_claim_role_caught(self) -> None:
        """H6: invalid claim_role is a validation error."""
        g = MissionGraphV4()
        node = MissionNodeV4(
            node_id="bad", node_type="combat",
            output_claims=(ClaimContract("x", claim_role="invalid_role"),),  # type: ignore
        )
        g.add_node(node)
        validator = MissionGraphValidatorV4()
        issues = validator.validate(g)
        assert any(i.rule == "invalid_claim_role" and i.severity == "error" for i in issues)

    def test_from_json_classmethod(self) -> None:
        """M4: from_json reconstructs graph from JSON string."""
        g = _linear_graph()
        j = g.to_json()
        g2 = MissionGraphV4.from_json(j)
        assert g2.mission_id == "test_mission"
        assert g2.node_count == 3
        assert g2.to_dict() == g.to_dict()

    def test_fallback_always_serialized(self) -> None:
        """H2: fallback dict always has both keys even if empty."""
        fb = FallbackDecl()
        from planning.mainline.mission_graph_v4 import _fallback_to_dict
        d = _fallback_to_dict(fb)
        assert "recovery_recipe" in d
        assert "replan_policy" in d
        assert d["recovery_recipe"] == ""
        assert d["replan_policy"] == ""

    def test_edge_reference_no_duplicates(self) -> None:
        """L2: edge reference to missing node reported only once."""
        g = MissionGraphV4()
        g.add_node(_node("a"))
        # Manually add edge to non-existent node
        g.add_edge(MissionEdgeV4("a", "nonexistent"))
        validator = MissionGraphValidatorV4()
        issues = validator.validate(g)
        edge_issues = [i for i in issues if i.rule == "edge_reference"]
        # Should report once, not twice
        assert len(edge_issues) == 1
