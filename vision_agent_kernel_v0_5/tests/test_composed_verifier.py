"""Tests for composed verifiers (AND, OR, NOT, VOTE) and nested evidence checks."""

from __future__ import annotations

import pytest

from execution.composed_verifier import AndVerifier, NotVerifier, OrVerifier, VoteVerifier
from execution.verifier_base import Verifier, VerifierContext, VerifierResult


class SimpleMockVerifier(Verifier):
    def __init__(self, verifier_id: str, ok: bool, confidence: float, reason: str = "") -> None:
        self.verifier_id = verifier_id
        self._ok = ok
        self._confidence = confidence
        self._reason = reason

    def verify(self, context: VerifierContext | dict[str, Any]) -> VerifierResult:
        return VerifierResult(
            ok=self._ok,
            verifier_id=self.verifier_id,
            confidence=self._confidence,
            reason=self._reason or f"{self.verifier_id} result is {self._ok}",
            evidence={"verifier_id": self.verifier_id, "score": self._confidence},
            frame_id=123 if self._ok else None,
        )


def test_composed_verifier_and_or_vote() -> None:
    """Verify that AND, OR, NOT, and VOTE compositions evaluate correctly and preserve nested evidence chains."""
    v1 = SimpleMockVerifier("v1", ok=True, confidence=0.9, reason="v1 passed")
    v2 = SimpleMockVerifier("v2", ok=True, confidence=0.8, reason="v2 passed")
    v3 = SimpleMockVerifier("v3", ok=False, confidence=0.2, reason="v3 failed")

    ctx = {}

    # 1. AND Composition
    and_all_pass = AndVerifier([v1, v2], verifier_id="and_ok")
    res_and_ok = and_all_pass.verify(ctx)
    assert res_and_ok.ok is True
    assert res_and_ok.confidence == 0.8  # min confidence
    assert res_and_ok.verifier_id == "and_ok"
    assert res_and_ok.evidence["composed_type"] == "AND"
    assert len(res_and_ok.evidence["sub_results"]) == 2
    assert res_and_ok.evidence["sub_results"][0]["ok"] is True
    assert res_and_ok.frame_id == 123  # derived from v1 or v2

    and_one_fail = AndVerifier([v1, v3], verifier_id="and_fail")
    res_and_fail = and_one_fail.verify(ctx)
    assert res_and_fail.ok is False
    assert res_and_fail.confidence == 0.2  # min confidence
    assert "Fails in sub-verifiers: v3" in res_and_fail.reason

    # 2. OR Composition
    or_one_pass = OrVerifier([v1, v3], verifier_id="or_ok")
    res_or_ok = or_one_pass.verify(ctx)
    assert res_or_ok.ok is True
    assert res_or_ok.confidence == 0.9  # max confidence
    assert "Passes in sub-verifiers: v1" in res_or_ok.reason
    assert res_or_ok.evidence["composed_type"] == "OR"

    or_all_fail = OrVerifier([v3], verifier_id="or_fail")
    res_or_fail = or_all_fail.verify(ctx)
    assert res_or_fail.ok is False
    assert res_or_fail.confidence == 0.2

    # 3. NOT Composition
    not_v3 = NotVerifier(v3, verifier_id="not_ok")
    res_not_ok = not_v3.verify(ctx)
    assert res_not_ok.ok is True
    assert pytest.approx(res_not_ok.confidence) == 0.2
    assert res_not_ok.evidence["composed_type"] == "NOT"
    assert res_not_ok.evidence["sub_result"]["verifier_id"] == "v3"

    not_v1 = NotVerifier(v1, verifier_id="not_fail")
    res_not_fail = not_v1.verify(ctx)
    assert res_not_fail.ok is False

    # 4. VOTE Composition
    # Vote requiring at least 2 passes
    vote_ok = VoteVerifier([v1, v2, v3], k=2, verifier_id="vote_ok")
    res_vote_ok = vote_ok.verify(ctx)
    assert res_vote_ok.ok is True
    assert pytest.approx(res_vote_ok.confidence) == 0.85  # average of ok: (0.9 + 0.8) / 2
    assert res_vote_ok.evidence["composed_type"] == "VOTE"
    assert res_vote_ok.evidence["passed_count"] == 2

    vote_fail = VoteVerifier([v1, v2, v3], k=3, verifier_id="vote_fail")
    res_vote_fail = vote_fail.verify(ctx)
    assert res_vote_fail.ok is False
    assert "Required 3 passes, but only got 2 passes" in res_vote_fail.reason


def test_vote_verifier_rejects_invalid_thresholds() -> None:
    """Vote verifiers must not silently pass impossible or empty configurations."""
    v1 = SimpleMockVerifier("v1", ok=True, confidence=0.9)

    with pytest.raises(ValueError, match="positive"):
        VoteVerifier([v1], k=0)

    with pytest.raises(ValueError, match="at least one"):
        VoteVerifier([], k=1)

    with pytest.raises(ValueError, match="cannot exceed"):
        VoteVerifier([v1], k=2)
