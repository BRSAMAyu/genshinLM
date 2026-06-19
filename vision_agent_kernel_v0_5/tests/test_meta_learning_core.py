"""Tests for the three core breakthrough modules:

1. BeliefProposer — hypothesis generation after BAGEL falsification
2. MetaLearningBridge — connecting BAGEL attribution to skill induction
3. ParameterizedSkillInduction — parameterized skill templates from traces

These tests verify the cognitive closed loop:
falsification → hypothesis → exploration → belief revision → skill learning
"""
from __future__ import annotations

import time
import uuid
from typing import Any

import pytest

from bagel.fig_schema import (
    BeliefNode,
    FalsifiableInterventionGraph,
    FeedbackNode,
    TypedEdge,
)


# ===========================================================================
# BeliefProposer Tests
# ===========================================================================


class TestBeliefProposer:
    """Test hypothesis generation after belief falsification."""

    def _make_falsified_belief(self, target: str = "boss_stormterror") -> BeliefNode:
        return BeliefNode(
            belief_id=f"belief_{uuid.uuid4().hex[:8]}",
            target_object=target,
            causal_role="combat_strategy_hypothesis",
            hypothesis="attack_with_pyro",
            falsification_condition="enemy_takes_damage",
            lifecycle="falsified",
            confidence=0.3,
        )

    def test_propose_generates_hypotheses(self) -> None:
        """BeliefProposer generates at least one hypothesis for a falsified belief."""
        from bagel.belief_proposer import BeliefProposer

        fig = FalsifiableInterventionGraph()
        proposer = BeliefProposer(fig=fig)
        belief = self._make_falsified_belief()

        result = proposer.propose(belief, falsification_reason="attack ineffective")

        assert len(result.proposals) >= 1
        assert result.best_proposal is not None
        assert result.best_proposal.confidence > 0.0

    def test_propose_classifies_failure_modes(self) -> None:
        """Failure mode classification returns correct categories."""
        from bagel.belief_proposer import classify_failure_mode

        assert classify_failure_mode("timeout", "") == "environment"
        assert classify_failure_mode("not_found in scene", "") == "perception"
        assert classify_failure_mode("wrong approach used", "") == "strategy"
        assert classify_failure_mode("stamina insufficient", "") == "resource"
        assert classify_failure_mode("waypoint locked", "") == "precondition"
        assert classify_failure_mode("blocked by dialogue", "") == "execution"
        assert classify_failure_mode("unknown error", "") == "strategy"

    def test_commit_best_proposal_creates_new_belief(self) -> None:
        """Committing a proposal creates a new provisional belief in FIG."""
        from bagel.belief_proposer import BeliefProposer

        fig = FalsifiableInterventionGraph()
        proposer = BeliefProposer(fig=fig)
        belief = self._make_falsified_belief()
        fig.commit_belief(belief)

        result = proposer.propose(belief, falsification_reason="enemy immune")
        new_belief = proposer.commit_best_proposal(result)

        assert new_belief is not None
        assert new_belief.lifecycle == "provisional"
        assert new_belief.belief_id != belief.belief_id
        assert new_belief.metadata.get("falsified_parent") == belief.belief_id
        assert new_belief.metadata.get("failure_mode") == result.failure_mode
        # Verify it's in the FIG
        assert new_belief.belief_id in fig.beliefs

    def test_proposals_differ_from_original(self) -> None:
        """Generated hypotheses must differ from the falsified belief."""
        from bagel.belief_proposer import BeliefProposer

        proposer = BeliefProposer()
        belief = self._make_falsified_belief()

        result = proposer.propose(belief, falsification_reason="strategy failed")

        for proposal in result.proposals:
            assert proposal.hypothesis != belief.hypothesis
            assert proposal.falsified_belief_id == belief.belief_id

    def test_proposer_uses_decision_memory(self) -> None:
        """BeliefProposer boosts confidence when DecisionMemory has similar successes."""
        from bagel.belief_proposer import BeliefProposer
        from learning.decision_memory import DecisionMemory

        memory = DecisionMemory(db_path=":memory:")
        # Pre-seed with a successful strategy for the target
        memory.record(
            goal="boss_stormterror",
            capsule_id="genshin",
            screen_state="boss_fight",
            plan=[{"action": "attack_with_cryo"}],
            success=True,
            duration_sec=30.0,
            confidence=0.8,
        )

        proposer = BeliefProposer(decision_memory=memory)
        belief = self._make_falsified_belief()

        result = proposer.propose(belief, falsification_reason="strategy failed")

        # At least one proposal should have boosted confidence from DecisionMemory
        assert result.best_proposal is not None
        # The best proposal should reference decision_memory as source
        dm_sourced = any(p.source == "decision_memory" for p in result.proposals)
        assert dm_sourced, "Expected at least one proposal sourced from DecisionMemory"

    def test_conflict_edge_added_to_fig(self) -> None:
        """When a proposal is committed, a conflict edge connects old and new beliefs."""
        from bagel.belief_proposer import BeliefProposer

        fig = FalsifiableInterventionGraph()
        proposer = BeliefProposer(fig=fig)
        belief = self._make_falsified_belief()
        fig.commit_belief(belief)

        result = proposer.propose(belief, falsification_reason="falsified")
        new_belief = proposer.commit_best_proposal(result)

        assert new_belief is not None
        # Check that a conflict edge was added
        conflict_edges = [
            e for e in fig.edges
            if e.kind == "belief_conflicts_belief"
            and e.source_id == belief.belief_id
            and e.target_id == new_belief.belief_id
        ]
        assert len(conflict_edges) >= 1


