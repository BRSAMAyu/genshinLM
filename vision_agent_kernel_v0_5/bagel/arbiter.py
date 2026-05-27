"""BAGEL Arbiter — decides belief status transitions based on evidence.

The arbiter consumes EvidenceScore results and produces lifecycle transitions
for beliefs. It also detects conflicts requiring tie-breaker probes.

Rules:
- Confirmed if strong support, no refutation.
- Suspect if any refutation present but not overwhelming.
- Falsified if core contradiction or overwhelming refutation.
- Conflict triggers probe request for tie-breaking.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from bagel.evidence_matrix import EvidenceMatrix, EvidenceScore
from bagel.fig_schema import (
    BeliefLifecycleState,
    BeliefNode,
    FalsifiableInterventionGraph,
    ProbeNode,
)

log = logging.getLogger(__name__)

# -- Arbitration result ---------------------------------------------------

@dataclass(frozen=True, slots=True)
class ArbitrationResult:
    belief_id: str
    old_lifecycle: BeliefLifecycleState
    new_lifecycle: BeliefLifecycleState
    score: float
    reason: str
    probe_requested: bool = False
    probe_description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


# -- Arbiter -------------------------------------------------------------

class BagelArbiter:
    """Evaluates evidence and recommends belief lifecycle transitions."""

    def __init__(
        self,
        confirm_threshold: float = 0.3,
        suspect_threshold: float = -0.1,
        falsify_threshold: float = -1.0,
    ) -> None:
        self._confirm_threshold = confirm_threshold
        self._suspect_threshold = suspect_threshold
        self._falsify_threshold = falsify_threshold

    def arbitrate(
        self,
        fig: FalsifiableInterventionGraph,
        matrix: EvidenceMatrix,
    ) -> list[ArbitrationResult]:
        """Run arbitration for all beliefs with evidence."""
        results: list[ArbitrationResult] = []
        scores = matrix.score_all()

        for belief_id, score in scores.items():
            belief = fig.beliefs.get(belief_id)
            if belief is None:
                continue
            if belief.lifecycle in ("retired", "stale", "posthoc_invalid"):
                continue

            result = self._evaluate(belief, score)
            if result is not None:
                results.append(result)

        return results

    def arbitrate_belief(
        self,
        belief: BeliefNode,
        matrix: EvidenceMatrix,
    ) -> ArbitrationResult | None:
        """Arbitrate a single belief."""
        score = matrix.score_belief(belief.belief_id)
        return self._evaluate(belief, score)

    def _evaluate(
        self, belief: BeliefNode, score: EvidenceScore,
    ) -> ArbitrationResult | None:
        old = belief.lifecycle

        # Determine new lifecycle
        if score.core_contradiction:
            new: BeliefLifecycleState = "falsified"
            reason = "core_contradiction"
        elif score.score <= self._falsify_threshold:
            new = "falsified"
            reason = f"score_below_threshold: {score.score:.3f}"
        elif score.score < self._suspect_threshold:
            new = "suspect"
            reason = f"refutation_detected: refute_sum={score.refute_sum:.3f}"
        elif score.conflict_detected:
            new = "suspect"
            reason = "auditor_conflict"
        elif score.score >= self._confirm_threshold and score.signal_count >= 2:
            new = "confirmed"
            reason = "sufficient_support"
        elif old == "provisional" and score.score >= 0:
            # No strong signal either way — leave provisional
            return None
        else:
            return None

        # Probe requested on conflict or suspect
        probe_requested = score.conflict_detected or (new == "suspect")
        probe_desc = ""
        if probe_requested:
            probe_desc = (
                f"Tie-breaker probe needed for belief {belief.belief_id}: "
                f"score={score.score:.3f}, support={score.support_max:.3f}, "
                f"refute={score.refute_sum:.3f}, signals={score.signal_count}"
            )

        return ArbitrationResult(
            belief_id=belief.belief_id,
            old_lifecycle=old,
            new_lifecycle=new,
            score=score.score,
            reason=reason,
            probe_requested=probe_requested,
            probe_description=probe_desc,
            metadata={
                "support_max": score.support_max,
                "refute_sum": score.refute_sum,
                "signal_count": score.signal_count,
                "core_contradiction": score.core_contradiction,
                "conflict_detected": score.conflict_detected,
            },
        )

    def apply_arbitration(
        self,
        fig: FalsifiableInterventionGraph,
        results: list[ArbitrationResult],
    ) -> list[str]:
        """Apply arbitration results to the FIG, returning updated belief IDs."""
        updated: list[str] = []
        for result in results:
            belief = fig.update_belief(
                result.belief_id,
                lifecycle=result.new_lifecycle,
            )
            if belief is not None:
                updated.append(result.belief_id)
                log.info(
                    "[BagelArbiter] %s -> %s for %s (score=%.3f, reason=%s)",
                    result.old_lifecycle, result.new_lifecycle,
                    result.belief_id, result.score, result.reason,
                )
        return updated

    def generate_probe_requests(
        self,
        results: list[ArbitrationResult],
    ) -> list[ProbeNode]:
        """Generate probe nodes for beliefs that need tie-breaking."""
        probes: list[ProbeNode] = []
        for result in results:
            if not result.probe_requested:
                continue
            probe = ProbeNode(
                probe_id=f"probe_{uuid.uuid4().hex[:12]}",
                belief_id=result.belief_id,
                description=result.probe_description,
                failure_criteria=f"Score for {result.belief_id} remains in conflict zone",
                status="generated",
                falsification_invariant=result.reason,
            )
            probes.append(probe)
        return probes
