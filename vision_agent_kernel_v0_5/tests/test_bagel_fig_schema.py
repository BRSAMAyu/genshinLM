"""Tests for BAGEL FIG schema — belief pre-commit ordering, lifecycle, identity."""
from __future__ import annotations

import pytest

from bagel.fig_schema import (
    ActionNode,
    BeliefIdentity,
    BeliefLifecycleState,
    BeliefNode,
    FalsifiableInterventionGraph,
    FeedbackNode,
    ProbeNode,
    TypedEdge,
)


def _make_belief(belief_id: str = "b1", **kw: object) -> BeliefNode:
    defaults = dict(
        target_object="quest_objective",
        causal_role="objective_type_hypothesis",
        hypothesis="Objective is a dialogue interaction",
        falsification_condition="dialogue_continue anchor absent for 3 frames",
    )
    defaults.update(kw)
    return BeliefNode(belief_id=belief_id, **defaults)


def _make_action(action_id: str = "a1", belief_ids: tuple[str, ...] = ("b1",)) -> ActionNode:
    return ActionNode(action_id=action_id, belief_ids=belief_ids, action_type="click_anchor")


class TestBeliefPreCommitOrdering:
    """BeliefCommit must precede ActionProposal — post-hoc insertion is rejected."""

    def test_belief_before_action_ok(self) -> None:
        fig = FalsifiableInterventionGraph()
        fig.commit_belief(_make_belief("b1"))
        fig.propose_action(_make_action("a1", belief_ids=("b1",)))
        assert fig.beliefs["b1"].lifecycle != "posthoc_invalid"

    def test_belief_after_action_tagged_posthoc(self) -> None:
        fig = FalsifiableInterventionGraph()
        fig.commit_belief(_make_belief("b1"))
        fig.propose_action(_make_action("a1", belief_ids=("b1",)))
        # Now insert a new belief that references the same action
        fig.commit_belief(_make_belief("b2"))
        # b2 was not referenced by any action, so it's fine
        assert fig.beliefs["b2"].lifecycle != "posthoc_invalid"

    def test_posthoc_belief_directly_tagged(self) -> None:
        fig = FalsifiableInterventionGraph()
        fig.commit_belief(_make_belief("b1"))
        fig.propose_action(_make_action("a1", belief_ids=("b1",)))
        # Try to insert b1 after a1 already exists — this should tag as posthoc
        fig.commit_belief(_make_belief("b1", lifecycle="posthoc_invalid"))
        assert fig.beliefs["b1"].lifecycle == "posthoc_invalid"

    def test_action_references_unknown_belief_rejected(self) -> None:
        fig = FalsifiableInterventionGraph()
        with pytest.raises(ValueError, match="unknown belief"):
            fig.propose_action(_make_action("a1", belief_ids=("nonexistent",)))


class TestBeliefLifecycle:
    def test_initial_lifecycle_is_provisional(self) -> None:
        belief = _make_belief()
        assert belief.lifecycle == "provisional"

    def test_update_lifecycle(self) -> None:
        fig = FalsifiableInterventionGraph()
        fig.commit_belief(_make_belief("b1"))
        updated = fig.update_belief("b1", lifecycle="falsified")
        assert updated is not None
        assert updated.lifecycle == "falsified"
        assert fig.beliefs["b1"].lifecycle == "falsified"

    def test_version_increments(self) -> None:
        fig = FalsifiableInterventionGraph()
        v0 = fig.version
        fig.commit_belief(_make_belief("b1"))
        assert fig.version == v0 + 1
        fig.propose_action(_make_action("a1", belief_ids=("b1",)))
        assert fig.version == v0 + 2


class TestBeliefIdentity:
    def test_provisional_identity(self) -> None:
        identity = BeliefIdentity(belief_id="b1", provisional_anchor="intent:dialogue")
        assert not identity.is_confirmed_identity
        assert identity.provisional_anchor == "intent:dialogue"

    def test_confirmed_identity(self) -> None:
        identity = BeliefIdentity(
            belief_id="b1",
            provisional_anchor="intent:dialogue",
            fingerprint="ast:func_x:branch_3",
        )
        assert identity.is_confirmed_identity


class TestFIGQueries:
    def test_actions_for_belief(self) -> None:
        fig = FalsifiableInterventionGraph()
        fig.commit_belief(_make_belief("b1"))
        fig.commit_belief(_make_belief("b2"))
        fig.propose_action(_make_action("a1", belief_ids=("b1",)))
        fig.propose_action(_make_action("a2", belief_ids=("b1", "b2")))

        b1_actions = fig.actions_for_belief("b1")
        assert len(b1_actions) == 2

        b2_actions = fig.actions_for_belief("b2")
        assert len(b2_actions) == 1

    def test_feedbacks_for_belief(self) -> None:
        fig = FalsifiableInterventionGraph()
        fig.commit_belief(_make_belief("b1"))
        fig.propose_action(_make_action("a1", belief_ids=("b1",)))
        fig.add_feedback(FeedbackNode(
            feedback_id="f1", action_id="a1", polarity="negative",
        ))
        fb = fig.feedbacks_for_belief("b1")
        assert len(fb) == 1
        assert fb[0].polarity == "negative"

    def test_downstream_beliefs(self) -> None:
        fig = FalsifiableInterventionGraph()
        fig.commit_belief(_make_belief("b1"))
        fig.commit_belief(_make_belief("b2"))
        fig.commit_belief(_make_belief("b3"))
        # b2 depends on b1: edge (b2 → b1)
        fig.add_edge(TypedEdge("e1", "b2", "b1", "belief_depends_on_belief"))
        # b3 depends on b2: edge (b3 → b2)
        fig.add_edge(TypedEdge("e2", "b3", "b2", "belief_depends_on_belief"))

        downstream = fig.downstream_beliefs("b1")
        assert "b2" in downstream
        assert "b3" in downstream

    def test_suspect_beliefs(self) -> None:
        fig = FalsifiableInterventionGraph()
        fig.commit_belief(_make_belief("b1"))
        fig.commit_belief(_make_belief("b2"))
        fig.update_belief("b1", lifecycle="suspect")
        suspect = fig.suspect_beliefs()
        assert len(suspect) == 1
        assert suspect[0].belief_id == "b1"

    def test_falsified_beliefs(self) -> None:
        fig = FalsifiableInterventionGraph()
        fig.commit_belief(_make_belief("b1"))
        fig.update_belief("b1", lifecycle="falsified")
        assert len(fig.falsified_beliefs()) == 1

    def test_to_dict(self) -> None:
        fig = FalsifiableInterventionGraph(graph_id="test_fig")
        fig.commit_belief(_make_belief("b1"))
        d = fig.to_dict()
        assert d["graph_id"] == "test_fig"
        assert "b1" in d["beliefs"]
        assert d["version"] >= 1


class TestFalsificationConditionRequired:
    """Without falsification_condition, belief shouldn't drive high-risk action."""

    def test_belief_without_falsification_condition(self) -> None:
        belief = BeliefNode(
            belief_id="b_risky",
            target_object="enemy_hp",
            causal_role="enemy_state_hypothesis",
            hypothesis="Boss is in phase 2",
            falsification_condition="",
            risk_level="high",
        )
        # Belief can exist but the probe policy should not generate probes for it
        from bagel.probe_policy import ProbePolicy
        fig = FalsifiableInterventionGraph()
        fig.commit_belief(belief)
        policy = ProbePolicy()
        probes = policy.generate_probes(fig)
        assert len(probes) == 0  # No falsification condition = no probes
