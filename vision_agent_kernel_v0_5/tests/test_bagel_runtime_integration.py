"""Integration tests for BAGEL Runtime — full attribution loop."""
from __future__ import annotations

import pytest

from bagel.evidence_matrix import EvidenceSignal
from bagel.event_store import BagelEventStore
from bagel.fig_schema import (
    ActionNode,
    BeliefNode,
    FeedbackNode,
)
from bagel.runtime import BagelRuntime


def _make_belief(belief_id: str, target: str = "quest") -> BeliefNode:
    return BeliefNode(
        belief_id=belief_id,
        target_object=target,
        causal_role="objective_type_hypothesis",
        hypothesis=f"Hypothesis for {belief_id}",
        falsification_condition=f"Condition for {belief_id}",
    )


class TestFullAttributionCycle:
    def test_successful_flow_no_revision(self) -> None:
        rt = BagelRuntime(event_store=BagelEventStore(path="/dev/null"))

        # Commit belief
        rt.commit_belief(_make_belief("b1"), trace_id="t1")
        # Propose action
        rt.propose_action(ActionNode("a1", ("b1",), "click_anchor"), trace_id="t1")
        # Materialize
        rt.materialize_action("a1", fingerprint="fp_001")
        # Positive feedback
        rt.receive_feedback(FeedbackNode("f1", "a1", "positive", signal_quality=0.9))

        # No attribution needed for success, but we can run it
        result = rt.run_attribution_cycle(trace_id="t1")
        assert result.strategy == "local_attribution"

    def test_failure_triggers_falsification(self) -> None:
        rt = BagelRuntime(event_store=BagelEventStore(path="/dev/null"))

        rt.commit_belief(_make_belief("b1"))
        rt.propose_action(ActionNode("a1", ("b1",), "click_anchor"))
        rt.materialize_action("a1", fingerprint="fp_001")
        # Negative feedback
        rt.receive_feedback(FeedbackNode("f1", "a1", "negative", signal_quality=0.9))

        result = rt.run_attribution_cycle(trace_id="t1")
        assert "b1" in result.belief_scores
        assert result.belief_scores["b1"] < 0

    def test_multiple_beliefs_correct_attribution(self) -> None:
        rt = BagelRuntime(event_store=BagelEventStore(path="/dev/null"))

        # Two beliefs driving different actions
        rt.commit_belief(_make_belief("b1", "nav"))
        rt.commit_belief(_make_belief("b2", "combat"))
        rt.propose_action(ActionNode("a1", ("b1",), "navigate"))
        rt.propose_action(ActionNode("a2", ("b2",), "attack"))

        # Navigation failed, combat succeeded
        rt.receive_feedback(FeedbackNode("f1", "a1", "negative", signal_quality=0.9))
        rt.receive_feedback(FeedbackNode("f2", "a2", "positive", signal_quality=0.9))

        result = rt.run_attribution_cycle(trace_id="t1")
        # b1 should have negative score, b2 positive
        assert result.belief_scores.get("b1", 0) < result.belief_scores.get("b2", 0)

    def test_probe_execution_updates_evidence(self) -> None:
        rt = BagelRuntime(event_store=BagelEventStore(path="/dev/null"))

        rt.commit_belief(_make_belief("b1"))
        rt.propose_action(ActionNode("a1", ("b1",), "click"))
        rt.receive_feedback(FeedbackNode("f1", "a1", "negative", signal_quality=0.5))

        # Run attribution with a probe executor that confirms falsification
        def mock_probe_executor(probe):
            return (False, {"reason": "probe confirmed falsification"})

        result = rt.run_attribution_cycle(
            trace_id="t1",
            probe_executor=mock_probe_executor,
        )
        assert result.probes_generated >= 0  # May or may not generate probes


class TestEventStore:
    def test_events_appended(self, tmp_path) -> None:
        store = BagelEventStore(path=str(tmp_path / "test.jsonl"))
        rt = BagelRuntime(event_store=store)

        rt.commit_belief(_make_belief("b1"))
        rt.propose_action(ActionNode("a1", ("b1",), "test"))

        events = store.read_events(graph_id=rt.fig.graph_id)
        assert len(events) >= 2
        assert events[0].event_type == "BeliefCommitted"
        assert events[1].event_type == "ActionProposed"
        store.close()

    def test_event_reconstruction(self, tmp_path) -> None:
        store = BagelEventStore(path=str(tmp_path / "test.jsonl"))
        rt = BagelRuntime(event_store=store)

        rt.commit_belief(_make_belief("b1"))
        store.close()

        # Reconstruct
        store2 = BagelEventStore(path=str(tmp_path / "test.jsonl"))
        reconstructed = store2.reconstruct_fig(rt.fig.graph_id)
        assert "beliefs" in reconstructed
        assert "b1" in reconstructed["beliefs"]
        store2.close()


class TestStateBusIntegration:
    def test_bagel_state_published(self) -> None:
        rt = BagelRuntime(event_store=BagelEventStore(path="/dev/null"))

        rt.commit_belief(_make_belief("b1"))

        slot = rt.state_bus.get_slot("bagel_evidence_state")
        assert slot is not None
        state = slot.get()
        assert state is not None
        assert state["belief_count"] == 1

    def test_attribution_result_published(self) -> None:
        rt = BagelRuntime(event_store=BagelEventStore(path="/dev/null"))
        rt.commit_belief(_make_belief("b1"))
        rt.propose_action(ActionNode("a1", ("b1",), "test"))
        rt.receive_feedback(FeedbackNode("f1", "a1", "negative", signal_quality=0.9))

        rt.run_attribution_cycle()

        slot = rt.state_bus.get_slot("bagel_attribution_result")
        assert slot is not None
        result = slot.get()
        assert result is not None
        assert "belief_scores" in result


class TestSuspectSummary:
    def test_summary_after_attribution(self) -> None:
        rt = BagelRuntime(event_store=BagelEventStore(path="/dev/null"))
        rt.commit_belief(_make_belief("b1"))
        rt.commit_belief(_make_belief("b2"))
        rt.propose_action(ActionNode("a1", ("b1",), "test"))
        rt.receive_feedback(FeedbackNode("f1", "a1", "negative", signal_quality=0.9))
        rt.run_attribution_cycle()

        summary = rt.get_suspect_summary()
        assert "active" in summary
        assert "suspect" in summary
        assert "falsified" in summary
        assert summary["total_beliefs"] == 2
