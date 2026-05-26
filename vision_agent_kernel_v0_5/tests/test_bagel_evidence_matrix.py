"""Tests for BAGEL Evidence Matrix — non-symmetric causal activation scoring."""
from __future__ import annotations

import math

import pytest

from bagel.evidence_matrix import EvidenceMatrix, EvidenceSignal, EvidenceScore


def _signal(
    belief_id: str = "b1",
    polarity: str = "support",
    weight: float = 1.0,
    is_core: bool = False,
) -> EvidenceSignal:
    return EvidenceSignal(
        signal_id=f"sig_{belief_id}_{polarity}",
        belief_id=belief_id,
        polarity=polarity,
        weight=weight,
        is_core_probe=is_core,
    )


class TestEvidenceMatrixBasicScoring:
    def test_no_signals_gives_zero_score(self) -> None:
        m = EvidenceMatrix()
        s = m.score_belief("b1")
        assert s.score == 0.0
        assert s.signal_count == 0

    def test_single_support_signal(self) -> None:
        m = EvidenceMatrix()
        m.add_signal(_signal("b1", "support", 0.8))
        s = m.score_belief("b1")
        assert s.score > 0
        assert s.support_max == 0.8
        assert s.refute_sum == 0.0

    def test_single_refute_signal(self) -> None:
        m = EvidenceMatrix()
        m.add_signal(_signal("b1", "refute", 0.9))
        s = m.score_belief("b1")
        assert s.score < 0
        assert s.refute_sum == 0.9

    def test_neutral_signal_no_effect(self) -> None:
        m = EvidenceMatrix()
        m.add_signal(_signal("b1", "support", 0.5))
        m.add_signal(_signal("b1", "neutral", 1.0))
        s = m.score_belief("b1")
        assert s.support_max == 0.5
        assert s.refute_sum == 0.0

    def test_insufficient_signal_excluded(self) -> None:
        m = EvidenceMatrix()
        m.add_signal(_signal("b1", "support", 0.5))
        m.add_signal(_signal("b1", "insufficient", 1.0))
        s = m.score_belief("b1")
        assert s.signal_count == 2
        assert s.support_max == 0.5  # insufficient excluded from scoring


class TestNonSymmetricScoring:
    """Core BAGEL v1.1 requirement: one core failure cannot be drowned."""

    def test_one_core_contradiction_vetoes_many_supports(self) -> None:
        """100 weak support signals should NOT override one strong core contradiction."""
        m = EvidenceMatrix()
        # 100 weak support signals
        for i in range(100):
            m.add_signal(_signal("b1", "support", 0.1))
        # 1 strong core contradiction
        m.add_signal(EvidenceSignal(
            signal_id="core_refute",
            belief_id="b1",
            polarity="refute",
            weight=0.9,
            is_core_probe=True,
        ))

        s = m.score_belief("b1")
        assert s.core_contradiction is True
        assert s.score < 0, f"Score should be negative but got {s.score}"

    def test_relevant_survival_lowers_rank_but_not_eliminates(self) -> None:
        m = EvidenceMatrix()
        m.add_signal(_signal("b1", "refute", 0.5))
        m.add_signal(_signal("b1", "support", 0.3))

        s = m.score_belief("b1")
        assert s.score < 0  # Refute dominates
        assert s.support_max == 0.3  # Support is recorded

    def test_multi_auditor_conflict_not_averaged(self) -> None:
        m = EvidenceMatrix()
        m.add_signal(EvidenceSignal("s1", "b1", "support", 1.0, auditor_id="aud1"))
        m.add_signal(EvidenceSignal("s2", "b1", "refute", 1.0, auditor_id="aud2"))

        s = m.score_belief("b1")
        assert s.conflict_detected is True

    def test_alpha_controls_relevance_weight(self) -> None:
        m1 = EvidenceMatrix(alpha=0.0)
        m2 = EvidenceMatrix(alpha=1.0)

        m1.add_signal(_signal("b1", "refute", 0.5))
        m1.add_signal(_signal("b1", "support", 0.2))
        m2.add_signal(_signal("b1", "refute", 0.5))
        m2.add_signal(_signal("b1", "support", 0.2))

        s1 = m1.score_belief("b1")
        s2 = m2.score_belief("b1")
        # Higher alpha should give higher score (more weight to relevant signals)
        assert s2.score > s1.score


class TestScoreAllAndRanking:
    def test_score_all(self) -> None:
        m = EvidenceMatrix()
        m.add_signal(_signal("b1", "support", 0.8))
        m.add_signal(_signal("b2", "refute", 0.9))

        scores = m.score_all()
        assert "b1" in scores
        assert "b2" in scores
        assert scores["b1"].score > 0
        assert scores["b2"].score < 0

    def test_top_suspects(self) -> None:
        m = EvidenceMatrix()
        m.add_signal(_signal("b1", "support", 0.9))
        m.add_signal(_signal("b2", "refute", 0.8))
        m.add_signal(_signal("b3", "refute", 0.5))

        suspects = m.top_suspects(limit=2)
        assert len(suspects) == 2
        assert suspects[0].score <= suspects[1].score
        assert suspects[0].belief_id == "b2"

    def test_signal_count(self) -> None:
        m = EvidenceMatrix()
        m.add_signal(_signal("b1", "support", 1.0))
        m.add_signal(_signal("b1", "refute", 0.5))
        m.add_signal(_signal("b2", "support", 0.3))

        assert m.signal_count("b1") == 2
        assert m.signal_count("b2") == 1
        assert m.signal_count() == 3
