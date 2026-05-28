"""Popper Probe Policy — generate falsification probes for candidate beliefs.

Probes are designed to *falsify* beliefs, not to confirm them.
Each probe must:
- Test a declared invariant.
- Have clear failure criteria.
- Not produce irreversible external actions.
- Be able to distinguish at least two candidate beliefs.
- Declare timeout and noise risks.
"""
from __future__ import annotations

import logging
import time
import uuid
import dataclasses
from dataclasses import dataclass, field
from typing import Any

from bagel.fig_schema import (
    BeliefNode,
    FalsifiableInterventionGraph,
    ProbeNode,
    ProbeClusterState,
)

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ProbeSanityCheck:
    probe_id: str
    passed: bool
    reason: str


@dataclass(frozen=True, slots=True)
class ProbeDegradationDecision:
    cluster_id: str
    state: ProbeClusterState
    taboo_probe_family: str
    recommended_action: str
    non_decidable_count: int


@dataclass(slots=True)
class ProbePolicy:
    """Generates and validates falsification probes."""

    non_decidable_limit: int = 2
    taboo_ttl_sec: float = 600.0
    _cluster_counts: dict[str, int] = field(default_factory=dict)
    _taboo_probe_families: dict[str, float] = field(default_factory=dict)

    def generate_probes(
        self,
        fig: FalsifiableInterventionGraph,
        belief_ids: list[str] | None = None,
    ) -> list[ProbeNode]:
        """Generate probes for suspect or conflicting beliefs.

        Skips beliefs that already have a pending probe (generated/sanity_checked/approved/executing).
        """
        targets = belief_ids or [
            b.belief_id for b in fig.suspect_beliefs()
        ]

        # Check for existing pending probes per belief
        snap = fig.snapshot()
        pending_beliefs: set[str] = set()
        for probe in snap["probes"].values():
            if probe.status in ("generated", "sanity_checked", "approved", "executing"):
                pending_beliefs.add(probe.belief_id)

        # Expire stale taboos
        self.expire_taboos()

        probes: list[ProbeNode] = []
        beliefs = snap["beliefs"]
        for bid in targets:
            if bid in pending_beliefs:
                continue
            belief = beliefs.get(bid)
            if belief is None:
                continue
            if not belief.falsification_condition:
                continue
            probe = self._create_probe(belief)
            if probe is not None:
                probes.append(probe)

        return probes

    def _create_probe(self, belief: BeliefNode) -> ProbeNode | None:
        """Create a single falsification probe for a belief."""
        probe = ProbeNode(
            probe_id=f"pprobe_{belief.belief_id[:12]}_{uuid.uuid4().hex[:6]}",
            belief_id=belief.belief_id,
            description=f"Falsify: {belief.hypothesis}",
            failure_criteria=belief.falsification_condition,
            status="generated",
            falsification_invariant=belief.falsification_condition,
            irreversible=False,
            can_distinguish=(belief.belief_id, f"not_{belief.belief_id}"),
            timeout_risk="medium",
            noise_risk="low",
            probe_cluster_id=f"cluster_{belief.belief_id}",
            sanity_status="valid",
        )

        # Run sanity check
        sanity = self.sanity_check(probe, belief)
        if not sanity.passed:
            return ProbeNode(
                probe_id=probe.probe_id,
                belief_id=probe.belief_id,
                description=probe.description,
                failure_criteria=probe.failure_criteria,
                status="rejected",
                falsification_invariant=probe.falsification_invariant,
                probe_cluster_id=probe.probe_cluster_id,
                sanity_status="rejected",
                result={"sanity_failure": sanity.reason},
            )

        return probe

    def sanity_check(self, probe: ProbeNode, belief: BeliefNode) -> ProbeSanityCheck:
        """Validate a probe before execution.

        Checks:
        1. Tests a declared invariant (has failure_criteria).
        2. Has clear failure criteria.
        3. Not irreversible.
        4. Can distinguish beliefs (has two candidates or at least belief_id).
        5. Has timeout/noise risk declared.
        """
        if not probe.failure_criteria:
            return ProbeSanityCheck(
                probe.probe_id, False, "no failure criteria defined",
            )
        if probe.irreversible:
            return ProbeSanityCheck(
                probe.probe_id, False, "probe is irreversible",
            )
        if not probe.belief_id:
            return ProbeSanityCheck(
                probe.probe_id, False, "probe has no target belief",
            )
        if not probe.falsification_invariant:
            return ProbeSanityCheck(
                probe.probe_id, False, "probe has no falsification invariant",
            )
        if not probe.timeout_risk and not probe.noise_risk:
            return ProbeSanityCheck(
                probe.probe_id, False, "probe has no timeout or noise risk declared",
            )
        # Check can_distinguish has two distinct belief IDs
        if (not probe.can_distinguish
                or len(probe.can_distinguish) < 2
                or not probe.can_distinguish[0]
                or not probe.can_distinguish[1]
                or probe.can_distinguish[0] == probe.can_distinguish[1]):
            return ProbeSanityCheck(
                probe.probe_id, False,
                "probe cannot distinguish beliefs (need two distinct candidates)",
            )
        return ProbeSanityCheck(probe.probe_id, True, "passed")

    def execute_probe(
        self,
        probe: ProbeNode,
        check_fn: Any,
    ) -> ProbeNode:
        """Execute a probe using the provided check function.

        The check_fn takes a ProbeNode and returns (passed: bool, result: dict).
        The caller supplies the concrete probe executor (OCR re-read, map
        check, replay perturbation, or synthetic state mutation).
        """
        try:
            passed, result = check_fn(probe)
            status = "passed" if passed else "failed"
            return dataclasses.replace(
                probe,
                status=status,
                result=result,
                executed_at=time.perf_counter(),
            )
        except Exception as exc:
            return dataclasses.replace(
                probe,
                status="timed_out",
                result={"error": str(exc)},
                executed_at=time.perf_counter(),
            )

    def degrade_non_decidable(
        self,
        probe: ProbeNode,
        signal: str,
    ) -> ProbeDegradationDecision:
        """Apply BAGEL v1.2 non-decidable probe degradation."""
        cluster_id = probe.probe_cluster_id or f"cluster_{probe.belief_id}"
        count = self._cluster_counts.get(cluster_id, 0) + 1
        self._cluster_counts[cluster_id] = count
        family = probe.falsification_invariant or probe.failure_criteria or "unknown_probe_family"
        if count == 1:
            state: ProbeClusterState = "non_decidable_once"
            action = "retry_with_controlled_probe"
        elif count < self.non_decidable_limit:
            state = "non_decidable_repeated"
            action = "retry_with_lower_noise_probe"
        else:
            state = "undecidable_cluster"
            self._taboo_probe_families[family] = time.perf_counter()
            action = "choose_lowest_impact_reversible_action_or_human_review"
        return ProbeDegradationDecision(cluster_id, state, family, action, count)

    def is_probe_family_taboo(self, family: str) -> bool:
        ts = self._taboo_probe_families.get(family)
        if ts is None:
            return False
        if self.taboo_ttl_sec > 0 and (time.perf_counter() - ts) > self.taboo_ttl_sec:
            del self._taboo_probe_families[family]
            return False
        return True

    def reset_taboo(self) -> None:
        """Clear all taboo families (e.g., on quest transition)."""
        self._taboo_probe_families.clear()
        self._cluster_counts.clear()

    def expire_taboos(self) -> None:
        """Remove expired taboo entries."""
        if self.taboo_ttl_sec <= 0:
            return
        now = time.perf_counter()
        expired = [f for f, ts in self._taboo_probe_families.items() if (now - ts) > self.taboo_ttl_sec]
        for f in expired:
            del self._taboo_probe_families[f]
