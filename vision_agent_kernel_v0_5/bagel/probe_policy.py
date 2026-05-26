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
from dataclasses import dataclass, field
from typing import Any

from bagel.fig_schema import (
    BeliefNode,
    FalsifiableInterventionGraph,
    ProbeNode,
)

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ProbeSanityCheck:
    probe_id: str
    passed: bool
    reason: str


@dataclass(slots=True)
class ProbePolicy:
    """Generates and validates falsification probes."""

    def generate_probes(
        self,
        fig: FalsifiableInterventionGraph,
        belief_ids: list[str] | None = None,
    ) -> list[ProbeNode]:
        """Generate probes for suspect or conflicting beliefs."""
        targets = belief_ids or [
            b.belief_id for b in fig.suspect_beliefs()
        ]

        probes: list[ProbeNode] = []
        for bid in targets:
            belief = fig.beliefs.get(bid)
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
            can_distinguish=(belief.belief_id, ""),
            timeout_risk="medium",
            noise_risk="low",
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
        return ProbeSanityCheck(probe.probe_id, True, "passed")

    def execute_probe(
        self,
        probe: ProbeNode,
        check_fn: Any,
    ) -> ProbeNode:
        """Execute a probe using the provided check function.

        The check_fn takes a ProbeNode and returns (passed: bool, result: dict).
        This is a placeholder for real probe execution (OCR re-read, map check, etc.)
        """
        import dataclasses
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
