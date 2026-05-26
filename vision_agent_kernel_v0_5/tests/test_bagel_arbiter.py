"""Tests for BAGEL Arbiter — lifecycle transitions and probe generation."""
from __future__ import annotations

import pytest

from bagel.arbiter import BagelArbiter
from bagel.evidence_matrix import EvidenceMatrix, EvidenceSignal
from bagel.fig_schema import BeliefNode, FalsifiableInterventionGraph


def _make_belief(belief_id: str = "b1", lifecycle: str = "committed") -> BeliefNode:
    return BeliefNode(
        belief_id=belief_id,
        target_object="quest_objective",
        causal_role="objective_type_hypothesis",
        hypothesis="Objective is dialogue",
        falsification_condition="no dialogue for 3 frames",
        lifecycle=lifecycle,
    )


def _add_signals(matrix: EvidenceMatrix, belief_id: str, supports: int = 0, refutes: int = 0) -> None:
    for i in range(supports):
        matrix.add_signal(EvidenceSignal(f"sup_{i}", belief_id, "support", 0.7))
    for i in range(refutes):
        matrix.add_signal(EvidenceSignal(f"ref_{i}", belief_id, "refute", 0.7))


class TestArbiterTransitions:
    def test_confirmed_on_strong_support(self) -> None:
        fig = FalsifiableInterventionGraph()
        fig.commit_belief(_make_belief("b1"))
        matrix = EvidenceMatrix()
        _add_signals(matrix, "b1", supports=3)

        arbiter = BagelArbiter()
        results = arbiter.arbitrate(fig, matrix)
        assert len(results) == 1
        assert results[0].new_lifecycle == "confirmed"

    def test_falsified_on_strong_refutation(self) -> None:
        fig = FalsifiableInterventionGraph()
        fig.commit_belief(_make_belief("b1"))
        matrix = EvidenceMatrix()
        _add_signals(matrix, "b1", refutes=3)

        arbiter = BagelArbiter()
        results = arbiter.arbitrate(fig, matrix)
        assert len(results) == 1
        assert results[0].new_lifecycle == "falsified"

    def test_suspect_on_mixed_evidence(self) -> None:
        fig = FalsifiableInterventionGraph()
        fig.commit_belief(_make_belief("b1"))
        matrix = EvidenceMatrix()
        matrix.add_signal(EvidenceSignal("s1", "b1", "support", 0.5))
        matrix.add_signal(EvidenceSignal("s2", "b1", "refute", 0.5))

        arbiter = BagelArbiter()
        results = arbiter.arbitrate(fig, matrix)
        assert len(results) == 1
        assert results[0].new_lifecycle in ("suspect", "falsified")

    def test_no_transition_for_retired_belief(self) -> None:
        fig = FalsifiableInterventionGraph()
        fig.commit_belief(_make_belief("b1"))
        fig.update_belief("b1", lifecycle="retired")
        matrix = EvidenceMatrix()
        _add_signals(matrix, "b1", supports=3)

        arbiter = BagelArbiter()
        results = arbiter.arbitrate(fig, matrix)
        assert len(results) == 0


class TestConflictTriggersProbe:
    def test_conflict_requests_probe(self) -> None:
        fig = FalsifiableInterventionGraph()
        fig.commit_belief(_make_belief("b1"))
        matrix = EvidenceMatrix()
        matrix.add_signal(EvidenceSignal("s1", "b1", "support", 1.0))
        matrix.add_signal(EvidenceSignal("s2", "b1", "refute", 1.0))

        arbiter = BagelArbiter()
        results = arbiter.arbitrate(fig, matrix)
        assert results[0].probe_requested is True

    def test_no_probe_without_conflict(self) -> None:
        fig = FalsifiableInterventionGraph()
        fig.commit_belief(_make_belief("b1"))
        matrix = EvidenceMatrix()
        _add_signals(matrix, "b1", supports=3)

        arbiter = BagelArbiter()
        results = arbiter.arbitrate(fig, matrix)
        assert results[0].probe_requested is False


class TestArbiterApply:
    def test_apply_updates_fig(self) -> None:
        fig = FalsifiableInterventionGraph()
        fig.commit_belief(_make_belief("b1"))
        matrix = EvidenceMatrix()
        _add_signals(matrix, "b1", refutes=3)

        arbiter = BagelArbiter()
        results = arbiter.arbitrate(fig, matrix)
        updated = arbiter.apply_arbitration(fig, results)
        assert "b1" in updated
        assert fig.beliefs["b1"].lifecycle == "falsified"

    def test_generate_probes_for_suspect(self) -> None:
        fig = FalsifiableInterventionGraph()
        fig.commit_belief(_make_belief("b1"))
        matrix = EvidenceMatrix()
        matrix.add_signal(EvidenceSignal("s1", "b1", "support", 1.0))
        matrix.add_signal(EvidenceSignal("s2", "b1", "refute", 1.0))

        arbiter = BagelArbiter()
        results = arbiter.arbitrate(fig, matrix)
        probes = arbiter.generate_probe_requests(results)
        assert len(probes) >= 1
        assert probes[0].belief_id == "b1"
        assert probes[0].status == "generated"
