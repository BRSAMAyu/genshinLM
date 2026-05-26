"""Tests for BAGEL Safe Revision — cascade risk and stale marking."""
from __future__ import annotations

import pytest

from bagel.fig_schema import (
    ActionNode,
    BeliefNode,
    FalsifiableInterventionGraph,
    TypedEdge,
)
from bagel.safe_revision import SafeRevisionEngine


def _make_belief(belief_id: str) -> BeliefNode:
    return BeliefNode(
        belief_id=belief_id,
        target_object="test",
        causal_role="custom",
        hypothesis="test hypothesis",
        falsification_condition="test condition",
    )


class TestCascadeRiskAssessment:
    def test_low_risk_single_belief(self) -> None:
        fig = FalsifiableInterventionGraph()
        fig.commit_belief(_make_belief("b1"))
        fig.propose_action(ActionNode("a1", ("b1",), "test"))

        engine = SafeRevisionEngine()
        report = engine.assess_cascade(fig, "b1")
        assert report.is_safe  # Safe because small absolute impact (<=2)
        assert report.affected_actions == 1

    def test_high_risk_hub_belief(self) -> None:
        fig = FalsifiableInterventionGraph()
        fig.commit_belief(_make_belief("hub"))
        for i in range(10):
            fig.propose_action(ActionNode(f"a{i}", ("hub",), "test"))

        engine = SafeRevisionEngine(kappa=0.3, max_impact=5)
        report = engine.assess_cascade(fig, "hub")
        # 10/1 = 100% affected ratio -> not safe
        assert not report.is_safe

    def test_downstream_beliefs_included(self) -> None:
        fig = FalsifiableInterventionGraph()
        fig.commit_belief(_make_belief("b1"))
        fig.commit_belief(_make_belief("b2"))
        fig.commit_belief(_make_belief("b3"))
        # b2 depends on b1: edge (b2 → b1)
        fig.add_edge(TypedEdge("e1", "b2", "b1", "belief_depends_on_belief"))
        fig.propose_action(ActionNode("a1", ("b1",), "test"))
        fig.propose_action(ActionNode("a2", ("b2",), "test"))

        engine = SafeRevisionEngine()
        report = engine.assess_cascade(fig, "b1")
        assert report.affected_beliefs >= 1


class TestRevisionDecision:
    def test_safe_local_revision(self) -> None:
        fig = FalsifiableInterventionGraph()
        fig.commit_belief(_make_belief("b1"))
        fig.propose_action(ActionNode("a1", ("b1",), "test"))

        engine = SafeRevisionEngine()
        decision = engine.decide(fig, "b1", "falsified")
        assert decision.safe
        assert decision.strategy == "local_revision"

    def test_unsafe_triggers_stale_marking(self) -> None:
        fig = FalsifiableInterventionGraph()
        fig.commit_belief(_make_belief("hub"))
        for i in range(20):
            fig.propose_action(ActionNode(f"a{i}", ("hub",), "test"))

        engine = SafeRevisionEngine(kappa=0.1, max_impact=3)
        decision = engine.decide(fig, "hub", "falsified")
        assert not decision.safe
        assert decision.strategy == "stale_marking"

    def test_retired_is_always_safe(self) -> None:
        fig = FalsifiableInterventionGraph()
        fig.commit_belief(_make_belief("b1"))
        for i in range(20):
            fig.propose_action(ActionNode(f"a{i}", ("b1",), "test"))

        engine = SafeRevisionEngine(kappa=0.1, max_impact=3)
        decision = engine.decide(fig, "b1", "retired")
        assert decision.safe
        assert decision.strategy == "local_revision"


class TestApplyRevision:
    def test_local_revision_only_changes_target(self) -> None:
        fig = FalsifiableInterventionGraph()
        fig.commit_belief(_make_belief("b1"))
        fig.commit_belief(_make_belief("b2"))

        engine = SafeRevisionEngine()
        decision = engine.decide(fig, "b1", "falsified")
        changed = engine.apply_revision(fig, decision, "falsified")
        assert "b1" in changed
        assert fig.beliefs["b1"].lifecycle == "falsified"
        assert fig.beliefs["b2"].lifecycle == "provisional"  # Unaffected

    def test_stale_marking_propagates(self) -> None:
        fig = FalsifiableInterventionGraph()
        fig.commit_belief(_make_belief("hub"))
        fig.commit_belief(_make_belief("child"))
        # Edge: child depends on hub (source=child, target=hub)
        fig.add_edge(TypedEdge("e1", "child", "hub", "belief_depends_on_belief"))
        for i in range(20):
            fig.propose_action(ActionNode(f"a{i}", ("hub",), "test"))

        engine = SafeRevisionEngine(kappa=0.01, max_impact=1)
        decision = engine.decide(fig, "hub", "falsified")
        assert decision.strategy == "stale_marking"
        changed = engine.apply_revision(fig, decision, "falsified")
        assert "hub" in changed
        assert "child" in changed
        assert fig.beliefs["hub"].lifecycle == "falsified"
        assert fig.beliefs["child"].lifecycle == "stale"

    def test_belief_not_found_returns_safe(self) -> None:
        fig = FalsifiableInterventionGraph()
        engine = SafeRevisionEngine()
        report = engine.assess_cascade(fig, "nonexistent")
        assert report.is_safe
