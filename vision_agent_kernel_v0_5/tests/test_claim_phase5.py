from __future__ import annotations

import pytest

from runtime.mission_graph import (
    MissionGraph,
    MissionGraphNode,
    PathResult,
    UnverifiableBudget,
    UnverifiableDecision,
    UnverifiablePolicy,
)


class TestMissionGraphNode:
    def test_create(self):
        node = MissionGraphNode(
            node_id="teleport", node_type="ui_interact",
            skill_binding="genshin_teleport", produces=["location_loaded"],
        )
        assert node.node_id == "teleport"
        assert node.produces == ["location_loaded"]

    def test_with_alternative(self):
        node = MissionGraphNode(
            node_id="route_b", node_type="navigate",
            skill_binding="genshin_route_b", alternative_for="route_a",
        )
        assert node.alternative_for == "route_a"


class TestMissionGraph:
    def test_add_nodes_and_find_path(self):
        mg = MissionGraph(mission_id="collect")
        mg.add_node(MissionGraphNode("teleport", "ui_interact", "genshin_teleport"))
        mg.add_node(MissionGraphNode("navigate", "navigate", "genshin_route_a", depends_on=["teleport"]))
        mg.add_node(MissionGraphNode("collect", "collect", "genshin_collect", depends_on=["navigate"]))
        mg.add_edge("teleport", "navigate")
        mg.add_edge("navigate", "collect")

        path = mg.find_path_to("collect")
        assert path is not None
        assert "teleport" in path
        assert "collect" in path

    def test_blocked_node_avoided(self):
        mg = MissionGraph(mission_id="test")
        mg.add_node(MissionGraphNode("a", "start"))
        mg.add_node(MissionGraphNode("b", "mid", depends_on=["a"]))
        mg.add_node(MissionGraphNode("c", "end", depends_on=["b"]))
        mg.add_edge("a", "b")
        mg.add_edge("b", "c")

        mg.mark_blocked("b", "failed_verification")
        path = mg.find_path_to("c")
        assert path is None  # no alternative

    def test_alternative_path(self):
        mg = MissionGraph(mission_id="test")
        mg.add_node(MissionGraphNode("teleport", "ui_interact", "teleport"))
        mg.add_node(MissionGraphNode("route_a", "navigate", "route_a", depends_on=["teleport"]))
        mg.add_node(MissionGraphNode("route_b", "navigate", "route_b", depends_on=["teleport"], alternative_for="route_a"))
        mg.add_node(MissionGraphNode("collect", "collect", "collect", depends_on=["route_a"]))
        mg.add_edge("teleport", "route_a")
        mg.add_edge("teleport", "route_b")
        mg.add_edge("route_a", "collect")
        mg.add_edge("route_b", "collect")

        mg.mark_blocked("route_a", "blocked")
        result = mg.find_alternative_path("route_a")
        assert result is not None
        assert result.used_alternative
        assert "route_b" in result.path

    def test_no_alternative_returns_none(self):
        mg = MissionGraph()
        mg.add_node(MissionGraphNode("a", "start"))
        mg.add_node(MissionGraphNode("b", "end", depends_on=["a"]))
        mg.add_edge("a", "b")
        result = mg.find_alternative_path("a")
        assert result is None

    def test_get_dependents(self):
        mg = MissionGraph()
        mg.add_node(MissionGraphNode("a", "start"))
        mg.add_node(MissionGraphNode("b", "mid", depends_on=["a"]))
        mg.add_node(MissionGraphNode("c", "end", depends_on=["b"]))
        mg.add_edge("a", "b")
        mg.add_edge("b", "c")
        deps = mg.get_dependents("a")
        assert "b" in deps
        assert "c" in deps

    def test_validate_dag_no_cycle(self):
        mg = MissionGraph()
        mg.add_node(MissionGraphNode("a", "start"))
        mg.add_node(MissionGraphNode("b", "end", depends_on=["a"]))
        mg.add_edge("a", "b")
        errors = mg.validate_dag()
        assert errors == []

    def test_validate_dag_cycle(self):
        mg = MissionGraph()
        mg.add_node(MissionGraphNode("a", "start"))
        mg.add_node(MissionGraphNode("b", "mid", depends_on=["a"]))
        mg.add_edge("a", "b")
        mg.add_edge("b", "a")  # cycle
        errors = mg.validate_dag()
        assert "cycle_detected" in errors

    def test_validate_missing_dependency(self):
        mg = MissionGraph()
        mg.add_node(MissionGraphNode("a", "start", depends_on=["nonexistent"]))
        errors = mg.validate_dag()
        assert any("missing_dependency" in e for e in errors)

    def test_node_count(self):
        mg = MissionGraph()
        mg.add_node(MissionGraphNode("a", "start"))
        mg.add_node(MissionGraphNode("b", "end"))
        assert mg.node_count == 2

    def test_blocked_count(self):
        mg = MissionGraph()
        mg.add_node(MissionGraphNode("a", "start"))
        assert mg.blocked_count == 0
        mg.mark_blocked("a", "reason")
        assert mg.blocked_count == 1

    def test_genshin_collect_scenario(self):
        mg = MissionGraph(mission_id="genshin_collect_qingxin", risk_level="low")
        mg.add_node(MissionGraphNode("teleport", "ui_interact", "genshin_teleport", produces=["location_loaded"]))
        mg.add_node(MissionGraphNode("route_a", "navigate", "genshin_route_a", depends_on=["teleport"]))
        mg.add_node(MissionGraphNode("route_b", "navigate", "genshin_route_b", depends_on=["teleport"], alternative_for="route_a"))
        mg.add_node(MissionGraphNode("collect", "collect", "genshin_collect_qingxin", depends_on=["route_a"], claim_role="terminal"))
        mg.add_edge("teleport", "route_a")
        mg.add_edge("teleport", "route_b")
        mg.add_edge("route_a", "collect")
        mg.add_edge("route_b", "collect")

        path = mg.find_path_to("collect")
        assert path is not None
        assert mg.node_count == 4
        errors = mg.validate_dag()
        assert errors == []