# ===========================================================================
# MetaLearningBridge Tests
# ===========================================================================


class TestMetaLearningBridge:
    """Test the connection between BAGEL attribution and skill induction."""

    def _make_components(self) -> tuple:
        from bagel.belief_proposer import BeliefProposer
        from learning.decision_memory import DecisionMemory
        from learning.meta_learning_bridge import MetaLearningBridge

        fig = FalsifiableInterventionGraph()
        memory = DecisionMemory(db_path=":memory:")
        proposer = BeliefProposer(fig=fig, decision_memory=memory)
        bridge = MetaLearningBridge(fig=fig, decision_memory=memory, belief_proposer=proposer)
        return fig, memory, proposer, bridge

    def test_falsification_cycle_produces_learning(self) -> None:
        """A falsification cycle generates proposals and records to DecisionMemory."""
        fig, memory, proposer, bridge = self._make_components()

        belief = BeliefNode(
            belief_id="b1",
            target_object="enemy_boss",
            causal_role="combat_strategy_hypothesis",
            hypothesis="attack_with_pyro",
            falsification_condition="enemy_takes_damage",
            lifecycle="falsified",
            confidence=0.3,
        )
        fig.commit_belief(belief)

        result = bridge.on_falsification_cycle(
            falsified_beliefs=[belief],
            feedbacks=[],
            error_context="attack had no effect",
        )

        assert len(result.falsified_belief_ids) == 1
        assert result.proposals_generated >= 1
        assert result.beliefs_committed >= 1
        assert result.decision_memory_updates >= 1

    def test_exploration_results_recorded_to_memory(self) -> None:
        """Exploration results are stored in DecisionMemory."""
        _, memory, _, bridge = self._make_components()

        bridge.on_exploration_result(
            exploration_target="unknown_npc",
            success=True,
            actions_taken=[{"action": "talk"}, {"action": "select_dialog"}],
            scene_description="dialogue",
        )

        from learning.decision_memory import DecisionQuery
        records = memory.query(DecisionQuery(goal="unknown_npc"))
        assert len(records) >= 1
        assert records[0].success is True

    def test_repeated_failures_trigger_skill_candidate(self) -> None:
        """3+ failures on same target trigger skill induction candidate."""
        fig, memory, proposer, bridge = self._make_components()

        for i in range(4):
            belief = BeliefNode(
                belief_id=f"b_{i}",
                target_object="puzzle_torch",
                causal_role="ui_affordance_hypothesis",
                hypothesis="light_torch_with_pyro",
                falsification_condition="torch_lit",
                lifecycle="falsified",
                confidence=0.3,
            )
            fig.commit_belief(belief)
            bridge.on_falsification_cycle(
                falsified_beliefs=[belief],
                feedbacks=[],
                error_context="torch did not light",
            )

        summary = bridge.get_learning_summary()
        assert summary["total_events"] >= 4
        # puzzle_torch should have strategy failure mode count >= 3
        assert summary["failure_mode_distribution"].get("strategy", 0) >= 3

    def test_learning_summary_structure(self) -> None:
        """Learning summary contains expected fields."""
        _, _, _, bridge = self._make_components()

        summary = bridge.get_learning_summary()
        assert "total_events" in summary
        assert "failure_mode_distribution" in summary
        assert "recent_events" in summary


# ===========================================================================
# ParameterizedSkillInduction Tests
# ===========================================================================