class TestUnverifiablePolicy:
    def test_terminal_always_requires_verification(self):
        policy = UnverifiablePolicy("opportunistic")
        budget = UnverifiableBudget()
        decision = policy.check(
            claim_role="terminal", risk_level="low",
            budget=budget, current_count=0, current_weight=0.0,
        )
        assert not decision.allowed

    def test_informational_always_allowed(self):
        policy = UnverifiablePolicy("conservative")
        budget = UnverifiableBudget()
        decision = policy.check(
            claim_role="informational", risk_level="medium",
            budget=budget, current_count=0, current_weight=0.0,
        )
        assert decision.allowed

    def test_conservative_blocks_dependency(self):
        policy = UnverifiablePolicy("conservative")
        budget = UnverifiableBudget()
        decision = policy.check(
            claim_role="dependency", risk_level="low",
            budget=budget, current_count=0, current_weight=0.0,
        )
        assert not decision.allowed

    def test_opportunistic_allows_low_risk_dependency(self):
        policy = UnverifiablePolicy("opportunistic")
        budget = UnverifiableBudget()
        decision = policy.check(
            claim_role="dependency", risk_level="low",
            budget=budget, current_count=0, current_weight=0.0,
        )
        assert decision.allowed

    def test_opportunistic_blocks_medium_dependency(self):
        policy = UnverifiablePolicy("opportunistic")
        budget = UnverifiableBudget()
        decision = policy.check(
            claim_role="dependency", risk_level="medium",
            budget=budget, current_count=0, current_weight=0.0,
        )
        assert not decision.allowed

    def test_local_low_risk_allowed(self):
        policy = UnverifiablePolicy("opportunistic")
        budget = UnverifiableBudget()
        decision = policy.check(
            claim_role="local", risk_level="low",
            budget=budget, current_count=0, current_weight=0.0,
        )
        assert decision.allowed

    def test_local_high_risk_blocked(self):
        policy = UnverifiablePolicy("opportunistic")
        budget = UnverifiableBudget()
        decision = policy.check(
            claim_role="local", risk_level="high",
            budget=budget, current_count=0, current_weight=0.0,
        )
        assert not decision.allowed

    def test_budget_exhausted(self):
        policy = UnverifiablePolicy("opportunistic")
        budget = UnverifiableBudget(max_count=2)
        decision = policy.check(
            claim_role="local", risk_level="low",
            budget=budget, current_count=2, current_weight=0.0,
        )
        assert not decision.allowed
        assert decision.reason == "unverifiable_budget_exhausted"

    def test_critical_never_unverifiable(self):
        policy = UnverifiablePolicy("opportunistic")
        budget = UnverifiableBudget(allowed_risk_levels=["low", "medium", "high", "critical"])
        decision = policy.check(
            claim_role="local", risk_level="critical",
            budget=budget, current_count=0, current_weight=0.0,
        )
        assert not decision.allowed