class TestParameterizedSkillInduction:
    """Test parameterized skill template induction from multiple traces."""

    def test_induce_from_two_traces(self) -> None:
        """Can induce a template from 2+ similar traces."""
        from learning.parameterized_skill_induction import ParameterizedSkillInductor

        inductor = ParameterizedSkillInductor(min_traces=2)

        traces = [
            [
                {"type": "navigate", "target": "mondstadt"},
                {"type": "click", "target": "npc_blacksmith"},
                {"type": "click", "target": "buy_iron"},
            ],
            [
                {"type": "navigate", "target": "liyue"},
                {"type": "click", "target": "npc_merchant"},
                {"type": "click", "target": "buy_crystal"},
            ],
        ]

        template = inductor.induce("npc_shop_buy", traces)

        assert template is not None
        assert template.source_trace_count == 2
        assert len(template.steps) >= 2
        assert template.generalization_confidence > 0.0

    def test_variable_parts_become_parameters(self) -> None:
        """Targets that vary across traces become parameters, not fixed values."""
        from learning.parameterized_skill_induction import ParameterizedSkillInductor

        inductor = ParameterizedSkillInductor(min_traces=2)

        traces = [
            [
                {"type": "click", "target": "item_A"},
                {"type": "click", "target": "confirm"},
            ],
            [
                {"type": "click", "target": "item_B"},
                {"type": "click", "target": "confirm"},
            ],
        ]

        template = inductor.induce("select_item", traces)
        assert template is not None

        # First step has variable target → should be a parameter
        assert len(template.parameters) >= 1
        first_param = template.parameters[0]
        assert first_param.variability_score > 0.0

        # Second step has fixed target ("confirm") → should be literal
        assert template.steps[-1].target_template == "confirm"

    def test_instantiate_fills_parameters(self) -> None:
        """Template instantiation fills parameter placeholders with values."""
        from learning.parameterized_skill_induction import ParameterizedSkillInductor

        inductor = ParameterizedSkillInductor(min_traces=2)

        traces = [
            [{"type": "click", "target": "item_A"}, {"type": "click", "target": "confirm"}],
            [{"type": "click", "target": "item_B"}, {"type": "click", "target": "confirm"}],
        ]

        template = inductor.induce("select_item", traces)
        assert template is not None

        if template.parameters:
            param_name = template.parameters[0].name
            concrete = template.instantiate(**{param_name: "item_C"})
            assert concrete[0]["target"] == "item_C"
            assert concrete[-1]["target"] == "confirm"

    def test_too_few_traces_returns_none(self) -> None:
        """Induction returns None when fewer traces than minimum."""
        from learning.parameterized_skill_induction import ParameterizedSkillInductor

        inductor = ParameterizedSkillInductor(min_traces=3)
        result = inductor.induce("test", [[{"type": "click", "target": "a"}]])
        assert result is None

    def test_repetition_detected_as_loop(self) -> None:
        """3+ consecutive steps of same type are detected as a loop pattern."""
        from learning.parameterized_skill_induction import ParameterizedSkillInductor

        inductor = ParameterizedSkillInductor(min_traces=2)

        traces = [
            [
                {"type": "key_press", "target": "attack"},
                {"type": "key_press", "target": "attack"},
                {"type": "key_press", "target": "attack"},
            ],
            [
                {"type": "key_press", "target": "attack"},
                {"type": "key_press", "target": "attack"},
                {"type": "key_press", "target": "attack"},
            ],
        ]

        template = inductor.induce("combat_attack_loop", traces)
        assert template is not None
        # The third step should have a loop condition
        loop_steps = [s for s in template.steps if s.loop_condition]
        assert len(loop_steps) >= 1, "Expected at least one step with a loop condition"

    def test_template_stored_and_retrieved(self) -> None:
        """Induced templates are stored and retrievable by ID."""
        from learning.parameterized_skill_induction import ParameterizedSkillInductor

        inductor = ParameterizedSkillInductor(min_traces=2)

        traces = [
            [{"type": "click", "target": "a"}],
            [{"type": "click", "target": "b"}],
        ]

        template = inductor.induce("test_retrieve", traces)
        assert template is not None

        retrieved = inductor.get_template(template.template_id)
        assert retrieved is not None
        assert retrieved.template_id == template.template_id

        all_templates = inductor.list_templates()
        assert len(all_templates) >= 1


# ===========================================================================
# Full Chain Integration Tests
# ===========================================================================


class TestFullChainIntegration:
    """Test the complete exploration→belief→skill chain."""

    def test_exploration_feeds_into_belief_system(self) -> None:
        """Exploration results feed into DecisionMemory via MetaLearningBridge."""
        from bagel.belief_proposer import BeliefProposer
        from learning.decision_memory import DecisionMemory, DecisionQuery
        from learning.meta_learning_bridge import MetaLearningBridge

        fig = FalsifiableInterventionGraph()
        memory = DecisionMemory(db_path=":memory:")
        proposer = BeliefProposer(fig=fig, decision_memory=memory)
        bridge = MetaLearningBridge(fig=fig, decision_memory=memory, belief_proposer=proposer)

        # Simulate exploration
        bridge.on_exploration_result(
            exploration_target="unknown_domain",
            success=True,
            actions_taken=[{"action": "enter"}, {"action": "fight"}, {"action": "claim"}],
            scene_description="domain",
        )

        # Verify it's in DecisionMemory
        records = memory.query(DecisionQuery(goal="unknown_domain"))
        assert len(records) >= 1
        assert records[0].success is True
        assert len(records[0].plan_steps()) == 3

    def test_falsification_to_new_belief_roundtrip(self) -> None:
        """Falsified belief → hypothesis generation → new belief committed to FIG."""
        from bagel.belief_proposer import BeliefProposer
        from learning.decision_memory import DecisionMemory
        from learning.meta_learning_bridge import MetaLearningBridge

        fig = FalsifiableInterventionGraph()
        memory = DecisionMemory(db_path=":memory:")
        proposer = BeliefProposer(fig=fig, decision_memory=memory)
        bridge = MetaLearningBridge(fig=fig, decision_memory=memory, belief_proposer=proposer)

        # Create and falsify a belief
        old_belief = BeliefNode(
            belief_id="old_b1",
            target_object="enemy_hydro_slime",
            causal_role="combat_strategy_hypothesis",
            hypothesis="attack_with_hydro",
            falsification_condition="enemy_takes_damage",
            lifecycle="falsified",
            confidence=0.2,
        )
        fig.commit_belief(old_belief)

        result = bridge.on_falsification_cycle(
            falsified_beliefs=[old_belief],
            feedbacks=[],
            error_context="hydro immune",
        )

        # Verify new belief was committed
        assert result.beliefs_committed >= 1
        new_beliefs = [b for b in fig.beliefs.values() if b.lifecycle == "provisional"]
        assert len(new_beliefs) >= 1

        # Verify the new belief is linked to the old one
        new_belief = new_beliefs[0]
        assert new_belief.metadata.get("falsified_parent") == "old_b1"

    def test_live_factory_has_bridge_connected(self) -> None:
        """AgentLoop from live_factory has meta-learning bridge connected."""
        from agent_kernel.live_factory import create_live_genshin_loop

        loop, _, _ = create_live_genshin_loop(
            goal="test", window_title="test", dry_run=True,
        )

        assert loop._meta_learning_bridge is not None
        assert hasattr(loop._meta_learning_bridge, 'on_exploration_result')


# ===========================================================================
# induce_from_patterns bridge method tests
# ===========================================================================

class TestInduceFromPatterns:
    """Verify induce_from_patterns() adapts MetaLearningBridge calls to induce()."""

    def test_induce_from_patterns_basic(self) -> None:
        from learning.parameterized_skill_induction import ParameterizedSkillInductor

        inductor = ParameterizedSkillInductor(min_traces=1)
        traces = [
            [
                {"action": "key_tap", "target": "E"},
                {"action": "wait", "target": "500ms"},
                {"action": "key_tap", "target": "E"},
            ],
            [
                {"action": "key_tap", "target": "E"},
                {"action": "wait", "target": "300ms"},
                {"action": "key_tap", "target": "E"},
            ],
        ]
        tpl = inductor.induce_from_patterns(
            target="npc_dialog",
            failure_mode="dialog_stuck",
            successful_plans=traces,
        )
        assert tpl is not None
        assert "npc_dialog" in tpl.name
        assert tpl.applicable_contexts == ("npc_dialog", "dialog_stuck")

    def test_induce_from_patterns_empty_plans(self) -> None:
        from learning.parameterized_skill_induction import ParameterizedSkillInductor

        inductor = ParameterizedSkillInductor()
        result = inductor.induce_from_patterns(
            target="boss",
            failure_mode="timeout",
            successful_plans=[],
        )
        assert result is None

    def test_induce_from_patterns_returns_template(self) -> None:
        from learning.parameterized_skill_induction import ParameterizedSkillInductor

        inductor = ParameterizedSkillInductor(min_traces=1)
        traces = [[{"action": "click", "target": "button_A"}]]
        tpl = inductor.induce_from_patterns(
            target="quest",
            failure_mode="navigation_lost",
            successful_plans=traces,
        )
        assert tpl is not None
        assert tpl.source_trace_count == 1
